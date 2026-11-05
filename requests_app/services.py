from django.utils import timezone
from django.db import transaction
from .models import RequestStatusHistory, Notification, AuditLog
from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth import get_user_model


def client_ip(request):
    return request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')


def notify(user, title, message, request_obj=None):
    if user:
        Notification.objects.create(user=user, title=title, message=message, request=request_obj)


def notify_admins(title, message, request_obj=None):
    """Create an in-system notification for every active administrator."""
    User = get_user_model()
    for admin in User.objects.filter(role='admin', is_active=True):
        notify(admin, title, message, request_obj)


def send_email_to_admins(subject, message, html_message=None):
    """Send an email to all active admin users. Silently returns if no admin emails or email backend not configured."""
    User = get_user_model()
    admin_emails = list(User.objects.filter(role='admin', is_active=True).exclude(email='').values_list('email', flat=True))
    if not admin_emails:
        return False
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'SERVER_EMAIL', None)
    if not from_email:
        # in development it's acceptable to skip if no from address configured
        try:
            send_mail(subject, message, None, admin_emails, html_message=html_message)
            return True
        except Exception:
            return False
    try:
        send_mail(subject, message, from_email, admin_emails, html_message=html_message)
        return True
    except Exception:
        return False


def email_user(user, subject, message):
    """Email one user. Never raises: a mail problem must not break the workflow. (Console backend prints it in the runserver window.)"""
    if not user or not getattr(user, 'email', ''):
        return False
    try:
        send_mail(subject, message, getattr(settings, 'DEFAULT_FROM_EMAIL', None), [user.email])
        return True
    except Exception:
        return False


def _when(starts_at, ends_at):
    s, e = timezone.localtime(starts_at), timezone.localtime(ends_at)
    return f'{s:%A %d %b %Y}, {s:%H:%M} to {e:%H:%M}'


def _tell_tenant_of_proposal(job, starts_at, ends_at):
    when = _when(starts_at, ends_at)
    msg = (f'A visit for "{job.title}" (request #{job.pk}) is proposed for {when}. '
           'Open your dashboard to confirm it, or ask for another time.')
    notify(job.tenant, 'Visit time proposed', msg, job)
    email_user(job.tenant, f'FixIt Pro: please confirm a visit time (request #{job.pk})',
               f'Hello {job.tenant.get_full_name() or job.tenant.username},\n\n{msg}\n\nWork cannot start until you answer.')
    return when


def audit(request, action, request_obj=None, details=''):
    AuditLog.objects.create(user=request.user if getattr(request, 'user', None) and request.user.is_authenticated else None,
                            action=action, request=request_obj, details=details, ip_address=client_ip(request))


def transition(request, obj, new_status, notes=''):
    old = obj.status
    if old == new_status:
        return True
    if not obj.is_transition_allowed(new_status):
        return False
    with transaction.atomic():
        now = timezone.now()
        obj.status = new_status
        if new_status in {'under_review', 'assigned'} and not obj.first_response_at:
            obj.first_response_at = now
        if new_status == 'accepted': obj.accepted_at = now
        if new_status == 'in_progress' and not obj.started_at: obj.started_at = now
        if new_status == 'completed': obj.completed_at = now
        if new_status == 'verified': obj.verified_at = now
        if new_status == 'closed': obj.closed_at = now
        obj.save()
        RequestStatusHistory.objects.create(request=obj, old_status=old, new_status=new_status, changed_by=request.user, notes=notes)
        audit(request, f'Status changed: {old} -> {new_status}', obj, notes)
        notify(obj.tenant, f'Request #{obj.id} updated', f'Your request is now {obj.get_status_display()}.', obj)
        # A reopened job is reported to the landlord first; the landlord alerts the contractor deliberately.
        if obj.assigned_staff and new_status != 'reopened':
            notify(obj.assigned_staff, f'Request #{obj.id} updated', f'Request status changed to {obj.get_status_display()}.', obj)
    return True


# A visit is arranged only AFTER the contractor has accepted the job (so the landlord knows he is on board).
ACTIVE_VISIT_STATUSES = {'accepted', 'in_progress', 'awaiting_parts'}


def start_tenant_wait(job):
    """A proposal is now waiting for the tenant: the SLA clock stops until they answer (the tenant's time is not the landlord's or contractor's)."""
    if not job.tenant_wait_started_at:
        job.tenant_wait_started_at = timezone.now()
        job.save(update_fields=['tenant_wait_started_at', 'updated_at'])


def end_tenant_wait(job):
    """The tenant answered (or the request ended): add the waiting time to the SLA deadline."""
    from datetime import timedelta
    if job.tenant_wait_started_at:
        seconds = max(0, int((timezone.now() - job.tenant_wait_started_at).total_seconds()))
        if job.sla_deadline:
            job.sla_deadline += timedelta(seconds=seconds)
        job.sla_paused_seconds += seconds
        job.tenant_wait_started_at = None
        job.save(update_fields=['sla_deadline', 'sla_paused_seconds', 'tenant_wait_started_at', 'updated_at'])


def chase_stalled_jobs():
    """Remind the landlord (at most once a day per job) about contractors who have not responded."""
    from datetime import timedelta
    from .models import MaintenanceRequest
    sent = 0
    for job in MaintenanceRequest.objects.filter(status__in=['assigned', 'accepted']):
        reason = job.stalled_reason
        if not reason:
            continue
        recent = Notification.objects.filter(request=job, title='Contractor not responding', created_at__gte=timezone.now() - timedelta(hours=24)).exists()
        if not recent:
            notify_admins('Contractor not responding', f'Request #{job.pk}: {reason} You can chase him or reassign the job.', job)
            sent += 1
    return sent


def _validate_window(job, starts_at, ends_at):
    if job.status not in ACTIVE_VISIT_STATUSES:
        if job.status == 'assigned':
            return 'The contractor has not accepted this job yet. A visit can be arranged once he has accepted it.'
        return 'A visit can only be arranged while the job is accepted or in progress.'
    if job.appointments.filter(status='confirmed').exists():
        return 'The tenant has already confirmed a visit. No other time can be arranged until it has taken place.'
    if starts_at <= timezone.now() or ends_at <= starts_at:
        return 'The visit must be in the future, and it must end after it starts.'
    return None


def propose_visit(user, job, starts_at, ends_at, note=''):
    """LANDLORD proposes a visit time to the TENANT. The tenant is the only one who can confirm it.

    Returns (ok, message). Contractors never propose to the tenant: they offer availability to the landlord.
    """
    from .models import MaintenanceAppointment
    if not user.is_admin_user():
        return False, 'Only the landlord proposes visit times to the tenant.'
    problem = _validate_window(job, starts_at, ends_at)
    if problem:
        return False, problem
    if job.appointments.filter(status='availability').exists():
        notify(job.assigned_staff, 'Landlord chose a different time', f'Request #{job.pk}: the landlord proposed another time to the tenant instead of the one you offered.', job)
    job.appointments.filter(status__in=['proposed', 'reschedule', 'availability']).update(status='cancelled')
    MaintenanceAppointment.objects.create(request=job, proposed_by=user, starts_at=starts_at, ends_at=ends_at, note=(note or '')[:1000])
    start_tenant_wait(job)
    notify(job.assigned_staff, 'Visit proposed to the tenant', f'Request #{job.pk}: the landlord proposed {timezone.localtime(starts_at):%d %b %H:%M} to the tenant. You can start once the tenant confirms.', job)
    when = _tell_tenant_of_proposal(job, starts_at, ends_at)
    return True, f'Sent to {job.tenant.get_full_name() or job.tenant.username} for {when}. They see it on their dashboard and by email. Work cannot start until they confirm.'


def offer_availability(user, job, starts_at, ends_at, note=''):
    """CONTRACTOR tells the LANDLORD when he is available (first visit or a return visit). Never goes straight to the tenant."""
    from .models import MaintenanceAppointment
    if not user.is_staff_user() or job.assigned_staff_id != user.id:
        return False, 'Only the assigned contractor can offer availability.'
    problem = _validate_window(job, starts_at, ends_at)
    if problem:
        return False, problem
    job.appointments.filter(status='availability').update(status='cancelled')
    MaintenanceAppointment.objects.create(request=job, proposed_by=user, starts_at=starts_at, ends_at=ends_at,
                                          status='availability', note=(note or '')[:1000])
    notify_admins('Contractor availability offered', f'Request #{job.pk}: the contractor can return {timezone.localtime(starts_at):%d %b %H:%M}. Send it to the tenant to confirm.', job)
    return True, 'Availability sent to the landlord, who will ask the tenant to confirm.'


def relay_availability(user, appointment):
    """LANDLORD turns a contractor's availability offer into a proposal the TENANT must confirm."""
    job = appointment.request
    if not user.is_admin_user():
        return False, 'Only the landlord can send a visit time to the tenant.'
    if appointment.status != 'availability':
        return False, 'This offer is no longer open.'
    if appointment.starts_at <= timezone.now():
        appointment.status = 'cancelled'
        appointment.save(update_fields=['status', 'updated_at'])
        notify(job.assigned_staff, 'Your offered time has passed', f'Request #{job.pk}: the time you offered has already gone. Please offer a new time.', job)
        return False, 'That time has already passed, so it was not sent. The contractor has been asked for a new time.'
    problem = _validate_window(job, appointment.starts_at, appointment.ends_at)
    if problem:
        return False, problem
    job.appointments.filter(status__in=['proposed', 'reschedule']).update(status='cancelled')
    appointment.status = 'proposed'
    appointment.proposed_by = user
    appointment.note = ('The contractor is available at this time. ' + (appointment.note or '')).strip()[:1000]
    appointment.save(update_fields=['status', 'proposed_by', 'note', 'updated_at'])
    start_tenant_wait(job)
    when = _tell_tenant_of_proposal(job, appointment.starts_at, appointment.ends_at)
    notify(job.assigned_staff, 'Time sent to the tenant', f'Request #{job.pk}: your time ({when}) was sent to the tenant to confirm.', job)
    return True, f'Sent to {job.tenant.get_full_name() or job.tenant.username} for {when}. They see it on their dashboard and by email. Work cannot resume until they confirm.'

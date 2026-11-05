from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.core.paginator import Paginator
from requests_app.models import MaintenanceRequest, ContractorPayment, RequestStatusHistory
from requests_app.forms import StaffNoteForm, AttachmentForm, WorkLogForm, MaterialForm, ContractorQuotationForm
from requests_app.services import transition, audit, notify_admins, notify

@login_required
def staff_dashboard(request):
    if not request.user.is_staff_user(): return redirect('dashboard')
    qs = MaintenanceRequest.objects.filter(assigned_staff=request.user)
    for obj in qs.filter(status__in=['assigned','accepted','in_progress','awaiting_parts']): obj.mark_sla_if_breached()
    return render(request, 'staff/staff_dashboard.html', {
        'total_assigned': qs.count(), 'pending_tasks': qs.filter(status='assigned').count(),
        'accepted_tasks': qs.filter(status='accepted').count(), 'in_progress_tasks': qs.filter(status__in=['in_progress','awaiting_parts']).count(),
        'completed_tasks': qs.filter(status__in=['completed','verified','closed']).count(),
        'overdue_tasks': qs.filter(sla_breached=True).exclude(status__in=['closed','cancelled']).count(),
        'recent_tasks': qs[:8],
        'urgent_tasks': qs.filter(priority='urgent', status__in=['assigned', 'accepted', 'in_progress', 'awaiting_parts']).order_by('-updated_at')[:8]})

@login_required
def my_tasks(request):
    if not request.user.is_staff_user(): return redirect('dashboard')
    tasks = MaintenanceRequest.objects.filter(assigned_staff=request.user)
    status_filter = request.GET.get('status')
    if status_filter: tasks = tasks.filter(status=status_filter)
    page_obj = Paginator(tasks, 12).get_page(request.GET.get('page'))
    return render(request, 'staff/my_tasks.html', {'page_obj': page_obj, 'status_filter': status_filter})

@login_required
def staff_request_detail(request, request_id):
    if not request.user.is_staff_user(): return redirect('dashboard')
    obj = get_object_or_404(MaintenanceRequest, id=request_id, assigned_staff=request.user)
    obj.mark_sla_if_breached()
    quotations = obj.quotations.filter(contractor=request.user).order_by('-created_at')
    last_rejected = quotations.filter(status='rejected').first() if not quotations.filter(status__in=['submitted', 'approved']).exists() else None
    quote_initial = {}
    if last_rejected:
        quote_initial = {'scope': last_rejected.scope, 'labour_amount': last_rejected.labour_amount,
                         'estimated_materials': last_rejected.estimated_materials, 'estimated_hours': last_rejected.estimated_hours}
    visit_record = obj.work_logs.filter(technician=request.user, visit_round=obj.rework_count).first()
    confirmed = obj.confirmed_appointment
    can_start_work = obj.status == 'accepted'
    start_blocker = None
    if can_start_work:
        if obj.quote_blocks_start(request.user):
            start_blocker = 'Waiting for the landlord to approve your quotation.'
        elif obj.visit_blocks_start():
            start_blocker = 'Waiting for the tenant to confirm a visit time (the landlord arranges it).'
        elif obj.visit_too_early():
            start_blocker = f'Visit confirmed for {timezone.localtime(obj.next_visit_start()):%d %b %Y at %H:%M}. You can start from {obj.VISIT_EARLY_MINUTES} minutes before.'
    access_failed = obj.access_failed
    checks = None
    if obj.status in {'in_progress', 'awaiting_parts'}:
        checks = [
            {'label': 'Visit / access record saved', 'ok': bool(visit_record)},
            {'label': 'Access gained at the visit', 'ok': bool(visit_record and visit_record.access_outcome == 'access_granted'),
             'hint': 'Update the record to "Access gained" once the tenant has confirmed a return visit and you have been in.' if access_failed else ''},
            {'label': 'Work photo uploaded (JPG or PNG)', 'ok': obj.has_completion_evidence(request.user), 'hint': 'Upload a photo of the finished work.'},
        ]
        if obj.quotation_required:
            checks.append({'label': 'Quotation approved' if not obj.emergency_callout else 'Quotation submitted (emergency call-out)', 'ok': not obj.quote_blocks_completion(request.user)})
    can_offer_availability = obj.status in {'accepted', 'in_progress', 'awaiting_parts'} and not confirmed
    return render(request, 'staff/staff_request_detail.html', {
        'request_obj': obj,
        'status_history': obj.status_history.all(),
        'notes': obj.notes.all(),
        'work_logs': obj.work_logs.filter(technician=request.user),
        'visit_record': visit_record,
        'appointments': obj.appointments.all(),
        'can_submit_quote': (obj.status in ({'accepted', 'in_progress', 'awaiting_parts'} if obj.emergency_callout else {'accepted'}))
                            and obj.quotation_required and not obj.quotations.filter(contractor=request.user, status__in=['submitted', 'approved']).exists(),
        'confirmed_appointment': confirmed,
        'awaiting_tenant': obj.appointments.filter(status='proposed').first(),
        'availability_offer': obj.appointments.filter(status='availability', proposed_by=request.user).first(),
        'can_offer_availability': can_offer_availability,
        'start_blocker': start_blocker,
        'completion_checks': checks,
        'access_failed': access_failed,
        'last_rejected': last_rejected,
        'materials': obj.materials.filter(recorded_by=request.user),
        'work_log_form': WorkLogForm(),
        'material_form': MaterialForm(),
        'attachment_form': AttachmentForm(),
        'quotation_form': ContractorQuotationForm(initial=quote_initial),
        'quotations': quotations,
        'payments': obj.payments.filter(contractor=request.user),
    })

def _sync_appointment(obj, log):
    """Mark the visit this record belongs to as attended / no-access so the history shows what really happened."""
    appt = obj.appointments.filter(status='confirmed').order_by('-starts_at').first() \
        or log.appointment \
        or obj.appointments.filter(status__in=['attended', 'no_access']).order_by('-starts_at').first()
    if appt:
        appt.status = 'attended' if log.access_outcome == 'access_granted' else 'no_access'
        appt.save(update_fields=['status', 'updated_at'])
        if log.appointment_id != appt.id:
            log.appointment = appt
            log.save(update_fields=['appointment'])


def _report_failed_access(request, obj, log):
    """No access: the landlord and the tenant must be told, and a new tenant-confirmed visit is needed."""
    RequestStatusHistory.objects.create(request=obj, old_status=obj.status, new_status=obj.status, changed_by=request.user,
                                        notes=f'No access at the visit: {log.notes[:200]}')
    notify_admins('No access: new visit needed', f'Request #{obj.pk}: the contractor could not get in ("{log.notes[:120]}"). Please propose a new visit time to the tenant.', obj)
    notify(obj.tenant, 'We could not get access', f'Request #{obj.pk}: the contractor could not get in. The landlord will propose a new visit time for you to confirm.', obj)


@login_required
def add_work_log(request, request_id):
    """Create the contractor visit / access record. Only after Start Work, and only ONE per visit round."""
    if not request.user.is_staff_user():
        return redirect('dashboard')
    obj = get_object_or_404(MaintenanceRequest, id=request_id, assigned_staff=request.user)
    if obj.status not in {'in_progress', 'awaiting_parts'} or not obj.started_at:
        messages.error(request, 'Click Start Work before recording the visit.')
        return redirect('staff_request_detail', request_id=request_id)
    if obj.work_logs.filter(visit_round=obj.rework_count).exists():
        messages.info(request, 'The visit record already exists. You can edit it, but not add another.')
        return redirect('staff_request_detail', request_id=request_id)
    if request.method == 'POST':
        form = WorkLogForm(request.POST)
        if form.is_valid():
            started = obj.started_at or timezone.now()
            local_started = timezone.localtime(started)
            log = form.save(commit=False)
            log.request = obj
            log.technician = request.user
            log.visit_round = obj.rework_count
            log.work_date = local_started.date()
            log.start_time = local_started.time().replace(tzinfo=None)
            log.end_time = None
            log.hourly_rate = obj.approved_hourly_rate
            log.save()
            _sync_appointment(obj, log)
            audit(request, 'Visit record submitted', obj, f'Outcome: {log.get_access_outcome_display()}')
            if log.access_outcome == 'no_access':
                _report_failed_access(request, obj, log)
                messages.warning(request, 'No access recorded. The landlord and tenant have been told; wait for a new visit time to be confirmed by the tenant.')
            else:
                messages.success(request, 'Visit record saved.')
        else:
            messages.error(request, 'Describe the visit (at least 10 characters) and choose the access outcome.')
    return redirect('staff_request_detail', request_id=request_id)


@login_required
def edit_work_log(request, request_id):
    """Re-edit the existing visit record (the only change allowed once it is recorded)."""
    if not request.user.is_staff_user():
        return redirect('dashboard')
    obj = get_object_or_404(MaintenanceRequest, id=request_id, assigned_staff=request.user)
    log = obj.work_logs.filter(technician=request.user, visit_round=obj.rework_count).first()
    if not log or obj.status not in {'in_progress', 'awaiting_parts'}:
        messages.error(request, 'The visit record can only be edited while the job is in progress.')
        return redirect('staff_request_detail', request_id=request_id)
    if request.method == 'POST':
        was_no_access = log.access_outcome == 'no_access'
        form = WorkLogForm(request.POST, instance=log)
        if form.is_valid():
            if form.cleaned_data['access_outcome'] == 'access_granted' and was_no_access and (obj.visit_blocks_start() or obj.visit_too_early()):
                messages.error(request, 'Access failed at the last visit. The tenant must confirm a return visit, and it must have taken place, before you can record that you gained access.')
                return redirect('staff_request_detail', request_id=request_id)
            log = form.save()
            _sync_appointment(obj, log)
            audit(request, 'Visit record edited', obj, f'Outcome: {log.get_access_outcome_display()}')
            if log.access_outcome == 'no_access' and not was_no_access:
                _report_failed_access(request, obj, log)
            messages.success(request, 'Visit record updated.')
        else:
            messages.error(request, 'Describe the visit (at least 10 characters).')
    return redirect('staff_request_detail', request_id=request_id)


@login_required
def offer_availability_view(request, request_id):
    """Contractor tells the LANDLORD when he can come back. The landlord relays it; the tenant confirms."""
    from django.utils.dateparse import parse_datetime
    from requests_app.services import offer_availability
    if not request.user.is_staff_user():
        return redirect('dashboard')
    obj = get_object_or_404(MaintenanceRequest, id=request_id, assigned_staff=request.user)
    if request.method == 'POST':
        start = parse_datetime(request.POST.get('starts_at', '')); end = parse_datetime(request.POST.get('ends_at', ''))
        note = (request.POST.get('note') or '').strip()
        if not start or not end:
            messages.error(request, 'Enter a valid start and end date/time.')
        else:
            if timezone.is_naive(start): start = timezone.make_aware(start)
            if timezone.is_naive(end): end = timezone.make_aware(end)
            ok, msg = offer_availability(request.user, obj, start, end, note)
            (messages.success if ok else messages.error)(request, msg)
            if ok:
                audit(request, 'Contractor offered return availability', obj, note[:200])
    return redirect('staff_request_detail', request_id=request_id)


@login_required
def add_material(request, request_id):
    if not request.user.is_staff_user():
        return redirect('dashboard')
    obj = get_object_or_404(MaintenanceRequest, id=request_id, assigned_staff=request.user)
    if obj.quotation_required:
        messages.info(request, 'Materials are already covered by your approved quotation; there is nothing to enter.')
        return redirect('staff_request_detail', request_id=request_id)
    if obj.status not in {'accepted', 'in_progress', 'awaiting_parts'} or obj.quote_blocks_start(request.user):
        messages.error(request, 'Materials can only be recorded after quotation approval and job acceptance.')
        return redirect('staff_request_detail', request_id=request_id)
    if request.method == 'POST':
        form = MaterialForm(request.POST)
        if form.is_valid():
            material = form.save(commit=False)
            material.request = obj
            material.recorded_by = request.user
            material.save()
            audit(request, 'Material recorded', obj, material.description)
            messages.success(request, 'Material successfully recorded.')
        else:
            messages.error(request, 'Please correct the material entry and try again.')
    return redirect('staff_request_detail', request_id=request_id)


@login_required
def accept_job(request, request_id):
    if not request.user.is_staff_user(): return redirect('dashboard')
    obj = get_object_or_404(MaintenanceRequest, id=request_id, assigned_staff=request.user)
    if request.method == 'POST':
        if transition(request, obj, 'accepted', 'Contractor accepted the job'):
            notify_admins('Contractor accepted the job', f'Request #{obj.pk}: {obj.assigned_staff.get_full_name() or obj.assigned_staff.username} accepted it. Check his availability and propose a visit time to the tenant.', obj)
            messages.success(request, 'Job accepted. Offer the landlord your availability, and submit your quotation.')
        else: messages.error(request, 'Job cannot be accepted in its current state.')
    return redirect('staff_request_detail', request_id=request_id)


@login_required
def start_job(request, request_id):
    if not request.user.is_staff_user():
        return redirect('dashboard')
    obj = get_object_or_404(MaintenanceRequest, id=request_id, assigned_staff=request.user)
    if request.method == 'POST':
        if obj.quote_blocks_start(request.user):
            messages.error(request, 'The landlord must approve your quotation before work can start.')
            return redirect('staff_request_detail', request_id=request_id)
        if obj.visit_blocks_start():
            messages.error(request, 'The tenant must confirm a visit time before work can start. The landlord arranges the visit with the tenant.')
            return redirect('staff_request_detail', request_id=request_id)
        if obj.visit_too_early():
            messages.error(request, f'The confirmed visit is on {timezone.localtime(obj.next_visit_start()):%d %b %Y at %H:%M}. You can start work from {obj.VISIT_EARLY_MINUTES} minutes before then.')
            return redirect('staff_request_detail', request_id=request_id)
        if transition(request, obj, 'in_progress', 'Contractor started work'):
            messages.success(request, 'Work started. The start date and time have been recorded automatically.')
        else:
            messages.error(request, 'This job cannot be started in its current state.')
    return redirect('staff_request_detail', request_id=request_id)


@login_required
def awaiting_parts(request, request_id):
    if not request.user.is_staff_user():
        return redirect('dashboard')
    obj = get_object_or_404(MaintenanceRequest, id=request_id, assigned_staff=request.user)
    if request.method == 'POST':
        reason = (request.POST.get('reason') or '').strip()
        if len(reason) < 8:
            messages.error(request, 'Explain why parts are required (at least 8 characters).')
            return redirect('staff_request_detail', request_id=request_id)
        if transition(request, obj, 'awaiting_parts', f'Awaiting parts: {reason}'):
            obj.sla_pause_reason = reason
            obj.sla_pause_approved = False
            obj.sla_pause_started_at = timezone.now()
            obj.save(update_fields=['sla_pause_reason', 'sla_pause_approved', 'sla_pause_started_at', 'updated_at'])
            notify_admins('Parts delay awaiting review', f'Request #{obj.pk}: {reason}', obj)
            messages.success(request, 'Job marked as awaiting parts.')
        else:
            messages.error(request, 'This job cannot be moved to Awaiting Parts in its current state.')
    return redirect('staff_request_detail', request_id=request_id)


@login_required
def resume_job(request, request_id):
    if not request.user.is_staff_user():
        return redirect('dashboard')
    obj = get_object_or_404(MaintenanceRequest, id=request_id, assigned_staff=request.user)
    if request.method == 'POST':
        if transition(request, obj, 'in_progress', 'Contractor resumed work after receiving parts/materials'):
            if obj.sla_pause_started_at:
                seconds = max(0, int((timezone.now() - obj.sla_pause_started_at).total_seconds()))
                if obj.sla_pause_approved and obj.sla_deadline:
                    from datetime import timedelta
                    obj.sla_deadline += timedelta(seconds=seconds)
                    obj.sla_paused_seconds += seconds
                obj.sla_pause_started_at = None
                obj.sla_pause_approved = False
                obj.save(update_fields=['sla_deadline','sla_paused_seconds','sla_pause_started_at','sla_pause_approved','updated_at'])
            messages.success(request, 'Work resumed; any approved waiting period was added to the SLA.')
        else:
            messages.error(request, 'This job cannot be resumed in its current state.')
    return redirect('staff_request_detail', request_id=request_id)


@login_required
def mark_complete(request, request_id):
    if not request.user.is_staff_user():
        return redirect('dashboard')
    obj = get_object_or_404(MaintenanceRequest, id=request_id, assigned_staff=request.user)
    if request.method == 'POST':
        if obj.quote_blocks_completion(request.user):
            messages.error(request,'Quotation approval is required before completing work.' if not obj.emergency_callout else 'Submit your quotation for this emergency call-out before completing the job.')
            return redirect('staff_request_detail',request_id=request_id)
        if obj.status not in {'in_progress', 'awaiting_parts'}:
            messages.error(request, 'Job cannot be marked complete in its current state.')
            return redirect('staff_request_detail', request_id=request_id)
        record = obj.work_logs.filter(technician=request.user, visit_round=obj.rework_count).first()
        if not record:
            messages.error(request, 'Record the contractor visit / access record before marking the job completed.')
            return redirect('staff_request_detail', request_id=request_id)
        if record.access_outcome != 'access_granted':
            if obj.visit_blocks_start() or obj.visit_too_early():
                messages.error(request, 'Access failed at the last visit. Wait for the tenant to confirm a return visit (the landlord arranges it), then update your record.')
            else:
                messages.error(request, 'The tenant has confirmed the return visit. Once you have done the work, edit your visit record and choose "Access gained", then upload a photo and mark the job complete.')
            return redirect('staff_request_detail', request_id=request_id)
        if not obj.has_completion_evidence(request.user):
            messages.error(request, 'Upload a photo (JPG or PNG) of the finished work before marking the job complete.')
            return redirect('staff_request_detail', request_id=request_id)
        # The visit record already says what was done; keep one copy of it for the tenant and landlord.
        obj.resolution_notes = record.notes
        obj.save(update_fields=['resolution_notes', 'updated_at'])
        if transition(request, obj, 'completed', f'Completed by contractor {request.user.get_full_name() or request.user.username}'):
            # Stop the automatic work timer and calculate labour server-side for Admin only.
            log = record
            if log and obj.completed_at:
                local_completed = timezone.localtime(obj.completed_at)
                log.end_time = local_completed.time().replace(tzinfo=None)
                log.save(update_fields=['end_time'])
                obj.recalculate_costs()
            messages.success(request, 'Job marked completed. The administrator and tenant can now review the completed work.')
        else:
            messages.error(request, 'Unable to mark job completed.')
    return redirect('staff_request_detail', request_id=request_id)

@login_required
def add_note(request, request_id):
    if not request.user.is_staff_user(): return redirect('dashboard')
    obj = get_object_or_404(MaintenanceRequest, id=request_id, assigned_staff=request.user)
    if obj.status not in {'accepted', 'in_progress', 'awaiting_parts'}:
        messages.error(request, 'Notes cannot be added after completion, closure or cancellation.')
        return redirect('staff_request_detail', request_id=request_id)
    if request.method == 'POST':
        form = StaffNoteForm(request.POST, request_obj=obj, staff=request.user)
        if form.is_valid(): form.save(); audit(request, 'Staff note added', obj); messages.success(request, 'Note added.'); return redirect('staff_request_detail', request_id=request_id)
    else: form = StaffNoteForm(request_obj=obj, staff=request.user)
    return render(request, 'staff/add_note.html', {'form': form, 'request_obj': obj})


@login_required
def submit_quotation(request, request_id):
    if not request.user.is_staff_user(): return redirect('dashboard')
    obj = get_object_or_404(MaintenanceRequest, pk=request_id, assigned_staff=request.user)
    if request.method != 'POST': return redirect('staff_request_detail', request_id=request_id)
    allowed_states = {'accepted', 'in_progress', 'awaiting_parts'} if obj.emergency_callout else {'accepted'}
    if obj.status not in allowed_states or obj.quotations.filter(contractor=request.user, status__in=['submitted','approved']).exists():
        messages.error(request, 'A quotation may be submitted only for an accepted job without an outstanding quotation.')
    else:
        form = ContractorQuotationForm(request.POST)
        if form.is_valid():
            quote = form.save(commit=False); quote.request=obj; quote.contractor=request.user
            quote.revision_number = obj.quotations.filter(contractor=request.user).count() + 1
            quote.save()
            notify_admins('Quotation awaiting approval', f'Request #{obj.pk}: quotation (revision {quote.revision_number}) of R{quote.quoted_total} needs review.', obj)
            audit(request,'Contractor quotation submitted',obj, f'Quotation #{quote.pk} revision {quote.revision_number}')
            messages.success(request, 'Quotation sent to the landlord for approval.' if quote.revision_number == 1 else f'Revised quotation (revision {quote.revision_number}) sent to the landlord.')
        else:
            for errs in form.errors.values():
                messages.error(request, errs[0]); break
    return redirect('staff_request_detail', request_id=request_id)


@login_required
def reject_job(request, request_id):
    if not request.user.is_staff_user(): return redirect('dashboard')
    obj = get_object_or_404(MaintenanceRequest, pk=request_id, assigned_staff=request.user)
    if request.method == 'POST' and obj.status == 'assigned':
        reason = (request.POST.get('reason') or '').strip()
        if len(reason) < 5: messages.error(request, 'Give a reason for declining the job.')
        else:
            if transition(request,obj,'reopened',f'Contractor declined assignment: {reason}'):
                obj.assigned_staff = None; obj.save(update_fields=['assigned_staff','updated_at'])
                from requests_app.services import notify_admins
                notify_admins('Assignment declined',f'Request #{obj.pk}: {reason}',obj)
                messages.success(request,'Assignment declined; landlord notified.')
    return redirect('staff_dashboard')


@login_required
def acknowledge_payment(request, payment_id):
    if not request.user.is_staff_user(): return redirect('dashboard')
    payment = get_object_or_404(ContractorPayment, pk=payment_id, contractor=request.user)
    if request.method == 'POST' and payment.status == 'recorded':
        decision = request.POST.get('decision')
        if decision in {'confirmed','disputed'}:
            payment.status=decision
            payment.contractor_comment=(request.POST.get('comment') or '').strip()[:2000]
            if decision == 'disputed' and not payment.contractor_comment:
                messages.error(request,'Please explain the payment discrepancy.')
                return redirect('staff_request_detail',request_id=payment.request_id)
            payment.acknowledged_at=timezone.now(); payment.save()
            from requests_app.services import notify_admins
            notify_admins('Payment acknowledgement', f'Payment #{payment.pk}: {payment.get_status_display()}', payment.request)
            audit(request,'Contractor payment acknowledgement',payment.request, f'Payment #{payment.pk}: {decision}')
            messages.success(request,'Your payment response has been recorded.')
    return redirect('staff_request_detail',request_id=payment.request_id)

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings
from django.utils import timezone
from django.urls import reverse
from accounts.models import Lease
from .models import MaintenanceAppointment, MaintenanceRequest, RequestStatusHistory, Feedback, Notification, IoTDevice, SensorReading
from .forms import MaintenanceRequestForm, FeedbackForm, AttachmentForm
from .services import transition, notify, audit, end_tenant_wait
from .services import send_email_to_admins, notify_admins


@login_required
def tenant_dashboard(request):
    if not request.user.is_tenant():
        return redirect('dashboard')
    qs = MaintenanceRequest.objects.filter(tenant=request.user)
    context = {
        'total_requests': qs.count(),
        'pending_requests': qs.filter(status__in=['pending', 'under_review']).count(),
        'in_progress_requests': qs.filter(status__in=['assigned', 'accepted', 'in_progress', 'awaiting_parts', 'reopened']).count(),
        'completed_requests': qs.filter(status__in=['completed', 'verified', 'closed']).count(),
        'overdue_requests': qs.filter(sla_breached=True).exclude(status__in=['closed', 'cancelled']).count(),
        'recent_requests': qs[:6],
        'awaiting_visit_proposals': MaintenanceAppointment.objects.filter(
            request__tenant=request.user,
            request__status__in=['assigned', 'accepted', 'in_progress', 'awaiting_parts', 'reopened'],
            status='proposed',
        ).select_related('request', 'request__assigned_staff'),
    }
    return render(request, 'requests_app/tenant_dashboard.html', context)


@login_required
def submit_request(request):
    if not request.user.is_tenant():
        return redirect('dashboard')
    from accounts.models import Lease
    lease = Lease.objects.filter(tenant=request.user, verified=True).first()
    if not lease or not lease.is_current():
        messages.error(request, 'A current, verified lease is required. Please contact your landlord.')
        return redirect('tenant_dashboard')
    if request.method == 'POST':
        form = MaintenanceRequestForm(request.POST, request.FILES, tenant=request.user)
        form.verified_lease = lease
        if form.is_valid():
            obj = form.save(commit=False)
            obj.quotation_required = True
            escalated = False
            if obj.safety_risk and obj.priority in {'low', 'medium'}:
                obj.priority = 'high'            # a reported safety risk is never handled slower than High
                escalated = True
            obj.sla_hours = MaintenanceRequest.sla_for_priority(obj.priority)
            obj.save()
            RequestStatusHistory.objects.create(request=obj, old_status='pending', new_status='pending', changed_by=request.user, notes='Request submitted')
            if obj.safety_risk:
                RequestStatusHistory.objects.create(request=obj, old_status='pending', new_status='pending', changed_by=request.user,
                                                    notes='SAFETY RISK reported by tenant' + ('; priority raised to High automatically' if escalated else ''))
            audit(request, 'Maintenance request created', obj, obj.title)
            notify(request.user, f'Request #{obj.id} submitted', f'Your request was submitted with a {obj.get_priority_display()} priority.', obj)
            # Send email to administrators so they see new requests even if not logged in.
            subject = f'{"SAFETY RISK - " if obj.safety_risk else ""}New maintenance request #{obj.id}: {obj.title}'
            message = f"A new maintenance request has been submitted by {request.user.get_full_name() or request.user.username}.\n\nTitle: {obj.title}\nPriority: {obj.get_priority_display()}\nApartment: {obj.apartment_number}\n\nVisit the admin dashboard to review: {request.build_absolute_uri(reverse('admin_request_detail', args=[obj.id]))}"
            # html_message omitted for now; helper is resilient if email backend/settings are not configured.
            send_email_to_admins(subject, message)
            if obj.safety_risk:
                notify_admins(f'SAFETY RISK: request #{obj.id}', f'{obj.title}: the tenant reports a safety risk. Review and assign a contractor straight away (priority {obj.get_priority_display()}).', obj)
            else:
                notify_admins(f'New request #{obj.id}', f'{obj.title} requires administrator review.', obj)
            messages.success(request, f'Request #{obj.id} submitted successfully.' + (' Because you reported a safety risk it has been flagged to the landlord as high priority.' if obj.safety_risk else ''))
            return redirect('tenant_dashboard')
        # Keep the tenant on the form only when validation failed, and explain why.
        messages.error(request, 'Please correct the highlighted fields and submit the request again.')
    else:
        form = MaintenanceRequestForm(tenant=request.user)
        form.verified_lease = lease
    return render(request, 'requests_app/submit_request.html', {'form': form, 'lease':lease})


@login_required
def tenant_request_detail(request, request_id):
    if not request.user.is_tenant():
        return redirect('dashboard')
    obj = get_object_or_404(MaintenanceRequest, id=request_id, tenant=request.user)
    obj.mark_sla_if_breached()
    existing_feedback = Feedback.objects.filter(request=obj).first()
    feedback_form = None if existing_feedback else FeedbackForm()
    steps = ['Submitted', 'Assigned', 'Accepted', 'In progress', 'Completed', 'Verified', 'Closed']
    position = {'pending': 0, 'under_review': 0, 'reopened': 0, 'assigned': 1, 'accepted': 2, 'in_progress': 3,
                'awaiting_parts': 3, 'completed': 4, 'verified': 5, 'closed': 6}.get(obj.status)
    progress = None
    if position is not None:
        progress = [{'label': label, 'state': ('done' if (i < position or obj.status == 'closed') else 'current' if i == position else 'todo')}
                    for i, label in enumerate(steps)]
    return render(request, 'requests_app/tenant_request_detail.html', {
        'request_obj': obj,
        'progress': progress,
        'status_history': obj.status_history.all(),
        'feedback_form': feedback_form,
        'visits': obj.appointments.exclude(status='availability'),
        'awaiting_visit_response': obj.appointments.filter(status='proposed').exists(),
        'confirmed_visit': obj.confirmed_appointment,
        'contractor_offered': obj.appointments.filter(status='availability').exists(),
        'needs_new_time': obj.status in {'assigned', 'accepted', 'in_progress', 'awaiting_parts', 'reopened'}
                          and not obj.appointments.filter(status__in=['proposed', 'confirmed']).exists()
                          and (obj.appointments.exclude(status='availability').exists() or obj.status == 'reopened'),
        'access_failed_banner': obj.access_failed,
        'existing_feedback': existing_feedback,
        'notifications': request.user.notifications.filter(is_read=False)[:5],
    })


@login_required
@require_POST
def cancel_request(request, request_id):
    obj = get_object_or_404(MaintenanceRequest, id=request_id, tenant=request.user)
    if not obj.can_be_cancelled_by_tenant:
        messages.error(request, 'A request can only be cancelled before work has started.')
        return redirect('tenant_request_detail', request_id=request_id)
    if request.method == 'POST':
        if transition(request, obj, 'cancelled', 'Cancelled by requester'):
            obj.appointments.filter(status__in=['proposed', 'availability', 'reschedule', 'confirmed']).update(status='cancelled')
            end_tenant_wait(obj)
            messages.success(request, 'Request cancelled.')
    return redirect('tenant_dashboard')


@login_required
@require_POST
def verify_request(request, request_id):
    obj = get_object_or_404(MaintenanceRequest, id=request_id, tenant=request.user)
    if request.method == 'POST':
        if transition(request, obj, 'verified', 'Repair verified by requester'):
            messages.success(request, 'Repair verified successfully.')
        else:
            messages.error(request, 'This request is not ready for verification.')
    return redirect('tenant_request_detail', request_id=request_id)


@login_required
@require_POST
def reopen_request(request, request_id):
    obj = get_object_or_404(MaintenanceRequest, id=request_id, tenant=request.user)
    if request.method == 'POST':
        if not obj.can_be_reopened_by_tenant:
            messages.error(request, f'A request can only be reopened once the contractor has finished, or within {obj.REOPEN_WINDOW_DAYS} days of it being closed.')
            return redirect('tenant_request_detail', request_id=request_id)
        was_closed = obj.status == 'closed'
        if transition(request, obj, 'reopened', 'Requester reported that the problem came back after closure' if was_closed else 'Requester reported that the issue was not resolved'):
            # The SAME contractor returns: keep the assignment, reset the work timestamps for the new visit round.
            reason = (request.POST.get('reason') or '').strip()[:1000]
            obj.rework_count += 1
            obj.accepted_at = None
            obj.started_at = None
            obj.completed_at = None
            obj.verified_at = None
            obj.save(update_fields=['rework_count', 'accepted_at', 'started_at', 'completed_at', 'verified_at', 'updated_at'])
            if reason:
                RequestStatusHistory.objects.create(request=obj, old_status='reopened', new_status='reopened', changed_by=request.user, notes=f'Tenant says still not fixed: {reason}')
            notify_admins(f'Request #{obj.id} reopened', f'{obj.tenant.get_full_name() or obj.tenant.username} reported that the repair is not fixed. Please alert the assigned contractor to return; do not assign a new one.', obj)
            send_email_to_admins(
                f'Maintenance request #{obj.id} reopened - repair not fixed',
                f'The tenant reported that request #{obj.id} ({obj.title}) is not fixed. Please review the request and alert the assigned contractor from the admin dashboard.'
            )
            messages.success(request, 'The issue has been reported as not fixed. The landlord has been notified and will send the same contractor back.')
        else:
            messages.error(request, 'This request cannot be reopened from its current state.')
    return redirect('tenant_request_detail', request_id=request_id)


@login_required
@require_POST
def submit_feedback(request, request_id):
    obj = get_object_or_404(MaintenanceRequest, id=request_id, tenant=request.user)
    if obj.status not in {'verified', 'closed'}:
        messages.error(request, 'Feedback is available after the repair has been verified.')
        return redirect('tenant_request_detail', request_id=request_id)
    if Feedback.objects.filter(request=obj).exists():
        messages.info(request, 'Feedback has already been submitted for this request.')
        return redirect('tenant_request_detail', request_id=request_id)
    if request.method == 'POST':
        form = FeedbackForm(request.POST)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.request = obj
            feedback.submitted_by = request.user
            feedback.save()
            audit(request, 'Feedback submitted', obj, f'Rating: {feedback.rating}')
            messages.success(request, 'Thank you for your feedback. Feedback can only be submitted once per request.')
    return redirect('tenant_request_detail', request_id=request_id)


@login_required
def add_attachment(request, request_id):
    obj = get_object_or_404(MaintenanceRequest, id=request_id)
    # Completion evidence belongs to maintenance staff (or administrators), not tenants.
    allowed = request.user.is_admin_user() or (request.user.is_staff_user() and obj.assigned_staff == request.user)
    if not allowed:
        messages.error(request, 'Maintenance evidence can only be uploaded by assigned staff or an administrator.')
        return redirect('tenant_request_detail' if request.user.is_tenant() else 'dashboard', request_id=request_id) if request.user.is_tenant() else redirect('dashboard')
    if obj.status in {'completed','verified','closed','cancelled'}:
        messages.error(request, 'Evidence cannot be added after the job is completed, closed or cancelled.')
        return redirect('admin_request_detail' if request.user.is_admin_user() else 'staff_request_detail', request_id=request_id)
    if request.method == 'POST':
        form = AttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            attachment = form.save(commit=False)
            attachment.request = obj
            attachment.uploaded_by = request.user
            attachment.save()
            audit(request, 'Attachment uploaded', obj, attachment.description)
            messages.success(request, 'Attachment uploaded.')
    return redirect('admin_request_detail' if request.user.is_admin_user() else 'staff_request_detail', request_id=request_id)


@login_required
def notifications(request):
    items = request.user.notifications.all()[:50]
    return render(request, 'requests_app/notifications.html', {'notifications': items})


@login_required
@require_POST
def mark_notification_read(request, notification_id):
    n = get_object_or_404(Notification, id=notification_id, user=request.user)
    n.is_read = True
    n.save(update_fields=['is_read'])
    return redirect('notifications')


@login_required
def request_detail(request, request_id):
    obj = get_object_or_404(MaintenanceRequest, id=request_id)
    if request.user.is_tenant():
        if obj.tenant_id != request.user.id: return redirect('tenant_dashboard')
        return redirect('tenant_request_detail', request_id=request_id)
    if request.user.is_admin_user(): return redirect('admin_request_detail', request_id=request_id)
    if request.user.is_staff_user() and obj.assigned_staff_id == request.user.id: return redirect('staff_request_detail', request_id=request_id)
    return redirect('dashboard')


@csrf_exempt
@require_POST
def iot_status(request):
    """Receive an authenticated sensor event and create a traceable maintenance alert."""
    api_key = request.headers.get('X-IOT-API-KEY')
    if api_key != getattr(settings, 'IOT_API_KEY', 'fixit-demo-key'):
        return JsonResponse({'error': 'Invalid API key'}, status=401)

    import json
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    sensor_id = str(data.get('sensor_id', '')).strip()
    if not sensor_id:
        return JsonResponse({'error': 'sensor_id is required'}, status=400)

    device = IoTDevice.objects.filter(sensor_id=sensor_id, is_active=True).select_related('default_tenant').first()
    if not device:
        return JsonResponse({'error': 'Unknown or inactive sensor'}, status=404)
    if not device.default_tenant or not device.default_tenant.is_active or not device.default_tenant.is_tenant():
        return JsonResponse({'error': 'Sensor has no valid default tenant'}, status=400)

    priority = data.get('priority', 'urgent')
    valid_priorities = {choice[0] for choice in MaintenanceRequest.PRIORITY_CHOICES}
    if priority not in valid_priorities:
        return JsonResponse({'error': 'Invalid priority'}, status=400)

    category = data.get('category', 'other')
    valid_categories = {choice[0] for choice in MaintenanceRequest.CATEGORY_CHOICES}
    if category not in valid_categories:
        return JsonResponse({'error': 'Invalid category'}, status=400)

    value = data.get('value')
    if value not in (None, ''):
        from decimal import Decimal, InvalidOperation
        try:
            value = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return JsonResponse({'error': 'value must be numeric'}, status=400)

    # Only mutate device/request data after all incoming sensor data has passed validation.
    device.last_seen = timezone.now()
    device.save(update_fields=['last_seen'])

    obj = MaintenanceRequest.objects.create(
        title=str(data.get('title') or f'Automatic {device.get_sensor_type_display()} alert'),
        description=str(data.get('description') or f'{device.name} reported a maintenance event.'),
        category=category,
        priority=priority,
        tenant=device.default_tenant,
        apartment_number=str(data.get('apartment_number') or device.apartment_number or device.default_tenant.apartment_number or 'N/A'),
        building=str(data.get('building') or device.building),
        floor=str(data.get('floor') or device.floor),
        location_description=str(data.get('location_description') or device.location_description),
        lease=Lease.objects.filter(tenant=device.default_tenant).first(),
        incident_at=timezone.now(),
        quotation_required=True,        # sensor-created requests follow the same quotation rule as every other request (BR-05)
    )

    reading = SensorReading.objects.create(
        device=device,
        value=value,
        unit=str(data.get('unit') or ''),
        alert_type=str(data.get('alert_type') or ''),
        payload=data,
    )
    RequestStatusHistory.objects.create(request=obj, old_status='pending', new_status='pending', changed_by=device.default_tenant, notes=f'IoT sensor alert received from {device.sensor_id}')
    notify(device.default_tenant, f'Automatic sensor alert #{obj.id}', obj.title, obj)
    audit(request, 'IoT maintenance request created', obj, f'Sensor: {device.sensor_id}; Reading: {reading.id}')

    return JsonResponse({
        'success': True,
        'request_id': obj.id,
        'sensor_id': device.sensor_id,
        'reading_id': reading.id,
        'status': obj.status,
        'sla_deadline': obj.sla_deadline.isoformat() if obj.sla_deadline else None,
    }, status=201)


@login_required
@require_POST
def respond_appointment(request, appointment_id):
    """Tenant confirms the proposed visit, or asks for another time (a reason is required)."""
    from .models import MaintenanceAppointment
    appointment = get_object_or_404(MaintenanceAppointment, pk=appointment_id, request__tenant=request.user)
    job = appointment.request
    decision = request.POST.get('decision')
    if appointment.status != 'proposed' or job.status in {'cancelled', 'closed', 'completed', 'verified'}:
        messages.error(request, 'This visit is no longer awaiting your response.')
    elif decision == 'confirm':
        appointment.status = 'confirmed'
        appointment.save(update_fields=['status', 'updated_at'])
        end_tenant_wait(job)
        job.appointments.filter(status__in=['proposed', 'availability', 'reschedule']).exclude(pk=appointment.pk).update(status='cancelled')
        RequestStatusHistory.objects.create(request=job, old_status=job.status, new_status=job.status, changed_by=request.user,
                                            notes=f'Tenant confirmed the visit on {timezone.localtime(appointment.starts_at):%d %b %Y %H:%M}')
        notify_admins('Visit confirmed by tenant', f'Request #{job.pk}: the tenant confirmed {timezone.localtime(appointment.starts_at):%d %b %H:%M}.', job)
        notify(job.assigned_staff, 'Visit confirmed: you can start work',
               f'Request #{job.pk}: the tenant confirmed the visit on {timezone.localtime(appointment.starts_at):%d %b %Y %H:%M}. You may now start work.', job)
        messages.success(request, 'Visit confirmed. The contractor can now start work.')
    elif decision == 'reschedule':
        reason = (request.POST.get('reason') or '').strip()[:1000]
        if len(reason) < 3:
            messages.error(request, 'Please tell us when you are available, or why this time does not work.')
        else:
            appointment.status = 'reschedule'
            appointment.tenant_response = reason
            appointment.save(update_fields=['status', 'tenant_response', 'updated_at'])
            end_tenant_wait(job)
            RequestStatusHistory.objects.create(request=job, old_status=job.status, new_status=job.status, changed_by=request.user,
                                                notes=f'Tenant asked for another visit time: {reason}')
            notify_admins('Tenant asked for another visit time', f'Request #{job.pk}: "{reason}". Please propose a new time.', job)
            notify(job.assigned_staff, 'Visit time declined by tenant', f'Request #{job.pk}: the tenant cannot make that time. The landlord will propose another.', job)
            messages.success(request, 'Thank you. The landlord has been told and will propose a new time for you to confirm.')
    return redirect('tenant_request_detail', request_id=job.pk)

from datetime import datetime, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Q, Sum, Count, Case, When, Value, IntegerField
from django.db.models.functions import TruncMonth
from django.core.paginator import Paginator
from accounts.models import User
from accounts.forms import StaffRegistrationForm
from requests_app.models import MaintenanceAppointment, MaintenanceRequest, RequestStatusHistory, ContractorQuotation
from requests_app.forms import AdminRequestUpdateForm, RequestFilterForm, ContractorPaymentForm
from requests_app.services import transition, notify, audit


def admin_only(request):
    return request.user.is_admin_user()

@login_required
def admin_dashboard(request):
    if not admin_only(request): return redirect('dashboard')
    qs = MaintenanceRequest.objects.all()
    for obj in qs.exclude(status__in=['closed','cancelled','verified']): obj.mark_sla_if_breached()
    parts = qs.aggregate(v=Sum('parts_cost'))['v'] or 0; labor = qs.aggregate(v=Sum('labor_cost'))['v'] or 0
    staff_workload = []
    for user in User.objects.filter(role='staff'):
        staff_workload.append({'staff': user, 'active': qs.filter(assigned_staff=user, status__in=['assigned','accepted','in_progress','awaiting_parts']).count(), 'completed': qs.filter(assigned_staff=user, status__in=['completed','verified','closed']).count()})
    active_urgent_statuses = ['pending', 'under_review', 'assigned', 'accepted', 'in_progress', 'awaiting_parts', 'reopened']
    monthly_stats = list(
        qs.filter(created_at__gte=timezone.now() - timedelta(days=180))
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(
            requests=Count('id'),
            completed=Count('id', filter=Q(status__in=['completed', 'verified', 'closed'])),
            breached=Count('id', filter=Q(sla_breached=True)),
        )
        .order_by('month')
    )
    for item in monthly_stats:
        item['label'] = item['month'].strftime('%b %Y')
    return render(request, 'admin_panel/admin_dashboard.html', {
        'total_requests': qs.count(), 'pending_requests': qs.filter(status__in=['pending','under_review','reopened']).count(),
        'assigned_requests': qs.filter(status__in=['assigned','accepted']).count(), 'in_progress_requests': qs.filter(status__in=['in_progress','awaiting_parts']).count(),
        'completed_requests': qs.filter(status__in=['completed','verified','closed']).count(), 'overdue_requests': qs.filter(sla_breached=True).exclude(status__in=['closed','cancelled']).count(),
        'total_parts_cost': parts, 'total_labor_cost': labor, 'total_cost': parts+labor,
        'total_staff': User.objects.filter(role='staff').count(), 'total_tenants': User.objects.filter(role='tenant').count(),
        'recent_requests': qs.annotate(priority_order=Case(When(priority='urgent',then=Value(0)),When(priority='high',then=Value(1)),When(priority='medium',then=Value(2)),default=Value(3),output_field=IntegerField())).order_by('priority_order','created_at')[:10], 'urgent_requests': qs.filter(Q(priority='urgent') | Q(safety_risk=True)).filter(status__in=active_urgent_statuses)[:8],
        'activity_feed': RequestStatusHistory.objects.select_related('request','changed_by')[:10], 'staff_workload': staff_workload,
        'availability_offers': MaintenanceAppointment.objects.filter(status='availability').select_related(
            'request', 'request__tenant', 'request__assigned_staff', 'proposed_by'
        )[:20],
        'monthly_stats': monthly_stats,
    })

@login_required
def all_requests(request):
    if not admin_only(request): return redirect('dashboard')
    items = MaintenanceRequest.objects.all(); form = RequestFilterForm(request.GET)
    active_filter = None
    if form.is_valid():
        cd=form.cleaned_data
        if cd['status']: items=items.filter(status=cd['status'])
        if cd['priority']: items=items.filter(priority=cd['priority'])
        if cd['category']: items=items.filter(category=cd['category'])
        if cd['search']: items=items.filter(Q(title__icontains=cd['search'])|Q(description__icontains=cd['search'])|Q(tenant__username__icontains=cd['search'])|Q(tenant__first_name__icontains=cd['search'])|Q(tenant__last_name__icontains=cd['search']))
        if cd['date_from']: items=items.filter(created_at__date__gte=cd['date_from'])
        if cd['date_to']: items=items.filter(created_at__date__lte=cd['date_to'])
    page_obj=Paginator(items,15).get_page(request.GET.get('page'))
    # Support simple URL filters: ?filter=breached or ?filter=at_risk
    f = request.GET.get('filter')
    if f == 'breached':
        items = MaintenanceRequest.objects.filter(sla_breached=True)
        active_filter = 'Breached SLAs'
    elif f == 'at_risk':
        # Determine 'at risk' using the model property (evaluate in Python for simplicity)
        candidate_ids = [r.id for r in MaintenanceRequest.objects.exclude(status__in=['closed','cancelled','verified']) if not r.sla_breached and r.sla_state == 'at_risk']
        items = MaintenanceRequest.objects.filter(id__in=candidate_ids)
        active_filter = 'At-risk SLAs'
    # Rebuild paginator after applying URL filters
    page_obj = Paginator(items, 15).get_page(request.GET.get('page'))
    return render(request,'admin_panel/all_requests.html',{'page_obj':page_obj,'filter_form':form,'total_count':items.count(),'active_filter':active_filter})

@login_required
def admin_request_detail(request, request_id):
    if not admin_only(request): return redirect('dashboard')
    obj=get_object_or_404(MaintenanceRequest,id=request_id); obj.mark_sla_if_breached()
    return render(request,'admin_panel/admin_request_detail.html',{
        'request_obj': obj,
        'status_history': obj.status_history.all(),
        'notes': obj.notes.all(),
        'audit_logs': obj.audit_logs.all()[:20],
        'work_logs': obj.work_logs.select_related('technician').all(),
        'materials': obj.materials.select_related('recorded_by').all(),
        'quotations': obj.quotations.select_related('contractor').all(),
        'payments': obj.payments.select_related('contractor').all(),
        'payment_form': ContractorPaymentForm(initial={'payment_date':timezone.localdate()}),
        'amount_due': obj.amount_due,
        'approved_quote': obj.approved_quotation(),
        'agreed_total': obj.agreed_total,
        'amount_paid': obj.amount_paid,
        'availability_offers': obj.appointments.filter(status='availability'),
        'latest_reschedule': obj.appointments.filter(status='reschedule').first() if not obj.appointments.filter(status__in=['proposed', 'confirmed']).exists() else None,
        'awaiting_tenant': obj.appointments.filter(status='proposed').first(),
        'waiting_for_acceptance': obj.status == 'assigned',
        'stalled_reason': obj.stalled_reason,
        'needs_visit': obj.status in {'accepted', 'in_progress', 'awaiting_parts'} and not obj.appointments.filter(status__in=['proposed', 'confirmed']).exists(),
        'close_blocker': obj.close_blocker(),
        'access_failed': obj.access_failed,
    })

@login_required
def assign_request(request, request_id):
    if not admin_only(request): return redirect('dashboard')
    obj=get_object_or_404(MaintenanceRequest,id=request_id); staff=User.objects.filter(role='staff',is_active=True)
    if request.method=='POST':
        try: selected=staff.get(id=request.POST.get('staff_id'))
        except User.DoesNotExist: selected=None
        if not selected: messages.error(request,'Please select a valid contractor.')
        elif obj.status not in {'pending','under_review','reopened'}: messages.error(request,'This request cannot be assigned in its current state.')
        elif obj.assigned_staff_id and obj.rework_count > 0: messages.error(request,'The tenant reported this repair as not fixed. The same contractor must return: use "Alert contractor" instead of assigning someone new.')
        else:
            obj.assigned_staff=selected; obj.assigned_at=timezone.now()
            emergency = request.POST.get('emergency') == 'on' and obj.priority == 'urgent'
            obj.emergency_callout = emergency
            note = f'Assigned to {selected.username}' + (' (EMERGENCY call-out: work may start before quotation approval)' if emergency else '')
            if obj.status != 'assigned':
                transition(request,obj,'assigned',note)
            else:
                obj.save()
                notify(selected,'New maintenance assignment',f'Request #{obj.id}: {obj.title}',obj)
                audit(request,'Request assigned',obj,selected.username)
            messages.success(request,'Request assigned successfully.'); return redirect('admin_request_detail',request_id=request_id)
    return render(request,'admin_panel/assign_request.html',{'request_obj':obj,'staff_members':staff})

@login_required
def update_request(request, request_id):
    if not admin_only(request): return redirect('dashboard')
    obj=get_object_or_404(MaintenanceRequest,id=request_id)
    original_rate = obj.approved_hourly_rate
    if obj.status in {'completed','verified','closed','cancelled'}:
        messages.error(request,'Completed, closed and cancelled requests are read-only.')
        return redirect('admin_request_detail',request_id=request_id)
    if request.method=='POST':
        form=AdminRequestUpdateForm(request.POST,instance=obj)
        if form.is_valid():
            updated=form.save(commit=False)
            if obj.status in {'accepted','in_progress','awaiting_parts','completed','verified','closed'}:
                updated.approved_hourly_rate = original_rate
            updated.save()
            audit(request,'Request details updated',updated)
            messages.success(request,'Request details updated. Costs remain system-calculated.')
            return redirect('admin_request_detail',request_id=request_id)
    else:
        form=AdminRequestUpdateForm(instance=obj)
    return render(request,'admin_panel/update_request.html',{'form':form,'request_obj':obj})

@login_required
def close_request(request, request_id):
    if not admin_only(request): return redirect('dashboard')
    obj=get_object_or_404(MaintenanceRequest,id=request_id)
    if request.method == 'POST':
        blocker = obj.close_blocker()
        if blocker:
            messages.error(request, blocker)
        elif transition(request, obj, 'closed', 'Closed by administrator: repair verified by the tenant and contractor paid in full'):
            messages.success(request, f'Request closed. The tenant can still reopen it within {obj.REOPEN_WINDOW_DAYS} days if the problem comes back.')
    return redirect('admin_request_detail', request_id=request_id)

@login_required
def manage_staff(request):
    if not admin_only(request): return redirect('dashboard')
    staff_members=User.objects.filter(role='staff')
    for s in staff_members:
        s.assigned_count=MaintenanceRequest.objects.filter(assigned_staff=s,status__in=['assigned','accepted','in_progress','awaiting_parts']).count(); s.completed_count=MaintenanceRequest.objects.filter(assigned_staff=s,status__in=['completed','verified','closed']).count()
    return render(request,'admin_panel/manage_staff.html',{'staff_members':staff_members})

@login_required
def add_staff(request):
    if not admin_only(request): return redirect('dashboard')
    form=StaffRegistrationForm(request.POST or None)
    if request.method=='POST' and form.is_valid(): form.save(); messages.success(request,'Contractor added.'); return redirect('manage_staff')
    return render(request,'admin_panel/add_staff.html',{'form':form})

@login_required
def reports(request):
    if not admin_only(request): return redirect('dashboard')
    end=timezone.localdate(); start=end-timedelta(days=30)
    return render(request,'admin_panel/reports.html',{'start_date':start,'end_date':end})

@login_required
def generate_report(request):
    if not admin_only(request): return redirect('dashboard')

    try:
        start = datetime.strptime(request.POST.get('start_date'), '%Y-%m-%d').date()
        end = datetime.strptime(request.POST.get('end_date'), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        messages.error(request, 'Invalid date range.')
        return redirect('reports')

    if start > end:
        messages.error(request, 'Start date must be before end date.')
        return redirect('reports')

    qs = MaintenanceRequest.objects.filter(created_at__date__gte=start, created_at__date__lte=end)
    total_requests = qs.count()

    completed = qs.filter(completed_at__isnull=False)
    avg_days = None
    if completed.exists():
        avg_hours = sum((x.completed_at - x.created_at).total_seconds() / 3600 for x in completed) / completed.count()
        avg_days = avg_hours / 24

    parts = float(qs.aggregate(v=Sum('parts_cost'))['v'] or 0)
    labor = float(qs.aggregate(v=Sum('labor_cost'))['v'] or 0)
    total_cost = parts + labor

    status_breakdown = list(qs.values('status').annotate(count=Count('id')).order_by('status'))
    for item in status_breakdown:
        item['percent'] = round((item['count'] / total_requests * 100), 1) if total_requests else 0

    priority_breakdown = list(qs.values('priority').annotate(count=Count('id')).order_by('priority'))
    for item in priority_breakdown:
        item['percent'] = round((item['count'] / total_requests * 100), 1) if total_requests else 0

    category_breakdown = list(qs.values('category').annotate(count=Count('id')).order_by('category'))
    for item in category_breakdown:
        item['percent'] = round((item['count'] / total_requests * 100), 1) if total_requests else 0

    category_cost_breakdown = list(
        qs.exclude(total_cost__isnull=True)
        .values('category')
        .annotate(total_cost=Sum('total_cost'))
        .order_by('-total_cost')
    )
    # Convert aggregated Decimal to float to avoid mixing Decimal and float in calculations
    max_category_cost = float(max((item['total_cost'] for item in category_cost_breakdown), default=0))
    for item in category_cost_breakdown:
        item['total_cost'] = float(item['total_cost'] or 0)
        item['percent'] = round((item['total_cost'] / total_cost * 100), 1) if total_cost else 0
        item['bar_width'] = round((item['total_cost'] / max_category_cost * 100), 1) if max_category_cost else 0

    cost_breakdown = [
        {'label': 'Parts', 'value': parts, 'percent': round((parts / total_cost * 100), 1) if total_cost else 0},
        {'label': 'Labor', 'value': labor, 'percent': round((labor / total_cost * 100), 1) if total_cost else 0},
    ]

    staff_performance = []
    for user in User.objects.filter(role='staff').order_by('username'):
        assigned_count = qs.filter(assigned_staff=user).count()
        completed_count = qs.filter(assigned_staff=user, status__in=['completed', 'verified', 'closed']).count()
        completion_rate = round((completed_count / assigned_count * 100), 1) if assigned_count else 0
        staff_performance.append({
            'user': user,
            'assigned_count': assigned_count,
            'completed_count': completed_count,
            'completion_rate': completion_rate,
        })

    return render(request, 'admin_panel/report_result.html', {
        'report_type': request.POST.get('report_type', 'summary'),
        'start_date': start,
        'end_date': end,
        'total_requests': total_requests,
        'status_breakdown': status_breakdown,
        'priority_breakdown': priority_breakdown,
        'category_breakdown': category_breakdown,
        'category_cost_breakdown': category_cost_breakdown,
        'cost_breakdown': cost_breakdown,
        'total_parts_cost': parts,
        'total_labor_cost': labor,
        'total_cost': total_cost,
        'avg_resolution_time': avg_days,
        'staff_performance': staff_performance,
        'requests_list': qs.select_related('tenant', 'assigned_staff').order_by('-created_at') if request.POST.get('report_type') == 'detailed' else None,
    })

@login_required
def process_sla(request):
    if not admin_only(request): return redirect('dashboard')
    breached=0
    for obj in MaintenanceRequest.objects.exclude(status__in=['closed','cancelled','verified']):
        if obj.mark_sla_if_breached():
            breached+=1; notify(obj.assigned_staff,'SLA breached',f'Request #{obj.id} has breached its SLA.',obj)
    from requests_app.services import chase_stalled_jobs
    chased = chase_stalled_jobs()
    messages.success(request,f'SLA monitoring complete. {breached} request(s) newly breached; {chased} non-responding contractor reminder(s) sent.')
    return redirect('admin_dashboard')


@login_required
def review_quotation(request, quote_id):
    """Approve a quotation, or reject it with a reason. A rejection sends the contractor back to revise and resubmit."""
    if not admin_only(request): return redirect('dashboard')
    quote = get_object_or_404(ContractorQuotation, pk=quote_id)
    obj = quote.request
    open_states = {'accepted', 'in_progress', 'awaiting_parts', 'completed', 'verified'} if obj.emergency_callout else {'accepted'}
    if request.method == 'POST' and quote.status == 'submitted' and obj.status in open_states and obj.assigned_staff_id == quote.contractor_id:
        decision = request.POST.get('decision')
        note = (request.POST.get('note') or '').strip()[:2000]
        label = f'#{obj.pk} (quotation revision {quote.revision_number})'
        if decision == 'rejected' and len(note) < 5:
            messages.error(request, 'Say why you are rejecting the quotation (at least 5 characters) so the contractor can revise it.')
            return redirect('admin_request_detail', request_id=obj.pk)
        if decision in {'approved', 'rejected'}:
            quote.status = decision; quote.reviewed_by = request.user; quote.landlord_note = note
            if decision == 'approved': quote.approved_at = timezone.now()
            quote.save()
            obj.recalculate_costs()
            if decision == 'approved':
                notify(quote.contractor, 'Quotation approved', f'Request {label} approved at R{quote.quoted_total}. Work can start once the tenant confirms a visit time.', obj)
            else:
                notify(quote.contractor, 'Quotation rejected: please revise', f'Request {label} was rejected: {note}. Submit a revised quotation.', obj)
                RequestStatusHistory.objects.create(request=obj, old_status=obj.status, new_status=obj.status, changed_by=request.user, notes=f'Quotation revision {quote.revision_number} rejected: {note}')
            audit(request, 'Quotation reviewed', obj, f'Quote #{quote.pk} revision {quote.revision_number}: {decision}')
            messages.success(request, 'Quotation approved.' if decision == 'approved' else 'Quotation rejected. The contractor has been asked to revise and resubmit it.')
    return redirect('admin_request_detail', request_id=obj.pk)


@login_required
def record_payment(request, request_id):
    if not admin_only(request): return redirect('dashboard')
    obj=get_object_or_404(MaintenanceRequest,pk=request_id)
    if request.method == 'POST':
        if obj.status != 'verified' or not obj.assigned_staff_id:
            messages.error(request,'Payment can be recorded only after the tenant has confirmed the repair is fixed.')
        else:
            due = obj.amount_due
            if due is None:
                messages.error(request,'A quotation must be approved before the amount payable can be calculated.')
                return redirect('admin_request_detail',request_id=request_id)
            if due <= 0:
                messages.error(request,'This job has already been paid in full.')
                return redirect('admin_request_detail',request_id=request_id)
            form=ContractorPaymentForm(request.POST,request.FILES)
            if form.is_valid():
                payment=form.save(commit=False)
                payment.request=obj; payment.contractor=obj.assigned_staff; payment.recorded_by=request.user
                payment.amount=due                      # calculated by the system, never typed in
                if not payment.reference:
                    payment.reference=f'PAY-{obj.pk}-{obj.payments.count()+1}'
                if obj.payments.filter(reference=payment.reference).exists():
                    messages.error(request,'A payment with this reference already exists for this request.')
                    return redirect('admin_request_detail',request_id=request_id)
                payment.save()
                notify(payment.contractor,'Payment recorded',f'Payment of R{payment.amount} recorded for request #{obj.pk}; please confirm receipt.',obj)
                audit(request,'Payment recorded',obj,f'Payment #{payment.pk}, reference {payment.reference}')
                messages.success(request,f'Payment of R{payment.amount} recorded. Contractor acknowledgement is pending.')
            else: messages.error(request,'Upload a valid proof of payment (PDF, JPG or PNG, max 5 MB).')
    return redirect('admin_request_detail',request_id=request_id)


@login_required
def pending_tenants(request):
    if not admin_only(request): return redirect('dashboard')
    users=User.objects.filter(role='tenant',is_active=False).order_by('date_joined')
    return render(request,'admin_panel/pending_tenants.html',{'tenants':users})


@login_required
def approve_tenant(request, user_id):
    if not admin_only(request): return redirect('dashboard')
    tenant=get_object_or_404(User,pk=user_id,role='tenant',is_active=False)
    if request.method == 'POST':
        if request.POST.get('decision') == 'approve':
            from accounts.models import Lease
            lease = Lease.objects.filter(tenant=tenant).first()
            if not lease:
                messages.error(request, 'No matching lease invitation. Approval blocked.')
                return redirect('pending_tenants')
            lease.verified = True
            lease.save(update_fields=['verified'])
            tenant.apartment_number = lease.unit
            tenant.address = lease.residence
            tenant.is_active = True
            tenant.save(update_fields=['apartment_number', 'address', 'is_active'])
            messages.success(request,'Tenant account activated after verification.')
        elif request.POST.get('decision') == 'reject':
            # Retain inactive registration for review/audit; do not delete automatically.
            messages.info(request,'Registration remains inactive.')
    return redirect('pending_tenants')


@login_required
def approve_sla_pause(request, request_id):
    if not admin_only(request): return redirect('dashboard')
    obj = get_object_or_404(MaintenanceRequest, pk=request_id)
    if request.method == 'POST' and obj.status == 'awaiting_parts' and obj.sla_pause_started_at:
        obj.sla_pause_approved = request.POST.get('decision') == 'approve'
        obj.save(update_fields=['sla_pause_approved','updated_at'])
        audit(request,'SLA pause reviewed',obj, 'Approved' if obj.sla_pause_approved else 'Not approved')
        messages.success(request, 'SLA waiting-time decision recorded.')
    return redirect('admin_request_detail', request_id=request_id)


@login_required
def create_lease(request):
    from accounts.models import Lease
    from django import forms
    import secrets
    if not request.user.is_admin_user():
        return redirect('dashboard')
    class LeaseForm(forms.ModelForm):
        class Meta:
            model = Lease
            fields = ['tenant_email','residence','unit','floor','start_date','end_date']
            widgets = {'start_date': forms.DateInput(attrs={'type':'date'}), 'end_date': forms.DateInput(attrs={'type':'date'})}
        def clean(self):
            data = super().clean()
            if data.get('start_date') and data.get('end_date') and data['end_date'] < data['start_date']:
                raise forms.ValidationError('Lease end must be after the start.')
            return data
    form = LeaseForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        lease = form.save(commit=False)
        lease.invitation_code = secrets.token_urlsafe(18)
        lease.save()
        messages.success(request, 'Lease invitation created. Share its code securely with the named tenant.')
        return redirect('admin_create_lease')
    return render(request,'admin_panel/leases.html',{'form':form,'leases':Lease.objects.order_by('-created_at')[:50]})


@login_required
@require_POST
def propose_appointment(request, request_id):
    from django.utils.dateparse import parse_datetime
    from django.utils import timezone
    if not request.user.is_admin_user():
        return redirect('dashboard')
    job = get_object_or_404(MaintenanceRequest, pk=request_id)
    if job.status in {'closed','cancelled','verified','completed'}:
        messages.error(request, 'Cannot schedule a closed or completed job.')
        return redirect('admin_request_detail', request_id=request_id)
    start = parse_datetime(request.POST.get('starts_at',''))
    end = parse_datetime(request.POST.get('ends_at',''))
    if not start or not end:
        messages.error(request, 'Enter a valid start and end date/time.')
    else:
        if timezone.is_naive(start): start = timezone.make_aware(start)
        if timezone.is_naive(end): end = timezone.make_aware(end)
        from requests_app.services import propose_visit
        ok, msg = propose_visit(request.user, job, start, end, request.POST.get('note', ''))
        (messages.success if ok else messages.error)(request, msg)
    return redirect('admin_request_detail', request_id=request_id)


@login_required
def alert_contractor(request, request_id):
    """After the tenant reports 'not fixed', the landlord sends the SAME contractor back."""
    if not admin_only(request): return redirect('dashboard')
    obj = get_object_or_404(MaintenanceRequest, pk=request_id)
    if request.method == 'POST':
        if obj.status != 'reopened' or not obj.assigned_staff_id:
            messages.error(request, 'Only a reopened request that still has an assigned contractor can be sent back.')
        elif transition(request, obj, 'assigned', f'Landlord alerted {obj.assigned_staff.username} to return (tenant reports not fixed)'):
            notify(obj.assigned_staff, 'Return visit required',
                   f'Request #{obj.pk} ({obj.title}): the tenant reports the repair is not fixed. Please accept the job and offer the landlord your availability for the return visit; the tenant must confirm it before you start.', obj)
            audit(request, 'Contractor alerted to return', obj, obj.assigned_staff.username)
            messages.success(request, f'{obj.assigned_staff.username} has been alerted to return.')
    return redirect('admin_request_detail', request_id=request_id)


@login_required
@require_POST
def relay_availability_view(request, appointment_id):
    """Send the contractor's offered return time to the tenant for confirmation."""
    from requests_app.models import MaintenanceAppointment
    from requests_app.services import relay_availability
    if not admin_only(request): return redirect('dashboard')
    appointment = get_object_or_404(MaintenanceAppointment, pk=appointment_id)
    ok, msg = relay_availability(request.user, appointment)
    (messages.success if ok else messages.error)(request, msg)
    return redirect('admin_request_detail', request_id=appointment.request_id)


@login_required
@require_POST
def reassign_contractor(request, request_id):
    """Replace a contractor who is not responding, before any work has started."""
    if not admin_only(request): return redirect('dashboard')
    obj = get_object_or_404(MaintenanceRequest, pk=request_id)
    reason = (request.POST.get('reason') or '').strip()
    if not obj.can_be_reassigned:
        messages.error(request, 'The contractor can only be replaced before work has started.')
    elif len(reason) < 5:
        messages.error(request, 'Say why you are replacing the contractor (at least 5 characters).')
    else:
        old = obj.assigned_staff
        old_status = obj.status
        if transition(request, obj, 'reopened', f'Contractor {old.username} replaced by landlord: {reason}'):
            obj.assigned_staff = None
            obj.emergency_callout = False
            obj.save(update_fields=['assigned_staff', 'emergency_callout', 'updated_at'])
            obj.appointments.filter(status__in=['proposed', 'availability', 'reschedule', 'confirmed']).update(status='cancelled')
            from requests_app.services import end_tenant_wait
            end_tenant_wait(obj)
            obj.quotations.filter(status='submitted').update(status='rejected', landlord_note='Contractor replaced by the landlord.', reviewed_by=request.user)
            notify(old, 'Job reassigned', f'Request #{obj.pk} was taken off you: {reason}', obj)
            notify(obj.tenant, 'Contractor being replaced', f'Request #{obj.pk}: the landlord is assigning a different contractor. Any visit you confirmed is cancelled and a new time will be proposed.', obj)
            audit(request, 'Contractor replaced', obj, f'{old.username} ({old_status}): {reason}')
            messages.success(request, f'{old.username} removed. Choose a new contractor.')
            return redirect('assign_request', request_id=obj.pk)
    return redirect('admin_request_detail', request_id=request_id)

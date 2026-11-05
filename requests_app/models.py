from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import os


def request_photo_path(instance, filename):
    ext = filename.split('.')[-1].lower()
    return os.path.join('request_photos', f'request_{instance.request_id}_{timezone.now().strftime("%Y%m%d%H%M%S")}.{ext}')


class MaintenanceRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Submitted'),
        ('under_review', 'Under Review'),
        ('assigned', 'Assigned'),
        ('accepted', 'Accepted'),
        ('in_progress', 'In Progress'),
        ('awaiting_parts', 'Awaiting Parts'),
        ('completed', 'Completed'),
        ('verified', 'Verified'),
        ('closed', 'Closed'),
        ('reopened', 'Reopened'),
        ('cancelled', 'Cancelled'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('urgent', 'Urgent')
    ]
    CATEGORY_CHOICES = [
        ('plumbing', 'Plumbing'), ('electrical', 'Electrical'),
        ('hvac', 'HVAC (Heating/Cooling)'), ('appliance', 'Appliance'),
        ('structural', 'Structural'), ('pest_control', 'Pest Control'),
        ('cleaning', 'Cleaning'), ('other', 'Other'),
    ]
    SLA_HOURS = {'low': 120, 'medium': 48, 'high': 24, 'urgent': 4}
    RESPONSE_HOURS = {'low': 24, 'medium': 4, 'high': 1, 'urgent': 0.25}

    incident_at = models.DateTimeField(null=True, blank=True, help_text="When the fault was first noticed (if known).")
    ACCESS_CHOICES = [('contact', 'Contact me to arrange access'), ('notify', 'Entry permitted with advance notice'), ('present', 'I must be present')]
    VISIT_CHOICES = [('', 'No preference'), ('morning', 'Morning'), ('afternoon', 'Afternoon'), ('anytime', 'Anytime')]
    access_permission = models.CharField(max_length=12, choices=ACCESS_CHOICES, default='contact')
    preferred_visit_time = models.CharField(max_length=12, choices=VISIT_CHOICES, blank=True, default='')
    safety_risk = models.BooleanField(default=False)
    tenant_wait_started_at = models.DateTimeField(null=True, blank=True, help_text='Set while a visit proposal waits for the tenant; the SLA clock is paused for that time.')

    quotation_required = models.BooleanField(default=False, help_text="New contractor jobs require an approved quotation; legacy jobs remain compatible.")
    rework_count = models.PositiveSmallIntegerField(default=0, help_text="How many times the tenant reported the repair as not fixed. The same contractor returns each time.")
    emergency_callout = models.BooleanField(default=False, help_text="Landlord-authorised emergency call-out: work may start before the quotation is approved; the quotation follows afterwards.")
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    lease = models.ForeignKey('accounts.Lease', null=True, blank=True, on_delete=models.PROTECT, related_name='requests')
    tenant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='maintenance_requests')
    assigned_staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name='assigned_tasks', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    photo = models.ImageField(upload_to='request_photos/', null=True, blank=True)
    apartment_number = models.CharField(max_length=20)
    location_description = models.TextField(blank=True, null=True)
    building = models.CharField(max_length=100, blank=True)
    floor = models.CharField(max_length=20, blank=True)
    parts_required = models.CharField(max_length=255, blank=True)
    parts_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    labor_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # Controlled by administrators; staff never enter or see this rate.
    approved_hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=250.00,
                                                help_text='Administrator-approved labour rate in Rand per hour.')
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cost_approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_costs')
    cost_approved_at = models.DateTimeField(null=True, blank=True)
    staff_notes = models.TextField(blank=True, null=True)
    admin_notes = models.TextField(blank=True, null=True)
    diagnosis = models.TextField(blank=True)
    resolution_notes = models.TextField(blank=True, null=True)
    rejection_reason = models.TextField(blank=True)
    sla_hours = models.PositiveIntegerField(default=24)
    sla_deadline = models.DateTimeField(null=True, blank=True)
    sla_breached = models.BooleanField(default=False)
    response_deadline = models.DateTimeField(null=True, blank=True)
    first_response_at = models.DateTimeField(null=True, blank=True)
    original_sla_deadline = models.DateTimeField(null=True, blank=True)
    sla_pause_started_at = models.DateTimeField(null=True, blank=True)
    sla_pause_reason = models.TextField(blank=True)
    sla_pause_approved = models.BooleanField(default=False)
    sla_paused_seconds = models.PositiveIntegerField(default=0)
    assigned_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Maintenance Request'
        verbose_name_plural = 'Maintenance Requests'

    def __str__(self):
        return f'#{self.id} - {self.title} ({self.get_status_display()})'

    @classmethod
    def sla_for_priority(cls, priority):
        return cls.SLA_HOURS.get(priority, 24)

    def set_sla(self, force=False):
        if force or not self.sla_deadline or self.sla_deadline <= (self.created_at or timezone.now()):
            self.sla_hours = self.sla_for_priority(self.priority)
            base = self.created_at or timezone.now()
            self.sla_deadline = base + timedelta(hours=self.sla_hours)
            if not self.original_sla_deadline:
                self.original_sla_deadline = self.sla_deadline
            if not self.response_deadline:
                self.response_deadline = base + timedelta(hours=self.RESPONSE_HOURS.get(self.priority, 4))

    @property
    def is_sla_breached(self):
        if self.status in {'closed', 'cancelled', 'verified', 'completed'}:
            return self.sla_breached
        return bool(self.sla_deadline and timezone.now() > self.sla_deadline and not self.sla_pause_started_at)

    @property
    def sla_state(self):
        if self.is_sla_breached:
            return 'breached'
        if not self.sla_deadline:
            return 'unknown'
        remaining = self.sla_deadline - timezone.now()
        if remaining.total_seconds() <= max(self.sla_hours * 3600 * 0.25, 3600):
            return 'at_risk'
        return 'within'

    def mark_sla_if_breached(self):
        if self.is_sla_breached and not self.sla_breached and self.status not in {'closed', 'cancelled', 'verified', 'completed'}:
            self.sla_breached = True
            self.save(update_fields=['sla_breached', 'updated_at'])
            return True
        return False

    @staticmethod
    def allowed_transitions_map():
        return {
            'pending': {'under_review', 'assigned', 'cancelled'},
            'under_review': {'assigned', 'cancelled'},
            'assigned': {'accepted', 'cancelled', 'reopened'},
            'accepted': {'in_progress', 'cancelled', 'reopened'},
            'in_progress': {'awaiting_parts', 'completed'},
            'awaiting_parts': {'in_progress', 'completed'},
            'completed': {'verified', 'reopened'},
            'verified': {'closed', 'reopened'},
            'closed': {'reopened'},
            'reopened': {'under_review', 'assigned'},
            'cancelled': set(),
        }

    CANCELLABLE_STATUSES = {'pending', 'under_review', 'assigned', 'accepted'}
    REOPEN_WINDOW_DAYS = 7

    @property
    def can_be_reopened_by_tenant(self):
        """Tenant may say 'not fixed' once the contractor has finished, and up to 7 days after closure ('problem came back')."""
        if self.status in {'completed', 'verified'}:
            return True
        if self.status == 'closed' and self.closed_at:
            return timezone.now() - self.closed_at <= timedelta(days=self.REOPEN_WINDOW_DAYS)
        return False

    def visit_blocks_start(self):
        """Work may not start until the TENANT has confirmed a visit (emergency call-outs excepted)."""
        if self.emergency_callout:
            return False
        return not self.appointments.filter(status='confirmed').exists()

    VISIT_EARLY_MINUTES = 30
    ACCEPT_REMINDER_HOURS = 24      # contractor has not accepted an assignment after this long
    VISIT_REMINDER_HOURS = 48       # accepted but still no visit arranged after this long

    def visit_too_early(self):
        """True when the tenant-confirmed visit has not begun yet (work may start 30 minutes before it)."""
        if self.emergency_callout:
            return False
        appt = self.appointments.filter(status='confirmed').order_by('starts_at').first()
        return bool(appt and timezone.now() < appt.starts_at - timedelta(minutes=self.VISIT_EARLY_MINUTES))

    def next_visit_start(self):
        appt = self.appointments.filter(status='confirmed').order_by('starts_at').first()
        return appt.starts_at if appt else None

    @property
    def stalled_reason(self):
        """Why the landlord should chase or replace the contractor, or None."""
        now = timezone.now()
        if self.status == 'assigned' and self.assigned_at and not self.rework_count:
            hours = int((now - self.assigned_at).total_seconds() // 3600)
            if hours >= self.ACCEPT_REMINDER_HOURS:
                return f'The contractor has not accepted this job after {hours} hours.'
        if self.status == 'accepted' and self.accepted_at and not self.rework_count:
            hours = int((now - self.accepted_at).total_seconds() // 3600)
            if hours >= self.VISIT_REMINDER_HOURS and not self.appointments.filter(status__in=['proposed', 'confirmed']).exists():
                return f'No visit has been arranged {hours} hours after the contractor accepted.'
        return None

    @property
    def can_be_reassigned(self):
        """The landlord may replace the contractor only before any work has started or been repeated."""
        return bool(self.assigned_staff_id and self.status in {'assigned', 'accepted'} and not self.rework_count)

    @property
    def access_failed(self):
        record = self.current_visit_record
        return bool(record and record.access_outcome == 'no_access')

    def has_completion_evidence(self, contractor):
        """A JPG/PNG work photo uploaded by the contractor since this round of work started."""
        if not self.started_at:
            return False
        for item in self.attachments.filter(uploaded_by=contractor, created_at__gte=self.started_at):
            if item.file.name.lower().rsplit('.', 1)[-1] in {'jpg', 'jpeg', 'png'}:
                return True
        return False

    def close_blocker(self):
        """Reason the landlord cannot close the request yet, or None when closing is allowed."""
        if self.status != 'verified':
            return 'The tenant must first confirm that the repair is fixed.'
        if self.quotation_required:
            due = self.amount_due
            if due is None:
                return 'No quotation was approved, so the payable amount is unknown.'
            if due > 0:
                return f'Payment of R{due} is still outstanding. Record the payment (with proof) before closing.'
        return None

    @property
    def can_be_cancelled_by_tenant(self):
        """Tenants may cancel only before any work has started."""
        return self.status in self.CANCELLABLE_STATUSES

    def quote_blocks_start(self, contractor):
        """True when work may not start yet because the quotation is not approved."""
        if not self.quotation_required or self.emergency_callout:
            return False
        return not self.quotations.filter(contractor=contractor, status='approved').exists()

    def quote_blocks_completion(self, contractor):
        """Normal jobs need an approved quotation; emergency jobs need one submitted afterwards."""
        if not self.quotation_required:
            return False
        allowed = ['submitted', 'approved'] if self.emergency_callout else ['approved']
        return not self.quotations.filter(contractor=contractor, status__in=allowed).exists()

    def is_transition_allowed(self, new_status):
        return new_status in self.allowed_transitions_map().get(self.status, set())

    def approved_quotation(self):
        return self.quotations.filter(status='approved', contractor_id=self.assigned_staff_id).order_by('-approved_at').first()

    @property
    def agreed_total(self):
        """Amount agreed with the contractor (approved quotation: labour + materials), or None if not yet approved."""
        quote = self.approved_quotation()
        return (quote.labour_amount + quote.estimated_materials) if quote else None

    @property
    def amount_paid(self):
        from decimal import Decimal
        return sum((p.amount for p in self.payments.filter(status__in=['recorded', 'confirmed'])), Decimal('0.00'))

    @property
    def amount_due(self):
        """Outstanding balance, calculated by the system. None until a quotation is approved."""
        total = self.agreed_total
        if total is None:
            return None
        return total - self.amount_paid

    @property
    def confirmed_appointment(self):
        return self.appointments.filter(status='confirmed').first()

    @property
    def current_visit_record(self):
        return self.work_logs.filter(visit_round=self.rework_count).first()

    def recalculate_costs(self):
        """Recalculate labour/material totals from work records.

        The calculation is deliberately server-side. Staff submit work evidence only;
        financial values are exposed through the administrator portal.
        """
        from decimal import Decimal
        labour = sum((log.labour_cost for log in self.work_logs.all()), Decimal('0.00'))
        materials = sum((item.total_cost for item in self.materials.all()), Decimal('0.00'))
        approved_quote = self.quotations.filter(status='approved', contractor_id=self.assigned_staff_id).order_by('-approved_at').first()
        if self.quotation_required and approved_quote:
            # The approved quotation is the agreed price: contractors do not re-enter materials.
            labour = approved_quote.labour_amount
            materials = approved_quote.estimated_materials
        self.labor_cost = labour
        self.parts_cost = materials
        self.total_cost = labour + materials
        self.save(update_fields=['labor_cost', 'parts_cost', 'total_cost', 'updated_at'])

    def save(self, *args, **kwargs):
        if self.parts_cost is not None or self.labor_cost is not None:
            self.total_cost = (self.parts_cost or 0) + (self.labor_cost or 0)
        # Only initialise an SLA when one has not already been set.
        # Never reset an overdue deadline during an unrelated save.
        if not self.sla_deadline:
            self.set_sla(force=True)
        super().save(*args, **kwargs)

    def get_status_badge_class(self):
        return {
            'pending': 'bg-warning text-dark', 'under_review': 'bg-secondary',
            'assigned': 'bg-info text-dark', 'accepted': 'bg-primary',
            'in_progress': 'bg-primary', 'awaiting_parts': 'bg-warning text-dark',
            'completed': 'bg-success', 'verified': 'bg-success', 'closed': 'bg-dark',
            'reopened': 'bg-danger', 'cancelled': 'bg-secondary'
        }.get(self.status, 'bg-secondary')

    def get_priority_badge_class(self):
        return {'low': 'bg-success', 'medium': 'bg-info text-dark', 'high': 'bg-warning text-dark', 'urgent': 'bg-danger'}.get(self.priority, 'bg-secondary')


class WorkLog(models.Model):
    """Contractor visit / access record: whether access was gained and the work performed, with automatic times."""
    request = models.ForeignKey(MaintenanceRequest, on_delete=models.CASCADE, related_name='work_logs')
    technician = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='work_logs')
    work_date = models.DateField(default=timezone.localdate)
    # Captured automatically from the request lifecycle; staff never type these values.
    start_time = models.TimeField()
    end_time = models.TimeField(null=True, blank=True)
    ACCESS_CHOICES = [('access_granted', 'Access gained: work carried out'), ('no_access', 'No access: tenant absent or entry refused')]
    access_outcome = models.CharField(max_length=15, choices=ACCESS_CHOICES, default='access_granted')
    visit_round = models.PositiveSmallIntegerField(default=0, help_text="0 for the first visit; increases each time the tenant reports the repair as not fixed.")
    appointment = models.ForeignKey('MaintenanceAppointment', null=True, blank=True, on_delete=models.SET_NULL, related_name='visit_records')
    updated_at = models.DateTimeField(auto_now=True)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-work_date', '-start_time']
        constraints = [
            models.UniqueConstraint(fields=['request', 'visit_round'], name='one_visit_record_per_round'),
        ]

    @property
    def hours(self):
        from datetime import datetime, timedelta
        if not self.end_time:
            return 0
        start = datetime.combine(self.work_date, self.start_time)
        end = datetime.combine(self.work_date, self.end_time)
        if end < start:
            end += timedelta(days=1)
        return round((end - start).total_seconds() / 3600, 2)

    @property
    def labour_cost(self):
        return (self.hourly_rate * Decimal(str(self.hours))).quantize(Decimal('0.01'))

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.end_time and self.end_time <= self.start_time:
            # Overnight jobs are valid; hours() handles the date rollover.
            pass
        if self.request_id and self.technician_id and self.request.assigned_staff_id != self.technician_id:
            raise ValidationError('Only the assigned technician can submit a work log for this request.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        self.request.recalculate_costs()

    def delete(self, *args, **kwargs):
        request_obj = self.request
        result = super().delete(*args, **kwargs)
        request_obj.recalculate_costs()
        return result


class Material(models.Model):
    """Materials/parts recorded by the technician; totals are calculated by the server."""
    request = models.ForeignKey(MaintenanceRequest, on_delete=models.CASCADE, related_name='materials')
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='recorded_materials')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def total_cost(self):
        return (self.quantity * self.unit_cost).quantize(Decimal('0.01'))

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.quantity <= 0:
            raise ValidationError({'quantity': 'Quantity must be greater than zero.'})
        if self.unit_cost < 0:
            raise ValidationError({'unit_cost': 'Unit cost cannot be negative.'})
        if self.request_id and self.recorded_by_id and self.request.assigned_staff_id != self.recorded_by_id:
            raise ValidationError('Only the assigned technician can submit materials for this request.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        self.request.recalculate_costs()

    def delete(self, *args, **kwargs):
        request_obj = self.request
        result = super().delete(*args, **kwargs)
        request_obj.recalculate_costs()
        return result


class RequestStatusHistory(models.Model):
    request = models.ForeignKey(MaintenanceRequest, on_delete=models.CASCADE, related_name='status_history')
    old_status = models.CharField(max_length=20, choices=MaintenanceRequest.STATUS_CHOICES)
    new_status = models.CharField(max_length=20, choices=MaintenanceRequest.STATUS_CHOICES)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.request.id}: {self.old_status} -> {self.new_status}'


class StaffNote(models.Model):
    request = models.ForeignKey(MaintenanceRequest, on_delete=models.CASCADE, related_name='notes')
    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']


class Attachment(models.Model):
    request = models.ForeignKey(MaintenanceRequest, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='maintenance_attachments/')
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Feedback(models.Model):
    request = models.OneToOneField(MaintenanceRequest, on_delete=models.CASCADE, related_name='feedback')
    rating = models.PositiveSmallIntegerField(choices=[(i, f'{i} Star') for i in range(1, 6)])
    comment = models.TextField(blank=True)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    request = models.ForeignKey(MaintenanceRequest, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=100)
    request = models.ForeignKey(MaintenanceRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    details = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

class IoTDevice(models.Model):
    """Registered embedded sensor/device that can create maintenance alerts."""
    SENSOR_TYPES = [
        ('water_leak', 'Water Leak'),
        ('temperature', 'Temperature'),
        ('smoke', 'Smoke'),
        ('power', 'Power'),
        ('other', 'Other'),
    ]

    sensor_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    sensor_type = models.CharField(max_length=30, choices=SENSOR_TYPES, default='other')
    building = models.CharField(max_length=100)
    floor = models.CharField(max_length=20, blank=True)
    apartment_number = models.CharField(max_length=20, blank=True)
    location_description = models.TextField(blank=True)
    default_tenant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='iot_devices')
    is_active = models.BooleanField(default=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sensor_id']

    def __str__(self):
        return f'{self.sensor_id} - {self.name}'


class SensorReading(models.Model):
    """Stores readings received from an IoT device for traceability."""
    device = models.ForeignKey(IoTDevice, on_delete=models.CASCADE, related_name='readings')
    value = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    unit = models.CharField(max_length=20, blank=True)
    alert_type = models.CharField(max_length=50, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-received_at']

    def __str__(self):
        return f'{self.device.sensor_id} @ {self.received_at:%Y-%m-%d %H:%M:%S}'



class ContractorQuotation(models.Model):
    """Estimate submitted by the assigned contractor and approved by the landlord."""
    STATUS_CHOICES = [('submitted', 'Awaiting Approval'), ('approved', 'Approved'), ('rejected', 'Rejected')]
    request = models.ForeignKey(MaintenanceRequest, on_delete=models.CASCADE, related_name='quotations')
    contractor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='contractor_quotations')
    scope = models.TextField()
    labour_amount = models.DecimalField(max_digits=10, decimal_places=2)
    estimated_materials = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estimated_hours = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True, help_text='Optional and informational only: the labour amount is the price.')
    revision_number = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='submitted')
    landlord_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_quotations')

    @property
    def quoted_total(self):
        return self.labour_amount + self.estimated_materials

    class Meta:
        ordering = ['-created_at']


class ContractorPayment(models.Model):
    """Landlord records actual transfer; contractor independently acknowledges receipt."""
    STATUS_CHOICES = [('recorded', 'Recorded by Landlord'), ('confirmed', 'Receipt Confirmed'), ('disputed', 'Disputed')]
    request = models.ForeignKey(MaintenanceRequest, on_delete=models.PROTECT, related_name='payments')
    contractor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='contractor_payments')
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='recorded_contract_payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField()
    reference = models.CharField(max_length=120)
    proof = models.FileField(upload_to='payment_proofs/', blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='recorded')
    contractor_comment = models.TextField(blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class MaintenanceAppointment(models.Model):
    STATUS = [('proposed','Proposed'), ('confirmed','Confirmed'), ('reschedule','Reschedule requested'), ('availability','Contractor availability'), ('cancelled','Cancelled'), ('attended','Attended'), ('no_access','No access')]
    request = models.ForeignKey(MaintenanceRequest, on_delete=models.CASCADE, related_name='appointments')
    proposed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='proposed_appointments')
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(max_length=15, choices=STATUS, default='proposed')
    note = models.TextField(blank=True, help_text="Message from whoever proposed the visit (for example why a return visit is needed).")
    tenant_response = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

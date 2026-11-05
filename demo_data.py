#!/usr/bin/env python
"""
Stage realistic demo data for the FixIt Pro presentation.

Run once after `python manage.py migrate` and `python setup.py`:

    python demo_data.py

Every step goes through the real web views (as the tenant, contractor and landlord would click them),
so the data is produced by the same business rules the system enforces. Safe to run again: it skips
anything already staged.
"""
import io
import os
import sys
from datetime import timedelta

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'maintenance_system.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.test import Client  # noqa: E402
from django.urls import reverse  # noqa: E402
from django.utils import timezone  # noqa: E402
from PIL import Image  # noqa: E402

from accounts.models import User  # noqa: E402
from requests_app.models import MaintenanceRequest, MaintenanceAppointment  # noqa: E402

HOST = 'localhost'


def client_for(username):
    c = Client(HTTP_HOST=HOST)
    c.force_login(User.objects.get(username=username))
    return c


tenant, landlord, mike, sarah = (client_for(u) for u in ('tenant', 'admin', 'contractor', 'contractor2'))


def photo(name='after_repair.jpg'):
    buf = io.BytesIO()
    Image.new('RGB', (640, 420), (214, 226, 232)).save(buf, 'JPEG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')


def proof():
    return SimpleUploadedFile('proof_of_payment.pdf', b'%PDF-1.4\n% FixIt Pro demo proof of payment\n', content_type='application/pdf')


def when(days, hour=9):
    start = (timezone.localtime() + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return {'starts_at': start.strftime('%Y-%m-%dT%H:%M'), 'ends_at': (start + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M')}


def submit(title, description, category, priority='medium', safety=False):
    existing = MaintenanceRequest.objects.filter(title=title).first()
    if existing:
        return existing, False
    data = {'title': title, 'description': description, 'category': category, 'priority': priority,
            'access_permission': 'contact', 'preferred_visit_time': 'morning', 'location_description': 'See description'}
    if safety:
        data['safety_risk'] = 'on'
    tenant.post(reverse('submit_request'), data)
    return MaintenanceRequest.objects.get(title=title), True


def assign(job, contractor_username='contractor', emergency=False):
    from django.contrib.auth import get_user_model
    staff = get_user_model().objects.get(username=contractor_username)
    data = {'staff_id': staff.id}
    if emergency:
        data['emergency'] = 'on'
    landlord.post(reverse('assign_request', args=[job.id]), data)


def quote(job, who, labour, materials, scope, hours=''):
    who.post(reverse('staff_submit_quotation', args=[job.id]),
             {'scope': scope, 'labour_amount': labour, 'estimated_materials': materials, 'estimated_hours': hours})


def approve(job):
    q = job.quotations.filter(status='submitted').first()
    landlord.post(reverse('admin_review_quotation', args=[q.id]), {'decision': 'approved', 'note': ''})


def visit(job, days=1, future=False):
    landlord.post(reverse('admin_propose_appointment', args=[job.id]), dict(when(days), note='Please be home for the visit'))
    appt = job.appointments.filter(status='proposed').first()
    tenant.post(reverse('respond_appointment', args=[appt.id]), {'decision': 'confirm'})
    if not future:   # let the visit day arrive so the contractor can start (work may begin 30 min before the visit)
        from datetime import timedelta as _td
        MaintenanceAppointment.objects.filter(pk=appt.pk).update(starts_at=timezone.now() - _td(minutes=5), ends_at=timezone.now() + _td(hours=2))


def start_and_record(job, who, notes, outcome='access_granted'):
    who.post(reverse('staff_start_job', args=[job.id]))
    who.post(reverse('staff_add_work_log', args=[job.id]), {'access_outcome': outcome, 'notes': notes})


def finish(job, who):
    who.post(reverse('add_attachment', args=[job.id]), {'file': photo(), 'description': 'Photo after the repair'})
    who.post(reverse('staff_mark_complete', args=[job.id]))


def pay_and_close(job):
    landlord.post(reverse('admin_record_payment', args=[job.id]),
                  {'payment_date': timezone.localdate().isoformat(), 'reference': f'EFT-DEMO-{job.id}', 'proof': proof()})
    payment = job.payments.first()
    mike.post(reverse('staff_acknowledge_payment', args=[payment.id]), {'decision': 'confirmed', 'comment': 'Received, thank you'})
    landlord.post(reverse('admin_close_request', args=[job.id]))


def refresh(job):
    job.refresh_from_db()
    return job


def stage():
    # 1. Assigned, waiting for the contractor (created by setup.py): "Leaking bathroom tap"
    #    Backdated 30 hours so the landlord sees the 'contractor not responding' warning and the Replace option.
    MaintenanceRequest.objects.filter(title='Leaking bathroom tap', status='assigned').update(assigned_at=timezone.now() - timedelta(hours=30))
    # 2. Quotation submitted, waiting for the landlord to decide
    j, new = submit('No hot water in the shower', 'The geyser is on but the shower only runs cold water.', 'plumbing', 'high')
    if new:
        assign(j); mike.post(reverse('staff_accept_job', args=[j.id]))
        quote(j, mike, '650', '300', 'Inspect the geyser, replace the faulty thermostat and test the hot water supply.', '2')
        mike.post(reverse('staff_offer_availability', args=[j.id]), dict(when(2, 8), note='I need about two hours'))

    # 3. Quotation rejected: contractor must revise
    j, new = submit('Water stain on bedroom ceiling', 'A brown stain is spreading on the bedroom ceiling.', 'structural', 'medium')
    if new:
        assign(j, 'contractor2'); sarah.post(reverse('staff_accept_job', args=[j.id]))
        quote(j, sarah, '2800', '900', 'Open the ceiling, trace and repair the leak, repaint.')
        q = j.quotations.first()
        landlord.post(reverse('admin_review_quotation', args=[q.id]),
                      {'decision': 'rejected', 'note': 'Labour looks high for this scope. Please break it down or revise to R2000.'})

    # 4. Approved, visit confirmed, work in progress (record saved, photo still to upload)
    j, new = submit('Broken kitchen socket', 'The double socket by the stove sparks when used.', 'electrical', 'high', safety=True)
    if new:
        assign(j); mike.post(reverse('staff_accept_job', args=[j.id]))
        quote(j, mike, '420', '130', 'Replace the damaged double socket and test the circuit.')
        approve(j); visit(j, 1); start_and_record(j, mike, 'Isolated the circuit and removed the burnt socket; new socket on order.')

    # 5. Completed: tenant must say fixed / not fixed
    j, new = submit('Bedroom window will not close', 'The window latch is broken and the frame has dropped.', 'structural', 'medium')
    if new:
        assign(j); mike.post(reverse('staff_accept_job', args=[j.id]))
        quote(j, mike, '380', '120', 'Re-hang the window and replace the latch.')
        approve(j); visit(j, 1); start_and_record(j, mike, 'Re-hung the window, fitted a new latch, window now closes and locks.')
        finish(j, mike)

    # 6. Tenant verified: landlord must now pay (proof of payment) and close
    j, new = submit('Blocked bathroom drain', 'Water drains very slowly and smells.', 'plumbing', 'medium')
    if new:
        assign(j, 'contractor2'); sarah.post(reverse('staff_accept_job', args=[j.id]))
        quote(j, sarah, '350', '50', 'Clear the drain with a rod and flush the line.')
        approve(j); visit(j, 1); start_and_record(j, sarah, 'Cleared the blockage and flushed the drain; water now runs freely.')
        finish(j, sarah)
        tenant.post(reverse('verify_request', args=[j.id]))

    # 7. Emergency call-out (work may start before the quotation is approved)
    j, new = submit('Burst pipe in the corridor', 'A pipe has burst and water is spreading along the corridor.', 'plumbing', 'urgent', safety=True)
    if new:
        assign(j, emergency=True); mike.post(reverse('staff_accept_job', args=[j.id]))
        mike.post(reverse('staff_start_job', args=[j.id]))
        mike.post(reverse('staff_add_work_log', args=[j.id]), {'access_outcome': 'access_granted', 'notes': 'Isolated the water supply and clamped the burst section.'})

    # 8. No access: waiting for a return visit
    j, new = submit('Heater not warming the room', 'The wall heater switches on but stays cold.', 'hvac', 'medium')
    if new:
        assign(j, 'contractor2'); sarah.post(reverse('staff_accept_job', args=[j.id]))
        quote(j, sarah, '300', '0', 'Test the heater element and replace if faulty.')
        approve(j); visit(j, 1)
        start_and_record(j, sarah, 'Arrived at 10:00 but nobody was home and the door was locked.', outcome='no_access')

    # 9. Closed: tenant verified, contractor paid, feedback given
    j, new = submit('Front door lock replaced', 'The front door lock jams and the key breaks.', 'other', 'low')
    if new:
        assign(j); mike.post(reverse('staff_accept_job', args=[j.id]))
        quote(j, mike, '300', '250', 'Supply and fit a new cylinder lock with three keys.')
        approve(j); visit(j, 1); start_and_record(j, mike, 'Fitted a new cylinder lock and tested all three keys.')
        finish(j, mike)
        tenant.post(reverse('verify_request', args=[j.id]))
        tenant.post(reverse('submit_feedback', args=[j.id]), {'rating': '5', 'comment': 'Quick and tidy. Thank you.'})
        pay_and_close(refresh(j))


if __name__ == '__main__':
    if not User.objects.filter(username='tenant').exists():
        sys.exit('Run `python setup.py` first so the demo accounts exist.')
    stage()
    print('Demo data staged. Requests now in the system:')
    for r in MaintenanceRequest.objects.order_by('id'):
        print(f'  #{r.id:<3} {r.get_status_display():<15} {r.get_priority_display():<7} {r.title}')

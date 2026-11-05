from datetime import timedelta
import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail
from django.test import override_settings
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, Lease
from requests_app.forms import MaintenanceRequestForm, WorkLogForm
from requests_app.models import (
    Attachment,
    Feedback,
    IoTDevice,
    MaintenanceRequest,
    Notification,
    RequestStatusHistory,
    SensorReading,
    StaffNote,
    WorkLog,
    MaintenanceAppointment,
)


class BaseProjectTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = User.objects.create_user(
            username='tenant_test', email='tenant@example.com', password='testpass123',
            role='tenant', apartment_number='A101', first_name='Test', last_name='Tenant'
        )
        self.staff = User.objects.create_user(
            username='staff_test', email='staff@example.com', password='testpass123',
            role='staff', first_name='Test', last_name='Staff'
        )
        self.admin = User.objects.create_user(
            username='admin_test', email='admin@example.com', password='testpass123',
            role='admin', is_staff=True, is_superuser=True
        )
        today = timezone.localdate()
        self.lease = Lease.objects.create(
            tenant=self.tenant, tenant_email='tenant@example.com', residence='Residence A',
            unit='A101', floor='1', start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=300), invitation_code='base-test-code', verified=True,
        )

    def make_request(self, **kwargs):
        defaults = dict(
            title='Leaking tap', description='Kitchen tap is leaking.', category='plumbing',
            priority='urgent', tenant=self.tenant, apartment_number='A101',
            building='Residence A', floor='1', location_description='Kitchen'
        )
        defaults.update(kwargs)
        return MaintenanceRequest.objects.create(**defaults)

    def confirm_visit(self, obj, days=None):
        """A visit the landlord proposed and the tenant confirmed. By default it is happening now, so work may start."""
        start = timezone.now() + timedelta(days=days) if days is not None else timezone.now() - timedelta(minutes=10)
        return MaintenanceAppointment.objects.create(request=obj, proposed_by=self.admin, starts_at=start,
                                                     ends_at=start + timedelta(hours=2), status='confirmed')

    def begin_visit(self, obj):
        """Move the confirmed visit to 'now' (simulates the visit day arriving)."""
        MaintenanceAppointment.objects.filter(request=obj, status='confirmed').update(
            starts_at=timezone.now() - timedelta(minutes=10), ends_at=timezone.now() + timedelta(hours=2))

    def work_photo(self, obj, user=None):
        return Attachment.objects.create(request=obj, uploaded_by=user or self.staff, description='After repair',
                                         file=SimpleUploadedFile('after.jpg', b'\xff\xd8\xff fake jpeg', content_type='image/jpeg'))


class AuthenticationAndAccessTests(BaseProjectTestCase):
    def test_home_page_loads(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'FixIt Pro')
        self.assertNotContains(response, 'AI Assist')
        self.assertNotContains(response, 'Chatbot')

    def _new_lease(self, email='new@example.com', code='new-lease-code'):
        today = timezone.localdate()
        return Lease.objects.create(
            tenant_email=email, residence='Residence B', unit='B202', floor='2',
            start_date=today - timedelta(days=1), end_date=today + timedelta(days=200), invitation_code=code,
        )

    def _register_payload(self, **over):
        data = {
            'username': 'newtenant', 'first_name': 'New', 'last_name': 'Tenant',
            'email': 'new@example.com', 'phone_number': '0123456789',
            'invitation_code': 'new-lease-code',
            'password1': 'StrongPass123!', 'password2': 'StrongPass123!',
        }
        data.update(over)
        return data

    def test_tenant_can_register_with_lease_invitation_but_is_inactive_until_approved(self):
        lease = self._new_lease()
        response = self.client.post(reverse('register'), self._register_payload())
        self.assertRedirects(response, reverse('login'))
        user = User.objects.get(username='newtenant')
        self.assertEqual(user.role, 'tenant')
        self.assertFalse(user.is_active)
        self.assertEqual(user.apartment_number, 'B202')   # unit comes from lease, not the tenant
        lease.refresh_from_db()
        self.assertEqual(lease.tenant, user)

    def test_registration_rejected_with_wrong_code_or_email(self):
        self._new_lease()
        self.client.post(reverse('register'), self._register_payload(invitation_code='nope'))
        self.client.post(reverse('register'), self._register_payload(email='someoneelse@example.com'))
        self.assertFalse(User.objects.filter(username='newtenant').exists())

    def test_pending_tenant_cannot_login_and_sees_clear_message_then_can_after_approval(self):
        self._new_lease()
        self.client.post(reverse('register'), self._register_payload())
        response = self.client.post(reverse('login'), {'username': 'newtenant', 'password': 'StrongPass123!'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'awaiting landlord approval')
        wrong = self.client.post(reverse('login'), {'username': 'newtenant', 'password': 'wrong-password'})
        self.assertContains(wrong, 'Invalid username or password')
        self.assertNotContains(wrong, 'awaiting landlord approval')
        user = User.objects.get(username='newtenant')
        self.client.force_login(self.admin)
        self.client.post(reverse('approve_tenant', args=[user.id]), {'decision': 'approve'})
        self.client.logout()
        response = self.client.post(reverse('login'), {'username': 'newtenant', 'password': 'StrongPass123!'})
        self.assertRedirects(response, reverse('tenant_dashboard'))

    def test_admin_can_add_contractor(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('add_staff'), {
            'username': 'newcontractor', 'first_name': 'New', 'last_name': 'Contractor',
            'email': 'contractor@example.com', 'phone_number': '0820000000',
            'password1': 'StrongPass123!', 'password2': 'StrongPass123!',
        })
        self.assertTrue(User.objects.filter(username='newcontractor', role='staff').exists())

    def test_login_redirects_to_correct_portal(self):
        for user, destination in [
            (self.tenant, 'tenant_dashboard'),
            (self.staff, 'staff_dashboard'),
            (self.admin, 'admin_dashboard'),
        ]:
            self.client.logout()
            response = self.client.post(reverse('login'), {'username': user.username, 'password': 'testpass123'})
            self.assertRedirects(response, reverse(destination))

    def test_tenant_cannot_access_admin_or_staff_portals(self):
        self.client.force_login(self.tenant)
        self.assertEqual(self.client.get(reverse('admin_dashboard')).status_code, 302)

    def test_staff_cannot_access_admin_portal(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('admin_dashboard')).status_code, 302)


class RequestWorkflowTests(BaseProjectTestCase):
    def test_request_form_defaults_category_and_priority(self):
        form = MaintenanceRequestForm()
        self.assertEqual(form.initial.get('category'), 'other')
        self.assertEqual(form.initial.get('priority'), 'medium')

    def test_submit_request_page_renders_required_location_fields(self):
        self.client.force_login(self.tenant)
        response = self.client.get(reverse('submit_request'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id_location_description')
        self.assertContains(response, 'id_priority')
        self.assertNotContains(response, 'id_apartment_number')  # residence/unit come from the lease

    def test_tenant_submit_redirects_to_dashboard_with_success_message(self):
        self.client.force_login(self.tenant)
        response = self.client.post(reverse('submit_request'), {
            'title': 'Broken light', 'description': 'Bedroom light is not working.',
            'category': 'electrical', 'priority': 'urgent', 'access_permission': 'contact', 'location_description': 'Bedroom',
        }, follow=True)
        self.assertRedirects(response, reverse('tenant_dashboard'))
        self.assertContains(response, 'Request')
        self.assertContains(response, 'submitted successfully')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_tenant_submission_sends_email_to_active_admin(self):
        self.client.force_login(self.tenant)
        response = self.client.post(reverse('submit_request'), {
            'title': 'Burst pipe', 'description': 'Water is leaking under the kitchen sink.',
            'category': 'plumbing', 'priority': 'urgent', 'access_permission': 'contact', 'location_description': 'Kitchen',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.admin.email, mail.outbox[0].to)
        self.assertIn('New maintenance request', mail.outbox[0].subject)
        self.assertIn('Burst pipe', mail.outbox[0].body)

    def test_tenant_can_submit_request_and_sla_is_created(self):
        self.client.force_login(self.tenant)
        response = self.client.post(reverse('submit_request'), {
            'title': 'Broken light', 'description': 'Bedroom light is not working.',
            'category': 'electrical', 'priority': 'urgent', 'access_permission': 'contact', 'location_description': 'Bedroom',
        })
        self.assertEqual(response.status_code, 302)
        obj = MaintenanceRequest.objects.get(title='Broken light')
        self.assertEqual(obj.tenant, self.tenant)
        self.assertEqual(obj.sla_hours, 4)
        self.assertIsNotNone(obj.sla_deadline)
        self.assertTrue(RequestStatusHistory.objects.filter(request=obj, notes='Request submitted').exists())
        self.assertTrue(Notification.objects.filter(user=self.tenant, request=obj).exists())

    def test_admin_assigns_request_through_dedicated_workflow(self):
        obj = self.make_request(status='pending')
        self.client.force_login(self.admin)
        response = self.client.post(reverse('assign_request', args=[obj.id]), {'staff_id': self.staff.id})
        self.assertEqual(response.status_code, 302)
        obj.refresh_from_db()
        self.assertEqual(obj.status, 'assigned')
        self.assertEqual(obj.assigned_staff, self.staff)
        self.assertTrue(RequestStatusHistory.objects.filter(request=obj, new_status='assigned').exists())

    def test_staff_cannot_complete_before_starting_work(self):
        obj = self.make_request(status='assigned', assigned_staff=self.staff)
        self.client.force_login(self.staff)
        response = self.client.post(reverse('staff_mark_complete', args=[obj.id]), {'resolution_notes': 'Done'})
        self.assertEqual(response.status_code, 302)
        obj.refresh_from_db()
        self.assertEqual(obj.status, 'assigned')

    def test_complete_verify_feedback_and_close_workflow(self):
        obj = self.make_request(status='assigned', assigned_staff=self.staff)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(reverse('staff_accept_job', args=[obj.id])).status_code, 302)
        self.client.post(reverse('staff_start_job', args=[obj.id]))
        obj.refresh_from_db(); self.assertEqual(obj.status, 'accepted')        # blocked: tenant has not confirmed a visit
        self.confirm_visit(obj)
        self.assertEqual(self.client.post(reverse('staff_start_job', args=[obj.id])).status_code, 302)
        obj.refresh_from_db()
        self.assertEqual(obj.status, 'in_progress')
        self.assertIsNotNone(obj.started_at)

        # Simulate 2.5 hours of work without asking the technician to type times.
        obj.started_at = timezone.now() - timedelta(hours=2, minutes=30)
        obj.save(update_fields=['started_at', 'updated_at'])

        response = self.client.post(reverse('staff_add_work_log', args=[obj.id]), {
            'access_outcome': 'access_granted', 'notes': 'Replaced the leaking tap cartridge and tested the connection.'
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(WorkLog.objects.filter(request=obj, technician=self.staff).count(), 1)

        # A second work-log submission is rejected; each request has one final work log.
        self.client.post(reverse('staff_add_work_log', args=[obj.id]), {
            'access_outcome': 'access_granted', 'notes': 'This second submission must not create another work log.'
        })
        self.assertEqual(WorkLog.objects.filter(request=obj).count(), 1)

        detail = self.client.get(reverse('staff_request_detail', args=[obj.id]))
        self.assertNotContains(detail, 'Labour Cost')
        self.assertNotContains(detail, 'Approved Labour Rate')

        self.client.post(reverse('staff_add_material', args=[obj.id]), {
            'description': 'Tap cartridge', 'quantity': '1', 'unit_cost': '100.00'
        })

        self.client.post(reverse('staff_mark_complete', args=[obj.id]))
        obj.refresh_from_db(); self.assertEqual(obj.status, 'in_progress')      # blocked: no work photo yet
        self.work_photo(obj)
        self.assertEqual(self.client.post(reverse('staff_mark_complete', args=[obj.id])).status_code, 302)
        obj.refresh_from_db()
        self.assertEqual(obj.status, 'completed')
        self.assertIsNotNone(obj.completed_at)
        log = obj.work_logs.get()
        self.assertIsNotNone(log.end_time)
        self.assertEqual(obj.labor_cost, 625)
        self.assertEqual(obj.parts_cost, 100)
        self.assertEqual(obj.total_cost, 725)

        self.client.force_login(self.tenant)
        self.assertEqual(self.client.post(reverse('verify_request', args=[obj.id])).status_code, 302)
        self.assertEqual(self.client.post(reverse('submit_feedback', args=[obj.id]), {
            'rating': '5', 'comment': 'Excellent service.'
        }).status_code, 302)
        self.assertTrue(Feedback.objects.filter(request=obj, rating=5).exists())
        # Feedback is immutable from the tenant portal: a second submission does not overwrite it.
        self.client.post(reverse('submit_feedback', args=[obj.id]), {'rating': '1', 'comment': 'Changed'})
        obj.feedback.refresh_from_db()
        self.assertEqual(obj.feedback.rating, 5)
        self.assertEqual(obj.feedback.comment, 'Excellent service.')

        self.client.force_login(self.admin)
        admin_detail = self.client.get(reverse('admin_request_detail', args=[obj.id]))
        self.assertContains(admin_detail, 'R625.00')
        self.assertContains(admin_detail, 'R725.00')
        self.assertContains(admin_detail, 'Approved Labour Rate')

        self.assertEqual(self.client.post(reverse('admin_close_request', args=[obj.id])).status_code, 302)
        obj.refresh_from_db()
        self.assertEqual(obj.status, 'closed')

    def test_staff_work_log_uses_automatic_time_and_never_exposes_wage(self):
        obj = self.make_request(status='accepted', assigned_staff=self.staff)
        self.confirm_visit(obj)
        self.client.force_login(self.staff)
        self.client.post(reverse('staff_start_job', args=[obj.id]))
        response = self.client.post(reverse('staff_add_work_log', args=[obj.id]), {
            'access_outcome': 'access_granted', 'notes': 'Inspected and repaired the fitting.'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Visit record saved.')
        log = WorkLog.objects.get(request=obj)
        self.assertIsNotNone(log.start_time)
        self.assertIsNone(log.end_time)
        self.assertNotContains(response, 'Labour cost:')
        self.assertNotContains(response, 'Approved Labour Rate')

    def test_visit_record_form_has_no_time_or_wage_fields(self):
        form = WorkLogForm({'access_outcome': 'access_granted', 'notes': 'Completed the required repair and checked operation.'})
        self.assertTrue(form.is_valid())
        self.assertEqual(list(form.fields), ['access_outcome', 'notes'])   # no times, rates or money

    def test_staff_cannot_submit_work_for_another_staff_member(self):
        other_staff = User.objects.create_user(
            username='other_staff', email='other@example.com', password='testpass123', role='staff'
        )
        obj = self.make_request(status='in_progress', assigned_staff=other_staff)
        self.client.force_login(self.staff)
        response = self.client.post(reverse('staff_add_work_log', args=[obj.id]), {
            'notes': 'Unauthorised work entry must be rejected.'
        })
        self.assertEqual(response.status_code, 404)
        self.assertFalse(WorkLog.objects.filter(request=obj).exists())



class EvidenceAndNotificationTests(BaseProjectTestCase):
    def test_tenant_cannot_upload_completion_evidence(self):
        obj = self.make_request()
        self.client.force_login(self.tenant)
        upload = SimpleUploadedFile('proof.jpg', b'fake-image', content_type='image/jpeg')
        response = self.client.post(reverse('add_attachment', args=[obj.id]), {'file': upload, 'description': 'Evidence'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Attachment.objects.filter(request=obj, uploaded_by=self.tenant).exists())

    def test_notification_mark_read_requires_post(self):
        notification = Notification.objects.create(user=self.tenant, title='Test', message='Test')
        self.client.force_login(self.tenant)
        self.assertEqual(self.client.get(reverse('mark_notification_read', args=[notification.id])).status_code, 405)
        self.client.post(reverse('mark_notification_read', args=[notification.id]))
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_tenant_cannot_get_mutating_request_actions(self):
        obj = self.make_request()
        self.client.force_login(self.tenant)
        for name in ['cancel_request', 'verify_request', 'reopen_request', 'submit_feedback']:
            self.assertEqual(self.client.get(reverse(name, args=[obj.id])).status_code, 405)


class IoTIntegrationTests(BaseProjectTestCase):
    def setUp(self):
        super().setUp()
        self.device = IoTDevice.objects.create(
            sensor_id='WLS-001', name='Bathroom Water Sensor', sensor_type='water_leak',
            building='Residence A', floor='1', apartment_number='A101',
            location_description='Bathroom', default_tenant=self.tenant
        )

    def payload(self):
        return {
            'sensor_id': 'WLS-001', 'title': 'Water leak detected',
            'description': 'Moisture detected by sensor.', 'category': 'plumbing',
            'priority': 'urgent', 'value': 0.912, 'unit': 'moisture', 'alert_type': 'leak'
        }

    def test_iot_requires_api_key(self):
        response = self.client.post(reverse('iot_status'), data=json.dumps(self.payload()), content_type='application/json')
        self.assertEqual(response.status_code, 401)

    def test_iot_rejects_unknown_sensor(self):
        data = self.payload(); data['sensor_id'] = 'UNKNOWN'
        response = self.client.post(reverse('iot_status'), data=json.dumps(data), content_type='application/json', HTTP_X_IOT_API_KEY='fixit-demo-key')
        self.assertEqual(response.status_code, 404)

    def test_iot_rejects_non_numeric_reading(self):
        data = self.payload(); data['value'] = 'not-a-number'
        response = self.client.post(reverse('iot_status'), data=json.dumps(data), content_type='application/json', HTTP_X_IOT_API_KEY='fixit-demo-key')
        self.assertEqual(response.status_code, 400)

    def test_iot_creates_request_and_reading(self):
        response = self.client.post(reverse('iot_status'), data=json.dumps(self.payload()), content_type='application/json', HTTP_X_IOT_API_KEY='fixit-demo-key')
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body['success'])
        created = MaintenanceRequest.objects.get(id=body['request_id'])
        self.assertEqual(created.tenant, self.tenant)
        self.assertTrue(created.quotation_required)            # sensor requests obey the quotation rule (BR-05)
        self.assertEqual(created.lease, self.lease)            # and are linked to the tenant's lease
        self.assertTrue(SensorReading.objects.filter(id=body['reading_id'], device=self.device).exists())
        self.device.refresh_from_db()
        self.assertIsNotNone(self.device.last_seen)


class ModelValidationTests(BaseProjectTestCase):
    def test_sla_mapping(self):
        self.assertEqual(MaintenanceRequest.sla_for_priority('urgent'), 4)
        self.assertEqual(MaintenanceRequest.sla_for_priority('high'), 24)
        self.assertEqual(MaintenanceRequest.sla_for_priority('medium'), 48)
        self.assertEqual(MaintenanceRequest.sla_for_priority('low'), 120)

    def test_sla_breach_can_be_marked(self):
        obj = self.make_request()
        obj.sla_deadline = timezone.now() - timedelta(hours=1)
        obj.save(update_fields=['sla_deadline'])
        self.assertTrue(obj.mark_sla_if_breached())
        obj.refresh_from_db()
        self.assertTrue(obj.sla_breached)

    def test_attachment_form_and_feedback_models_are_related(self):
        obj = self.make_request()
        StaffNote.objects.create(request=obj, staff=self.staff, note='Inspection completed.')
        Feedback.objects.create(request=obj, submitted_by=self.tenant, rating=4, comment='Good')
        self.assertEqual(obj.notes.count(), 1)
        self.assertEqual(obj.feedback.rating, 4)


class PortalAndReportingTests(BaseProjectTestCase):
    def setUp(self):
        super().setUp()
        self.obj = self.make_request(status='accepted', assigned_staff=self.staff)

    def test_tenant_portal_pages_load(self):
        self.client.force_login(self.tenant)
        for name in ['tenant_dashboard', 'submit_request', 'notifications', 'profile']:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)
        response = self.client.get(reverse('tenant_request_detail', args=[self.obj.id]))
        self.assertEqual(response.status_code, 200)

    def test_sla_badges_are_only_shown_to_admins(self):
        self.obj.sla_breached = True
        self.obj.save(update_fields=['sla_breached'])

        self.client.force_login(self.tenant)
        tenant_page = self.client.get(reverse('tenant_dashboard'))
        self.assertNotContains(tenant_page, 'Breached requests')

        self.client.force_login(self.admin)
        admin_page = self.client.get(reverse('admin_dashboard'))
        self.assertContains(admin_page, 'Breached requests')

    def test_staff_portal_pages_load_for_assigned_request(self):
        self.client.force_login(self.staff)
        for name in ['staff_dashboard', 'my_tasks']:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)
        self.assertEqual(self.client.get(reverse('staff_request_detail', args=[self.obj.id])).status_code, 200)
        self.assertEqual(self.client.get(reverse('staff_add_note', args=[self.obj.id])).status_code, 200)

    def test_admin_portal_pages_load(self):
        self.client.force_login(self.admin)
        for name in ['admin_dashboard', 'all_requests', 'manage_staff', 'add_staff', 'reports']:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)
        self.assertEqual(self.client.get(reverse('admin_request_detail', args=[self.obj.id])).status_code, 200)
        self.assertEqual(self.client.get(reverse('assign_request', args=[self.obj.id])).status_code, 200)
        self.assertEqual(self.client.get(reverse('admin_update_request', args=[self.obj.id])).status_code, 200)

    def test_admin_can_generate_report(self):
        self.client.force_login(self.admin)
        start = (timezone.localdate() - timedelta(days=2)).isoformat()
        end = timezone.localdate().isoformat()
        response = self.client.post(reverse('generate_report'), {
            'start_date': start, 'end_date': end, 'report_type': 'detailed'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Leaking tap')

    def test_staff_can_add_note(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse('staff_add_note', args=[self.obj.id]), {'note': 'Inspected the fitting.'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(StaffNote.objects.filter(request=self.obj, staff=self.staff, note__icontains='Inspected').exists())


class LeaseLinkedAppointmentTests(BaseProjectTestCase):
    """Landlord proposes a visit; tenant confirms or asks for another time."""

    def setUp(self):
        super().setUp()
        self.obj = self.make_request(status='accepted', assigned_staff=self.staff)
        start = timezone.now() + timedelta(days=2)
        self.times = {
            'starts_at': start.strftime('%Y-%m-%dT%H:%M'),
            'ends_at': (start + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M'),
        }

    def test_admin_proposes_future_appointment(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('admin_propose_appointment', args=[self.obj.id]), self.times)
        self.assertEqual(response.status_code, 302)
        appt = MaintenanceAppointment.objects.get(request=self.obj)
        self.assertEqual(appt.status, 'proposed')   # proposed is NOT confirmed
        note = Notification.objects.get(user=self.tenant, title='Visit time proposed')
        self.assertIn(timezone.localtime(appt.starts_at).strftime('%H:%M'), note.message)
        self.assertNotIn('return visit', note.message.lower())
        from django.core import mail
        sent = [m for m in mail.outbox if self.tenant.email in m.to]
        self.assertTrue(sent and 'confirm' in sent[-1].subject.lower())
        self.client.force_login(self.tenant)
        dashboard = self.client.get(reverse('tenant_dashboard'))
        self.assertContains(dashboard, 'Visit time awaiting your response')
        self.assertContains(dashboard, 'Confirm this time')
        self.assertContains(dashboard, 'I need another time')
        self.assertContains(dashboard, timezone.localtime(appt.starts_at).strftime('%H:%M'))

    def test_past_appointment_is_rejected(self):
        self.client.force_login(self.admin)
        past = timezone.now() - timedelta(days=1)
        self.client.post(reverse('admin_propose_appointment', args=[self.obj.id]), {
            'starts_at': past.strftime('%Y-%m-%dT%H:%M'),
            'ends_at': (past + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertFalse(MaintenanceAppointment.objects.exists())

    def test_only_admin_can_propose(self):
        self.client.force_login(self.tenant)
        self.client.post(reverse('admin_propose_appointment', args=[self.obj.id]), self.times)
        self.assertFalse(MaintenanceAppointment.objects.exists())

    def test_tenant_confirms_or_requests_new_time(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_propose_appointment', args=[self.obj.id]), self.times)
        appt = MaintenanceAppointment.objects.get()
        self.client.force_login(self.tenant)
        self.client.post(reverse('respond_appointment', args=[appt.id]), {'decision': 'confirm'})
        appt.refresh_from_db()
        self.assertEqual(appt.status, 'confirmed')

        again = MaintenanceAppointment.objects.create(
            request=self.obj, proposed_by=self.admin,
            starts_at=timezone.now() + timedelta(days=3), ends_at=timezone.now() + timedelta(days=3, hours=1))
        self.client.post(reverse('respond_appointment', args=[again.id]), {'decision': 'reschedule', 'reason': 'Not home'})
        again.refresh_from_db()
        self.assertEqual((again.status, again.tenant_response), ('reschedule', 'Not home'))
        self.assertTrue(Notification.objects.filter(user=self.admin, title='Tenant asked for another visit time').exists())

    def test_other_tenant_cannot_respond(self):
        appt = MaintenanceAppointment.objects.create(
            request=self.obj, proposed_by=self.admin,
            starts_at=timezone.now() + timedelta(days=2), ends_at=timezone.now() + timedelta(days=2, hours=1))
        other = User.objects.create_user(username='other_t', password='testpass123', role='tenant')
        self.client.force_login(other)
        response = self.client.post(reverse('respond_appointment', args=[appt.id]), {'decision': 'confirm'})
        self.assertEqual(response.status_code, 404)


class CancellationAndEmergencyTests(BaseProjectTestCase):
    """Real-world rules: cancel only before work starts; emergency call-out skips quote gate."""

    def test_tenant_can_cancel_until_work_starts(self):
        for status in ('pending', 'under_review', 'assigned', 'accepted'):
            obj = self.make_request(status=status, assigned_staff=self.staff if status in ('assigned', 'accepted') else None)
            self.client.force_login(self.tenant)
            self.client.post(reverse('cancel_request', args=[obj.id]))
            obj.refresh_from_db()
            self.assertEqual(obj.status, 'cancelled', status)

    def test_tenant_cannot_cancel_once_work_started(self):
        for status in ('in_progress', 'awaiting_parts', 'completed', 'verified', 'closed'):
            obj = self.make_request(status=status, assigned_staff=self.staff)
            self.client.force_login(self.tenant)
            self.client.post(reverse('cancel_request', args=[obj.id]))
            obj.refresh_from_db()
            self.assertEqual(obj.status, status, status)

    def test_normal_job_cannot_start_without_approved_quote(self):
        obj = self.make_request(status='accepted', assigned_staff=self.staff, priority='urgent')
        obj.quotation_required = True; obj.save()
        self.client.force_login(self.staff)
        self.client.post(reverse('staff_start_job', args=[obj.id]))
        obj.refresh_from_db()
        self.assertEqual(obj.status, 'accepted')

    def test_emergency_callout_can_start_then_must_submit_quote_to_complete(self):
        obj = self.make_request(status='pending', priority='urgent')
        obj.quotation_required = True; obj.save()
        self.client.force_login(self.admin)
        self.client.post(reverse('assign_request', args=[obj.id]), {'staff_id': self.staff.id, 'emergency': 'on'})
        obj.refresh_from_db()
        self.assertTrue(obj.emergency_callout)
        obj.status = 'accepted'; obj.save()
        self.client.force_login(self.staff)
        self.client.post(reverse('staff_start_job', args=[obj.id]))
        obj.refresh_from_db()
        self.assertEqual(obj.status, 'in_progress')           # started with no approved quote
        self.assertTrue(obj.quote_blocks_completion(self.staff))   # but a quote must follow

    def test_emergency_flag_only_applies_to_urgent_requests(self):
        obj = self.make_request(status='pending', priority='medium')
        self.client.force_login(self.admin)
        self.client.post(reverse('assign_request', args=[obj.id]), {'staff_id': self.staff.id, 'emergency': 'on'})
        obj.refresh_from_db()
        self.assertFalse(obj.emergency_callout)


class VisitRecordPaymentAndReworkTests(BaseProjectTestCase):
    """Contractor visit / access record, calculated payments, single appointment, same-contractor rework."""

    def setUp(self):
        super().setUp()
        from requests_app.models import ContractorQuotation, ContractorPayment
        self.Quote, self.Payment = ContractorQuotation, ContractorPayment
        self.obj = self.make_request(status='accepted', assigned_staff=self.staff, priority='medium')
        self.obj.quotation_required = True
        self.obj.save()
        self.quote = ContractorQuotation.objects.create(
            request=self.obj, contractor=self.staff, scope='Replace tap cartridge', labour_amount='500.00',
            estimated_materials='200.00', estimated_hours='2', status='approved', approved_at=timezone.now())
        self.future = timezone.now() + timedelta(days=2)
        self.times = {'starts_at': self.future.strftime('%Y-%m-%dT%H:%M'), 'ends_at': (self.future + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M')}

    # ---- appointments: one confirmed visit at a time
    def test_confirmed_appointment_blocks_any_new_proposal(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_propose_appointment', args=[self.obj.id]), self.times)
        appt = MaintenanceAppointment.objects.get()
        self.client.force_login(self.tenant)
        self.client.post(reverse('respond_appointment', args=[appt.id]), {'decision': 'confirm'})
        later = self.future + timedelta(days=1)
        t2 = {'starts_at': later.strftime('%Y-%m-%dT%H:%M'), 'ends_at': (later + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M')}
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_propose_appointment', args=[self.obj.id]), t2)
        self.client.force_login(self.staff)
        self.client.post(reverse('staff_offer_availability', args=[self.obj.id]), dict(t2, note='Another time please'))
        self.assertEqual(MaintenanceAppointment.objects.count(), 1)

    def test_unanswered_proposal_is_replaced_and_reschedule_allows_a_new_one(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_propose_appointment', args=[self.obj.id]), self.times)
        self.client.post(reverse('admin_propose_appointment', args=[self.obj.id]), self.times)
        self.assertEqual(MaintenanceAppointment.objects.filter(status='proposed').count(), 1)
        appt = MaintenanceAppointment.objects.get(status='proposed')
        self.client.force_login(self.tenant)
        self.client.post(reverse('respond_appointment', args=[appt.id]), {'decision': 'reschedule', 'reason': 'Not home'})
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_propose_appointment', args=[self.obj.id]), self.times)
        self.assertTrue(MaintenanceAppointment.objects.filter(status='proposed').exists())

    def test_appointment_panels_render_in_the_page_body_not_the_title(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_propose_appointment', args=[self.obj.id]), self.times)
        body = self.client.get(reverse('admin_request_detail', args=[self.obj.id])).content.decode()
        self.assertNotIn('<section class="container card p-3 my-3"><h5>Propose', body)
        self.assertIn('Maintenance visits', body.split('</head>')[1])
        self.client.force_login(self.tenant)
        page = self.client.get(reverse('tenant_request_detail', args=[self.obj.id])).content.decode()
        self.assertNotIn('<title>Request #%d - FixIt Pro<section' % self.obj.id, page)
        self.assertIn('I am available: confirm', page.split('</head>')[1])

    # ---- visit record
    def test_visit_record_not_allowed_before_work_starts(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('staff_add_work_log', args=[self.obj.id]), {'access_outcome': 'access_granted', 'notes': 'Trying to record before starting'})
        self.assertFalse(WorkLog.objects.exists())

    def _start(self):
        if not self.obj.confirmed_appointment:
            self.confirm_visit(self.obj)
        self.client.force_login(self.staff)
        self.client.post(reverse('staff_start_job', args=[self.obj.id]))
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.status, 'in_progress')

    def test_cannot_complete_without_visit_record_and_one_record_only_but_editable(self):
        self._start()
        self.client.post(reverse('staff_mark_complete', args=[self.obj.id]))
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'in_progress')       # blocked: no record
        data = {'access_outcome': 'access_granted', 'notes': 'Replaced the cartridge and tested.'}
        self.client.post(reverse('staff_add_work_log', args=[self.obj.id]), data)
        self.client.post(reverse('staff_add_work_log', args=[self.obj.id]), dict(data, notes='A second record must be refused.'))
        self.assertEqual(WorkLog.objects.count(), 1)
        self.client.post(reverse('staff_edit_work_log', args=[self.obj.id]), dict(data, notes='Edited: replaced cartridge, tested twice.'))
        self.assertEqual(WorkLog.objects.get().notes, 'Edited: replaced cartridge, tested twice.')
        self.client.post(reverse('staff_mark_complete', args=[self.obj.id]))                # blocked: no work photo
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'in_progress')
        self.work_photo(self.obj)
        self.client.post(reverse('staff_mark_complete', args=[self.obj.id]))                # no resolution notes needed
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.status, 'completed')
        self.assertEqual(self.obj.resolution_notes, 'Edited: replaced cartridge, tested twice.')
        self.client.post(reverse('staff_edit_work_log', args=[self.obj.id]), dict(data, notes='Edit after completion must fail.'))
        self.assertNotEqual(WorkLog.objects.get().notes, 'Edit after completion must fail.')

    def test_no_access_record_blocks_completion_until_corrected_after_return_visit(self):
        self._start()
        self.client.post(reverse('staff_add_work_log', args=[self.obj.id]), {'access_outcome': 'no_access', 'notes': 'Tenant was not home.'})
        self.client.post(reverse('staff_mark_complete', args=[self.obj.id]))
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'in_progress')
        # the landlord and tenant are told, and the record cannot simply be flipped back
        self.assertTrue(Notification.objects.filter(user=self.admin, title='No access: new visit needed').exists())
        self.assertTrue(Notification.objects.filter(user=self.tenant, title='We could not get access').exists())
        self.client.post(reverse('staff_edit_work_log', args=[self.obj.id]), {'access_outcome': 'access_granted', 'notes': 'Claiming access without a new visit.'})
        self.assertEqual(WorkLog.objects.get().access_outcome, 'no_access')
        # tenant-confirmed return visit, then the contractor can update the record
        self.confirm_visit(self.obj)
        self.client.post(reverse('staff_edit_work_log', args=[self.obj.id]), {'access_outcome': 'access_granted', 'notes': 'Returned, fixed the tap.'})
        self.work_photo(self.obj)
        self.client.post(reverse('staff_mark_complete', args=[self.obj.id]))
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'completed')
        self.assertEqual(MaintenanceAppointment.objects.filter(status='attended').count(), 1)
        self.assertEqual(MaintenanceAppointment.objects.filter(status='no_access').count(), 1)

    def test_visit_record_marks_confirmed_appointment_attended(self):
        appt = self.confirm_visit(self.obj)
        self._start()
        self.client.post(reverse('staff_add_work_log', args=[self.obj.id]), {'access_outcome': 'access_granted', 'notes': 'All done and tested.'})
        appt.refresh_from_db(); self.assertEqual(appt.status, 'attended')

    # ---- materials and cost
    def test_materials_not_re_entered_when_quotation_approved(self):
        self._start()
        self.client.post(reverse('staff_add_material', args=[self.obj.id]), {'description': 'Cartridge', 'quantity': '1', 'unit_cost': '999'})
        self.assertFalse(self.obj.materials.exists())
        page = self.client.get(reverse('staff_request_detail', args=[self.obj.id])).content.decode()
        self.assertNotIn('Materials / Parts Used', page)
        self.assertNotIn('resolution_notes', page)

    def test_costs_come_from_the_approved_quotation(self):
        self.obj.recalculate_costs(); self.obj.refresh_from_db()
        self.assertEqual((self.obj.labor_cost, self.obj.parts_cost, self.obj.total_cost), (500, 200, 700))

    # ---- payments
    def _complete(self):
        self._start()
        self.client.post(reverse('staff_add_work_log', args=[self.obj.id]), {'access_outcome': 'access_granted', 'notes': 'Replaced the cartridge.'})
        self.work_photo(self.obj)
        self.client.post(reverse('staff_mark_complete', args=[self.obj.id]))
        self.obj.refresh_from_db()

    def _verify(self):
        self.client.force_login(self.tenant)
        self.client.post(reverse('verify_request', args=[self.obj.id]))
        self.obj.refresh_from_db()

    def _proof(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile('proof.pdf', b'%PDF-1.4 proof', content_type='application/pdf')

    def test_payment_amount_is_calculated_and_proof_is_required(self):
        self._complete(); self._verify()
        self.client.force_login(self.admin)
        url = reverse('admin_record_payment', args=[self.obj.id])
        self.client.post(url, {'payment_date': timezone.localdate().isoformat()})            # no proof -> refused
        self.assertFalse(self.Payment.objects.exists())
        self.client.post(url, {'payment_date': timezone.localdate().isoformat(), 'proof': self._proof(), 'amount': '1'})
        pay = self.Payment.objects.get()
        self.assertEqual(str(pay.amount), '700.00')            # 500 labour + 200 materials; a typed amount is ignored
        self.assertTrue(pay.reference.startswith('PAY-'))
        self.client.post(url, {'payment_date': timezone.localdate().isoformat(), 'proof': self._proof()})
        self.assertEqual(self.Payment.objects.count(), 1)      # already paid in full

    def test_disputed_payment_makes_the_amount_due_again(self):
        self._complete(); self._verify()
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_record_payment', args=[self.obj.id]), {'payment_date': timezone.localdate().isoformat(), 'proof': self._proof()})
        pay = self.Payment.objects.get()
        self.client.force_login(self.staff)
        self.client.post(reverse('staff_acknowledge_payment', args=[pay.id]), {'decision': 'disputed', 'comment': 'Not received'})
        self.obj.refresh_from_db()
        self.assertEqual(str(self.obj.amount_due), '700.00')

    def test_admin_page_shows_contractor_payments_only_once(self):
        self._complete(); self._verify()
        self.client.force_login(self.admin)
        page = self.client.get(reverse('admin_request_detail', args=[self.obj.id])).content.decode()
        self.assertEqual(page.count('Contractor payments</h5>'), 1)
        self.assertEqual(page.count('action="%s"' % reverse('admin_record_payment', args=[self.obj.id])), 1)

    # ---- not fixed: same contractor returns
    def test_not_fixed_keeps_same_contractor_and_landlord_must_alert_them(self):
        self._complete()
        other = User.objects.create_user(username='other_c', email='o@example.com', password='testpass123', role='staff')
        before = Notification.objects.filter(user=self.staff).count()
        self.client.force_login(self.tenant)
        self.client.post(reverse('reopen_request', args=[self.obj.id]), {'reason': 'Still dripping'})
        self.obj.refresh_from_db()
        self.assertEqual((self.obj.status, self.obj.assigned_staff_id, self.obj.rework_count), ('reopened', self.staff.id, 1))
        self.assertTrue(Notification.objects.filter(user=self.admin).exists())              # landlord notified
        self.assertEqual(Notification.objects.filter(user=self.staff).count(), before)      # contractor NOT told directly
        # landlord cannot hand it to someone else
        self.client.force_login(self.admin)
        self.client.post(reverse('assign_request', args=[self.obj.id]), {'staff_id': other.id})
        self.obj.refresh_from_db(); self.assertEqual(self.obj.assigned_staff_id, self.staff.id)
        # landlord alerts the same contractor
        self.client.post(reverse('admin_alert_contractor', args=[self.obj.id]))
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'assigned')
        self.assertTrue(Notification.objects.filter(user=self.staff, title='Return visit required').exists())

    def test_return_visit_needs_tenant_confirmation_and_a_fresh_visit_record(self):
        self._complete()
        self.client.force_login(self.tenant); self.client.post(reverse('reopen_request', args=[self.obj.id]))
        self.client.force_login(self.admin); self.client.post(reverse('admin_alert_contractor', args=[self.obj.id]))
        self.client.force_login(self.staff)
        self.client.post(reverse('staff_accept_job', args=[self.obj.id]))
        # the contractor can only OFFER availability to the landlord; nothing reaches the tenant yet
        self.client.post(reverse('staff_offer_availability', args=[self.obj.id]), dict(self.times, note='Parts arrive Friday'))
        offer = MaintenanceAppointment.objects.get(status='availability')
        self.assertEqual((offer.status, offer.proposed_by_id), ('availability', self.staff.id))
        # cannot start: the tenant has not confirmed anything
        self.client.post(reverse('staff_start_job', args=[self.obj.id]))
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'accepted')
        # landlord relays it to the tenant
        self.client.force_login(self.admin)
        self.client.post(reverse('admin_relay_availability', args=[offer.id]))
        appt = MaintenanceAppointment.objects.get(status='proposed')
        self.assertEqual((appt.status, appt.proposed_by_id), ('proposed', self.admin.id))
        self.assertTrue(Notification.objects.filter(user=self.tenant, title='Visit time proposed').exists())
        self.client.force_login(self.tenant)
        self.client.post(reverse('respond_appointment', args=[appt.id]), {'decision': 'confirm'})
        appt.refresh_from_db(); self.assertEqual(appt.status, 'confirmed')
        self.begin_visit(self.obj)
        self.client.force_login(self.staff)
        self.client.post(reverse('staff_start_job', args=[self.obj.id]))
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'in_progress')
        # round 1 needs its own record; the old one does not count
        self.client.post(reverse('staff_mark_complete', args=[self.obj.id]))
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'in_progress')
        self.client.post(reverse('staff_add_work_log', args=[self.obj.id]), {'access_outcome': 'access_granted', 'notes': 'Re-sealed the tap, no more drips.'})
        self.client.post(reverse('staff_mark_complete', args=[self.obj.id]))
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'in_progress')   # the OLD photo does not count for the return visit
        self.work_photo(self.obj)
        self.client.post(reverse('staff_mark_complete', args=[self.obj.id]))
        self.obj.refresh_from_db()
        self.assertEqual((self.obj.status, WorkLog.objects.count()), ('completed', 2))
        appt.refresh_from_db(); self.assertEqual(appt.status, 'attended')

    def test_decline_still_lets_landlord_pick_a_new_contractor(self):
        job = self.make_request(status='assigned', assigned_staff=self.staff)
        other = User.objects.create_user(username='other_c2', email='o2@example.com', password='testpass123', role='staff')
        self.client.force_login(self.staff)
        self.client.post(reverse('staff_reject_job', args=[job.id]), {'reason': 'Cannot do this job'})
        job.refresh_from_db(); self.assertIsNone(job.assigned_staff_id)
        self.client.force_login(self.admin)
        self.client.post(reverse('assign_request', args=[job.id]), {'staff_id': other.id})
        job.refresh_from_db(); self.assertEqual(job.assigned_staff_id, other.id)


class PasswordResetTests(BaseProjectTestCase):
    """A registered tenant who forgets their password can set a new one by email."""

    def _request_link(self, email='tenant@example.com'):
        import re
        from django.core import mail
        mail.outbox.clear()
        response = self.client.post(reverse('password_reset'), {'email': email})
        self.assertRedirects(response, reverse('password_reset_done'))
        if not mail.outbox:
            return None
        match = re.search(r'/password/reset/[^\s/]+/[^\s/]+/', mail.outbox[0].body)
        return match.group(0)

    def test_forgot_password_page_is_linked_from_login_and_loads(self):
        self.assertContains(self.client.get(reverse('login')), reverse('password_reset'))
        self.assertEqual(self.client.get(reverse('password_reset')).status_code, 200)

    def test_full_reset_flow_gives_a_working_new_password_and_blocks_the_old_one(self):
        from django.core import mail
        link = self._request_link()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['tenant@example.com'])
        self.assertIn(self.tenant.username, mail.outbox[0].body)           # also reminds them of their username
        page = self.client.get(link, follow=True)
        self.assertContains(page, 'new_password1')
        set_url = page.request['PATH_INFO']
        done = self.client.post(set_url, {'new_password1': 'Br@ndNewPass2026', 'new_password2': 'Br@ndNewPass2026'})
        self.assertRedirects(done, reverse('password_reset_complete'))
        self.client.logout()
        old = self.client.post(reverse('login'), {'username': 'tenant_test', 'password': 'testpass123'})
        self.assertContains(old, 'Invalid username or password')
        new = self.client.post(reverse('login'), {'username': 'tenant_test', 'password': 'Br@ndNewPass2026'})
        self.assertRedirects(new, reverse('tenant_dashboard'))

    def test_reset_link_works_only_once(self):
        link = self._request_link()
        set_url = self.client.get(link, follow=True).request['PATH_INFO']
        self.client.post(set_url, {'new_password1': 'Br@ndNewPass2026', 'new_password2': 'Br@ndNewPass2026'})
        again = self.client.get(link, follow=True)
        self.assertNotContains(again, 'new_password1')
        self.assertContains(again, 'invalid, has already been used, or has expired')

    def test_weak_new_password_is_rejected(self):
        link = self._request_link()
        set_url = self.client.get(link, follow=True).request['PATH_INFO']
        response = self.client.post(set_url, {'new_password1': '12345', 'new_password2': '12345'})
        self.assertEqual(response.status_code, 200)                      # stays on the form with errors
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.check_password('testpass123'))

    def test_unknown_email_gives_same_page_and_sends_nothing(self):
        from django.core import mail
        self.assertIsNone(self._request_link('nobody@nowhere.com'))
        self.assertEqual(len(mail.outbox), 0)

    def test_tenant_awaiting_approval_cannot_reset_password(self):
        User.objects.create_user(username='pending_t', email='pending@example.com', password='testpass123', role='tenant', is_active=False)
        self.assertIsNone(self._request_link('pending@example.com'))

    def test_tampered_link_is_rejected(self):
        link = self._request_link()
        bad = link[:-3] + 'xyz/'
        self.assertContains(self.client.get(bad, follow=True), 'invalid, has already been used, or has expired')

    def test_expired_link_is_rejected(self):
        from django.test import override_settings
        link = self._request_link()
        with override_settings(PASSWORD_RESET_TIMEOUT=-1):
            self.assertContains(self.client.get(link, follow=True), 'invalid, has already been used, or has expired')


class NonFunctionalAndSecurityTests(BaseProjectTestCase):
    """Verification of the non-functional requirements: security, validation, uploads, reliability, performance."""

    def _submit_payload(self, **extra):
        data = {'title': 'Leaking tap', 'description': 'The kitchen tap is leaking badly.', 'category': 'plumbing', 'priority': 'high',
                'access_permission': 'contact', 'location_description': 'Kitchen'}
        data.update(extra)
        return data

    # ---- NFR security / authentication
    def test_passwords_are_stored_hashed(self):
        self.assertTrue(self.tenant.password.startswith('pbkdf2_'))
        self.assertNotIn('testpass123', self.tenant.password)

    def test_csrf_token_is_enforced_on_state_changing_requests(self):
        strict = Client(enforce_csrf_checks=True)
        self.assertEqual(strict.post(reverse('login'), {'username': 'tenant_test', 'password': 'testpass123'}).status_code, 403)

    def test_anonymous_users_are_redirected_to_login_from_protected_pages(self):
        obj = self.make_request()
        for url in (reverse('tenant_dashboard'), reverse('tenant_request_detail', args=[obj.id]), reverse('admin_dashboard'),
                    reverse('all_requests'), reverse('my_tasks'), reverse('staff_request_detail', args=[obj.id])):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertIn(reverse('login'), response['Location'])

    def test_tenant_cannot_open_another_tenants_request(self):
        obj = self.make_request()
        other = User.objects.create_user(username='other_tenant', password='testpass123', role='tenant')
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('tenant_request_detail', args=[obj.id])).status_code, 404)

    # ---- NFR validation / uploads
    def test_oversized_request_photo_is_rejected(self):
        self.client.force_login(self.tenant)
        big = SimpleUploadedFile('big.png', b'\x89PNG' + b'0' * (6 * 1024 * 1024), content_type='image/png')
        before = MaintenanceRequest.objects.count()
        response = self.client.post(reverse('submit_request'), self._submit_payload(photo=big))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MaintenanceRequest.objects.count(), before)

    def test_non_image_request_photo_is_rejected(self):
        self.client.force_login(self.tenant)
        fake = SimpleUploadedFile('virus.png', b'this is not an image', content_type='image/png')
        before = MaintenanceRequest.objects.count()
        self.client.post(reverse('submit_request'), self._submit_payload(photo=fake))
        self.assertEqual(MaintenanceRequest.objects.count(), before)

    def test_missing_required_request_fields_are_rejected_with_errors(self):
        self.client.force_login(self.tenant)
        before = MaintenanceRequest.objects.count()
        response = self.client.post(reverse('submit_request'), {'title': '', 'description': ''})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MaintenanceRequest.objects.count(), before)
        self.assertContains(response, 'This field is required')

    def test_payment_proof_of_wrong_type_is_rejected(self):
        from requests_app.models import ContractorQuotation, ContractorPayment
        job = self.make_request(status='verified', assigned_staff=self.staff)
        job.quotation_required = True; job.save()
        ContractorQuotation.objects.create(request=job, contractor=self.staff, scope='Fix', labour_amount='100', estimated_materials='50',
                                           estimated_hours='1', status='approved', approved_at=timezone.now())
        self.client.force_login(self.admin)
        bad = SimpleUploadedFile('proof.exe', b'MZ binary', content_type='application/octet-stream')
        self.client.post(reverse('admin_record_payment', args=[job.id]), {'payment_date': timezone.localdate().isoformat(), 'proof': bad})
        self.assertFalse(ContractorPayment.objects.exists())

    # ---- NFR reliability / data integrity
    def test_email_failure_does_not_stop_a_request_being_saved(self):
        from unittest import mock
        self.client.force_login(self.tenant)
        before = MaintenanceRequest.objects.count()
        with mock.patch('requests_app.services.send_mail', side_effect=OSError('SMTP server down')):
            response = self.client.post(reverse('submit_request'), self._submit_payload())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(MaintenanceRequest.objects.count(), before + 1)

    def test_invalid_lifecycle_transition_is_refused(self):
        closed = self.make_request(status='closed')
        self.assertFalse(closed.is_transition_allowed('in_progress'))
        self.assertFalse(self.make_request(status='pending').is_transition_allowed('completed'))
        self.assertTrue(self.make_request(status='completed').is_transition_allowed('verified'))

    def test_database_allows_only_one_visit_record_per_visit_round(self):
        from django.core.exceptions import ValidationError
        from django.db import IntegrityError, transaction
        job = self.make_request(status='in_progress', assigned_staff=self.staff)
        fields = dict(request=job, technician=self.staff, work_date=timezone.localdate(), start_time='09:00', hourly_rate=0, notes='First visit record', visit_round=0)
        WorkLog.objects.create(**fields)
        with self.assertRaises((IntegrityError, ValidationError)), transaction.atomic():   # model validation or the DB constraint
            WorkLog.objects.create(**dict(fields, notes='Duplicate for the same round'))
        self.assertEqual(WorkLog.objects.filter(request=job).count(), 1)

    # ---- NFR performance (target: every normal page under 3 seconds with realistic data)
    def test_normal_pages_respond_within_three_seconds(self):
        import time
        for i in range(30):
            self.make_request(title=f'Request {i}', status='pending')
        pages = [(self.tenant, reverse('tenant_dashboard')), (self.tenant, reverse('submit_request')),
                 (self.admin, reverse('admin_dashboard')), (self.admin, reverse('all_requests')),
                 (self.admin, reverse('admin_request_detail', args=[MaintenanceRequest.objects.first().id])),
                 (self.staff, reverse('staff_dashboard'))]
        slowest = 0
        for user, url in pages:
            self.client.force_login(user)
            start = time.perf_counter()
            response = self.client.get(url)
            elapsed = time.perf_counter() - start
            slowest = max(slowest, elapsed)
            self.assertEqual(response.status_code, 200, url)
            self.assertLess(elapsed, 3.0, f'{url} took {elapsed:.2f}s')


class WorkflowRuleTests(BaseProjectTestCase):
    """Rules added after the lecturer-style walk-through: visits, quotations, no-access, closure, safety risk."""

    def setUp(self):
        super().setUp()
        from requests_app.models import ContractorQuotation, ContractorPayment
        self.Quote, self.Payment = ContractorQuotation, ContractorPayment
        self.obj = self.make_request(status='accepted', assigned_staff=self.staff, priority='medium', quotation_required=True)
        self.future = timezone.now() + timedelta(days=2)
        self.times = {'starts_at': self.future.strftime('%Y-%m-%dT%H:%M'), 'ends_at': (self.future + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M')}

    def approve_quote(self, labour='500.00', materials='200.00'):
        return self.Quote.objects.create(request=self.obj, contractor=self.staff, scope='Replace tap cartridge', labour_amount=labour,
                                         estimated_materials=materials, status='approved', approved_at=timezone.now())

    def login(self, user):
        self.client.force_login(user)

    # ---- who proposes visits
    def test_contractor_availability_on_first_visit_is_only_an_offer_to_the_landlord(self):
        self.login(self.staff)
        self.client.post(reverse('staff_offer_availability', args=[self.obj.id]), self.times)
        self.assertEqual(MaintenanceAppointment.objects.get().status, 'availability')   # an offer, not a visit
        from requests_app.services import propose_visit
        ok, _ = propose_visit(self.staff, self.obj, self.future, self.future + timedelta(hours=1))
        self.assertFalse(ok)

    def test_contractor_availability_goes_to_landlord_never_straight_to_tenant(self):
        self.obj.rework_count = 1; self.obj.save()
        self.login(self.staff)
        self.client.post(reverse('staff_offer_availability', args=[self.obj.id]), dict(self.times, note='After lunch'))
        offer = MaintenanceAppointment.objects.get()
        self.assertEqual(offer.status, 'availability')
        self.assertTrue(Notification.objects.filter(user=self.admin, title='Contractor availability offered').exists())
        self.assertFalse(Notification.objects.filter(user=self.tenant, title__contains='proposed').exists())
        self.login(self.admin)
        dashboard = self.client.get(reverse('admin_dashboard'))
        self.assertContains(dashboard, 'Contractor availability received')
        self.assertContains(dashboard, 'Review and send to tenant')
        self.assertContains(dashboard, reverse('admin_request_detail', args=[self.obj.id]))
        self.assertContains(self.client.get(reverse('notifications')), 'Review request')
        self.assertContains(self.client.get(reverse('admin_request_detail', args=[self.obj.id])), 'Availability received.')
        self.login(self.tenant)                                         # the tenant does not even see the offer
        self.assertNotContains(self.client.get(reverse('tenant_request_detail', args=[self.obj.id])), 'After lunch')

    # ---- start rules
    def test_work_cannot_start_until_tenant_confirms_a_visit(self):
        self.approve_quote()
        self.login(self.admin)
        self.client.post(reverse('admin_propose_appointment', args=[self.obj.id]), self.times)
        self.login(self.staff)
        self.client.post(reverse('staff_start_job', args=[self.obj.id]))
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'accepted')          # proposed is not confirmed
        page = self.client.get(reverse('staff_request_detail', args=[self.obj.id]))
        self.assertContains(page, 'Waiting for the tenant to confirm a visit time')
        appt = MaintenanceAppointment.objects.get()
        self.login(self.tenant)
        self.client.post(reverse('respond_appointment', args=[appt.id]), {'decision': 'confirm'})
        self.assertTrue(Notification.objects.filter(user=self.staff, title__startswith='Visit confirmed').exists())
        self.login(self.staff)
        self.client.post(reverse('staff_start_job', args=[self.obj.id]))
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'accepted')          # confirmed, but the visit is 2 days away
        self.assertContains(self.client.get(reverse('staff_request_detail', args=[self.obj.id])), 'You can start from 30 minutes before')
        self.begin_visit(self.obj)
        self.client.post(reverse('staff_start_job', args=[self.obj.id]))
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'in_progress')

    def test_emergency_callout_may_start_without_a_confirmed_visit(self):
        self.obj.emergency_callout = True; self.obj.save()
        self.login(self.staff)
        self.client.post(reverse('staff_start_job', args=[self.obj.id]))
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'in_progress')

    def test_rejected_visit_then_new_proposal_must_be_confirmed(self):
        self.approve_quote()
        self.login(self.admin)
        self.client.post(reverse('admin_propose_appointment', args=[self.obj.id]), self.times)
        first = MaintenanceAppointment.objects.get()
        self.login(self.tenant)
        self.client.post(reverse('respond_appointment', args=[first.id]), {'decision': 'reschedule', 'reason': ''})   # reason required
        first.refresh_from_db(); self.assertEqual(first.status, 'proposed')
        self.client.post(reverse('respond_appointment', args=[first.id]), {'decision': 'reschedule', 'reason': 'Free after 14:00'})
        first.refresh_from_db(); self.assertEqual((first.status, first.tenant_response), ('reschedule', 'Free after 14:00'))
        self.assertTrue(RequestStatusHistory.objects.filter(request=self.obj, notes__contains='Free after 14:00').exists())
        self.assertContains(self.client.get(reverse('tenant_request_detail', args=[self.obj.id])), 'The landlord will propose a new time')
        self.login(self.admin)
        self.assertContains(self.client.get(reverse('admin_request_detail', args=[self.obj.id])), 'cannot make the proposed time')
        self.login(self.staff)
        self.client.post(reverse('staff_start_job', args=[self.obj.id]))
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'accepted')          # still blocked
        self.login(self.admin)
        self.client.post(reverse('admin_propose_appointment', args=[self.obj.id]), self.times)
        second = MaintenanceAppointment.objects.get(status='proposed')
        self.login(self.tenant)
        self.client.post(reverse('respond_appointment', args=[second.id]), {'decision': 'confirm'})
        self.begin_visit(self.obj)
        self.login(self.staff)
        self.client.post(reverse('staff_start_job', args=[self.obj.id]))
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'in_progress')

    # ---- tenant Actions card
    def test_tenant_card_text_matches_the_status(self):
        self.login(self.tenant)
        url = reverse('tenant_request_detail', args=[self.obj.id])
        self.obj.status = 'verified'; self.obj.save()
        page = self.client.get(url).content.decode()
        self.assertIn('You confirmed the repair is fixed', page)
        self.assertNotIn('Work is under way', page)
        self.obj.status = 'in_progress'; self.obj.save()
        self.assertIn('Work is under way', self.client.get(url).content.decode())

    # ---- reopening
    def test_closed_request_can_be_reopened_for_seven_days_only(self):
        self.obj.status = 'closed'; self.obj.closed_at = timezone.now() - timedelta(days=3); self.obj.save()
        self.login(self.tenant)
        self.client.post(reverse('reopen_request', args=[self.obj.id]), {'reason': 'Leaking again'})
        self.obj.refresh_from_db()
        self.assertEqual((self.obj.status, self.obj.rework_count, self.obj.assigned_staff_id), ('reopened', 1, self.staff.id))
        late = self.make_request(status='closed', assigned_staff=self.staff, closed_at=timezone.now() - timedelta(days=8))
        self.client.post(reverse('reopen_request', args=[late.id]), {'reason': 'Too late'})
        late.refresh_from_db(); self.assertEqual(late.status, 'closed')

    def test_tenant_cannot_reopen_a_job_that_is_not_finished(self):
        self.login(self.tenant)
        self.client.post(reverse('reopen_request', args=[self.obj.id]), {'reason': 'x'})
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'accepted')

    # ---- closing needs payment
    def test_request_cannot_be_closed_until_the_contractor_is_paid(self):
        self.approve_quote()
        self.obj.status = 'verified'; self.obj.save()
        self.login(self.admin)
        self.client.post(reverse('admin_close_request', args=[self.obj.id]))
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'verified')
        self.assertIn('R700.00', self.obj.close_blocker())
        proof = SimpleUploadedFile('proof.pdf', b'%PDF-1.4 proof', content_type='application/pdf')
        self.client.post(reverse('admin_record_payment', args=[self.obj.id]), {'payment_date': timezone.localdate().isoformat(), 'proof': proof})
        self.client.post(reverse('admin_close_request', args=[self.obj.id]))
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'closed')

    def test_payment_form_is_hidden_until_the_tenant_verifies(self):
        self.approve_quote()
        self.obj.status = 'completed'; self.obj.save()
        self.login(self.admin)
        page = self.client.get(reverse('admin_request_detail', args=[self.obj.id])).content.decode()
        self.assertNotIn(reverse('admin_record_payment', args=[self.obj.id]), page)
        proof = SimpleUploadedFile('proof.pdf', b'%PDF-1.4 proof', content_type='application/pdf')
        self.client.post(reverse('admin_record_payment', args=[self.obj.id]), {'payment_date': timezone.localdate().isoformat(), 'proof': proof})
        self.assertFalse(self.Payment.objects.exists())

    def test_cost_information_is_hidden_until_a_quotation_is_approved(self):
        self.login(self.admin)
        page = self.client.get(reverse('admin_request_detail', args=[self.obj.id])).content.decode()
        self.assertNotIn('Cost Information', page)
        self.assertNotIn('Update Rate', page)
        self.assertNotIn('/hour', page)
        self.approve_quote()
        self.assertIn('Cost Information', self.client.get(reverse('admin_request_detail', args=[self.obj.id])).content.decode())
        edit = self.client.get(reverse('admin_update_request', args=[self.obj.id])).content.decode()
        self.assertNotIn('Labour Rate', edit)

    # ---- safety risk
    def test_safety_risk_raises_priority_and_alerts_the_landlord(self):
        self.login(self.tenant)
        data = {'title': 'Exposed wires', 'description': 'Live wires hanging from the ceiling in the bedroom.', 'category': 'electrical',
                'priority': 'low', 'access_permission': 'contact', 'location_description': 'Bedroom', 'safety_risk': 'on'}
        mail.outbox.clear()
        self.client.post(reverse('submit_request'), data)
        job = MaintenanceRequest.objects.get(title='Exposed wires')
        self.assertEqual(job.priority, 'high')
        self.assertEqual(job.sla_hours, 24)
        self.assertTrue(RequestStatusHistory.objects.filter(request=job, notes__contains='SAFETY RISK').exists())
        self.assertTrue(Notification.objects.filter(user=self.admin, title__startswith='SAFETY RISK').exists())
        self.assertTrue(any(m.subject.startswith('SAFETY RISK') for m in mail.outbox))
        self.login(self.admin)
        self.assertContains(self.client.get(reverse('admin_dashboard')), 'Exposed wires')
        self.assertContains(self.client.get(reverse('admin_request_detail', args=[job.id])), 'Safety risk reported by the tenant')

    def test_ordinary_request_keeps_the_priority_the_tenant_chose(self):
        self.login(self.tenant)
        data = {'title': 'Squeaky door', 'description': 'The bedroom door squeaks every time.', 'category': 'other', 'priority': 'low',
                'access_permission': 'contact', 'location_description': 'Bedroom'}
        self.client.post(reverse('submit_request'), data)
        self.assertEqual(MaintenanceRequest.objects.get(title='Squeaky door').priority, 'low')

    # ---- quotations
    def _submit_quote(self, **over):
        data = {'scope': 'Replace the leaking tap and test it', 'labour_amount': '450', 'estimated_materials': '100', 'estimated_hours': ''}
        data.update(over)
        self.login(self.staff)
        return self.client.post(reverse('staff_submit_quotation', args=[self.obj.id]), data)

    def test_quotation_hours_are_optional_and_any_number_is_accepted(self):
        self._submit_quote()
        self.assertEqual(self.Quote.objects.get().estimated_hours, None)
        self.Quote.objects.all().delete()
        self._submit_quote(estimated_hours='3.7', estimated_materials='')
        quote = self.Quote.objects.get()
        self.assertEqual((str(quote.estimated_hours), str(quote.estimated_materials), quote.revision_number), ('3.70', '0.00', 1))

    def test_quotation_total_must_be_positive(self):
        self._submit_quote(labour_amount='0', estimated_materials='0')
        self.assertFalse(self.Quote.objects.exists())

    def test_quotation_page_has_no_hourly_rate_wording(self):
        self.login(self.staff)
        page = self.client.get(reverse('staff_request_detail', args=[self.obj.id])).content.decode()
        self.assertIn('Prepare your quotation', page)
        self.assertNotIn('R250', page)
        self.assertNotIn('per hour', page.lower())

    def test_rejected_quotation_needs_a_reason_and_can_be_revised(self):
        self._submit_quote()
        quote = self.Quote.objects.get()
        self.login(self.admin)
        url = reverse('admin_review_quotation', args=[quote.id])
        self.client.post(url, {'decision': 'rejected', 'note': ''})
        quote.refresh_from_db(); self.assertEqual(quote.status, 'submitted')                 # a reason is mandatory
        self.client.post(url, {'decision': 'rejected', 'note': 'Labour is too high for a tap.'})
        quote.refresh_from_db(); self.assertEqual((quote.status, quote.landlord_note), ('rejected', 'Labour is too high for a tap.'))
        self.assertTrue(Notification.objects.filter(user=self.staff, title__startswith='Quotation rejected').exists())
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'accepted')            # job stays open for a revision
        self.login(self.staff)
        page = self.client.get(reverse('staff_request_detail', args=[self.obj.id])).content.decode()
        self.assertIn('Revise your quotation', page)
        self.assertIn('Labour is too high for a tap.', page)
        self._submit_quote(labour_amount='300')
        revised = self.Quote.objects.get(status='submitted')
        self.assertEqual(revised.revision_number, 2)
        self.login(self.admin)
        self.client.post(reverse('admin_review_quotation', args=[revised.id]), {'decision': 'approved'})
        self.obj.refresh_from_db()
        self.assertEqual(str(self.obj.agreed_total), '400.00')

    # ---- completion evidence
    def test_work_photo_is_required_before_completion(self):
        self.approve_quote(); self.confirm_visit(self.obj)
        self.login(self.staff)
        self.client.post(reverse('staff_start_job', args=[self.obj.id]))
        self.client.post(reverse('staff_add_work_log', args=[self.obj.id]), {'access_outcome': 'access_granted', 'notes': 'Replaced the cartridge.'})
        self.client.post(reverse('staff_mark_complete', args=[self.obj.id]))
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'in_progress')
        pdf = SimpleUploadedFile('invoice.pdf', b'%PDF-1.4', content_type='application/pdf')      # a PDF is not a work photo
        self.client.post(reverse('add_attachment', args=[self.obj.id]), {'file': pdf, 'description': 'doc'})
        self.client.post(reverse('staff_mark_complete', args=[self.obj.id]))
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'in_progress')
        import io
        from PIL import Image
        buf = io.BytesIO(); Image.new('RGB', (20, 20), (200, 200, 200)).save(buf, 'PNG')
        photo = SimpleUploadedFile('after.png', buf.getvalue(), content_type='image/png')
        self.client.post(reverse('add_attachment', args=[self.obj.id]), {'file': photo, 'description': 'After repair'})
        self.client.post(reverse('staff_mark_complete', args=[self.obj.id]))
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'completed')

    # ---- no access
    def test_no_access_tells_everyone_and_shows_what_to_do_next(self):
        self.approve_quote(); self.confirm_visit(self.obj)
        self.login(self.staff)
        self.client.post(reverse('staff_start_job', args=[self.obj.id]))
        self.client.post(reverse('staff_add_work_log', args=[self.obj.id]), {'access_outcome': 'no_access', 'notes': 'Nobody home at 10:00.'})
        self.assertTrue(RequestStatusHistory.objects.filter(request=self.obj, notes__startswith='No access').exists())
        page = self.client.get(reverse('staff_request_detail', args=[self.obj.id])).content.decode()
        self.assertIn('No access at the last visit', page)
        self.assertIn('Offer the landlord a time you can return', page)
        self.login(self.tenant)
        tpage = self.client.get(reverse('tenant_request_detail', args=[self.obj.id]))
        self.assertContains(tpage, 'could not get access')
        self.assertNotContains(tpage, 'Work is under way')
        self.login(self.admin)
        self.assertContains(self.client.get(reverse('admin_request_detail', args=[self.obj.id])), 'No access at the last visit')
        # contractor may now offer availability; landlord relays; tenant confirms; message changes for the contractor
        self.login(self.staff)
        self.client.post(reverse('staff_offer_availability', args=[self.obj.id]), dict(self.times, note='Tomorrow'))
        offer = MaintenanceAppointment.objects.get(status='availability')
        self.login(self.admin)
        self.client.post(reverse('admin_relay_availability', args=[offer.id]))
        offer.refresh_from_db(); self.assertEqual(offer.status, 'proposed')
        self.login(self.tenant)
        self.client.post(reverse('respond_appointment', args=[offer.id]), {'decision': 'confirm'})
        self.begin_visit(self.obj)
        self.login(self.staff)
        page = self.client.get(reverse('staff_request_detail', args=[self.obj.id])).content.decode()
        self.assertIn('The tenant has confirmed a return visit', page)
        self.client.post(reverse('staff_mark_complete', args=[self.obj.id]))
        self.assertIn('The tenant has confirmed the return visit', ''.join(m.message for m in self.client.get(reverse('staff_request_detail', args=[self.obj.id])).context['messages']))

    # ---- quotation card renders for both roles
    def test_quotation_card_renders_for_contractor_and_landlord(self):
        self._submit_quote(estimated_hours='2')
        self.assertContains(self.client.get(reverse('staff_request_detail', args=[self.obj.id])), 'Quotation Q-')
        self.login(self.admin)
        page = self.client.get(reverse('admin_request_detail', args=[self.obj.id]))
        self.assertContains(page, 'Reject and ask for a revision')
        self.assertContains(page, 'R 550.00')

    # ---- visit order and other robustness rules
    def test_landlord_cannot_propose_a_visit_before_the_contractor_accepts(self):
        job = self.make_request(status='assigned', assigned_staff=self.staff)
        self.login(self.admin)
        self.client.post(reverse('admin_propose_appointment', args=[job.id]), self.times)
        self.assertFalse(MaintenanceAppointment.objects.filter(request=job).exists())
        self.assertContains(self.client.get(reverse('admin_request_detail', args=[job.id])), 'Waiting for the contractor to accept')
        self.login(self.staff)
        self.client.post(reverse('staff_accept_job', args=[job.id]))
        self.assertTrue(Notification.objects.filter(user=self.admin, title='Contractor accepted the job').exists())
        self.login(self.admin)
        self.client.post(reverse('admin_propose_appointment', args=[job.id]), self.times)
        self.assertEqual(MaintenanceAppointment.objects.get(request=job).status, 'proposed')
        self.assertTrue(Notification.objects.filter(user=self.staff, title='Visit proposed to the tenant').exists())

    def test_fake_image_is_rejected_as_work_photo(self):
        self.approve_quote(); self.confirm_visit(self.obj)
        self.login(self.staff)
        self.client.post(reverse('staff_start_job', args=[self.obj.id]))
        fake = SimpleUploadedFile('after.jpg', b'this is not a picture', content_type='image/jpeg')
        self.client.post(reverse('add_attachment', args=[self.obj.id]), {'file': fake, 'description': 'x'})
        self.assertFalse(Attachment.objects.filter(request=self.obj).exists())

    def test_cancelling_a_request_closes_its_open_visit_proposals(self):
        self.login(self.admin)
        self.client.post(reverse('admin_propose_appointment', args=[self.obj.id]), self.times)
        appt = MaintenanceAppointment.objects.get()
        self.login(self.tenant)
        self.client.post(reverse('cancel_request', args=[self.obj.id]))
        appt.refresh_from_db(); self.assertEqual(appt.status, 'cancelled')
        self.client.post(reverse('respond_appointment', args=[appt.id]), {'decision': 'confirm'})
        appt.refresh_from_db(); self.assertEqual(appt.status, 'cancelled')

    # ---- start only when the visit time comes
    def test_cannot_start_before_the_confirmed_visit_and_return_edit_waits_for_the_visit(self):
        self.approve_quote()
        self.confirm_visit(self.obj, days=1)
        self.login(self.staff)
        self.client.post(reverse('staff_start_job', args=[self.obj.id]))
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'accepted')
        self.assertTrue(self.obj.visit_too_early())
        self.begin_visit(self.obj)
        self.assertFalse(self.obj.visit_too_early())
        self.client.post(reverse('staff_start_job', args=[self.obj.id]))
        self.obj.refresh_from_db(); self.assertEqual(self.obj.status, 'in_progress')

    # ---- contractor not responding
    def test_stalled_assignment_is_flagged_reminded_once_and_can_be_replaced(self):
        from requests_app.services import chase_stalled_jobs
        job = self.make_request(status='assigned', assigned_staff=self.staff, assigned_at=timezone.now() - timedelta(hours=30))
        self.assertIn('has not accepted this job after 30 hours', job.stalled_reason)
        self.assertEqual(chase_stalled_jobs(), 1)
        self.assertEqual(chase_stalled_jobs(), 0)                      # not repeated within 24 hours
        self.assertTrue(Notification.objects.filter(user=self.admin, title='Contractor not responding').exists())
        self.login(self.admin)
        self.assertContains(self.client.get(reverse('admin_request_detail', args=[job.id])), 'Contractor not responding')
        other = User.objects.create_user(username='fresh_c', email='f@example.com', password='testpass123', role='staff')
        self.client.post(reverse('admin_reassign_contractor', args=[job.id]), {'reason': ''})
        job.refresh_from_db(); self.assertEqual(job.assigned_staff_id, self.staff.id)        # a reason is required
        self.client.post(reverse('admin_reassign_contractor', args=[job.id]), {'reason': 'Not responding for a day'})
        job.refresh_from_db(); self.assertEqual((job.status, job.assigned_staff_id), ('reopened', None))
        self.assertTrue(Notification.objects.filter(user=self.staff, title='Job reassigned').exists())
        self.client.post(reverse('assign_request', args=[job.id]), {'staff_id': other.id})
        job.refresh_from_db(); self.assertEqual((job.status, job.assigned_staff_id), ('assigned', other.id))

    def test_accepted_job_with_no_visit_is_flagged_and_reassignment_cancels_open_visits(self):
        self.obj.accepted_at = timezone.now() - timedelta(hours=60); self.obj.save()
        self.assertIn('No visit has been arranged 60 hours', self.obj.stalled_reason)
        self.login(self.admin)
        self.client.post(reverse('admin_propose_appointment', args=[self.obj.id]), self.times)
        self.assertIsNone(self.obj.stalled_reason)                    # a proposal is now on the table
        appt = MaintenanceAppointment.objects.get()
        self.client.post(reverse('admin_reassign_contractor', args=[self.obj.id]), {'reason': 'Contractor unreachable'})
        appt.refresh_from_db(); self.assertEqual(appt.status, 'cancelled')
        self.obj.refresh_from_db(); self.assertIsNone(self.obj.tenant_wait_started_at)

    def test_work_in_progress_cannot_be_reassigned(self):
        self.obj.status = 'in_progress'; self.obj.save()
        self.login(self.admin)
        self.client.post(reverse('admin_reassign_contractor', args=[self.obj.id]), {'reason': 'Changed my mind'})
        self.obj.refresh_from_db(); self.assertEqual((self.obj.status, self.obj.assigned_staff_id), ('in_progress', self.staff.id))

    # ---- SLA clock pauses while the tenant decides
    def test_sla_clock_pauses_while_waiting_for_the_tenant(self):
        before = MaintenanceRequest.objects.get(pk=self.obj.pk).sla_deadline
        self.login(self.admin)
        self.client.post(reverse('admin_propose_appointment', args=[self.obj.id]), self.times)
        self.obj.refresh_from_db()
        self.assertIsNotNone(self.obj.tenant_wait_started_at)
        MaintenanceRequest.objects.filter(pk=self.obj.pk).update(tenant_wait_started_at=timezone.now() - timedelta(hours=5))
        appt = MaintenanceAppointment.objects.get()
        self.login(self.tenant)
        self.client.post(reverse('respond_appointment', args=[appt.id]), {'decision': 'confirm'})
        self.obj.refresh_from_db()
        self.assertIsNone(self.obj.tenant_wait_started_at)
        self.assertGreaterEqual(self.obj.sla_paused_seconds, 5 * 3600)
        self.assertGreaterEqual(self.obj.sla_deadline - before, timedelta(hours=5))

    # ---- production guard
    def test_production_refuses_the_default_secrets(self):
        import subprocess, sys, os
        env = dict(os.environ, DJANGO_DEBUG='0', DJANGO_SETTINGS_MODULE='maintenance_system.settings')
        env.pop('DJANGO_SECRET_KEY', None); env.pop('FIXIT_IOT_API_KEY', None)
        bad = subprocess.run([sys.executable, '-c', 'import django; django.setup()'], env=env, capture_output=True, text=True)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn('ImproperlyConfigured', bad.stderr)
        env.update(DJANGO_SECRET_KEY='x' * 60, FIXIT_IOT_API_KEY='private-sensor-key')
        good = subprocess.run([sys.executable, '-c', 'import django; django.setup()'], env=env, capture_output=True, text=True)
        self.assertEqual(good.returncode, 0, good.stderr)

    # ---- visibility of the availability hand-over (contractor -> landlord -> tenant)
    def test_offer_is_visible_to_landlord_and_explained_to_tenant_until_it_is_sent(self):
        self.login(self.staff)
        self.client.post(reverse('staff_offer_availability', args=[self.obj.id]), dict(self.times, note='Two hours needed'))
        offer = MaintenanceAppointment.objects.get(status='availability')
        self.login(self.admin)
        page = self.client.get(reverse('admin_request_detail', args=[self.obj.id])).content.decode()
        self.assertIn('Action needed: the contractor has offered his availability', page)
        self.assertEqual(page.count(reverse('admin_relay_availability', args=[offer.id])), 2)   # banner + visits panel
        self.assertContains(self.client.get(reverse('admin_dashboard')), 'Contractor availability received')
        self.assertEqual(self.client.get(reverse('notifications')).status_code, 200)
        self.login(self.tenant)
        tenant_page = self.client.get(reverse('tenant_request_detail', args=[self.obj.id])).content.decode()
        self.assertIn('The contractor has told the landlord when he is available', tenant_page)
        self.assertNotIn('Waiting for him to share', tenant_page)
        self.login(self.admin)
        self.client.post(reverse('admin_relay_availability', args=[offer.id]))
        self.login(self.tenant)
        self.assertContains(self.client.get(reverse('tenant_dashboard')), 'Visit time awaiting your response')

    def test_tenant_is_told_when_the_contractor_has_not_yet_offered(self):
        self.login(self.tenant)
        page = self.client.get(reverse('tenant_request_detail', args=[self.obj.id])).content.decode()
        self.assertIn('Waiting for him to share when he is available', page)

    def test_every_role_has_a_notifications_link_with_an_unread_badge(self):
        Notification.objects.create(user=self.staff, title='Quotation approved', message='x', request=self.obj)
        self.login(self.staff)
        page = self.client.get(reverse('staff_dashboard')).content.decode()
        self.assertIn(reverse('notifications'), page)
        self.assertIn('bg-danger">1</span>', page)

    def test_expired_offer_cannot_be_sent_and_the_contractor_is_asked_again(self):
        offer = MaintenanceAppointment.objects.create(request=self.obj, proposed_by=self.staff, status='availability',
                                                      starts_at=timezone.now() - timedelta(hours=1), ends_at=timezone.now() + timedelta(hours=1))
        self.login(self.admin)
        self.client.post(reverse('admin_relay_availability', args=[offer.id]))
        offer.refresh_from_db(); self.assertEqual(offer.status, 'cancelled')
        self.assertTrue(Notification.objects.filter(user=self.staff, title='Your offered time has passed').exists())

    def test_contractor_is_told_when_the_landlord_picks_a_different_time(self):
        self.login(self.staff)
        self.client.post(reverse('staff_offer_availability', args=[self.obj.id]), self.times)
        self.login(self.admin)
        self.client.post(reverse('admin_propose_appointment', args=[self.obj.id]), self.times)
        self.assertTrue(Notification.objects.filter(user=self.staff, title='Landlord chose a different time').exists())

#!/usr/bin/env python
"""
Setup script for Maintenance Request Management System.
This script initializes the database and creates demo users.
"""

import os
import sys
import django
from django.utils import timezone

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'maintenance_system.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from accounts.models import User
from requests_app.models import MaintenanceRequest, IoTDevice, RequestStatusHistory, Notification, AuditLog


def create_demo_users():
    """Create demo users for testing."""
    print("Creating demo users...")
    
    # Create/update deterministic demo accounts. Running setup.py repeatedly is safe.
    demo_accounts = [
        ('tenant', 'tenant@example.com', 'John', 'Tenant', 'tenant', False, False, 'A101', '555-0101'),
        ('admin', 'admin@example.com', 'Admin', 'User', 'admin', True, True, None, None),
        ('contractor', 'contractor@example.com', 'Mike', 'Contractor', 'staff', False, False, None, '555-0201'),
        ('contractor2', 'contractor2@example.com', 'Sarah', 'Contractor', 'staff', False, False, None, '555-0202'),
    ]
    users = {}
    for username, email, first_name, last_name, role, is_staff, is_superuser, apartment, phone in demo_accounts:
        user, created = User.objects.get_or_create(username=username)
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.role = role
        user.is_staff = is_staff
        user.is_superuser = is_superuser
        user.is_active = True
        if apartment:
            user.apartment_number = apartment
        if phone:
            user.phone_number = phone
        # Keep the published demo credentials stable even when the user already exists.
        user.set_password('password123')
        user.save()
        users[username] = user
        print(f"  {'[OK] Created' if created else '[OK] Updated'} {role} user: {username} / password123")

    tenant = users['tenant']
    admin = users['admin']
    staff1 = users['contractor']
    staff2 = users['contractor2']

    # Create a realistic demo maintenance request and registered sensor.
    demo_request, created = MaintenanceRequest.objects.get_or_create(
        title='Leaking bathroom tap',
        tenant=tenant,
        defaults={
            'description': 'Bathroom tap is leaking and requires inspection.',
            'category': 'plumbing', 'priority': 'high', 'apartment_number': tenant.apartment_number or 'A101',
            'building': 'Residence A', 'floor': '1', 'location_description': 'Bathroom',
            'status': 'assigned', 'assigned_staff': staff1, 'parts_required': 'Tap cartridge',
        }
    )
    if created:
        demo_request.assigned_at = timezone.now()
        demo_request.save()
        RequestStatusHistory.objects.create(request=demo_request, old_status='pending', new_status='assigned', changed_by=admin, notes='Demo request assigned during project setup')
        Notification.objects.create(user=tenant, title=f'Request #{demo_request.id} submitted', message='Your demo maintenance request is ready for tracking.', request=demo_request)
        Notification.objects.create(user=staff1, title=f'New maintenance assignment #{demo_request.id}', message='A demo maintenance request has been assigned to you.', request=demo_request)
        AuditLog.objects.create(user=admin, action='Demo request created', request=demo_request, details='Created by setup.py')
        print('  [OK] Created demo maintenance request #{}'.format(demo_request.id))

    device, created = IoTDevice.objects.get_or_create(
        sensor_id='WLS-001',
        defaults={
            'name': 'Residence A Bathroom Water Sensor', 'sensor_type': 'water_leak',
            'building': 'Residence A', 'floor': '1', 'apartment_number': tenant.apartment_number,
            'location_description': 'Bathroom', 'default_tenant': tenant, 'is_active': True,
        }
    )
    if not created and device.default_tenant_id != tenant.id:
        device.default_tenant = tenant
        device.save(update_fields=['default_tenant'])
    print('  [OK] IoT sensor WLS-001 is ready for demonstration')

    print("\nDemo users created successfully!")
    print("\nLogin credentials:")
    print("  Tenant:     username='tenant',     password='password123'")
    print("  Admin:      username='admin',      password='password123'")
    print("  Contractor: username='contractor', password='password123'")
    print("  Contractor2: username='contractor2', password='password123'")


def main():
    """Main setup function."""
    print("=" * 60)
    print("Maintenance Request Management System - Setup")
    print("=" * 60)
    print()
    
    try:
        create_demo_users()
        print()
        print("=" * 60)
        print("Setup completed successfully!")
        print("=" * 60)
        print()
        print("You can now run the server with:")
        print("  python manage.py runserver")
        print()
        print("Access the application at: http://127.0.0.1:8000/")
        print()
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

# Local demo tenancy for the existing tenant login.
from accounts.models import Lease
from datetime import timedelta
_demo_tenant = User.objects.filter(username='tenant', role='tenant').first()
if _demo_tenant:
    _lease, _ = Lease.objects.get_or_create(tenant=_demo_tenant, defaults={
        'tenant_email': _demo_tenant.email or 'tenant@example.com',
        'residence': _demo_tenant.address or 'Demo Residence',
        'unit': _demo_tenant.apartment_number or 'A1',
        'start_date': timezone.localdate() - timedelta(days=30),
        'end_date': timezone.localdate() + timedelta(days=365),
        'invitation_code': 'demo-tenant-lease-2026', 'verified': True,
    })

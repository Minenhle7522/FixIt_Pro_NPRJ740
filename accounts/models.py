from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = [
        ('tenant', 'Tenant'),
        ('admin', 'Administrator'),
        ('staff', 'Contractor'),
    ]
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='tenant')
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    apartment_number = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def is_tenant(self):
        return self.role == 'tenant'
    
    def is_admin_user(self):
        return self.role == 'admin'
    
    def is_staff_user(self):
        return self.role == 'staff'
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class Lease(models.Model):
    """Landlord-issued tenancy invitation; the tenant cannot choose their own unit."""
    tenant = models.OneToOneField('accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='lease')
    tenant_email = models.EmailField()
    residence = models.CharField(max_length=120)
    unit = models.CharField(max_length=30)
    floor = models.CharField(max_length=30, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    invitation_code = models.CharField(max_length=32, unique=True)
    verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_current(self):
        from django.utils import timezone
        today = timezone.localdate()
        return self.verified and self.start_date <= today <= self.end_date

    def __str__(self):
        return f'{self.residence} / {self.unit} ({self.tenant_email})'

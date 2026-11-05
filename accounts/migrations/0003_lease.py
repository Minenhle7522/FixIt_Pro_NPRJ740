from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings
class Migration(migrations.Migration):
    dependencies=[('accounts','0002_contractor_role_label')]
    operations=[migrations.CreateModel(name='Lease',fields=[('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),('tenant_email',models.EmailField(max_length=254)),('residence',models.CharField(max_length=120)),('unit',models.CharField(max_length=30)),('floor',models.CharField(max_length=30,blank=True)),('start_date',models.DateField()),('end_date',models.DateField()),('invitation_code',models.CharField(max_length=32,unique=True)),('verified',models.BooleanField(default=False)),('created_at',models.DateTimeField(auto_now_add=True)),('tenant',models.OneToOneField(to=settings.AUTH_USER_MODEL,on_delete=django.db.models.deletion.SET_NULL,related_name='lease',null=True,blank=True))])]

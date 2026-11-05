from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings
class Migration(migrations.Migration):
    dependencies=[('accounts','0003_lease'),('requests_app','0009_sla_real_world')]
    operations=[migrations.AddField(model_name='maintenancerequest',name='lease',field=models.ForeignKey(to='accounts.lease',null=True,blank=True,on_delete=django.db.models.deletion.PROTECT,related_name='requests')),
        migrations.CreateModel(name='MaintenanceAppointment',fields=[('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),('starts_at',models.DateTimeField()),('ends_at',models.DateTimeField()),('status',models.CharField(max_length=15,default='proposed',choices=[('proposed','Proposed'),('confirmed','Confirmed'),('reschedule','Reschedule requested'),('cancelled','Cancelled'),('attended','Attended'),('no_access','No access')])),('tenant_response',models.TextField(blank=True)),('created_at',models.DateTimeField(auto_now_add=True)),('updated_at',models.DateTimeField(auto_now=True)),('proposed_by',models.ForeignKey(to=settings.AUTH_USER_MODEL,on_delete=django.db.models.deletion.PROTECT,related_name='proposed_appointments')),('request',models.ForeignKey(to='requests_app.maintenancerequest',on_delete=django.db.models.deletion.CASCADE,related_name='appointments'))],options={'ordering':['-created_at']})]

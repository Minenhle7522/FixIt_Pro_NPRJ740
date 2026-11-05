from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('requests_app','0008_tenant_intake_fields')]
    operations = [
        migrations.AddField(model_name='maintenancerequest', name='response_deadline', field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name='maintenancerequest', name='first_response_at', field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name='maintenancerequest', name='original_sla_deadline', field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name='maintenancerequest', name='sla_pause_started_at', field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name='maintenancerequest', name='sla_pause_reason', field=models.TextField(blank=True)),
        migrations.AddField(model_name='maintenancerequest', name='sla_pause_approved', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='maintenancerequest', name='sla_paused_seconds', field=models.PositiveIntegerField(default=0)),
    ]

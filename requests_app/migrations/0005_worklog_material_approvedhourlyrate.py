from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone

class Migration(migrations.Migration):
    dependencies = [
        ('requests_app', '0004_iotdevice_sensorreading'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField(
            model_name='maintenancerequest', name='approved_hourly_rate',
            field=models.DecimalField(decimal_places=2, default=250.0, help_text='Administrator-approved labour rate in Rand per hour.', max_digits=10),
        ),
        migrations.CreateModel(
            name='WorkLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('work_date', models.DateField(default=timezone.localdate)),
                ('start_time', models.TimeField()), ('end_time', models.TimeField()),
                ('hourly_rate', models.DecimalField(decimal_places=2, max_digits=10)),
                ('notes', models.TextField(blank=True)), ('created_at', models.DateTimeField(auto_now_add=True)),
                ('request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='work_logs', to='requests_app.maintenancerequest')),
                ('technician', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='work_logs', to=settings.AUTH_USER_MODEL)),
            ], options={'ordering':['-work_date','-start_time']},
        ),
        migrations.CreateModel(
            name='Material',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.CharField(max_length=255)),
                ('quantity', models.DecimalField(decimal_places=2, default=1, max_digits=10)),
                ('unit_cost', models.DecimalField(decimal_places=2, max_digits=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('recorded_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='recorded_materials', to=settings.AUTH_USER_MODEL)),
                ('request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='materials', to='requests_app.maintenancerequest')),
            ], options={'ordering':['-created_at']},
        ),
    ]

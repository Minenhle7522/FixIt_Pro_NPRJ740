from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('requests_app', '0003_alter_requeststatushistory_options_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='IoTDevice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sensor_id', models.CharField(max_length=50, unique=True)),
                ('name', models.CharField(max_length=100)),
                ('sensor_type', models.CharField(choices=[('water_leak', 'Water Leak'), ('temperature', 'Temperature'), ('smoke', 'Smoke'), ('power', 'Power'), ('other', 'Other')], default='other', max_length=30)),
                ('building', models.CharField(max_length=100)),
                ('floor', models.CharField(blank=True, max_length=20)),
                ('apartment_number', models.CharField(blank=True, max_length=20)),
                ('location_description', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('last_seen', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('default_tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='iot_devices', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['sensor_id']},
        ),
        migrations.CreateModel(
            name='SensorReading',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('value', models.DecimalField(blank=True, decimal_places=3, max_digits=12, null=True)),
                ('unit', models.CharField(blank=True, max_length=20)),
                ('alert_type', models.CharField(blank=True, max_length=50)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('received_at', models.DateTimeField(auto_now_add=True)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='readings', to='requests_app.iotdevice')),
            ],
            options={'ordering': ['-received_at']},
        ),
    ]

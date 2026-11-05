from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('requests_app', '0005_worklog_material_approvedhourlyrate'),
    ]

    operations = [
        migrations.AlterField(
            model_name='worklog',
            name='end_time',
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name='worklog',
            constraint=models.UniqueConstraint(fields=('request',), name='one_work_log_per_request'),
        ),
    ]

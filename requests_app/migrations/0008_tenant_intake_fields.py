from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('requests_app', '0007_contract_workflow')]
    operations = [
        migrations.AddField(model_name='maintenancerequest', name='access_permission', field=models.CharField(max_length=12, default='contact', choices=[('contact', 'Contact me to arrange access'), ('notify', 'Entry permitted with advance notice'), ('present', 'I must be present')])),
        migrations.AddField(model_name='maintenancerequest', name='preferred_visit_time', field=models.CharField(max_length=12, blank=True, default='', choices=[('', 'No preference'), ('morning', 'Morning'), ('afternoon', 'Afternoon'), ('anytime', 'Anytime')])),
        migrations.AddField(model_name='maintenancerequest', name='safety_risk', field=models.BooleanField(default=False)),
    ]

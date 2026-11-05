from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

STATUS = [('pending','Submitted'),('under_review','Under Review'),('assigned','Assigned'),('accepted','Accepted'),('in_progress','In Progress'),('awaiting_parts','Awaiting Parts'),('completed','Completed'),('verified','Verified'),('closed','Closed'),('reopened','Reopened'),('cancelled','Cancelled')]
PRIORITY = [('low','Low'),('medium','Medium'),('high','High'),('urgent','Urgent')]

class Migration(migrations.Migration):
    dependencies=[('requests_app','0001_initial')]
    operations=[
        migrations.AlterField('maintenancerequest','status',models.CharField(choices=STATUS,default='pending',max_length=20)),
        migrations.AlterField('requeststatushistory','old_status',models.CharField(choices=STATUS,max_length=20)),
        migrations.AlterField('requeststatushistory','new_status',models.CharField(choices=STATUS,max_length=20)),
        migrations.AddField('maintenancerequest','building',models.CharField(blank=True,max_length=100)),
        migrations.AddField('maintenancerequest','floor',models.CharField(blank=True,max_length=20)),
        migrations.AddField('maintenancerequest','parts_required',models.CharField(blank=True,max_length=255)),
        migrations.AddField('maintenancerequest','diagnosis',models.TextField(blank=True)),
        migrations.AddField('maintenancerequest','rejection_reason',models.TextField(blank=True)),
        migrations.AddField('maintenancerequest','sla_hours',models.PositiveIntegerField(default=24)),
        migrations.AddField('maintenancerequest','sla_deadline',models.DateTimeField(blank=True,null=True)),
        migrations.AddField('maintenancerequest','sla_breached',models.BooleanField(default=False)),
        migrations.AddField('maintenancerequest','accepted_at',models.DateTimeField(blank=True,null=True)),
        migrations.AddField('maintenancerequest','verified_at',models.DateTimeField(blank=True,null=True)),
        migrations.AddField('maintenancerequest','closed_at',models.DateTimeField(blank=True,null=True)),
        migrations.CreateModel(name='Attachment',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('file',models.FileField(upload_to='maintenance_attachments/')),('description',models.CharField(blank=True,max_length=255)),('created_at',models.DateTimeField(auto_now_add=True)),
            ('request',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='attachments',to='requests_app.maintenancerequest')),
            ('uploaded_by',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,to=settings.AUTH_USER_MODEL))]),
        migrations.CreateModel(name='Feedback',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('rating',models.PositiveSmallIntegerField(choices=[(1,'1 Star'),(2,'2 Star'),(3,'3 Star'),(4,'4 Star'),(5,'5 Star')])),('comment',models.TextField(blank=True)),('created_at',models.DateTimeField(auto_now_add=True)),
            ('request',models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,related_name='feedback',to='requests_app.maintenancerequest')),
            ('submitted_by',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,to=settings.AUTH_USER_MODEL))]),
        migrations.CreateModel(name='Notification',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),('title',models.CharField(max_length=200)),('message',models.TextField()),('is_read',models.BooleanField(default=False)),('created_at',models.DateTimeField(auto_now_add=True)),
            ('request',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.CASCADE,related_name='notifications',to='requests_app.maintenancerequest')),
            ('user',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='notifications',to=settings.AUTH_USER_MODEL))],options={'ordering':['-created_at']}),
        migrations.CreateModel(name='AuditLog',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),('action',models.CharField(max_length=100)),('details',models.TextField(blank=True)),('ip_address',models.GenericIPAddressField(blank=True,null=True)),('created_at',models.DateTimeField(auto_now_add=True)),
            ('request',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name='audit_logs',to='requests_app.maintenancerequest')),
            ('user',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,to=settings.AUTH_USER_MODEL))],options={'ordering':['-created_at']}),
    ]

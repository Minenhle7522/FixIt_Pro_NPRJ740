from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('requests_app', '0006_single_automatic_worklog')]
    operations = [
        migrations.AddField(model_name='maintenancerequest', name='incident_at', field=models.DateTimeField(blank=True, null=True, help_text='When the fault was first noticed (if known).')),
        migrations.AddField(model_name='maintenancerequest', name='quotation_required', field=models.BooleanField(default=False, help_text='New contractor jobs require an approved quotation; legacy jobs remain compatible.')),
        migrations.CreateModel(name='ContractorQuotation', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('scope', models.TextField()), ('labour_amount', models.DecimalField(decimal_places=2,max_digits=10)),
            ('estimated_materials', models.DecimalField(decimal_places=2,max_digits=10,default=0)),
            ('estimated_hours', models.DecimalField(decimal_places=2,max_digits=7,default=1)),
            ('status', models.CharField(max_length=12,choices=[('submitted','Awaiting Approval'),('approved','Approved'),('rejected','Rejected')],default='submitted')),
            ('landlord_note',models.TextField(blank=True)), ('created_at',models.DateTimeField(auto_now_add=True)),
            ('approved_at',models.DateTimeField(blank=True,null=True)),
            ('contractor',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='contractor_quotations',to='accounts.user')),
            ('request',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='quotations',to='requests_app.maintenancerequest')),
            ('reviewed_by',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name='reviewed_quotations',to='accounts.user')),
        ],options={'ordering':['-created_at']}),
        migrations.CreateModel(name='ContractorPayment', fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('amount',models.DecimalField(decimal_places=2,max_digits=10)),('payment_date',models.DateField()),
            ('reference',models.CharField(max_length=120)),('proof',models.FileField(blank=True,upload_to='payment_proofs/')),
            ('status',models.CharField(max_length=12,choices=[('recorded','Recorded by Landlord'),('confirmed','Receipt Confirmed'),('disputed','Disputed')],default='recorded')),
            ('contractor_comment',models.TextField(blank=True)),('acknowledged_at',models.DateTimeField(blank=True,null=True)),
            ('created_at',models.DateTimeField(auto_now_add=True)),
            ('request',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='payments',to='requests_app.maintenancerequest')),
            ('contractor',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='contractor_payments',to='accounts.user')),
            ('recorded_by',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='recorded_contract_payments',to='accounts.user')),
        ],options={'ordering':['-created_at']}),
    ]

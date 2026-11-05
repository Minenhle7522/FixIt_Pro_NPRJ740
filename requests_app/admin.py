from django.contrib import admin
from .models import MaintenanceRequest, RequestStatusHistory, StaffNote, Attachment, Feedback, Notification, AuditLog, IoTDevice, SensorReading, WorkLog, Material

@admin.register(MaintenanceRequest)
class MaintenanceRequestAdmin(admin.ModelAdmin):
    list_display = ('id','title','tenant','priority','status','assigned_staff','sla_deadline','sla_breached','total_cost','created_at')
    list_filter = ('status','priority','category','sla_breached')
    search_fields = ('title','description','tenant__username','tenant__first_name','tenant__last_name')

admin.site.register(RequestStatusHistory)
admin.site.register(StaffNote)
admin.site.register(Attachment)
admin.site.register(Feedback)
admin.site.register(Notification)
admin.site.register(AuditLog)
admin.site.register(IoTDevice)
admin.site.register(SensorReading)

admin.site.register(WorkLog)
admin.site.register(Material)

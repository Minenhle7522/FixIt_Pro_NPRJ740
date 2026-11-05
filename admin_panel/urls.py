from django.urls import path
from . import views
urlpatterns=[
 path('request/<int:request_id>/alert-contractor/',views.alert_contractor,name='admin_alert_contractor'),
 path('request/<int:request_id>/appointment/',views.propose_appointment,name='admin_propose_appointment'),
 path('availability/<int:appointment_id>/relay/',views.relay_availability_view,name='admin_relay_availability'),
 path('request/<int:request_id>/reassign/',views.reassign_contractor,name='admin_reassign_contractor'),
 path('leases/',views.create_lease,name='admin_create_lease'),
 path('request/<int:request_id>/sla-pause/',views.approve_sla_pause,name='admin_approve_sla_pause'),
 path('quotation/<int:quote_id>/review/',views.review_quotation,name='admin_review_quotation'),
 path('request/<int:request_id>/payment/',views.record_payment,name='admin_record_payment'),
 path('tenants/pending/',views.pending_tenants,name='pending_tenants'),
 path('tenants/<int:user_id>/approve/',views.approve_tenant,name='approve_tenant'),
 path('dashboard/',views.admin_dashboard,name='admin_dashboard'), path('requests/',views.all_requests,name='all_requests'),
 path('request/<int:request_id>/',views.admin_request_detail,name='admin_request_detail'), path('request/<int:request_id>/assign/',views.assign_request,name='assign_request'),
 path('request/<int:request_id>/update/',views.update_request,name='admin_update_request'),
 path('request/<int:request_id>/close/',views.close_request,name='admin_close_request'),
 path('staff/',views.manage_staff,name='manage_staff'), path('staff/add/',views.add_staff,name='add_staff'), path('reports/',views.reports,name='reports'),
 path('reports/generate/',views.generate_report,name='generate_report'), path('sla/process/',views.process_sla,name='process_sla'),
]

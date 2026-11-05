from django.urls import path
from . import views

urlpatterns = [
    path('tenant/appointment/<int:appointment_id>/respond/', views.respond_appointment, name='respond_appointment'),
    path('tenant/dashboard/', views.tenant_dashboard, name='tenant_dashboard'),
    path('tenant/submit/', views.submit_request, name='submit_request'),
    path('tenant/request/<int:request_id>/', views.tenant_request_detail, name='tenant_request_detail'),
    path('tenant/request/<int:request_id>/cancel/', views.cancel_request, name='cancel_request'),
    path('tenant/request/<int:request_id>/verify/', views.verify_request, name='verify_request'),
    path('tenant/request/<int:request_id>/reopen/', views.reopen_request, name='reopen_request'),
    path('tenant/request/<int:request_id>/feedback/', views.submit_feedback, name='submit_feedback'),
    path('request/<int:request_id>/attachment/', views.add_attachment, name='add_attachment'),
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/<int:notification_id>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('request/<int:request_id>/', views.request_detail, name='request_detail'),
    path('api/iot/status/', views.iot_status, name='iot_status'),
]

from django.urls import path
from . import views
urlpatterns = [
 path('request/<int:request_id>/quotation/', views.submit_quotation, name='staff_submit_quotation'),
 path('request/<int:request_id>/decline/', views.reject_job, name='staff_reject_job'),
 path('payment/<int:payment_id>/acknowledge/', views.acknowledge_payment, name='staff_acknowledge_payment'),
 path('dashboard/', views.staff_dashboard, name='staff_dashboard'), path('request/<int:request_id>/', views.staff_request_detail, name='staff_request_detail'),
 path('request/<int:request_id>/accept/', views.accept_job, name='staff_accept_job'),
 path('request/<int:request_id>/start/', views.start_job, name='staff_start_job'),
 path('request/<int:request_id>/awaiting-parts/', views.awaiting_parts, name='staff_awaiting_parts'),
 path('request/<int:request_id>/resume/', views.resume_job, name='staff_resume_job'),
 path('request/<int:request_id>/complete/', views.mark_complete, name='staff_mark_complete'),
 path('request/<int:request_id>/work-log/add/', views.add_work_log, name='staff_add_work_log'),
 path('request/<int:request_id>/work-log/edit/', views.edit_work_log, name='staff_edit_work_log'),
 path('request/<int:request_id>/availability/', views.offer_availability_view, name='staff_offer_availability'),
 path('request/<int:request_id>/material/add/', views.add_material, name='staff_add_material'),
 path('request/<int:request_id>/add-note/', views.add_note, name='staff_add_note'), path('tasks/', views.my_tasks, name='my_tasks'),
]

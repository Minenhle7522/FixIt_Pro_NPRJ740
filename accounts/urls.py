from django.urls import path
from django.contrib.auth.views import PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView, PasswordChangeView, PasswordChangeDoneView
from . import views
from .forms import StyledSetPasswordForm, StyledPasswordChangeForm

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.custom_login, name='login'),
    path('logout/', views.custom_logout, name='logout'),
    path('register/', views.tenant_register, name='register'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile, name='profile'),
    path('password/reset/', PasswordResetView.as_view(template_name='accounts/password_reset.html', email_template_name='accounts/password_reset_email.txt', subject_template_name='accounts/password_reset_subject.txt'), name='password_reset'),
    path('password/reset/sent/', PasswordResetDoneView.as_view(template_name='accounts/password_reset_done.html'), name='password_reset_done'),
    path('password/reset/<uidb64>/<token>/', PasswordResetConfirmView.as_view(template_name='accounts/password_reset_confirm.html', form_class=StyledSetPasswordForm), name='password_reset_confirm'),
    path('password/reset/complete/', PasswordResetCompleteView.as_view(template_name='accounts/password_reset_complete.html'), name='password_reset_complete'),
    path('password/change/', PasswordChangeView.as_view(template_name='accounts/password_change.html', form_class=StyledPasswordChangeForm), name='password_change'),
    path('password/change/done/', PasswordChangeDoneView.as_view(template_name='accounts/password_change_done.html'), name='password_change_done'),
]

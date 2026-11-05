from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import TenantRegistrationForm, CustomAuthenticationForm


def home(request):
    """Home page view."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'accounts/home.html')


def custom_login(request):
    """Custom login view that redirects based on user role."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = CustomAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.first_name or user.username}!')
                # Role-safe redirect after login (prevents falling into wrong portal)
                if user.is_admin_user():
                    return redirect('admin_dashboard')
                if user.is_staff_user():
                    return redirect('staff_dashboard')
                if user.is_tenant():
                    return redirect('tenant_dashboard')
                return redirect('home')
        else:
            # Django's backend silently rejects inactive users, which looks like a wrong
            # password. Only if the credentials are correct do we say the account is pending.
            from .models import User
            u = User.objects.filter(username__iexact=request.POST.get('username', '')).first()
            if u and not u.is_active and u.check_password(request.POST.get('password', '')):
                messages.error(request, 'Your account is awaiting landlord approval. You can sign in once it has been verified.')
            else:
                messages.error(request, 'Invalid username or password.')
    else:
        form = CustomAuthenticationForm()
    
    return render(request, 'accounts/login.html', {'form': form})


def tenant_register(request):
    """Tenant registration view."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = TenantRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            user.is_active = False
            user.save(update_fields=['is_active'])
            messages.success(request, 'Registration received. The landlord must verify your tenancy before you can sign in.')
            return redirect('login')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = TenantRegistrationForm()
    
    return render(request, 'accounts/register.html', {'form': form})


@login_required
def dashboard(request):
    """Role-based portal landing.

    Keeps users inside their correct portal home.
    """
    if request.user.is_admin_user():
        return redirect('admin_dashboard')
    if request.user.is_staff_user():
        return redirect('staff_dashboard')
    if request.user.is_tenant():
        return redirect('tenant_dashboard')

    # Fallback: unknown role
    messages.error(request, 'Your account role is not recognized for portal access.')
    return redirect('home')



@login_required
def profile(request):
    """User profile view."""
    return render(request, 'accounts/profile.html', {'user': request.user})


def custom_logout(request):
    """Custom logout view that handles both GET and POST requests."""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('login')

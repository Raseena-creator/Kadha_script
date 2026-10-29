from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import PasswordChangeForm
from .forms import UserRegisterForm, UserLoginForm, ProfileUpdateForm

def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='accounts.backends.EmailOrUsernameModelBackend')
            display_name = user.first_name or (user.profile.pen_name if hasattr(user, 'profile') and user.profile.pen_name else 'Writer')
            messages.success(request, f'Welcome to KadhaScript, {display_name}! Your screenwriting journey starts here.')
            return redirect('dashboard')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{error}')
    else:
        form = UserRegisterForm()
    return render(request, 'accounts/register.html', {'form': form})

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = UserLoginForm(request.POST)
        if form.is_valid():
            email_or_username = form.cleaned_data['email'].strip()
            password = form.cleaned_data['password']

            user = authenticate(request, email=email_or_username, password=password)
            if user is not None:
                login(request, user)
                display_name = user.first_name or (user.profile.pen_name if hasattr(user, 'profile') and user.profile.pen_name else 'Writer')
                messages.success(request, f'Welcome back, {display_name}!')
                next_url = request.GET.get('next') or 'dashboard'
                return redirect(next_url)
            else:
                messages.error(request, 'Invalid email or password. Please try again.')
    else:
        form = UserLoginForm()
    return render(request, 'accounts/login.html', {'form': form})

def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('landing')

@login_required
def profile_view(request):
    user = request.user
    profile = user.profile
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, instance=profile)
        if form.is_valid():
            user.first_name = form.cleaned_data['first_name']
            user.last_name = form.cleaned_data['last_name']
            user.email = form.cleaned_data['email']
            user.save()
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile')
    else:
        initial = {
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
        }
        form = ProfileUpdateForm(instance=profile, initial=initial)
    return render(request, 'accounts/profile.html', {'form': form})

@login_required
def change_password_view(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Your password was successfully updated!')
            return redirect('profile')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'accounts/change_password.html', {'form': form})

import logging
import smtplib
from django.conf import settings
from django.contrib.auth import views as auth_views

logger = logging.getLogger(__name__)

class CustomPasswordResetView(auth_views.PasswordResetView):
    EMAIL_DELIVERY_EXCEPTIONS = (
        smtplib.SMTPException,
        OSError,
        ValueError,
        RuntimeError,
    )

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except self.EMAIL_DELIVERY_EXCEPTIONS as e:
            logger.error(
                "Failed to send password reset email (error_type=%s, backend=%s, host=%s, port=%s, tls=%s, ssl=%s)",
                type(e).__name__,
                getattr(settings, 'EMAIL_BACKEND', ''),
                getattr(settings, 'EMAIL_HOST', ''),
                getattr(settings, 'EMAIL_PORT', ''),
                getattr(settings, 'EMAIL_USE_TLS', ''),
                getattr(settings, 'EMAIL_USE_SSL', ''),
            )
            return redirect(self.get_success_url())

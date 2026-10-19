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
            login(request, user)
            messages.success(request, f'Welcome to KadhaScript, {user.username}! Your screenwriting journey starts here.')
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
            login_input = form.cleaned_data['username'].strip()
            password = form.cleaned_data['password']

            username_to_auth = login_input
            if '@' in login_input:
                from django.contrib.auth.models import User
                try:
                    user_matched = User.objects.get(email__iexact=login_input)
                    username_to_auth = user_matched.username
                except (User.DoesNotExist, User.MultipleObjectsReturned):
                    username_to_auth = login_input

            user = authenticate(request, username=username_to_auth, password=password)
            if user is not None:
                login(request, user)
                display_name = user.first_name or user.username
                messages.success(request, f'Welcome back, {display_name}!')
                next_url = request.GET.get('next') or 'dashboard'
                return redirect(next_url)
            else:
                messages.error(request, 'Invalid username or password. Please try again.')
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
from django.contrib.auth import views as auth_views

logger = logging.getLogger(__name__)

class CustomPasswordResetView(auth_views.PasswordResetView):
    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except Exception as e:
            logger.error("Failed to send password reset email: %s", type(e).__name__)
            return redirect(self.get_success_url())

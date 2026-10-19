import re
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.forms import PasswordChangeForm
from .models import Profile

class UserRegisterForm(forms.ModelForm):
    full_name = forms.CharField(
        max_length=150,
        required=True,
        label='Full Name',
        widget=forms.TextInput(attrs={
            'placeholder': 'Your full name',
            'class': 'form-control',
            'autocomplete': 'name',
            'autofocus': True,
        })
    )
    email = forms.EmailField(
        required=True,
        label='Email Address',
        widget=forms.EmailInput(attrs={
            'placeholder': 'name@example.com',
            'class': 'form-control',
            'autocomplete': 'email',
        })
    )
    password = forms.CharField(
        required=True,
        label='Password',
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Create a password',
            'class': 'form-control',
            'autocomplete': 'new-password',
        })
    )

    class Meta:
        model = User
        fields = ['full_name', 'email', 'password']

    def clean_full_name(self):
        full_name = self.cleaned_data.get('full_name', '').strip()
        if not full_name:
            raise forms.ValidationError('Full name is required.')
        return full_name

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email address already exists.')
        return email

    def clean_password(self):
        password = self.cleaned_data.get('password')
        dummy_user = User(
            email=self.cleaned_data.get('email', ''),
            first_name=self.cleaned_data.get('full_name', '')
        )
        validate_password(password, user=dummy_user)
        return password

    def generate_unique_username(self, email, full_name):
        base = email.split('@')[0] if email else ''
        cleaned_base = re.sub(r'[^a-zA-Z0-9_]', '', base).lower()
        if not cleaned_base:
            cleaned_base = re.sub(r'[^a-zA-Z0-9_]', '', full_name).lower() or 'writer'

        candidate = cleaned_base[:140]
        counter = 1
        while User.objects.filter(username__iexact=candidate).exists():
            candidate = f"{cleaned_base[:135]}_{counter}"
            counter += 1
        return candidate

    def save(self, commit=True):
        user = super().save(commit=False)
        full_name = self.cleaned_data['full_name'].strip()
        email = self.cleaned_data['email'].strip().lower()
        password = self.cleaned_data['password']

        user.email = email
        name_parts = full_name.split(None, 1)
        user.first_name = name_parts[0]
        user.last_name = name_parts[1] if len(name_parts) > 1 else ''

        if not user.username:
            user.username = self.generate_unique_username(email, full_name)

        user.set_password(password)

        if commit:
            user.save()
            if hasattr(user, 'profile'):
                user.profile.pen_name = full_name
                user.profile.save()
        return user

class UserLoginForm(forms.Form):
    username = forms.CharField(
        label='Username or Email',
        widget=forms.TextInput(attrs={
            'placeholder': 'Username or Email',
            'class': 'form-control',
            'autocomplete': 'username'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Password',
            'class': 'form-control',
            'autocomplete': 'current-password'
        })
    )

class ProfileUpdateForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=True)

    class Meta:
        model = Profile
        fields = ['pen_name', 'bio', 'preferred_language']
        widgets = {
            'pen_name': forms.TextInput(attrs={'class': 'form-control'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'preferred_language': forms.TextInput(attrs={'class': 'form-control'}),
        }

from unittest.mock import patch
from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.urls import reverse
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.forms import UserRegisterForm, UserLoginForm

User = get_user_model()


class SixRequirementsRegressionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='existingwriter',
            email='existing@kadhascript.com',
            password='ExistingPass123!',
            first_name='Existing',
            last_name='Writer'
        )

    # =========================================================================
    # REQUIREMENT 2: Mobile Navbar Spacing & Brand Text
    # =========================================================================

    def test_navbar_branding_and_responsive_classes(self):
        """Navbar renders Malayalam brand text and hides English subtitle on mobile breakpoints."""
        response = self.client.get(reverse('landing'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        # Malayalam brand must be present
        self.assertIn('കഥാസ്ക്രിപ്റ്റ്', content)
        # English brand subtitle must have mobile-hide classes
        self.assertIn('ks-brand-subtitle', content)
        self.assertIn('d-none d-md-inline', content)
        # Sign In and Get Started must be present
        self.assertIn('Sign In', content)
        self.assertIn('Get Started', content)

    # =========================================================================
    # REQUIREMENT 3: Simplified Create Account Form & Login
    # =========================================================================

    def test_registration_form_has_exactly_three_fields(self):
        """UserRegisterForm exposes exactly three fields: full_name, email, password."""
        form = UserRegisterForm()
        expected_fields = {'full_name', 'email', 'password'}
        self.assertEqual(set(form.fields.keys()), expected_fields)

    def test_registration_form_empty_name_rejected(self):
        """Empty full name is rejected with a validation error."""
        form = UserRegisterForm({
            'full_name': '   ',
            'email': 'new@kadhascript.com',
            'password': 'StrongPassword123!'
        })
        self.assertFalse(form.is_valid())
        self.assertIn('full_name', form.errors)

    def test_registration_form_invalid_email_rejected(self):
        """Invalid email is rejected."""
        form = UserRegisterForm({
            'full_name': 'John Doe',
            'email': 'not-an-email',
            'password': 'StrongPassword123!'
        })
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_registration_form_duplicate_email_rejected(self):
        """Duplicate email address is rejected case-insensitively."""
        form = UserRegisterForm({
            'full_name': 'Another Writer',
            'email': 'EXISTING@kadhascript.com',
            'password': 'StrongPassword123!'
        })
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)
        self.assertIn('already exists', str(form.errors['email']))

    def test_registration_form_weak_password_rejected(self):
        """Short or weak password is rejected by Django password validation."""
        form = UserRegisterForm({
            'full_name': 'John Doe',
            'email': 'johndoe@example.com',
            'password': '123'
        })
        self.assertFalse(form.is_valid())
        self.assertIn('password', form.errors)

    def test_registration_form_successful_creation_and_username_derivation(self):
        """Valid registration derives username, splits names, sets pen_name, and hashes password."""
        form = UserRegisterForm({
            'full_name': 'Mohanlal Viswanathan',
            'email': 'lalettan@cinema.com',
            'password': 'CinemaPassword@2026'
        })
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        self.assertEqual(user.first_name, 'Mohanlal')
        self.assertEqual(user.last_name, 'Viswanathan')
        self.assertEqual(user.email, 'lalettan@cinema.com')
        self.assertTrue(user.username.startswith('lalettan'))
        self.assertTrue(user.check_password('CinemaPassword@2026'))
        if hasattr(user, 'profile'):
            self.assertEqual(user.profile.pen_name, 'Mohanlal Viswanathan')

    def test_register_view_renders_three_fields_and_eye_toggle(self):
        """Register template renders full_name, email, password and eye toggle."""
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        self.assertIn('name="full_name"', content)
        self.assertIn('name="email"', content)
        self.assertIn('name="password"', content)
        self.assertNotIn('name="password2"', content)
        self.assertNotIn('name="username"', content)
        self.assertIn('id="togglePassword"', content)
        self.assertIn('Create Account', content)
        self.assertIn('Already have an account?', content)

    def test_register_view_post_logs_in_and_redirects(self):
        """Submitting valid registration logs user in and redirects to dashboard."""
        response = self.client.post(reverse('register'), {
            'full_name': 'Mammootty Panaparambil',
            'email': 'mammukka@cinema.com',
            'password': 'MasterActor@2026'
        }, follow=True)
        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(response.context['user'].is_authenticated)
        self.assertEqual(response.context['user'].email, 'mammukka@cinema.com')

    def test_login_with_username_and_email(self):
        """Users can log in using either their username or their email address."""
        # 1. Login with username
        res_user = self.client.post(reverse('login'), {
            'username': 'existingwriter',
            'password': 'ExistingPass123!'
        })
        self.assertRedirects(res_user, reverse('dashboard'))
        self.client.logout()

        # 2. Login with email
        res_email = self.client.post(reverse('login'), {
            'username': 'existing@kadhascript.com',
            'password': 'ExistingPass123!'
        })
        self.assertRedirects(res_email, reverse('dashboard'))
        self.client.logout()

    # =========================================================================
    # REQUIREMENT 4: Password Reset Flow & Safe Logging
    # =========================================================================

    def test_password_reset_email_generation(self):
        """Requesting password reset generates an email with valid reset link."""
        response = self.client.post(reverse('password_reset'), {
            'email': 'existing@kadhascript.com'
        })
        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ['existing@kadhascript.com'])
        self.assertIn('Password reset', sent.subject)
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        self.assertIn(uid, sent.body)

    def test_password_reset_token_inspection_password_change_and_login(self):
        """Inspect token from email, execute password change, and log in with new credentials."""
        self.client.post(reverse('password_reset'), {'email': 'existing@kadhascript.com'})
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]

        import re
        match = re.search(r'accounts/reset/([^/]+)/([^/\s]+)/', sent.body)
        self.assertIsNotNone(match, f"Reset URL not found in email body:\n{sent.body}")
        uidb64, token = match.group(1), match.group(2)

        # Confirm token is valid for user
        self.assertTrue(default_token_generator.check_token(self.user, token))

        # Confirm GET to reset confirm view sets session and renders form
        confirm_url = reverse('password_reset_confirm', kwargs={'uidb64': uidb64, 'token': token})
        get_res = self.client.get(confirm_url, follow=True)
        self.assertEqual(get_res.status_code, 200)
        self.assertTrue(len(get_res.redirect_chain) > 0)
        set_pwd_url = get_res.redirect_chain[0][0]

        # Change password via POST to the session-guarded set-password URL
        post_res = self.client.post(set_pwd_url, {
            'new_password1': 'BrandNewPass2026!',
            'new_password2': 'BrandNewPass2026!'
        }, follow=True)
        self.assertEqual(post_res.status_code, 200)

        # Verify database update and old password invalidation
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('BrandNewPass2026!'))
        self.assertFalse(self.user.check_password('ExistingPass123!'))

        # Verify login with new password succeeds
        login_res = self.client.post(reverse('login'), {
            'username': 'existing@kadhascript.com',
            'password': 'BrandNewPass2026!'
        })
        self.assertRedirects(login_res, reverse('dashboard'))

    def test_password_reset_invalid_and_expired_tokens(self):
        """Invalid or expired tokens cannot reset the password."""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        invalid_confirm_url = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': 'invalid-token-xyz'})

        # Invalid token view loads with error message
        res = self.client.get(invalid_confirm_url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Reset Link Invalid')
        self.assertContains(res, 'The password reset link was invalid')

        # Submitting with invalid token fails
        post_res = self.client.post(invalid_confirm_url, {
            'new_password1': 'HackedPass2026!',
            'new_password2': 'HackedPass2026!'
        })
        self.assertEqual(post_res.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password('HackedPass2026!'))

        # Expired token check
        valid_token = default_token_generator.make_token(self.user)
        with override_settings(PASSWORD_RESET_TIMEOUT=-1):
            self.assertFalse(default_token_generator.check_token(self.user, valid_token))

    def test_password_reset_safe_error_handling(self):
        """When mail sending raises an exception, view logs safely, prevents enumeration, and does not crash."""
        with patch('django.contrib.auth.forms.PasswordResetForm.save', side_effect=RuntimeError("SMTP Connection Lost")):
            with self.assertLogs('accounts.views', level='ERROR') as cm:
                response = self.client.post(reverse('password_reset'), {
                    'email': 'existing@kadhascript.com'
                }, follow=True)
            # Should redirect to password_reset_done to prevent account enumeration without crashing or leaking errors
            self.assertRedirects(response, reverse('password_reset_done'))
            self.assertNotContains(response, 'SMTP Connection Lost')
            self.assertNotContains(response, 'RuntimeError')
            self.assertIn('RuntimeError', "\n".join(cm.output))

    # =========================================================================
    # REQUIREMENT 5: Backup Feature Cleanup Verification
    # =========================================================================

    def test_backup_services_and_commands_removed(self):
        """Removed backup services and commands cannot be imported or executed."""
        # Services removed
        with self.assertRaises(ImportError):
            import scripts.services.gdrive_backup_service  # noqa: F401

        with self.assertRaises(ImportError):
            import scripts.services.email_backup_service  # noqa: F401

        # Management commands removed
        with self.assertRaises(CommandError):
            call_command('backup_to_gdrive')

        with self.assertRaises(CommandError):
            call_command('send_daily_backup')

    def test_screenplay_pdf_export_service_remains_intact(self):
        """PDF export service was not deleted and remains fully operational."""
        from scripts.services.pdf_export import generate_screenplay_pdf
        from scripts.models import Script, Scene

        script = Script.objects.create(title="Active Movie", user=self.user)
        Scene.objects.create(script=script, scene_number=1, heading="INT. STUDIO - DAY", order=1)
        pdf = generate_screenplay_pdf(script)
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(pdf.startswith(b'%PDF'))

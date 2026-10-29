import re
import smtplib
from unittest.mock import patch
from django.conf import settings
from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.urls import reverse
from django.core import mail
from accounts.models import Profile


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PasswordResetTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.username = 'testwriter'
        self.email = 'writer@kadhascript.com'
        self.old_password = 'OldSecurePassword123!'
        self.user = User.objects.create_user(
            username=self.username,
            email=self.email,
            password=self.old_password
        )
        Profile.objects.get_or_create(user=self.user, defaults={'pen_name': 'Test Writer'})

    def test_login_page_renders_forgot_password_link(self):
        """1. Login page displays a clearly visible 'Forgot password?' link."""
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Forgot password?')
        self.assertContains(response, reverse('password_reset'))

    def test_forgot_password_page_loads(self):
        """2. Forgot password page loads with expected title and explanation."""
        response = self.client.get(reverse('password_reset'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Forgot your password?')
        self.assertContains(response, "Enter the email address associated with your account and we'll send you a link to reset your password.")
        self.assertContains(response, 'name="email"')
        self.assertContains(response, 'Send reset link')

    def test_registered_email_triggers_password_reset_email(self):
        """3. Registered email submission sends reset email with valid link."""
        response = self.client.post(reverse('password_reset'), {'email': self.email})
        self.assertRedirects(response, reverse('password_reset_done'))

        # Verify email was sent
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.to, [self.email])
        self.assertIn('Password reset', sent_email.subject)

        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        self.assertIn(uid, sent_email.body)

    def test_unknown_email_same_response_without_revealing_user_existence(self):
        """4. Unknown email returns same confirmation page without revealing existence."""
        response = self.client.post(reverse('password_reset'), {'email': 'nonexistent@example.com'})
        self.assertRedirects(response, reverse('password_reset_done'))
        # No email should be sent for nonexistent account
        self.assertEqual(len(mail.outbox), 0)

        # Confirm page loads cleanly with generic message
        done_response = self.client.get(reverse('password_reset_done'))
        self.assertEqual(done_response.status_code, 200)
        self.assertContains(done_response, 'Check your email')
        self.assertContains(done_response, 'If an account exists with that email address, you will receive instructions')
        self.assertNotContains(done_response, 'Email not found')

    def test_valid_reset_link_renders_set_password_form(self):
        """5. Valid reset token link opens the 'Set a new password' form."""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        reset_url = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})

        response = self.client.get(reset_url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['validlink'])
        self.assertContains(response, 'Set a new password')
        self.assertContains(response, 'name="new_password1"')
        self.assertContains(response, 'name="new_password2"')

    def test_invalid_token_is_rejected(self):
        """6. Invalid token is rejected and shows invalid/expired message."""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        invalid_url = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': 'invalid-token-123'})

        response = self.client.get(invalid_url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['validlink'])
        self.assertContains(response, 'Reset Link Invalid')
        self.assertContains(response, 'The password reset link was invalid')

    def test_invalid_uid_is_handled_gracefully(self):
        """7. Malformed or invalid uidb64 is handled safely."""
        invalid_url = reverse('password_reset_confirm', kwargs={'uidb64': 'invalid_uid!', 'token': 'dummy-token'})
        response = self.client.get(invalid_url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['validlink'])

    def test_password_can_be_changed_successfully_and_verified(self):
        """8, 9, 10. Password reset flow updates password, invalidates old password, and allows login."""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        reset_url = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})

        # Load initial reset token to populate session
        get_res = self.client.get(reset_url, follow=True)
        self.assertEqual(get_res.status_code, 200)
        self.assertTrue(get_res.context['validlink'])

        new_password = 'NewBrandNewPassword2026!'
        set_password_url = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': 'set-password'})
        response = self.client.post(set_password_url, {
            'new_password1': new_password,
            'new_password2': new_password,
        })
        self.assertRedirects(response, reverse('password_reset_complete'))

        # Success page
        complete_response = self.client.get(reverse('password_reset_complete'))
        self.assertEqual(complete_response.status_code, 200)
        self.assertContains(complete_response, 'Password reset successful')
        self.assertContains(complete_response, 'Your password has been changed successfully.')
        self.assertContains(complete_response, 'Log in')

        # Old password no longer authenticates
        self.assertIsNone(authenticate(username=self.username, password=self.old_password))

        # New password authenticates
        authenticated_user = authenticate(username=self.username, password=new_password)
        self.assertIsNotNone(authenticated_user)
        self.assertEqual(authenticated_user.pk, self.user.pk)

        # Login with new password works
        login_response = self.client.post(reverse('login'), {
            'username': self.username,
            'password': new_password
        })
        self.assertRedirects(login_response, reverse('dashboard'))

    def test_reset_token_cannot_be_reused(self):
        """Reset token cannot be used again after password has changed."""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        reset_url = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})

        # Change password first time
        self.client.get(reset_url, follow=True)
        set_password_url = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': 'set-password'})
        new_password = 'ValidNewPass12345!'
        self.client.post(set_password_url, {
            'new_password1': new_password,
            'new_password2': new_password,
        })

        # Clear session to simulate a new session/browser trying the link
        self.client.session.flush()

        # Attempting to access the original token link again must now fail
        response = self.client.get(reset_url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['validlink'])

    def test_password_mismatch_shows_validation_error(self):
        """Mismatched passwords show validation error and do not change password."""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        reset_url = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})

        self.client.get(reset_url, follow=True)
        set_password_url = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': 'set-password'})
        response = self.client.post(set_password_url, {
            'new_password1': 'MismatchPassword1!',
            'new_password2': 'MismatchPassword2!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'The two password fields didn’t match.')

        # Old password still intact
        self.assertIsNotNone(authenticate(username=self.username, password=self.old_password))

    def test_weak_password_shows_validation_error(self):
        """Short / weak password shows validation error according to settings validators."""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        reset_url = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})

        self.client.get(reset_url, follow=True)
        set_password_url = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': 'set-password'})
        response = self.client.post(set_password_url, {
            'new_password1': '123',
            'new_password2': '123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)

        # Old password still intact
        self.assertIsNotNone(authenticate(username=self.username, password=self.old_password))

        # Old password still intact
        self.assertIsNotNone(authenticate(username=self.username, password=self.old_password))

    def test_existing_authentication_flows(self):
        """11, 12. Existing login, logout, registration and next-redirect flows remain fully functional."""
        # 1. Login with next redirect
        login_res = self.client.post(f"{reverse('login')}?next=/scripts/", {
            'username': self.username,
            'password': self.old_password
        })
        self.assertRedirects(login_res, '/scripts/')

        # 2. Profile view accessible when authenticated
        profile_res = self.client.get(reverse('profile'))
        self.assertEqual(profile_res.status_code, 200)

        # 3. Logout
        logout_res = self.client.post(reverse('logout'))
        self.assertRedirects(logout_res, reverse('landing'))

        # 4. Anonymous user redirected from protected view
        anon_res = self.client.get(reverse('profile'))
        self.assertRedirects(anon_res, f"{reverse('login')}?next={reverse('profile')}")

    def test_case_insensitive_and_whitespace_email_reset_request(self):
        """Mixed-case and whitespace-padded registered email still finds the user and sends reset email."""
        response = self.client.post(
            reverse('password_reset'),
            {'email': '  WRITER@KADHASCRIPT.COM  '},
        )
        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.email])

    def test_inactive_and_unusable_password_users_do_not_receive_reset_email(self):
        """Inactive users and users without a usable password receive generic redirect and no email."""
        inactive_user = User.objects.create_user(
            username='inactive_writer',
            email='inactive@kadhascript.com',
            password='ValidPassword123!',
            is_active=False,
        )
        unusable_user = User.objects.create_user(
            username='unusable_writer',
            email='unusable@kadhascript.com',
        )
        unusable_user.set_unusable_password()
        unusable_user.save()

        res_inactive = self.client.post(reverse('password_reset'), {'email': inactive_user.email})
        self.assertRedirects(res_inactive, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 0)

        res_unusable = self.client.post(reverse('password_reset'), {'email': unusable_user.email})
        self.assertRedirects(res_unusable, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(ALLOWED_HOSTS=['kadha-script.onrender.com', 'testserver', 'localhost', '127.0.0.1'])
    def test_reset_email_contains_correct_domain_and_html_multipart_link(self):
        """Generated reset email contains valid reset URL in both plain-text and HTML alternatives."""
        response = self.client.post(
            reverse('password_reset'),
            {'email': self.email},
            HTTP_HOST='kadha-script.onrender.com',
        )
        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]

        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        expected_prefix = f"http://kadha-script.onrender.com/accounts/reset/{uid}/"
        self.assertIn(expected_prefix, sent.body)

        self.assertEqual(len(sent.alternatives), 1)
        html_body, mimetype = sent.alternatives[0]
        self.assertEqual(mimetype, 'text/html')
        self.assertIn(expected_prefix, html_body)
        self.assertIn(self.email, html_body)

    @override_settings(ALLOWED_HOSTS=['kadha-script.onrender.com', 'testserver', 'localhost', '127.0.0.1'])
    def test_production_reverse_proxy_https_reset_link_and_header_trust_safety(self):
        """
        When SECURE_PROXY_SSL_HEADER is configured in production, X-Forwarded-Proto: https
        generates an https:// reset URL. When SECURE_PROXY_SSL_HEADER is None, arbitrary
        client-supplied X-Forwarded-Proto headers over plain HTTP are not trusted.
        """
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))

        # 1. Unsafe/direct deployment (SECURE_PROXY_SSL_HEADER=None): client header ignored
        with override_settings(SECURE_PROXY_SSL_HEADER=None):
            mail.outbox.clear()
            self.client.post(
                reverse('password_reset'),
                {'email': self.email},
                HTTP_HOST='kadha-script.onrender.com',
                HTTP_X_FORWARDED_PROTO='https',
            )
            self.assertEqual(len(mail.outbox), 1)
            self.assertIn(f"http://kadha-script.onrender.com/accounts/reset/{uid}/", mail.outbox[0].body)

        # 2. Production behind Render reverse proxy (SECURE_PROXY_SSL_HEADER set)
        with override_settings(
            SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'),
            CSRF_TRUSTED_ORIGINS=['https://kadha-script.onrender.com'],
        ):
            mail.outbox.clear()
            self.client.post(
                reverse('password_reset'),
                {'email': self.email},
                HTTP_HOST='kadha-script.onrender.com',
                HTTP_X_FORWARDED_PROTO='https',
            )
            self.assertEqual(len(mail.outbox), 1)
            self.assertIn(f"https://kadha-script.onrender.com/accounts/reset/{uid}/", mail.outbox[0].body)

    def test_email_backend_exception_prevents_enumeration_and_logs_safely(self):
        """
        When the email backend fails, registered and unregistered addresses must receive
        the same generic confirmation redirect and page without account enumeration,
        no SMTP exception details or credentials may be exposed, and the failure is logged safely.
        """
        secret_password = 'super-secret-smtp-password-98765'
        with override_settings(
            EMAIL_HOST='smtp.gmail.com',
            EMAIL_PORT=587,
            EMAIL_USE_TLS=True,
            EMAIL_USE_SSL=False,
            EMAIL_HOST_USER='sender@kadhascript.com',
            EMAIL_HOST_PASSWORD=secret_password,
        ):
            with patch(
                'django.contrib.auth.forms.PasswordResetForm.send_mail',
                side_effect=smtplib.SMTPAuthenticationError(535, b'Authentication credentials invalid'),
            ):
                with self.assertLogs('accounts.views', level='ERROR') as cm:
                    reg_res = self.client.post(
                        reverse('password_reset'),
                        {'email': self.email},
                        follow=True,
                    )
                unreg_res = self.client.post(
                    reverse('password_reset'),
                    {'email': 'unknown.user@kadhascript.com'},
                    follow=True,
                )

        # Registered and unregistered emails receive the exact same redirect target and status
        self.assertRedirects(reg_res, reverse('password_reset_done'))
        self.assertRedirects(unreg_res, reverse('password_reset_done'))
        self.assertEqual(reg_res.status_code, 200)
        self.assertEqual(unreg_res.status_code, 200)

        # Confirmation page uses conditional non-guaranteeing wording
        self.assertContains(reg_res, 'We have received your password reset request.')
        self.assertContains(reg_res, 'If an account exists with that email address, you will receive instructions')
        self.assertNotContains(reg_res, 'Password reset instructions have been dispatched.')

        # Sensitive details must not be shown to the user
        self.assertNotContains(reg_res, 'SMTPAuthenticationError')
        self.assertNotContains(reg_res, '535')
        self.assertNotContains(reg_res, secret_password)

        # Diagnostic log contains error_type and non-secret transport config, but never secrets
        log_output = "\n".join(cm.output)
        self.assertIn('SMTPAuthenticationError', log_output)
        self.assertIn('host=smtp.gmail.com', log_output)
        self.assertIn('port=587', log_output)
        self.assertNotIn(secret_password, log_output)

    def test_resend_reset_email_form_on_done_page_and_csrf_protection(self):
        """
        Password reset done page includes a CSRF-protected POST form to resend the reset email,
        and submitting it sends another working reset email.
        """
        # 1. Initial reset request
        first_res = self.client.post(reverse('password_reset'), {'email': self.email})
        self.assertRedirects(first_res, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)

        # 2. Done page renders the POST resend form with CSRF token and submit button
        done_res = self.client.get(reverse('password_reset_done'))
        self.assertEqual(done_res.status_code, 200)
        self.assertContains(done_res, 'Resend reset email')
        self.assertContains(done_res, f'action="{reverse("password_reset")}"')
        self.assertContains(done_res, 'name="csrfmiddlewaretoken"')
        self.assertContains(done_res, 'name="email"')

        # 3. Submitting the resend POST form sends a fresh reset email
        second_res = self.client.post(reverse('password_reset'), {'email': self.email})
        self.assertRedirects(second_res, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 2)

        # Extract the reset path from the second email and confirm it works
        second_body = mail.outbox[1].body
        match = re.search(r'(/accounts/reset/[^/]+/[^/\s]+/)', second_body)
        self.assertIsNotNone(match)
        confirm_res = self.client.get(match.group(1), follow=True)
        self.assertEqual(confirm_res.status_code, 200)
        self.assertTrue(confirm_res.context['validlink'])

        # 4. Verify CSRF protection is enforced on POST
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_res = csrf_client.post(reverse('password_reset'), {'email': self.email})
        self.assertEqual(csrf_res.status_code, 403)

    @override_settings(PASSWORD_RESET_TIMEOUT=-1)
    def test_expired_reset_token_is_rejected(self):
        """Expired reset token is rejected safely with validlink=False and a link to request a new one."""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        reset_url = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})

        response = self.client.get(reset_url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['validlink'])
        self.assertContains(response, 'Reset Link Invalid')
        self.assertContains(response, 'Request a new reset link')

    def test_common_and_numeric_password_validators_enforced(self):
        """Common and purely numeric passwords are rejected during password reset."""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        reset_url = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
        self.client.get(reset_url, follow=True)
        set_password_url = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': 'set-password'})

        # Common password
        common_res = self.client.post(set_password_url, {
            'new_password1': 'password123',
            'new_password2': 'password123',
        })
        self.assertEqual(common_res.status_code, 200)
        self.assertTrue(common_res.context['form'].errors)

        # Numeric password
        numeric_res = self.client.post(set_password_url, {
            'new_password1': '123456789',
            'new_password2': '123456789',
        })
        self.assertEqual(numeric_res.status_code, 200)
        self.assertTrue(numeric_res.context['form'].errors)
        self.assertIsNotNone(authenticate(username=self.username, password=self.old_password))

    def test_email_settings_timeout_and_tls_ssl_mutual_exclusion(self):
        """Settings define a positive EMAIL_TIMEOUT and never enable both EMAIL_USE_TLS and EMAIL_USE_SSL."""
        self.assertTrue(hasattr(settings, 'EMAIL_TIMEOUT'))
        self.assertGreater(settings.EMAIL_TIMEOUT, 0)
        self.assertFalse(settings.EMAIL_USE_TLS and settings.EMAIL_USE_SSL)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class EmailLoginAuthenticationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = "ValidSecret123!"
        self.user = User.objects.create_user(
            username="writer_ravi",
            email="ravi.screenwriter@kadhascript.com",
            password=self.password,
            first_name="Ravi"
        )
        Profile.objects.get_or_create(user=self.user, defaults={'pen_name': 'Ravi Screenwriter'})

    def test_login_page_renders_email_field_and_no_visible_username_field(self):
        """Login template displays Email Address input and no visible Username field."""
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        self.assertIn('Email Address', content)
        self.assertIn('name="email"', content)
        self.assertIn('id="id_email"', content)
        self.assertIn('type="email"', content)
        self.assertIn('placeholder="name@example.com"', content)
        self.assertIn('name="password"', content)
        self.assertIn('id="id_password"', content)
        self.assertNotIn('name="username"', content)
        self.assertNotIn('>Username<', content)

    def test_successful_email_login(self):
        """User can log in using their exact registered email and password."""
        response = self.client.post(reverse('login'), {
            'email': 'ravi.screenwriter@kadhascript.com',
            'password': self.password
        })
        self.assertRedirects(response, reverse('dashboard'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_case_insensitive_email_login(self):
        """Email matching is case-insensitive (e.g. mixed-case and uppercase)."""
        response = self.client.post(reverse('login'), {
            'email': 'RAVI.SCREENWRITER@KADHASCRIPT.COM',
            'password': self.password
        })
        self.assertRedirects(response, reverse('dashboard'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_whitespace_handling_in_email_login(self):
        """Surrounding whitespace in email input is stripped safely."""
        response = self.client.post(reverse('login'), {
            'email': '   ravi.screenwriter@kadhascript.com   ',
            'password': self.password
        })
        self.assertRedirects(response, reverse('dashboard'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_invalid_password_returns_generic_error(self):
        """Invalid password returns standard generic error and does not log in."""
        response = self.client.post(reverse('login'), {
            'email': 'ravi.screenwriter@kadhascript.com',
            'password': 'WrongPassword999!'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid email or password. Please try again.')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_unknown_email_returns_generic_error(self):
        """Unknown email returns identical generic error without revealing account existence."""
        response = self.client.post(reverse('login'), {
            'email': 'nonexistent.writer@kadhascript.com',
            'password': self.password
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid email or password. Please try again.')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_empty_credentials_rejected(self):
        """Empty email or empty password is rejected with form validation error."""
        response = self.client.post(reverse('login'), {
            'email': '   ',
            'password': ''
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)

    def test_legacy_username_compatibility(self):
        """Legacy username login works through the email input as backward compatibility fallback."""
        response = self.client.post(reverse('login'), {
            'email': 'writer_ravi',
            'password': self.password
        })
        self.assertRedirects(response, reverse('dashboard'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_legacy_username_post_data_compatibility(self):
        """Legacy callers submitting 'username' parameter are accepted by the form."""
        response = self.client.post(reverse('login'), {
            'username': 'ravi.screenwriter@kadhascript.com',
            'password': self.password
        })
        self.assertRedirects(response, reverse('dashboard'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_duplicate_email_ambiguity_safety(self):
        """When duplicate accounts have the same email and same password, authentication is rejected as ambiguous."""
        User.objects.create_user(
            username="writer_ravi_clone",
            email="ravi.screenwriter@kadhascript.com",
            password=self.password
        )
        response = self.client.post(reverse('login'), {
            'email': 'ravi.screenwriter@kadhascript.com',
            'password': self.password
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid email or password. Please try again.')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_inactive_account_cannot_log_in(self):
        """Inactive accounts (is_active=False) cannot log in."""
        self.user.is_active = False
        self.user.save()
        response = self.client.post(reverse('login'), {
            'email': 'ravi.screenwriter@kadhascript.com',
            'password': self.password
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid email or password. Please try again.')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_registration_success_message_does_not_leak_username(self):
        """Registration success message greets the user by name without exposing the internal username."""
        response = self.client.post(reverse('register'), {
            'full_name': 'Anoop Menon',
            'email': 'anoop.menon@cinema.com',
            'password': 'StrongPassword2026!'
        }, follow=True)
        self.assertRedirects(response, reverse('dashboard'))
        content = response.content.decode('utf-8')
        created_user = User.objects.get(email='anoop.menon@cinema.com')
        self.assertIn('Welcome to KadhaScript, Anoop!', content)
        self.assertNotIn(f'Welcome to KadhaScript, {created_user.username}!', content)

    def test_password_reset_email_wording_omits_username(self):
        """Password reset email does not instruct the user about or expose an internal username."""
        self.client.post(reverse('password_reset'), {
            'email': 'ravi.screenwriter@kadhascript.com'
        })
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertNotIn('Your username:', sent.body)
        self.assertIn('Your account email: ravi.screenwriter@kadhascript.com', sent.body)

    def test_login_redirect_and_session_preservation(self):
        """Next parameter redirect is preserved when logging in via email."""
        response = self.client.post(f"{reverse('login')}?next=/scripts/", {
            'email': 'ravi.screenwriter@kadhascript.com',
            'password': self.password
        })
        self.assertRedirects(response, '/scripts/')
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

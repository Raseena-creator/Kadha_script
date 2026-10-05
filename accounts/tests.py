from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.urls import reverse
from django.core import mail
from accounts.models import Profile


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

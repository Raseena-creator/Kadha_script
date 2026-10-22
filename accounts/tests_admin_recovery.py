import os
from io import StringIO
from unittest.mock import patch

from django.test import TestCase
from django.core.management import call_command
from django.contrib.auth import get_user_model

User = get_user_model()


class EnsureAdminRecoveryCommandTests(TestCase):
    """
    Automated tests verifying the safety, idempotency, and collision protection
    of the ensure_admin_recovery management command.
    """

    def setUp(self):
        super().setUp()
        self.stdout = StringIO()

    def test_disabled_mode_makes_no_changes(self):
        """1. When ADMIN_RECOVERY_ENABLED is disabled or unset, no DB changes occur."""
        env = {
            'ADMIN_RECOVERY_ENABLED': 'false',
            'ADMIN_RECOVERY_USERNAME': 'recovery_admin',
            'ADMIN_RECOVERY_EMAIL': 'recovery@kadhascript.com',
            'ADMIN_RECOVERY_PASSWORD': 'SecurePass123!@#',
        }
        with patch.dict(os.environ, env, clear=True):
            call_command('ensure_admin_recovery', stdout=self.stdout)

        output = self.stdout.getvalue()
        self.assertIn("Admin recovery mode is disabled", output)
        self.assertEqual(User.objects.count(), 0)

    def test_missing_settings_makes_no_changes(self):
        """2. When enabled but credentials/settings are incomplete, no DB changes occur."""
        env = {
            'ADMIN_RECOVERY_ENABLED': 'true',
            'ADMIN_RECOVERY_USERNAME': 'recovery_admin',
            'ADMIN_RECOVERY_EMAIL': 'recovery@kadhascript.com',
            'ADMIN_RECOVERY_PASSWORD': '',  # missing password
        }
        with patch.dict(os.environ, env, clear=True):
            call_command('ensure_admin_recovery', stdout=self.stdout)

        output = self.stdout.getvalue()
        self.assertIn("missing or empty", output)
        self.assertEqual(User.objects.count(), 0)

    def test_successful_superuser_creation(self):
        """3. When enabled with unused credentials, creates an administrative superuser safely."""
        env = {
            'ADMIN_RECOVERY_ENABLED': 'true',
            'ADMIN_RECOVERY_USERNAME': 'recovery_admin',
            'ADMIN_RECOVERY_EMAIL': 'recovery@kadhascript.com',
            'ADMIN_RECOVERY_PASSWORD': '  SuperSecretPassword987!  ',
        }
        with patch.dict(os.environ, env, clear=True):
            call_command('ensure_admin_recovery', stdout=self.stdout)

        output = self.stdout.getvalue()
        self.assertIn("Successfully created administrative superuser 'recovery_admin'", output)
        # Ensure password is never printed to stdout
        self.assertNotIn('SuperSecretPassword987!', output)

        # Verify DB state
        self.assertEqual(User.objects.count(), 1)
        user = User.objects.get(username='recovery_admin')
        self.assertEqual(user.email, 'recovery@kadhascript.com')
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_active)
        # Verify leading and trailing spaces are preserved exactly as supplied
        self.assertTrue(user.check_password('  SuperSecretPassword987!  '))
        self.assertFalse(user.check_password('SuperSecretPassword987!'))

    def test_existing_username_collision_aborts_without_modification(self):
        """4. If username is already taken by an existing account, aborts without modifying it."""
        original_user = User.objects.create_user(
            username='recovery_admin',
            email='client@example.com',
            password='OriginalPassword123'
        )
        self.assertFalse(original_user.is_staff)
        self.assertFalse(original_user.is_superuser)

        env = {
            'ADMIN_RECOVERY_ENABLED': 'true',
            'ADMIN_RECOVERY_USERNAME': 'recovery_admin',
            'ADMIN_RECOVERY_EMAIL': 'new_recovery@kadhascript.com',
            'ADMIN_RECOVERY_PASSWORD': 'AttackerPassword999!',
        }
        with patch.dict(os.environ, env, clear=True):
            call_command('ensure_admin_recovery', stdout=self.stdout)

        output = self.stdout.getvalue()
        self.assertIn("Account collision detected for username 'recovery_admin'", output)

        # Confirm original user is completely untouched
        original_user.refresh_from_db()
        self.assertEqual(original_user.email, 'client@example.com')
        self.assertFalse(original_user.is_staff)
        self.assertFalse(original_user.is_superuser)
        self.assertTrue(original_user.check_password('OriginalPassword123'))
        self.assertFalse(original_user.check_password('AttackerPassword999!'))
        self.assertEqual(User.objects.count(), 1)

    def test_existing_email_collision_aborts_without_modification(self):
        """5. If email is already taken by an existing account, aborts without modifying it."""
        original_user = User.objects.create_user(
            username='client_user',
            email='recovery@kadhascript.com',
            password='OriginalPassword123'
        )
        self.assertFalse(original_user.is_staff)
        self.assertFalse(original_user.is_superuser)

        env = {
            'ADMIN_RECOVERY_ENABLED': 'true',
            'ADMIN_RECOVERY_USERNAME': 'recovery_admin',
            'ADMIN_RECOVERY_EMAIL': 'recovery@kadhascript.com',
            'ADMIN_RECOVERY_PASSWORD': 'AttackerPassword999!',
        }
        with patch.dict(os.environ, env, clear=True):
            call_command('ensure_admin_recovery', stdout=self.stdout)

        output = self.stdout.getvalue()
        self.assertIn("Account collision detected for username 'recovery_admin' or the provided email", output)

        # Confirm original user is completely untouched
        original_user.refresh_from_db()
        self.assertEqual(original_user.username, 'client_user')
        self.assertFalse(original_user.is_staff)
        self.assertFalse(original_user.is_superuser)
        self.assertTrue(original_user.check_password('OriginalPassword123'))
        self.assertFalse(original_user.check_password('AttackerPassword999!'))
        self.assertEqual(User.objects.count(), 1)

    def test_repeat_execution_is_idempotent_and_non_destructive(self):
        """6. Re-running with existing recovery superuser skips modification safely."""
        env = {
            'ADMIN_RECOVERY_ENABLED': 'true',
            'ADMIN_RECOVERY_USERNAME': 'recovery_admin',
            'ADMIN_RECOVERY_EMAIL': 'recovery@kadhascript.com',
            'ADMIN_RECOVERY_PASSWORD': 'InitialPassword123!',
        }
        # First execution: creates user
        with patch.dict(os.environ, env, clear=True):
            call_command('ensure_admin_recovery', stdout=self.stdout)

        user = User.objects.get(username='recovery_admin')
        initial_pw_hash = user.password

        # Second execution: repeat with same environment
        stdout_second = StringIO()
        with patch.dict(os.environ, env, clear=True):
            call_command('ensure_admin_recovery', stdout=stdout_second)

        output_second = stdout_second.getvalue()
        self.assertIn("Superuser account 'recovery_admin' already exists", output_second)
        self.assertIn("Idempotent skip: no account modifications or password resets performed", output_second)

        # Confirm count and hash remain unchanged
        self.assertEqual(User.objects.count(), 1)
        user.refresh_from_db()
        self.assertEqual(user.password, initial_pw_hash)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)

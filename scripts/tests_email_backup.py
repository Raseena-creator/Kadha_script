import io
import os
from unittest.mock import MagicMock, patch
from datetime import date
from django.test import TestCase, override_settings
from django.core import mail
from django.core.management import call_command
from django.contrib.auth.models import User
from django.utils import timezone

from scripts.models import Script, Scene, ScriptElement, ScriptBackupLog
from scripts.services.pdf_export import generate_screenplay_pdf
from scripts.services.email_backup_service import (
    send_daily_script_backup,
    run_daily_email_backup,
    resolve_script_owner_email,
    generate_backup_filename,
    build_backup_email_message,
    EmailConfigError,
    EmailBackupError
)


class DynamicEmailBackupTests(TestCase):
    def setUp(self):
        # User 1: Filmmaker with valid email
        self.user1 = User.objects.create_user(
            username='filmmaker_rasi',
            email='rasi_director@kadhascript.com',
            password='SecurePassword123!'
        )
        self.script1 = Script.objects.create(
            user=self.user1,
            title='ആരണ്യം (Aaranyam)',
            author_name='Rasi K.',
            genre='Thriller',
            script_type='Feature Film',
            language='Malayalam'
        )
        self.scene1 = Scene.objects.create(
            script=self.script1,
            scene_number=1,
            heading='INT. FOREST CABIN - NIGHT',
            transition='CUT TO',
            order=0
        )
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type='scene_heading',
            content='INT. FOREST CABIN - NIGHT',
            order=0
        )
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type='action',
            content='കാറ്റിന്റെ ശബ്ദം പുറത്ത് കേൾക്കുന്നു.',
            order=1
        )
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type='character',
            content='വിക്രം',
            order=2
        )
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type='dialogue',
            content='നമുക്ക് ഇവിടെ നിന്ന് ഉടൻ പോകണം.',
            order=3
        )

        # User 2: Another writer with different email
        self.user2 = User.objects.create_user(
            username='writer_jane',
            email='jane_writer@kadhascript.com',
            password='SecurePassword456!'
        )
        self.script2 = Script.objects.create(
            user=self.user2,
            title='City of Shadows',
            author_name='Jane Doe',
            genre='Crime',
            script_type='Short Film',
            language='English'
        )
        self.scene2 = Scene.objects.create(
            script=self.script2,
            scene_number=1,
            heading='EXT. STREET - RAIN',
            order=0
        )
        ScriptElement.objects.create(
            scene=self.scene2,
            element_type='action',
            content='Rain pours heavily on the neon-lit asphalt.',
            order=0
        )

        # User 3: User without an email address configured
        self.user_no_email = User.objects.create_user(
            username='writer_no_email',
            email='',
            password='SecurePassword789!'
        )
        self.script_no_email = Script.objects.create(
            user=self.user_no_email,
            title='Silent Whispers',
            author_name='Anonymous',
            genre='Drama',
            script_type='Short Film',
            language='Malayalam'
        )

    def test_pdf_generation_succeeds_for_backup(self):
        """Reuses existing generate_screenplay_pdf logic and returns valid PDF bytes."""
        pdf_bytes = generate_screenplay_pdf(self.script1, include_notes=False)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 500)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))

    def test_backup_filename_format(self):
        """Verifies filename format matches KadhaScript_<script-name>_<YYYY-MM-DD>.pdf."""
        test_date = date(2026, 10, 5)
        filename1 = generate_backup_filename(self.script1, test_date)
        self.assertEqual(filename1, 'KadhaScript_ആരണ്യം_(Aaranyam)_2026-10-05.pdf')

        filename2 = generate_backup_filename(self.script2, test_date)
        self.assertEqual(filename2, 'KadhaScript_City_of_Shadows_2026-10-05.pdf')

    def test_resolve_script_owner_email_success(self):
        """Resolves recipient dynamically from script.user.email."""
        email1 = resolve_script_owner_email(self.script1)
        self.assertEqual(email1, 'rasi_director@kadhascript.com')

        email2 = resolve_script_owner_email(self.script2)
        self.assertEqual(email2, 'jane_writer@kadhascript.com')

    def test_resolve_script_owner_email_missing_raises_error(self):
        """Raises EmailConfigError with clear message when user has no email."""
        with self.assertRaises(EmailConfigError) as ctx:
            resolve_script_owner_email(self.script_no_email)
        self.assertIn("writer_no_email", str(ctx.exception))
        self.assertIn("does not have a configured email address", str(ctx.exception))

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        DEFAULT_FROM_EMAIL='KadhaScript Backup <backups@kadhascript.com>'
    )
    def test_script_owner_email_is_used_as_recipient(self):
        """Backup email for script1 is sent dynamically to user1's email."""
        test_date = date(2026, 10, 5)
        res = send_daily_script_backup(
            script=self.script1,
            backup_date=test_date
        )

        self.assertTrue(res['success'])
        self.assertFalse(res['skipped'])
        self.assertEqual(res['recipient'], 'rasi_director@kadhascript.com')
        self.assertEqual(len(mail.outbox), 1)

        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.to, ['rasi_director@kadhascript.com'])
        self.assertIn('KadhaScript', sent_email.subject)
        self.assertIn('ആരണ്യം (Aaranyam)', sent_email.subject)
        self.assertIn('2026-10-05', sent_email.subject)

        # Audit log verification
        log = ScriptBackupLog.objects.filter(
            script=self.script1,
            backup_date=test_date,
            backup_type='EMAIL',
            status='SUCCESS'
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.recipient_email, 'rasi_director@kadhascript.com')
        self.assertEqual(log.filename, 'KadhaScript_ആരണ്യം_(Aaranyam)_2026-10-05.pdf')
        self.assertTrue(log.file_size > 0)

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'
    )
    def test_different_users_scripts_go_to_different_email_addresses(self):
        """Batch backup routes each script exclusively to its respective owner's email address."""
        test_date = date(2026, 10, 5)
        out = run_daily_email_backup(backup_date=test_date)

        # script1 (user1), script2 (user2) succeed; script_no_email (user_no_email) fails safely
        self.assertFalse(out['success'])  # Because 1 failed safely
        self.assertEqual(out['total_scripts'], 3)
        self.assertEqual(out['successful_count'], 2)
        self.assertEqual(out['failed_count'], 1)

        self.assertEqual(len(mail.outbox), 2)
        recipients = [m.to[0] for m in mail.outbox]
        self.assertIn('rasi_director@kadhascript.com', recipients)
        self.assertIn('jane_writer@kadhascript.com', recipients)

        # Verify mapping: email with Aaranyam goes to user1, email with City of Shadows goes to user2
        for m in mail.outbox:
            if 'ആരണ്യം' in m.subject:
                self.assertEqual(m.to, ['rasi_director@kadhascript.com'])
            elif 'City of Shadows' in m.subject:
                self.assertEqual(m.to, ['jane_writer@kadhascript.com'])

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'
    )
    def test_missing_owner_email_fails_safely_and_logs(self):
        """Script with no owner email records FAILED in ScriptBackupLog and does not send email."""
        test_date = date(2026, 10, 5)
        res = send_daily_script_backup(
            script=self.script_no_email,
            backup_date=test_date
        )

        self.assertFalse(res['success'])
        self.assertIn("does not have a configured email address", res['error'])
        self.assertEqual(len(mail.outbox), 0)

        log = ScriptBackupLog.objects.filter(
            script=self.script_no_email,
            backup_date=test_date,
            backup_type='EMAIL',
            status='FAILED'
        ).first()
        self.assertIsNotNone(log)
        self.assertIn("does not have a configured email address", log.error_message)
        self.assertEqual(log.recipient_email, '')

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'
    )
    def test_duplicate_protection_prevents_re_sending(self):
        """Duplicate backup on the same day is skipped by default; --force forces resending."""
        test_date = date(2026, 10, 5)

        # First run: sends
        res1 = send_daily_script_backup(script=self.script1, backup_date=test_date)
        self.assertTrue(res1['success'])
        self.assertFalse(res1['skipped'])
        self.assertEqual(len(mail.outbox), 1)

        # Second run: skipped
        res2 = send_daily_script_backup(script=self.script1, backup_date=test_date, force=False)
        self.assertTrue(res2['success'])
        self.assertTrue(res2['skipped'])
        self.assertIn('already sent', res2['reason'].lower())
        self.assertEqual(len(mail.outbox), 1)

        # Third run with force=True: resends
        res3 = send_daily_script_backup(script=self.script1, backup_date=test_date, force=True)
        self.assertTrue(res3['success'])
        self.assertFalse(res3['skipped'])
        self.assertEqual(len(mail.outbox), 2)

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'
    )
    def test_pdf_generation_failure_logged_gracefully(self):
        """PDF generation error is captured, recorded as FAILED, and returns error response."""
        test_date = date(2026, 10, 5)
        with patch('scripts.services.email_backup_service.generate_screenplay_pdf', side_effect=RuntimeError("Font rendering corrupted")):
            res = send_daily_script_backup(script=self.script1, backup_date=test_date)
            self.assertFalse(res['success'])
            self.assertIn("Font rendering corrupted", res['error'])

            log = ScriptBackupLog.objects.filter(
                script=self.script1,
                backup_date=test_date,
                backup_type='EMAIL',
                status='FAILED'
            ).first()
            self.assertIsNotNone(log)
            self.assertIn("Font rendering corrupted", log.error_message)

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'
    )
    def test_email_send_failure_logged_gracefully(self):
        """SMTP / network failure is captured, recorded as FAILED, and does not expose secrets."""
        test_date = date(2026, 10, 5)
        with patch.object(mail.EmailMessage, 'send', side_effect=Exception("SMTPAuthenticationError: Username and Password not accepted")):
            res = send_daily_script_backup(script=self.script1, backup_date=test_date)
            self.assertFalse(res['success'])
            self.assertIn("SMTPAuthenticationError", res['error'])

            log = ScriptBackupLog.objects.filter(
                script=self.script1,
                backup_date=test_date,
                backup_type='EMAIL',
                status='FAILED'
            ).first()
            self.assertIsNotNone(log)
            self.assertIn("SMTPAuthenticationError", log.error_message)

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'
    )
    def test_management_command_send_daily_backup(self):
        """Tests python manage.py send_daily_backup for specific script with dynamic email delivery."""
        test_date_str = '2026-10-05'
        out = io.StringIO()
        call_command(
            'send_daily_backup',
            '--script-id', str(self.script1.id),
            '--date', test_date_str,
            stdout=out
        )
        output_str = out.getvalue()
        self.assertIn('[SUCCESS]', output_str)
        self.assertIn('rasi_director@kadhascript.com', output_str)
        self.assertEqual(len(mail.outbox), 1)

        # Second execution for same script should skip duplicate
        out2 = io.StringIO()
        call_command(
            'send_daily_backup',
            '--script-id', str(self.script1.id),
            '--date', test_date_str,
            stdout=out2
        )
        output_str2 = out2.getvalue()
        self.assertIn('[SKIPPED]', output_str2)
        self.assertEqual(len(mail.outbox), 1)

        # Third execution with --force should send again
        out3 = io.StringIO()
        call_command(
            'send_daily_backup',
            '--script-id', str(self.script1.id),
            '--date', test_date_str,
            '--force',
            stdout=out3
        )
        output_str3 = out3.getvalue()
        self.assertIn('[SUCCESS]', output_str3)
        self.assertEqual(len(mail.outbox), 2)

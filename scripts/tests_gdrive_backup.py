import io
import os
import re
from unittest.mock import MagicMock, patch
from datetime import date
from django.test import TestCase
from django.core.management import call_command
from django.contrib.auth.models import User

from scripts.models import Script, Scene, ScriptElement
from scripts.services.gdrive_backup_service import (
    run_daily_screenplay_backup,
    get_or_create_backup_folder,
    upload_pdf_to_drive,
    prune_old_drive_backups,
    save_local_backup,
    GoogleDriveAuthError,
    GoogleDriveBackupError,
    GOOGLE_DRIVE_FOLDER_NAME
)


class GoogleDriveBackupTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='director', password='Password123!')
        self.script = Script.objects.create(
            user=self.user,
            title='The Malayalam Epic',
            author_name='A. Director',
            genre='Drama',
            script_type='Feature Film',
            language='Malayalam'
        )
        self.scene1 = Scene.objects.create(
            script=self.script,
            scene_number=1,
            heading='INT. PALACE - DAY',
            transition='CUT TO',
            order=0
        )
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type='action',
            content='The king sits on the royal throne.',
            order=0
        )
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type='note',
            content='SECRET NOTE: King will give sword here.',
            order=1
        )
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type='character',
            content='KING',
            order=2
        )
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type='dialogue',
            content='ഇവിടെ ആരംഭിക്കുന്നു (It begins here).',
            order=3
        )

    def test_get_or_create_backup_folder_existing(self):
        """When folder exists on Drive, return its ID without creating a new folder."""
        mock_drive = MagicMock()
        mock_list = MagicMock()
        mock_list.execute.return_value = {
            'files': [{'id': 'folder_12345', 'name': GOOGLE_DRIVE_FOLDER_NAME}]
        }
        mock_drive.files().list.return_value = mock_list

        folder_id = get_or_create_backup_folder(mock_drive, GOOGLE_DRIVE_FOLDER_NAME)
        self.assertEqual(folder_id, 'folder_12345')
        mock_drive.files().create.assert_not_called()

    def test_get_or_create_backup_folder_new(self):
        """When folder does not exist, create it and return the new ID."""
        mock_drive = MagicMock()
        mock_list = MagicMock()
        mock_list.execute.return_value = {'files': []}
        mock_drive.files().list.return_value = mock_list

        mock_create = MagicMock()
        mock_create.execute.return_value = {'id': 'new_folder_999'}
        mock_drive.files().create.return_value = mock_create

        folder_id = get_or_create_backup_folder(mock_drive, GOOGLE_DRIVE_FOLDER_NAME)
        self.assertEqual(folder_id, 'new_folder_999')
        mock_drive.files().create.assert_called_once()

    def test_upload_pdf_to_drive_new_file(self):
        """When file does not exist, upload a new file."""
        mock_drive = MagicMock()
        mock_list = MagicMock()
        mock_list.execute.return_value = {'files': []}
        mock_drive.files().list.return_value = mock_list

        mock_create = MagicMock()
        mock_create.execute.return_value = {
            'id': 'file_001',
            'name': 'KadhaScript_2026-10-04.pdf',
            'createdTime': '2026-10-04T00:00:00Z',
            'size': '45000'
        }
        mock_drive.files().create.return_value = mock_create

        result = upload_pdf_to_drive(
            mock_drive,
            b'%PDF-1.4 test',
            'KadhaScript_2026-10-04.pdf',
            'folder_12345'
        )
        self.assertEqual(result['id'], 'file_001')
        mock_drive.files().create.assert_called_once()
        mock_drive.files().update.assert_not_called()

    def test_upload_pdf_to_drive_existing_file_idempotency(self):
        """When file already exists for today's date, update existing snapshot without duplicate files."""
        mock_drive = MagicMock()
        mock_list = MagicMock()
        mock_list.execute.return_value = {
            'files': [{'id': 'existing_file_001', 'name': 'KadhaScript_2026-10-04.pdf'}]
        }
        mock_drive.files().list.return_value = mock_list

        mock_update = MagicMock()
        mock_update.execute.return_value = {
            'id': 'existing_file_001',
            'name': 'KadhaScript_2026-10-04.pdf',
            'createdTime': '2026-10-04T12:00:00Z',
            'size': '48000'
        }
        mock_drive.files().update.return_value = mock_update

        result = upload_pdf_to_drive(
            mock_drive,
            b'%PDF-1.4 updated test',
            'KadhaScript_2026-10-04.pdf',
            'folder_12345'
        )
        self.assertEqual(result['id'], 'existing_file_001')
        mock_drive.files().update.assert_called_once()
        mock_drive.files().create.assert_not_called()

    def test_prune_old_drive_backups_within_retention_limit(self):
        """If 30 or fewer backups exist, do not delete any files."""
        mock_drive = MagicMock()
        mock_list = MagicMock()
        mock_list.execute.return_value = {
            'files': [{'id': f'f_{i}', 'name': f'KadhaScript_2026-09-{i:02d}.pdf'} for i in range(1, 31)]
        }
        mock_drive.files().list.return_value = mock_list

        deleted = prune_old_drive_backups(mock_drive, 'folder_123', keep_count=30)
        self.assertEqual(deleted, 0)
        mock_drive.files().delete.assert_not_called()

    def test_prune_old_drive_backups_exceeds_retention_limit(self):
        """If more than 30 backups exist, delete files beyond the 30 newest."""
        mock_drive = MagicMock()
        mock_list = MagicMock()
        # 35 backup files
        mock_list.execute.return_value = {
            'files': [{'id': f'f_{i}', 'name': f'KadhaScript_backup_{i}.pdf'} for i in range(1, 36)]
        }
        mock_drive.files().list.return_value = mock_list

        mock_delete = MagicMock()
        mock_delete.execute.return_value = {}
        mock_drive.files().delete.return_value = mock_delete

        deleted = prune_old_drive_backups(mock_drive, 'folder_123', keep_count=30)
        self.assertEqual(deleted, 5)
        self.assertEqual(mock_drive.files().delete.call_count, 5)

    def test_run_daily_screenplay_backup_success(self):
        """Full end-to-end backup pipeline: generate PDF, upload, prune, and verify."""
        mock_drive = MagicMock()

        # Folder search returns existing folder
        mock_folder_list = MagicMock()
        mock_folder_list.execute.return_value = {'files': [{'id': 'fld_1', 'name': GOOGLE_DRIVE_FOLDER_NAME}]}

        # File search returns no existing file
        mock_file_list = MagicMock()
        mock_file_list.execute.return_value = {'files': []}

        def list_side_effect(**kwargs):
            q = kwargs.get('q', '')
            if 'mimeType = \'application/vnd.google-apps.folder\'' in q:
                return mock_folder_list
            return mock_file_list

        mock_drive.files().list.side_effect = list_side_effect

        mock_create = MagicMock()
        mock_create.execute.return_value = {'id': 'uploaded_pdf_id_123', 'name': 'KadhaScript_2026-10-04.pdf'}
        mock_drive.files().create.return_value = mock_create

        test_date = date(2026, 10, 4)
        result = run_daily_screenplay_backup(
            script_id=self.script.id,
            backup_date=test_date,
            drive_service=mock_drive
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['filename'], 'KadhaScript_2026-10-04.pdf')
        self.assertEqual(result['drive_file_id'], 'uploaded_pdf_id_123')
        self.assertTrue(result['pdf_size'] > 1000)
        self.assertIsNotNone(result['local_path'])
        self.assertTrue(os.path.exists(result['local_path']))

    def test_run_daily_screenplay_backup_failure_handling(self):
        """When Drive upload fails, preserve local backup and DO NOT delete older backups."""
        mock_drive = MagicMock()
        mock_drive.files().list.side_effect = Exception("Google Drive API rate limit / 500 error")

        test_date = date(2026, 10, 4)
        result = run_daily_screenplay_backup(
            script_id=self.script.id,
            backup_date=test_date,
            drive_service=mock_drive
        )

        self.assertFalse(result['success'])
        self.assertIn("Google Drive API rate limit", result['error'])
        # Local PDF was preserved
        self.assertIsNotNone(result['local_path'])
        self.assertTrue(os.path.exists(result['local_path']))
        # Older backups were NOT pruned on failure
        self.assertEqual(result['pruned_count'], 0)
        mock_drive.files().delete.assert_not_called()

    def test_management_command_backup_to_gdrive(self):
        """Verify management command backup_to_gdrive runs and handles arguments."""
        with patch('scripts.management.commands.backup_to_gdrive.run_daily_screenplay_backup') as mock_run:
            mock_run.return_value = {
                'success': True,
                'filename': 'KadhaScript_2026-10-04.pdf',
                'script_title': self.script.title,
                'script_id': self.script.id,
                'pdf_size': 12345,
                'drive_file_id': 'drv_123',
                'local_path': '/path/to/local.pdf',
                'pruned_count': 0
            }

            out = io.StringIO()
            call_command('backup_to_gdrive', script_id=self.script.id, date='2026-10-04', stdout=out)
            output = out.getvalue()
            self.assertIn('[SUCCESS]', output)
            self.assertIn('KadhaScript_2026-10-04.pdf', output)

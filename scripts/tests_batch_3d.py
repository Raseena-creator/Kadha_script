import json
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse

from scripts.models import (
    Script, Scene, ScriptElement, Character, ScriptNote, ScriptVersion, ScriptTitlePage, ScriptBackupLog
)

User = get_user_model()


class Batch3DProjectRestorationTests(TestCase):
    """
    Batch 3D Test Suite: Safe Project Restoration and UI Safeguards.
    Covers:
    1. Unauthenticated POST to restore redirects to login.
    2. Authenticated owner can restore their own trashed project.
    3. Successful restoration sets is_deleted=False.
    4. Successful restoration clears deleted_at (None).
    5. Restored project appears on Dashboard and disappears from Trash.
    6. Another user's project cannot be restored by manipulating project ID (returns 404).
    7. A project that is already active cannot be restored again (redirects with info message).
    8. A GET request cannot restore a project (returns 405 Method Not Allowed).
    9. CSRF protection is not bypassed by the implementation (Client(enforce_csrf_checks=True)).
    10. Duplicate active title does not prevent restoration or rename either screenplay, and user receives informative message.
    11. Related records remain completely intact (Scenes, Elements, Characters, Notes, TitlePage, Versions, BackupLogs).
    12. Scene Trash state remains unchanged when parent project is restored.
    13. Scene UUIDs, hierarchy, ordering, and intercut metadata remain unchanged.
    14. Trash Restore form uses POST and includes a CSRF token.
    15. Corrected project-deletion wording is rendered in dashboard and confirmation templates.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='restore_writer',
            email='restore_writer@example.com',
            password='Password123!'
        )
        self.other_user = User.objects.create_user(
            username='other_writer',
            email='other_writer@example.com',
            password='Password123!'
        )

        # Trashed Script
        self.del_time = timezone.now()
        self.trashed_script = Script.objects.create(
            user=self.user,
            title='ആരണ്യം (Aaranyam)',
            description='Original description of Aaranyam',
            genre='Drama',
            script_type='Feature Film',
            is_deleted=True,
            deleted_at=self.del_time
        )

        # Main Scene (active before script trashed)
        self.scene1 = Scene.objects.create(
            script=self.trashed_script,
            scene_number=1,
            heading='INT. CABIN - NIGHT',
            order=0,
            is_deleted=False
        )
        self.elem1 = ScriptElement.objects.create(
            scene=self.scene1,
            element_type='action',
            content='Rain beats heavily against cabin window.',
            order=0
        )

        # Sub-scene (active before script trashed)
        self.sub_scene = Scene.objects.create(
            script=self.trashed_script,
            parent_scene=self.scene1,
            scene_number=1,
            heading='INT. CABIN - ATTIC - NIGHT',
            order=1,
            is_deleted=False
        )

        # Intercut Scene (active before script trashed)
        self.intercut_scene = Scene.objects.create(
            script=self.trashed_script,
            scene_number=2,
            heading='EXT. POLICE CAR - NIGHT',
            order=2,
            is_intercut=True,
            intercut_source=self.scene1,
            is_deleted=False
        )

        # Scene that was INDEPENDENTLY in Scene Trash before the script was trashed
        self.independently_trashed_scene = Scene.objects.create(
            script=self.trashed_script,
            scene_number=3,
            heading='EXT. LAKE - SUNRISE',
            order=3,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        # Character
        self.character = Character.objects.create(
            script=self.trashed_script,
            name='രഘു (Raghu)',
            age=38
        )

        # Note
        self.note = ScriptNote.objects.create(
            script=self.trashed_script,
            title='Climax Twist Idea',
            content='Raghu reveals the truth in the attic.'
        )

        # Title Page
        self.title_page = ScriptTitlePage.objects.create(
            script=self.trashed_script,
            title='ആരണ്യം (Aaranyam)',
            author_name='Rasi Writer',
            draft_revision='Draft 1'
        )

        # Version
        self.version = ScriptVersion.objects.create(
            script=self.trashed_script,
            version_number=1,
            title='Initial Draft Snapshot',
            snapshot_data={'scenes': []}
        )

        # Backup Log
        self.backup_log = ScriptBackupLog.objects.create(
            script=self.trashed_script,
            backup_date=timezone.now().date(),
            backup_type='EMAIL',
            status='SUCCESS'
        )

        # Other User's Trashed Script
        self.other_trashed_script = Script.objects.create(
            user=self.other_user,
            title='മറ്റൊരാളുടെ തിരക്കഥ',
            is_deleted=True,
            deleted_at=timezone.now()
        )

    def test_1_unauthenticated_post_redirects_to_login(self):
        """1. An unauthenticated POST is redirected to login."""
        url = reverse('script_restore', kwargs={'script_id': self.trashed_script.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        expected_redirect = f"{reverse('login')}?next={url}"
        self.assertRedirects(response, expected_redirect)

    def test_2_and_3_and_4_authenticated_owner_can_restore_trashed_project(self):
        """2, 3, 4. Authenticated owner restores project; sets is_deleted=False and clears deleted_at."""
        self.client.force_login(self.user)
        url = reverse('script_restore', kwargs={'script_id': self.trashed_script.id})
        response = self.client.post(url)
        self.assertRedirects(response, reverse('dashboard'))

        self.trashed_script.refresh_from_db()
        self.assertFalse(self.trashed_script.is_deleted)
        self.assertIsNone(self.trashed_script.deleted_at)
        self.assertEqual(self.trashed_script.title, 'ആരണ്യം (Aaranyam)')

    def test_5_restored_project_appears_on_dashboard_and_disappears_from_trash(self):
        """5. Restored project appears on Dashboard and disappears from Trash."""
        self.client.force_login(self.user)
        url = reverse('script_restore', kwargs={'script_id': self.trashed_script.id})
        self.client.post(url)

        # Dashboard view check
        dash_res = self.client.get(reverse('dashboard'))
        self.assertEqual(dash_res.status_code, 200)
        self.assertContains(dash_res, 'ആരണ്യം (Aaranyam)')

        # Trash view check
        trash_res = self.client.get(reverse('script_trash'))
        self.assertEqual(trash_res.status_code, 200)
        self.assertNotContains(trash_res, 'ആരണ്യം (Aaranyam)')

    def test_6_cross_user_project_restoration_rejected(self):
        """6. Another user's project cannot be restored by manipulating the project ID."""
        self.client.force_login(self.user)
        url = reverse('script_restore', kwargs={'script_id': self.other_trashed_script.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

        self.other_trashed_script.refresh_from_db()
        self.assertTrue(self.other_trashed_script.is_deleted)

    def test_7_already_active_project_cannot_be_restored_again(self):
        """7. A project that is already active cannot be restored again."""
        self.client.force_login(self.user)
        # First restore it
        self.trashed_script.is_deleted = False
        self.trashed_script.deleted_at = None
        self.trashed_script.save()

        url = reverse('script_restore', kwargs={'script_id': self.trashed_script.id})
        response = self.client.post(url, follow=True)
        self.assertRedirects(response, reverse('dashboard'))
        self.assertContains(response, 'is already active')

    def test_8_get_request_cannot_restore_project(self):
        """8. A GET request cannot restore a project (Method Not Allowed)."""
        self.client.force_login(self.user)
        url = reverse('script_restore', kwargs={'script_id': self.trashed_script.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

        self.trashed_script.refresh_from_db()
        self.assertTrue(self.trashed_script.is_deleted)

    def test_9_csrf_protection_enforced(self):
        """9. CSRF protection is not bypassed by the implementation."""
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        url = reverse('script_restore', kwargs={'script_id': self.trashed_script.id})
        # Post without CSRF token
        response = csrf_client.post(url)
        self.assertEqual(response.status_code, 403)

        self.trashed_script.refresh_from_db()
        self.assertTrue(self.trashed_script.is_deleted)

    def test_10_duplicate_active_title_restores_safely_with_informative_warning(self):
        """10. Duplicate active title restores without renaming, displaying informative warning."""
        # Create an active project with the exact same title
        active_duplicate = Script.objects.create(
            user=self.user,
            title='ആരണ്യം (Aaranyam)',
            is_deleted=False
        )

        self.client.force_login(self.user)
        url = reverse('script_restore', kwargs={'script_id': self.trashed_script.id})
        response = self.client.post(url, follow=True)
        self.assertRedirects(response, reverse('dashboard'))

        self.trashed_script.refresh_from_db()
        self.assertFalse(self.trashed_script.is_deleted)
        # Original title preserved
        self.assertEqual(self.trashed_script.title, 'ആരണ്യം (Aaranyam)')
        self.assertEqual(active_duplicate.title, 'ആരണ്യം (Aaranyam)')

        # Assert warning message was shown on redirected response
        self.assertContains(response, 'another active screenplay with the same title')

    def test_11_all_related_records_remain_intact(self):
        """11. All child models (scenes, elements, characters, notes, title-page, versions, logs) remain intact."""
        self.client.force_login(self.user)
        url = reverse('script_restore', kwargs={'script_id': self.trashed_script.id})
        self.client.post(url)

        self.assertEqual(self.trashed_script.scenes.count(), 4)
        self.assertEqual(ScriptElement.objects.filter(scene__script=self.trashed_script).count(), 1)
        self.assertEqual(self.trashed_script.characters.count(), 1)
        self.assertEqual(self.trashed_script.notes.count(), 1)
        self.assertTrue(ScriptTitlePage.objects.filter(script=self.trashed_script).exists())
        self.assertEqual(self.trashed_script.versions.count(), 1)
        self.assertEqual(self.trashed_script.backup_logs.count(), 1)

    def test_12_scene_trash_state_remains_unchanged(self):
        """12. Scenes that were independently trashed before project deletion remain trashed."""
        self.client.force_login(self.user)
        url = reverse('script_restore', kwargs={'script_id': self.trashed_script.id})
        self.client.post(url)

        self.independently_trashed_scene.refresh_from_db()
        self.assertTrue(self.independently_trashed_scene.is_deleted)

        self.scene1.refresh_from_db()
        self.assertFalse(self.scene1.is_deleted)

    def test_13_scene_uuids_hierarchy_order_and_intercut_metadata_unchanged(self):
        """13. Scene UUIDs, parent-child hierarchy, order, and intercut references remain untouched."""
        pre_uuid1 = self.scene1.scene_uuid
        pre_sub_uuid = self.sub_scene.scene_uuid
        pre_intercut_uuid = self.intercut_scene.scene_uuid

        self.client.force_login(self.user)
        url = reverse('script_restore', kwargs={'script_id': self.trashed_script.id})
        self.client.post(url)

        self.scene1.refresh_from_db()
        self.sub_scene.refresh_from_db()
        self.intercut_scene.refresh_from_db()

        self.assertEqual(self.scene1.scene_uuid, pre_uuid1)
        self.assertEqual(self.sub_scene.scene_uuid, pre_sub_uuid)
        self.assertEqual(self.intercut_scene.scene_uuid, pre_intercut_uuid)

        # Hierarchy check
        self.assertEqual(self.sub_scene.parent_scene_id, self.scene1.id)
        # Order check
        self.assertEqual(self.scene1.order, 0)
        self.assertEqual(self.sub_scene.order, 1)
        self.assertEqual(self.intercut_scene.order, 2)
        # Intercut check
        self.assertTrue(self.intercut_scene.is_intercut)
        self.assertEqual(self.intercut_scene.intercut_source_id, self.scene1.id)

    def test_14_trash_template_renders_post_restore_form_with_csrf(self):
        """14. The Project Trash page renders a POST restore form with CSRF token for each trashed item."""
        self.client.force_login(self.user)
        response = self.client.get(reverse('script_trash'))
        self.assertEqual(response.status_code, 200)

        expected_action = reverse('script_restore', kwargs={'script_id': self.trashed_script.id})
        self.assertContains(response, f'action="{expected_action}"')
        self.assertContains(response, 'method="POST"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, 'Restore')

    def test_15_corrected_project_deletion_wording_rendered(self):
        """15. Corrected project-deletion wording is rendered in dashboard and confirmation templates."""
        self.client.force_login(self.user)

        # Dashboard modal warning
        dash_res = self.client.get(reverse('dashboard'))
        self.assertEqual(dash_res.status_code, 200)
        self.assertContains(dash_res, 'This screenplay will be moved to Trash and can be restored.')
        self.assertNotContains(dash_res, 'This action cannot be undone.')

        # Direct confirmation delete page
        confirm_res = self.client.get(reverse('script_delete', kwargs={'script_id': self.trashed_script.id}))
        # Note: script_delete requires active script by default, let's test against an active script
        active_sc = Script.objects.create(user=self.user, title='Active Delete Test Script', is_deleted=False)
        confirm_res = self.client.get(reverse('script_delete', kwargs={'script_id': active_sc.id}))
        self.assertEqual(confirm_res.status_code, 200)
        self.assertContains(confirm_res, 'Move Screenplay to Trash?')
        self.assertContains(confirm_res, 'The following items will be moved to Trash:')
        self.assertContains(confirm_res, 'Move to Trash')
        self.assertNotContains(confirm_res, 'Permanently Delete Screenplay?')
        self.assertNotContains(confirm_res, 'Yes, Permanently Delete')

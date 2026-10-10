import json
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from scripts.models import (
    Script, Scene, ScriptElement, Character, ScriptNote, ScriptVersion, ScriptTitlePage
)

User = get_user_model()


class Batch2CDashboardAndProjectSoftDeleteTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='dashboard_writer',
            email='dash@example.com',
            password='password123'
        )
        self.other_user = User.objects.create_user(
            username='other_writer',
            email='other@example.com',
            password='password123'
        )
        self.client.force_login(self.user)

        # Active Script 1
        self.script1 = Script.objects.create(
            user=self.user,
            title='Active Master Screenplay',
            language='Malayalam',
            genre='Drama',
            script_type='Feature Film'
        )
        self.scene1 = Scene.objects.create(
            script=self.script1,
            scene_number=1,
            heading='INT. PALACE - DAY',
            order=0,
            is_deleted=False
        )
        self.element1 = ScriptElement.objects.create(
            scene=self.scene1,
            element_type='action',
            content='രാജാവ് ഇരിക്കുന്നു.',
            order=0
        )
        self.sub_scene1 = Scene.objects.create(
            script=self.script1,
            parent_scene=self.scene1,
            scene_number=1,
            heading='INT. PALACE - CORRIDOR - DAY',
            order=1,
            is_deleted=False
        )
        self.char1 = Character.objects.create(
            script=self.script1,
            name='രാജാവ്',
            age=45
        )
        self.note1 = ScriptNote.objects.create(
            script=self.script1,
            title='Scene 1 Note',
            content='Important opening'
        )
        self.title_page1 = ScriptTitlePage.objects.create(
            script=self.script1,
            title='Active Master Screenplay Title',
            author_name='Royal Writer'
        )
        self.version1 = ScriptVersion.objects.create(
            script=self.script1,
            version_number=1,
            title='Draft 1',
            snapshot_data={'test': 123}
        )

        # Active Script 2
        self.script2 = Script.objects.create(
            user=self.user,
            title='Active Second Screenplay',
            language='Malayalam',
            genre='Thriller',
            script_type='Short Film'
        )
        self.scene2 = Scene.objects.create(
            script=self.script2,
            scene_number=1,
            heading='EXT. ROAD - NIGHT',
            order=0,
            is_deleted=False
        )

        # Trashed Script 3
        self.script_trashed = Script.objects.create(
            user=self.user,
            title='Old Trashed Screenplay',
            language='Malayalam',
            genre='Horror',
            script_type='Feature Film',
            is_deleted=True,
            deleted_at=timezone.now()
        )
        self.trashed_scene = Scene.objects.create(
            script=self.script_trashed,
            scene_number=1,
            heading='INT. HAUNTED HOUSE - NIGHT',
            order=0,
            is_deleted=False
        )

    def test_trashed_projects_excluded_from_dashboard(self):
        """Dashboard lists only active scripts; trashed scripts are excluded."""
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)

        scripts_in_context = list(response.context['scripts'])
        script_ids = [s.id for s in scripts_in_context]

        self.assertIn(self.script1.id, script_ids)
        self.assertIn(self.script2.id, script_ids)
        self.assertNotIn(self.script_trashed.id, script_ids)

    def test_active_project_counts_correct(self):
        """Dashboard statistics accurately reflect only active scripts and active scenes."""
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)

        # Only 2 active scripts
        self.assertEqual(response.context['total_scripts'], 2)
        # Total active scenes across active scripts:
        # script1: 1 primary + 1 sub = 2 scenes
        # script2: 1 primary = 1 scene
        # Total = 3 scenes
        self.assertEqual(response.context['total_scenes'], 3)
        self.assertEqual(response.context['total_primary_scenes'], 2)
        self.assertEqual(response.context['total_sub_scenes'], 1)

    def test_scene_counts_exclude_trashed_scenes(self):
        """Dashboard metrics and project scene counts exclude trashed scenes."""
        # Trash sub_scene1
        self.sub_scene1.is_deleted = True
        self.sub_scene1.deleted_at = timezone.now()
        self.sub_scene1.save()

        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.context['total_scenes'], 2)
        self.assertEqual(response.context['total_sub_scenes'], 0)

        # Per-project num_scenes annotation check
        scripts_map = {s.id: s for s in response.context['scripts']}
        self.assertEqual(scripts_map[self.script1.id].num_scenes, 1)

    def test_project_deletion_preserves_project_row_and_marks_trashed(self):
        """Soft-deleting a project marks is_deleted=True, populates deleted_at, and preserves the row."""
        response = self.client.post(
            f'/scripts/{self.script2.id}/delete/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertIn('moved to Trash', data['message'])
        self.assertEqual(data['total_scripts'], 1)

        # Row still exists in database
        self.script2.refresh_from_db()
        self.assertTrue(self.script2.is_deleted)
        self.assertIsNotNone(self.script2.deleted_at)

    def test_project_soft_deletion_preserves_all_associated_data(self):
        """Soft-deleting a script preserves all scenes, elements, characters, notes, title page, and versions."""
        response = self.client.post(
            f'/scripts/{self.script1.id}/delete/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)

        self.script1.refresh_from_db()
        self.assertTrue(self.script1.is_deleted)

        # Check all child rows exist in database
        self.assertEqual(Scene.objects.filter(script=self.script1).count(), 2)
        self.assertEqual(ScriptElement.objects.filter(scene__script=self.script1).count(), 1)
        self.assertEqual(Character.objects.filter(script=self.script1).count(), 1)
        self.assertEqual(ScriptNote.objects.filter(script=self.script1).count(), 1)
        self.assertEqual(ScriptTitlePage.objects.filter(script=self.script1).count(), 1)
        self.assertEqual(ScriptVersion.objects.filter(script=self.script1).count(), 1)

    def test_cross_user_project_deletion_rejected(self):
        """User cannot delete a project owned by another user."""
        other_script = Script.objects.create(
            user=self.other_user,
            title='Other User Script'
        )

        response = self.client.post(
            f'/scripts/{other_script.id}/delete/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 404)

        other_script.refresh_from_db()
        self.assertFalse(other_script.is_deleted)

    def test_repeated_deletion_behavior(self):
        """Attempting to delete an already trashed script returns 404."""
        response = self.client.post(
            f'/scripts/{self.script_trashed.id}/delete/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 404)

    def test_standard_post_redirect_behavior(self):
        """Standard form POST (non-AJAX) redirects to script_list with flash message."""
        response = self.client.post(f'/scripts/{self.script2.id}/delete/')
        self.assertRedirects(response, '/scripts/')

        self.script2.refresh_from_db()
        self.assertTrue(self.script2.is_deleted)

    def test_trashed_project_rejected_by_editor_views_and_apis(self):
        """All editor endpoints reject a trashed project."""
        # HTML editor view
        resp_editor = self.client.get(f'/scripts/{self.script_trashed.id}/editor/')
        self.assertEqual(resp_editor.status_code, 404)

        # API endpoint
        resp_tree = self.client.get(f'/scripts/api/{self.script_trashed.id}/scenes/tree/')
        self.assertEqual(resp_tree.status_code, 404)

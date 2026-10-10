import json
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from scripts.models import Script, Scene, ScriptElement
from scripts.services.scene_service import (
    resequence_script_scenes,
    insert_scene_relative,
    create_sub_scene,
    create_sub_scene_2,
    create_intercut_scene,
    move_scene,
    duplicate_scene,
    serialize_scenes_hierarchy,
)

User = get_user_model()


class Batch2BSceneServiceAndSoftDeleteTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='writer_test',
            email='writer@example.com',
            password='password123'
        )
        self.other_user = User.objects.create_user(
            username='writer_other',
            email='other@example.com',
            password='password123'
        )
        self.client.force_login(self.user)

        self.script = Script.objects.create(
            user=self.user,
            title='Batch 2B Test Script',
            language='Malayalam'
        )

        # Main Scene 1 (Active)
        self.scene1 = Scene.objects.create(
            script=self.script,
            scene_number=1,
            heading='INT. LIVING ROOM - DAY',
            order=0,
            is_deleted=False
        )
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type='scene_heading',
            content='INT. LIVING ROOM - DAY',
            order=0
        )
        ScriptElement.objects.create(
            scene=self.scene1,
            element_type='action',
            content='കഥാപാത്രം ഇരിക്കുന്നു.',
            order=1
        )

        # Sub Scene 1A (Active)
        self.scene1a = Scene.objects.create(
            script=self.script,
            parent_scene=self.scene1,
            scene_number=1,
            heading='INT. LIVING ROOM - CORNER - DAY',
            order=1,
            is_deleted=False
        )
        ScriptElement.objects.create(
            scene=self.scene1a,
            element_type='scene_heading',
            content='INT. LIVING ROOM - CORNER - DAY',
            order=0
        )

        # Main Scene 2 (Active)
        self.scene2 = Scene.objects.create(
            script=self.script,
            scene_number=2,
            heading='EXT. GARDEN - DAY',
            order=2,
            is_deleted=False
        )
        ScriptElement.objects.create(
            scene=self.scene2,
            element_type='scene_heading',
            content='EXT. GARDEN - DAY',
            order=0
        )

    def test_active_scene_filtering_in_scene_service(self):
        """Active scene queries in scene_service exclude trashed scenes."""
        # Trash Scene 2 manually
        self.scene2.is_deleted = True
        self.scene2.deleted_at = timezone.now()
        self.scene2.save()

        # Resequence should only touch scene 1 and 1a
        resequence_script_scenes(self.script)
        self.scene2.refresh_from_db()
        self.scene1.refresh_from_db()
        self.assertEqual(self.scene1.scene_number, 1)

        # serialize_scenes_hierarchy must not include scene2
        hierarchy = serialize_scenes_hierarchy(self.script)
        hierarchy_ids = [s['id'] for s in hierarchy]
        self.assertIn(self.scene1.id, hierarchy_ids)
        self.assertIn(self.scene1a.id, hierarchy_ids)
        self.assertNotIn(self.scene2.id, hierarchy_ids)

    def test_trashed_scenes_remain_unchanged_during_resequencing(self):
        """Resequence does not alter order, scene_number, or duplicate_number of trashed scenes."""
        trashed_scene = Scene.objects.create(
            script=self.script,
            scene_number=99,
            heading='INT. TRASHED VAULT - NIGHT',
            order=99,
            is_deleted=True,
            deleted_at=timezone.now(),
            duplicate_number=5
        )

        resequence_script_scenes(self.script)
        trashed_scene.refresh_from_db()

        self.assertEqual(trashed_scene.scene_number, 99)
        self.assertEqual(trashed_scene.order, 99)
        self.assertEqual(trashed_scene.duplicate_number, 5)

    def test_soft_deletion_preserves_scene_row_and_elements(self):
        """api_delete_scene soft-deletes the scene, sets deleted_at, keeps elements in DB."""
        elem_count_before = ScriptElement.objects.filter(scene=self.scene2).count()
        self.assertGreater(elem_count_before, 0)

        response = self.client.post(f'/scripts/api/{self.script.id}/scenes/{self.scene2.id}/delete/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')

        self.scene2.refresh_from_db()
        self.assertTrue(self.scene2.is_deleted)
        self.assertIsNotNone(self.scene2.deleted_at)
        self.assertEqual(self.scene2.original_order, 2)

        # Verify ScriptElement rows are untouched
        elem_count_after = ScriptElement.objects.filter(scene=self.scene2).count()
        self.assertEqual(elem_count_before, elem_count_after)

    def test_trashing_main_scene_cascades_to_active_subscenes(self):
        """Soft-deleting a main scene also soft-deletes its active sub-scenes and records parent metadata."""
        # Add subscene 1B as well
        scene1b = Scene.objects.create(
            script=self.script,
            parent_scene=self.scene1,
            scene_number=1,
            heading='INT. LIVING ROOM - WINDOW - DAY',
            order=2,
            is_deleted=False
        )
        self.scene2.order = 3
        self.scene2.save()

        response = self.client.post(f'/scripts/api/{self.script.id}/scenes/{self.scene1.id}/delete/')
        self.assertEqual(response.status_code, 200)

        self.scene1.refresh_from_db()
        self.scene1a.refresh_from_db()
        scene1b.refresh_from_db()

        # Both main and sub-scenes must be soft-deleted
        self.assertTrue(self.scene1.is_deleted)
        self.assertTrue(self.scene1a.is_deleted)
        self.assertTrue(scene1b.is_deleted)

        self.assertIsNotNone(self.scene1.deleted_at)
        self.assertIsNotNone(self.scene1a.deleted_at)
        self.assertIsNotNone(scene1b.deleted_at)

        # Hierarchy metadata preserved
        self.assertEqual(self.scene1a.original_parent_uuid, self.scene1.scene_uuid)
        self.assertEqual(self.scene1a.original_parent_scene_number, 1)
        self.assertEqual(self.scene1a.original_parent_heading, self.scene1.heading)
        self.assertEqual(scene1b.original_parent_uuid, self.scene1.scene_uuid)

        # Scene 2 must now be active and resequenced to scene 1
        self.scene2.refresh_from_db()
        self.assertFalse(self.scene2.is_deleted)
        self.assertEqual(self.scene2.scene_number, 1)
        self.assertEqual(self.scene2.order, 0)

    def test_trashing_sub_scene_leaves_parent_and_siblings_active(self):
        """Trashing a sub-scene leaves parent and siblings active, preserving its original parent metadata."""
        scene1b = Scene.objects.create(
            script=self.script,
            parent_scene=self.scene1,
            scene_number=1,
            heading='INT. LIVING ROOM - WINDOW - DAY',
            order=2,
            is_deleted=False
        )

        response = self.client.post(f'/scripts/api/{self.script.id}/scenes/{self.scene1a.id}/delete/')
        self.assertEqual(response.status_code, 200)

        self.scene1a.refresh_from_db()
        self.scene1.refresh_from_db()
        scene1b.refresh_from_db()

        self.assertTrue(self.scene1a.is_deleted)
        self.assertEqual(self.scene1a.original_parent_uuid, self.scene1.scene_uuid)
        self.assertEqual(self.scene1a.original_parent_scene_number, 1)
        self.assertEqual(self.scene1a.original_parent_heading, self.scene1.heading)

        # Parent and sibling remain active
        self.assertFalse(self.scene1.is_deleted)
        self.assertFalse(scene1b.is_deleted)

    def test_intercut_reference_safety_on_soft_delete(self):
        """Soft-deleting an intercut captures original_intercut_source_uuid and does not delete the source."""
        intercut_scene = Scene.objects.create(
            script=self.script,
            scene_number=1,
            heading='INT. LIVING ROOM - DAY',
            order=3,
            is_intercut=True,
            intercut_source=self.scene1,
            is_deleted=False
        )

        response = self.client.post(f'/scripts/api/{self.script.id}/scenes/{intercut_scene.id}/delete/')
        self.assertEqual(response.status_code, 200)

        intercut_scene.refresh_from_db()
        self.scene1.refresh_from_db()

        self.assertTrue(intercut_scene.is_deleted)
        self.assertEqual(intercut_scene.original_intercut_source_uuid, self.scene1.scene_uuid)
        # Source scene remains active and exists
        self.assertFalse(self.scene1.is_deleted)
        self.assertEqual(intercut_scene.intercut_source_id, self.scene1.id)

    def test_last_active_scene_protection(self):
        """Prevent deleting the last active scene or last remaining scene block."""
        # Delete scene2 first
        self.client.post(f'/scripts/api/{self.script.id}/scenes/{self.scene2.id}/delete/')

        # Now only scene1 and scene1a remain.
        # Deleting scene1a is allowed because scene1 is still active
        resp = self.client.post(f'/scripts/api/{self.script.id}/scenes/{self.scene1a.id}/delete/')
        self.assertEqual(resp.status_code, 200)

        # Now only scene1 remains active. Attempting to delete scene1 must fail with 400.
        resp_last = self.client.post(f'/scripts/api/{self.script.id}/scenes/{self.scene1.id}/delete/')
        self.assertEqual(resp_last.status_code, 400)
        data = resp_last.json()
        self.assertEqual(data['status'], 'error')
        self.assertIn('Cannot delete the only scene', data['message'])

        self.scene1.refresh_from_db()
        self.assertFalse(self.scene1.is_deleted)

    def test_last_active_main_scene_with_subscenes_protection(self):
        """Deleting the only main scene when its sub-scenes would also be deleted must be blocked."""
        # Delete scene2
        self.client.post(f'/scripts/api/{self.script.id}/scenes/{self.scene2.id}/delete/')

        # Script now has active scene1 and active scene1a.
        # Attempting to delete scene1 would delete both scene1 and scene1a, leaving 0 active scenes.
        resp = self.client.post(f'/scripts/api/{self.script.id}/scenes/{self.scene1.id}/delete/')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Cannot delete the only scene', resp.json()['message'])

        self.scene1.refresh_from_db()
        self.assertFalse(self.scene1.is_deleted)

    def test_repeated_deletion_behavior(self):
        """Attempting to delete an already soft-deleted scene returns 404."""
        self.client.post(f'/scripts/api/{self.script.id}/scenes/{self.scene2.id}/delete/')
        self.scene2.refresh_from_db()
        self.assertTrue(self.scene2.is_deleted)

        # Second deletion attempt
        resp = self.client.post(f'/scripts/api/{self.script.id}/scenes/{self.scene2.id}/delete/')
        self.assertEqual(resp.status_code, 404)

    def test_cross_user_and_wrong_project_rejected(self):
        """Cross-user deletion and wrong-project deletion return 404."""
        other_script = Script.objects.create(
            user=self.other_user,
            title='Other Script'
        )
        other_scene = Scene.objects.create(
            script=other_script,
            scene_number=1,
            heading='INT. OTHER - DAY',
            order=0
        )

        # User tries to delete other_user's scene
        resp = self.client.post(f'/scripts/api/{other_script.id}/scenes/{other_scene.id}/delete/')
        self.assertEqual(resp.status_code, 404)

        # User tries to delete own scene under other script id
        resp2 = self.client.post(f'/scripts/api/{self.script.id}/scenes/{other_scene.id}/delete/')
        self.assertEqual(resp2.status_code, 404)

    def test_editor_response_compatibility(self):
        """Response returns status ok, fallback_scene_id, and scenes_tree excluding trashed scenes."""
        response = self.client.post(f'/scripts/api/{self.script.id}/scenes/{self.scene2.id}/delete/')
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['fallback_scene_id'], self.scene1a.id)
        self.assertIsInstance(data['scenes_tree'], list)

        # Ensure scenes_tree only contains active scenes
        tree_ids = [s['id'] for s in data['scenes_tree']]
        self.assertIn(self.scene1.id, tree_ids)
        self.assertIn(self.scene1a.id, tree_ids)
        self.assertNotIn(self.scene2.id, tree_ids)

    def test_move_scene_isolates_trashed(self):
        """Moving a scene does not consider trashed scenes in sibling navigation."""
        scene3 = Scene.objects.create(
            script=self.script,
            scene_number=3,
            heading='INT. BASEMENT - NIGHT',
            order=3,
            is_deleted=False
        )
        # Trash scene 2
        self.scene2.is_deleted = True
        self.scene2.deleted_at = timezone.now()
        self.scene2.save()

        # Resequence
        resequence_script_scenes(self.script)

        # Move scene 3 up (it should move before scene 1)
        moved = move_scene(self.script, scene3.id, 'up')
        self.assertTrue(moved)
        scene3.refresh_from_db()
        self.scene1.refresh_from_db()
        self.assertLess(scene3.order, self.scene1.order)

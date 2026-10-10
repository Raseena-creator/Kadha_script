import json
import uuid
from unittest.mock import patch
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse

from scripts.models import Script, Scene, ScriptElement, ScriptNote
from scripts.services.scene_service import resequence_script_scenes

User = get_user_model()


class Batch3DSceneTrashAndRestorationTests(TestCase):
    """
    Batch 3D-C-B Test Suite: Scene Trash Listing and Scene Restoration Backend.
    Covers all 28 specification requirements.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='kadha_writer',
            email='kadha_writer@example.com',
            password='Password123!'
        )
        self.other_user = User.objects.create_user(
            username='other_writer',
            email='other_writer@example.com',
            password='Password123!'
        )

        # Active script for owner
        self.script = Script.objects.create(
            user=self.user,
            title='കഥാവശേഷൻ (Kadhavaseshan)',
            description='Active project for scene trash tests',
            is_deleted=False
        )

        # Other user's script
        self.other_script = Script.objects.create(
            user=self.other_user,
            title='മറ്റൊരു കഥ (Another Story)',
            is_deleted=False
        )

        # Trashed script
        self.trashed_script = Script.objects.create(
            user=self.user,
            title='ഉപേക്ഷിച്ച തിരക്കഥ (Discarded Script)',
            is_deleted=True,
            deleted_at=timezone.now()
        )

        # Helper method to log in
        self.client.login(username='kadha_writer', password='Password123!')

    # --- LISTING TESTS (1-8) ---

    def test_01_unauthenticated_requests_are_rejected(self):
        """Unauthenticated requests are rejected with redirect or 403."""
        anon_client = Client()
        list_url = reverse('api_get_trashed_scenes', args=[self.script.id])
        restore_url = reverse('api_restore_scene', args=[self.script.id, 999])

        res_list = anon_client.get(list_url)
        self.assertEqual(res_list.status_code, 302)

        res_restore = anon_client.post(restore_url, data='{}', content_type='application/json')
        self.assertEqual(res_restore.status_code, 302)

    def test_02_owner_can_list_trashed_scenes(self):
        """The owner can list trashed scenes for their active screenplay."""
        now = timezone.now()
        sc = Scene.objects.create(
            script=self.script,
            heading='EXT. OLD HOUSE - NIGHT',
            scene_number=1,
            order=0,
            original_order=0,
            is_deleted=True,
            deleted_at=now
        )

        url = reverse('api_get_trashed_scenes', args=[self.script.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['total_trashed'], 1)
        self.assertEqual(len(data['trashed_scenes']), 1)
        self.assertEqual(data['trashed_scenes'][0]['id'], sc.id)
        self.assertEqual(data['trashed_scenes'][0]['heading'], 'EXT. OLD HOUSE - NIGHT')

    def test_03_another_user_cannot_list_trash(self):
        """Another user cannot list the screenplay's Trash (returns 404)."""
        self.client.login(username='other_writer', password='Password123!')
        url = reverse('api_get_trashed_scenes', args=[self.script.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_04_active_scenes_are_excluded(self):
        """Active scenes are excluded from the Trash listing."""
        Scene.objects.create(
            script=self.script,
            heading='INT. ACTIVE ROOM - DAY',
            scene_number=1,
            order=0,
            is_deleted=False
        )
        trashed_sc = Scene.objects.create(
            script=self.script,
            heading='INT. TRASHED ROOM - DAY',
            scene_number=2,
            order=1,
            original_order=1,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        url = reverse('api_get_trashed_scenes', args=[self.script.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data['total_trashed'], 1)
        self.assertEqual(data['trashed_scenes'][0]['id'], trashed_sc.id)

    def test_05_screenplay_dialogue_action_notes_elements_excluded(self):
        """Screenplay dialogue, action, notes, and elements are not included in listing."""
        sc = Scene.objects.create(
            script=self.script,
            heading='INT. STUDY - NIGHT',
            scene_number=1,
            order=0,
            is_deleted=True,
            deleted_at=timezone.now()
        )
        ScriptElement.objects.create(scene=sc, element_type='action', content='Secret confidential text', order=0)
        ScriptElement.objects.create(scene=sc, element_type='dialogue', content='Confidential speech', order=1)
        ScriptNote.objects.create(script=self.script, title='Director Note', content='Confidential director note')

        url = reverse('api_get_trashed_scenes', args=[self.script.id])
        response = self.client.get(url)
        data = response.json()
        scene_item = data['trashed_scenes'][0]

        # Verify forbidden fields
        self.assertNotIn('elements', scene_item)
        self.assertNotIn('dialogue', scene_item)
        self.assertNotIn('action', scene_item)
        self.assertNotIn('notes', scene_item)
        self.assertNotIn('content', scene_item)

    def test_06_parent_status_distinguishes_active_trashed_missing(self):
        """Parent status correctly distinguishes active, trashed, and missing."""
        parent_uuid_active = str(uuid.uuid4())
        active_parent = Scene.objects.create(
            script=self.script,
            heading='INT. MAIN SCENE ACTIVE - DAY',
            scene_uuid=parent_uuid_active,
            scene_number=1,
            order=0,
            is_deleted=False
        )

        parent_uuid_trashed = str(uuid.uuid4())
        trashed_parent = Scene.objects.create(
            script=self.script,
            heading='INT. MAIN SCENE TRASHED - DAY',
            scene_uuid=parent_uuid_trashed,
            scene_number=2,
            order=1,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        missing_parent_uuid = str(uuid.uuid4())

        sub_active_p = Scene.objects.create(
            script=self.script,
            heading='INT. SUB 1 - DAY',
            parent_scene=active_parent,
            original_parent_uuid=parent_uuid_active,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        sub_trashed_p = Scene.objects.create(
            script=self.script,
            heading='INT. SUB 2 - DAY',
            parent_scene=trashed_parent,
            original_parent_uuid=parent_uuid_trashed,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        sub_missing_p = Scene.objects.create(
            script=self.script,
            heading='INT. SUB 3 - DAY',
            original_parent_uuid=missing_parent_uuid,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        main_trashed = Scene.objects.create(
            script=self.script,
            heading='INT. MAIN TRASHED - DAY',
            is_deleted=True,
            deleted_at=timezone.now()
        )

        url = reverse('api_get_trashed_scenes', args=[self.script.id])
        data = self.client.get(url).json()
        trashed_dict = {s['id']: s for s in data['trashed_scenes']}

        self.assertEqual(trashed_dict[sub_active_p.id]['parent_status'], 'active')
        self.assertEqual(trashed_dict[sub_trashed_p.id]['parent_status'], 'trashed')
        self.assertEqual(trashed_dict[sub_missing_p.id]['parent_status'], 'missing')
        self.assertIsNone(trashed_dict[main_trashed.id]['parent_status'])

    def test_07_intercut_source_status_distinguishes_active_trashed_missing(self):
        """Intercut source status correctly distinguishes active, trashed, and missing."""
        source_uuid_active = str(uuid.uuid4())
        active_source = Scene.objects.create(
            script=self.script,
            heading='INT. CALLER ROOM - DAY',
            scene_uuid=source_uuid_active,
            scene_number=1,
            order=0,
            is_deleted=False
        )

        source_uuid_trashed = str(uuid.uuid4())
        trashed_source = Scene.objects.create(
            script=self.script,
            heading='INT. LISTENER ROOM - DAY',
            scene_uuid=source_uuid_trashed,
            scene_number=2,
            order=1,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        missing_source_uuid = str(uuid.uuid4())

        intercut_active = Scene.objects.create(
            script=self.script,
            heading='INT. CALLER INTERCUT - DAY',
            is_intercut=True,
            intercut_source=active_source,
            original_intercut_source_uuid=source_uuid_active,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        intercut_trashed = Scene.objects.create(
            script=self.script,
            heading='INT. LISTENER INTERCUT - DAY',
            is_intercut=True,
            intercut_source=trashed_source,
            original_intercut_source_uuid=source_uuid_trashed,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        intercut_missing = Scene.objects.create(
            script=self.script,
            heading='INT. GHOST INTERCUT - DAY',
            is_intercut=True,
            original_intercut_source_uuid=missing_source_uuid,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        url = reverse('api_get_trashed_scenes', args=[self.script.id])
        data = self.client.get(url).json()
        trashed_dict = {s['id']: s for s in data['trashed_scenes']}

        self.assertEqual(trashed_dict[intercut_active.id]['intercut_source_status'], 'active')
        self.assertEqual(trashed_dict[intercut_trashed.id]['intercut_source_status'], 'trashed')
        self.assertEqual(trashed_dict[intercut_missing.id]['intercut_source_status'], 'missing')

    def test_08_listing_does_not_modify_any_records(self):
        """Listing does not modify any database records."""
        now = timezone.now()
        sc = Scene.objects.create(
            script=self.script,
            heading='INT. UNCHANGED SCENE - DAY',
            scene_number=1,
            order=0,
            original_order=0,
            is_deleted=True,
            deleted_at=now
        )
        orig_updated_at = sc.updated_at

        url = reverse('api_get_trashed_scenes', args=[self.script.id])
        self.client.get(url)

        sc.refresh_from_db()
        self.assertTrue(sc.is_deleted)
        self.assertEqual(sc.deleted_at, now)
        self.assertEqual(sc.updated_at, orig_updated_at)

    # --- RESTORATION TESTS (9-28) ---

    def test_09_trashed_main_scene_restores_successfully(self):
        """A trashed main scene restores successfully."""
        sc = Scene.objects.create(
            script=self.script,
            heading='EXT. MOUNTAINS - DAY',
            scene_number=1,
            order=0,
            original_order=0,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        url = reverse('api_restore_scene', args=[self.script.id, sc.id])
        res = self.client.post(url, data='{}', content_type='application/json')
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['restored_scene_id'], sc.id)
        self.assertIn('scenes_tree', data)
        self.assertIn('script_stats', data)

        sc.refresh_from_db()
        self.assertFalse(sc.is_deleted)
        self.assertIsNone(sc.deleted_at)

    def test_10_sub_scene_with_active_original_parent_restores_under_correct_parent(self):
        """A sub-scene with an active original parent restores under the correct parent."""
        parent_uuid = str(uuid.uuid4())
        parent = Scene.objects.create(
            script=self.script,
            heading='INT. POLICE STATION - DAY',
            scene_uuid=parent_uuid,
            scene_number=1,
            order=0,
            is_deleted=False
        )
        resequence_script_scenes(self.script)

        sub = Scene.objects.create(
            script=self.script,
            heading='INT. INTERROGATION ROOM - CONTINUOUS',
            parent_scene=parent,
            original_parent_uuid=parent_uuid,
            original_order=1,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        url = reverse('api_restore_scene', args=[self.script.id, sub.id])
        res = self.client.post(url, data='{}', content_type='application/json')
        self.assertEqual(res.status_code, 200)

        sub.refresh_from_db()
        self.assertFalse(sub.is_deleted)
        self.assertEqual(sub.parent_scene, parent)
        self.assertTrue(sub.is_sub_scene)

    def test_11_sub_scene_with_trashed_parent_requires_explicit_choice(self):
        """A sub-scene with a trashed parent requires an explicit choice."""
        parent_uuid = str(uuid.uuid4())
        trashed_parent = Scene.objects.create(
            script=self.script,
            heading='INT. WAREHOUSE - NIGHT',
            scene_uuid=parent_uuid,
            scene_number=1,
            order=0,
            is_deleted=True,
            deleted_at=timezone.now()
        )
        sub = Scene.objects.create(
            script=self.script,
            heading='INT. WAREHOUSE BACKROOM - NIGHT',
            parent_scene=trashed_parent,
            original_parent_uuid=parent_uuid,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        url = reverse('api_restore_scene', args=[self.script.id, sub.id])
        # Auto restore should fail
        res = self.client.post(url, data='{}', content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('in Trash', res.json()['message'])

        sub.refresh_from_db()
        self.assertTrue(sub.is_deleted)

    def test_12_sub_scene_with_missing_parent_requires_explicit_choice(self):
        """A sub-scene with a missing parent requires an explicit choice."""
        missing_uuid = str(uuid.uuid4())
        sub = Scene.objects.create(
            script=self.script,
            heading='INT. MYSTERY VAULT - DAY',
            original_parent_uuid=missing_uuid,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        url = reverse('api_restore_scene', args=[self.script.id, sub.id])
        res = self.client.post(url, data='{}', content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('missing', res.json()['message'])

        sub.refresh_from_db()
        self.assertTrue(sub.is_deleted)

    def test_13_restore_as_main_scene_safely_detaches(self):
        """restore_as: 'main_scene' safely detaches the sub-scene from its old parent."""
        missing_uuid = str(uuid.uuid4())
        sub = Scene.objects.create(
            script=self.script,
            heading='INT. DETACHED SCENE - DAY',
            original_parent_uuid=missing_uuid,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        url = reverse('api_restore_scene', args=[self.script.id, sub.id])
        payload = json.dumps({'restore_as': 'main_scene'})
        res = self.client.post(url, data=payload, content_type='application/json')
        self.assertEqual(res.status_code, 200)

        sub.refresh_from_db()
        self.assertFalse(sub.is_deleted)
        self.assertIsNone(sub.parent_scene)
        self.assertFalse(sub.is_sub_scene)

    def test_14_restore_as_specified_parent_attaches_to_valid_main(self):
        """restore_as: 'specified_parent' attaches to a valid active main scene."""
        target_main = Scene.objects.create(
            script=self.script,
            heading='INT. TARGET MAIN SCENE - DAY',
            scene_number=1,
            order=0,
            is_deleted=False
        )
        resequence_script_scenes(self.script)

        sub = Scene.objects.create(
            script=self.script,
            heading='INT. ATTACHED SUB - DAY',
            original_parent_uuid=str(uuid.uuid4()),
            is_deleted=True,
            deleted_at=timezone.now()
        )

        url = reverse('api_restore_scene', args=[self.script.id, sub.id])
        payload = json.dumps({
            'restore_as': 'specified_parent',
            'target_parent_id': target_main.id
        })
        res = self.client.post(url, data=payload, content_type='application/json')
        self.assertEqual(res.status_code, 200)

        sub.refresh_from_db()
        self.assertFalse(sub.is_deleted)
        self.assertEqual(sub.parent_scene, target_main)
        self.assertTrue(sub.is_sub_scene)

    def test_15_invalid_trashed_subscene_foreign_target_parents_rejected(self):
        """Invalid, trashed, sub-scene, or foreign target parents are rejected."""
        # 1. Trashed parent
        trashed_main = Scene.objects.create(
            script=self.script,
            heading='INT. TRASHED MAIN - DAY',
            is_deleted=True,
            deleted_at=timezone.now()
        )
        # 2. Main scene and its sub-scene
        active_main = Scene.objects.create(
            script=self.script,
            heading='INT. ACTIVE MAIN - DAY',
            is_deleted=False
        )
        active_sub = Scene.objects.create(
            script=self.script,
            heading='INT. ACTIVE SUB - DAY',
            parent_scene=active_main,
            is_deleted=False
        )
        # 3. Foreign parent in another user's script
        foreign_main = Scene.objects.create(
            script=self.other_script,
            heading='INT. FOREIGN MAIN - DAY',
            is_deleted=False
        )

        candidate = Scene.objects.create(
            script=self.script,
            heading='INT. CANDIDATE SUB - DAY',
            original_parent_uuid=str(uuid.uuid4()),
            is_deleted=True,
            deleted_at=timezone.now()
        )

        url = reverse('api_restore_scene', args=[self.script.id, candidate.id])

        # Test trashed
        res = self.client.post(url, data=json.dumps({'restore_as': 'specified_parent', 'target_parent_id': trashed_main.id}), content_type='application/json')
        self.assertEqual(res.status_code, 400)

        # Test sub-scene target
        res = self.client.post(url, data=json.dumps({'restore_as': 'specified_parent', 'target_parent_id': active_sub.id}), content_type='application/json')
        self.assertEqual(res.status_code, 400)

        # Test foreign target
        res = self.client.post(url, data=json.dumps({'restore_as': 'specified_parent', 'target_parent_id': foreign_main.id}), content_type='application/json')
        self.assertEqual(res.status_code, 400)

        # Test nonexistent target
        res = self.client.post(url, data=json.dumps({'restore_as': 'specified_parent', 'target_parent_id': 999999}), content_type='application/json')
        self.assertEqual(res.status_code, 400)

    def test_16_cross_user_and_wrong_screenplay_scene_ids_rejected(self):
        """Cross-user and wrong-screenplay scene IDs are rejected (404)."""
        other_scene = Scene.objects.create(
            script=self.other_script,
            heading='INT. OTHER SCENE - DAY',
            is_deleted=True,
            deleted_at=timezone.now()
        )

        # Authenticated user tries to restore other user's scene using other script ID
        url_other = reverse('api_restore_scene', args=[self.other_script.id, other_scene.id])
        res = self.client.post(url_other, data='{}', content_type='application/json')
        self.assertEqual(res.status_code, 404)

        # Authenticated user tries to restore other user's scene using own script ID
        url_wrong = reverse('api_restore_scene', args=[self.script.id, other_scene.id])
        res2 = self.client.post(url_wrong, data='{}', content_type='application/json')
        self.assertEqual(res2.status_code, 404)

    def test_17_already_active_scenes_cannot_be_restored(self):
        """Already-active scenes cannot be restored again (returns 400)."""
        active_scene = Scene.objects.create(
            script=self.script,
            heading='INT. ALREADY ACTIVE - DAY',
            is_deleted=False
        )

        url = reverse('api_restore_scene', args=[self.script.id, active_scene.id])
        res = self.client.post(url, data='{}', content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('already active', res.json()['message'])

    def test_18_trashed_screenplay_cannot_receive_scene_restoration(self):
        """A trashed screenplay cannot receive scene restoration (returns 404)."""
        scene_in_trashed_script = Scene.objects.create(
            script=self.trashed_script,
            heading='INT. SCENE IN TRASHED SCRIPT - DAY',
            is_deleted=True,
            deleted_at=timezone.now()
        )

        url = reverse('api_restore_scene', args=[self.trashed_script.id, scene_in_trashed_script.id])
        res = self.client.post(url, data='{}', content_type='application/json')
        self.assertEqual(res.status_code, 404)

    def test_19_get_and_unsupported_methods_rejected(self):
        """GET and unsupported methods are rejected with 405 Method Not Allowed."""
        sc = Scene.objects.create(
            script=self.script,
            heading='INT. METHOD TEST - DAY',
            is_deleted=True,
            deleted_at=timezone.now()
        )

        url = reverse('api_restore_scene', args=[self.script.id, sc.id])
        res_get = self.client.get(url)
        self.assertEqual(res_get.status_code, 405)

        res_put = self.client.put(url, data='{}', content_type='application/json')
        self.assertEqual(res_put.status_code, 405)

        res_delete = self.client.delete(url)
        self.assertEqual(res_delete.status_code, 405)

    def test_20_invalid_json_and_invalid_choice_values_rejected(self):
        """Invalid JSON and invalid choice values are rejected with 400."""
        sc = Scene.objects.create(
            script=self.script,
            heading='INT. BAD JSON TEST - DAY',
            original_parent_uuid=str(uuid.uuid4()),
            is_deleted=True,
            deleted_at=timezone.now()
        )
        url = reverse('api_restore_scene', args=[self.script.id, sc.id])

        # Malformed JSON
        res = self.client.post(url, data='{"restore_as": ', content_type='application/json')
        self.assertEqual(res.status_code, 400)

        # Invalid choice string
        res = self.client.post(url, data=json.dumps({'restore_as': 'invalid_mode'}), content_type='application/json')
        self.assertEqual(res.status_code, 400)

        # specified_parent missing target_parent_id
        res = self.client.post(url, data=json.dumps({'restore_as': 'specified_parent'}), content_type='application/json')
        self.assertEqual(res.status_code, 400)

        # specified_parent with non-integer target_parent_id
        res = self.client.post(url, data=json.dumps({'restore_as': 'specified_parent', 'target_parent_id': 'abc'}), content_type='application/json')
        self.assertEqual(res.status_code, 400)

    def test_21_active_intercut_source_preserved_correctly(self):
        """An active intercut source is preserved correctly upon restoration."""
        source_uuid = str(uuid.uuid4())
        active_source = Scene.objects.create(
            script=self.script,
            heading='INT. ACTIVE SOURCE ROOM - DAY',
            scene_uuid=source_uuid,
            scene_number=1,
            order=0,
            is_deleted=False
        )
        resequence_script_scenes(self.script)

        intercut = Scene.objects.create(
            script=self.script,
            heading='INT. INTERCUT TO SOURCE - DAY',
            is_intercut=True,
            intercut_source=active_source,
            original_intercut_source_uuid=source_uuid,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        url = reverse('api_restore_scene', args=[self.script.id, intercut.id])
        res = self.client.post(url, data='{}', content_type='application/json')
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertFalse(data['intercut_fallback'])

        intercut.refresh_from_db()
        self.assertFalse(intercut.is_deleted)
        self.assertTrue(intercut.is_intercut)
        self.assertEqual(intercut.intercut_source, active_source)

    def test_22_trashed_or_missing_intercut_source_never_leaves_broken_reference(self):
        """A trashed or missing intercut source never leaves a broken reference; falls back to normal scene."""
        missing_source_uuid = str(uuid.uuid4())
        intercut = Scene.objects.create(
            script=self.script,
            heading='INT. ORPHAN INTERCUT - DAY',
            is_intercut=True,
            original_intercut_source_uuid=missing_source_uuid,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        url = reverse('api_restore_scene', args=[self.script.id, intercut.id])
        res = self.client.post(url, data='{}', content_type='application/json')
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertTrue(data['intercut_fallback'])
        self.assertIn('restored as a normal scene', data['message'])

        intercut.refresh_from_db()
        self.assertFalse(intercut.is_deleted)
        self.assertFalse(intercut.is_intercut)
        self.assertIsNone(intercut.intercut_source)

    def test_23_ambiguous_uuids_never_cause_silent_parent_or_source_rebinding(self):
        """Ambiguous UUIDs never cause silent parent or source rebinding."""
        ambiguous_uuid = str(uuid.uuid4())
        # Two active scenes share the same UUID
        Scene.objects.create(
            script=self.script,
            heading='INT. AMBIGUOUS MAIN 1 - DAY',
            scene_uuid=ambiguous_uuid,
            is_deleted=False
        )
        Scene.objects.create(
            script=self.script,
            heading='INT. AMBIGUOUS MAIN 2 - DAY',
            scene_uuid=ambiguous_uuid,
            is_deleted=False
        )

        sub = Scene.objects.create(
            script=self.script,
            heading='INT. SUB TO AMBIGUOUS - DAY',
            original_parent_uuid=ambiguous_uuid,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        url = reverse('api_restore_scene', args=[self.script.id, sub.id])
        res = self.client.post(url, data='{}', content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('ambiguous', res.json()['message'].lower())

        sub.refresh_from_db()
        self.assertTrue(sub.is_deleted)

    def test_24_restoring_main_scene_leaves_subscenes_trashed(self):
        """Restoring a main scene leaves its trashed sub-scenes in Trash."""
        main_uuid = str(uuid.uuid4())
        main = Scene.objects.create(
            script=self.script,
            heading='INT. MAIN SCENE - DAY',
            scene_uuid=main_uuid,
            order=0,
            is_deleted=True,
            deleted_at=timezone.now()
        )
        sub1 = Scene.objects.create(
            script=self.script,
            heading='INT. SUB SCENE 1 - DAY',
            parent_scene=main,
            original_parent_uuid=main_uuid,
            order=1,
            is_deleted=True,
            deleted_at=timezone.now()
        )
        sub2 = Scene.objects.create(
            script=self.script,
            heading='INT. SUB SCENE 2 - DAY',
            parent_scene=main,
            original_parent_uuid=main_uuid,
            order=2,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        url = reverse('api_restore_scene', args=[self.script.id, main.id])
        res = self.client.post(url, data='{}', content_type='application/json')
        self.assertEqual(res.status_code, 200)

        main.refresh_from_db()
        sub1.refresh_from_db()
        sub2.refresh_from_db()

        self.assertFalse(main.is_deleted)
        self.assertTrue(sub1.is_deleted)
        self.assertTrue(sub2.is_deleted)

    def test_25_original_order_conflicts_handled_without_overwriting(self):
        """Original-order conflicts are handled without overwriting other scenes."""
        s1 = Scene.objects.create(script=self.script, heading='SCENE 1', order=0, is_deleted=False)
        s2 = Scene.objects.create(script=self.script, heading='SCENE 2', order=1, is_deleted=False)
        resequence_script_scenes(self.script)

        # Trashed scene was originally at order 0
        trashed = Scene.objects.create(
            script=self.script,
            heading='RESTORED AT ZERO',
            order=0,
            original_order=0,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        url = reverse('api_restore_scene', args=[self.script.id, trashed.id])
        res = self.client.post(url, data='{}', content_type='application/json')
        self.assertEqual(res.status_code, 200)

        active_orders = list(self.script.scenes.filter(is_deleted=False).order_by('order').values_list('order', flat=True))
        # Ensure sequential orders without duplicates
        self.assertEqual(active_orders, [0, 1, 2])

    def test_26_ordering_and_numbering_consistent_after_restoration(self):
        """Ordering and numbering remain consistent after restoration."""
        s1 = Scene.objects.create(script=self.script, heading='SCENE 1', order=0, is_deleted=False)
        s2 = Scene.objects.create(script=self.script, heading='SCENE 2', order=1, is_deleted=False)
        resequence_script_scenes(self.script)

        s3 = Scene.objects.create(
            script=self.script,
            heading='SCENE 3',
            order=2,
            original_order=2,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        url = reverse('api_restore_scene', args=[self.script.id, s3.id])
        res = self.client.post(url, data='{}', content_type='application/json')
        self.assertEqual(res.status_code, 200)

        s1.refresh_from_db()
        s2.refresh_from_db()
        s3.refresh_from_db()

        self.assertEqual([s1.scene_number, s2.scene_number, s3.scene_number], [1, 2, 3])
        self.assertEqual([s1.order, s2.order, s3.order], [0, 1, 2])

    def test_27_simulated_failure_rolls_back_restoration_and_order_changes(self):
        """A simulated failure rolls back the restoration and order changes atomically."""
        s1 = Scene.objects.create(script=self.script, heading='SCENE 1', order=0, is_deleted=False)
        trashed = Scene.objects.create(
            script=self.script,
            heading='TRASHED SCENE',
            order=1,
            original_order=1,
            is_deleted=True,
            deleted_at=timezone.now()
        )

        url = reverse('api_restore_scene', args=[self.script.id, trashed.id])

        with patch('scripts.services.scene_service.resequence_script_scenes', side_effect=RuntimeError('Simulated DB failure')):
            res = self.client.post(url, data='{}', content_type='application/json')
            self.assertEqual(res.status_code, 500)

        trashed.refresh_from_db()
        s1.refresh_from_db()

        self.assertTrue(trashed.is_deleted)
        self.assertIsNotNone(trashed.deleted_at)
        self.assertEqual(s1.order, 0)

    def test_28_existing_scene_deletion_safeguards_continue_to_work(self):
        """Existing scene deletion safeguards continue to record metadata properly."""
        p_uuid = str(uuid.uuid4())
        parent = Scene.objects.create(
            script=self.script,
            heading='INT. MAIN SCENE - DAY',
            scene_uuid=p_uuid,
            scene_number=1,
            order=0,
            is_deleted=False
        )
        sub = Scene.objects.create(
            script=self.script,
            heading='INT. SUB SCENE - DAY',
            parent_scene=parent,
            order=1,
            is_deleted=False
        )
        resequence_script_scenes(self.script)

        # Delete sub-scene via existing api_delete_scene endpoint
        del_url = reverse('api_delete_scene', args=[self.script.id, sub.id])
        res = self.client.post(del_url, data='{}', content_type='application/json')
        self.assertEqual(res.status_code, 200)

        sub.refresh_from_db()
        self.assertTrue(sub.is_deleted)
        self.assertIsNotNone(sub.deleted_at)
        self.assertEqual(str(sub.original_parent_uuid), p_uuid)
        self.assertEqual(sub.original_order, 1)


class Batch3DC1SubSceneLetteringTests(TestCase):
    """
    Batch 3D-C.1 Test Suite: Fix Active Sub-Scene Lettering.
    Verifies that soft-deleted sub-scenes do not consume alphabetical letters.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='letter_writer',
            email='letter_writer@example.com',
            password='Password123!'
        )
        self.script = Script.objects.create(
            user=self.user,
            title='അക്ഷരമാല (Aksharamala)',
            is_deleted=False
        )
        self.client.login(username='letter_writer', password='Password123!')

    def test_a_first_subscene_deleted(self):
        """Test A: Deleting 1.A shifts 1.B -> 1.A, 1.C -> 1.B while trashed scene remains in DB."""
        parent = Scene.objects.create(script=self.script, heading='INT. HOUSE - DAY', order=0, is_deleted=False)
        sub_a = Scene.objects.create(script=self.script, heading='LIVING ROOM', parent_scene=parent, order=1, is_deleted=False)
        sub_b = Scene.objects.create(script=self.script, heading='KITCHEN', parent_scene=parent, order=2, is_deleted=False)
        sub_c = Scene.objects.create(script=self.script, heading='BEDROOM', parent_scene=parent, order=3, is_deleted=False)
        resequence_script_scenes(self.script)

        self.assertEqual(sub_a.display_number, 'Scene 1.A')
        self.assertEqual(sub_b.display_number, 'Scene 1.B')
        self.assertEqual(sub_c.display_number, 'Scene 1.C')

        # Trash 1.A
        res = self.client.post(reverse('api_delete_scene', args=[self.script.id, sub_a.id]))
        self.assertEqual(res.status_code, 200)

        sub_a.refresh_from_db()
        sub_b.refresh_from_db()
        sub_c.refresh_from_db()

        # Trashed scene remains in DB and is_deleted=True
        self.assertTrue(sub_a.is_deleted)
        self.assertTrue(Scene.objects.filter(id=sub_a.id).exists())

        # Active sub-scenes reletter
        self.assertEqual(sub_b.display_number, 'Scene 1.A')
        self.assertEqual(sub_c.display_number, 'Scene 1.B')

    def test_b_middle_subscene_deleted(self):
        """Test B: Deleting 1.B leaves 1.A as 1.A and shifts 1.C -> 1.B."""
        parent = Scene.objects.create(script=self.script, heading='INT. OFFICE - DAY', order=0, is_deleted=False)
        sub_a = Scene.objects.create(script=self.script, heading='CABIN', parent_scene=parent, order=1, is_deleted=False)
        sub_b = Scene.objects.create(script=self.script, heading='CORRIDOR', parent_scene=parent, order=2, is_deleted=False)
        sub_c = Scene.objects.create(script=self.script, heading='CONFERENCE', parent_scene=parent, order=3, is_deleted=False)
        resequence_script_scenes(self.script)

        # Trash 1.B
        res = self.client.post(reverse('api_delete_scene', args=[self.script.id, sub_b.id]))
        self.assertEqual(res.status_code, 200)

        sub_a.refresh_from_db()
        sub_b.refresh_from_db()
        sub_c.refresh_from_db()

        self.assertEqual(sub_a.display_number, 'Scene 1.A')
        self.assertTrue(sub_b.is_deleted)
        self.assertEqual(sub_c.display_number, 'Scene 1.B')

    def test_c_restore_deleted_subscene(self):
        """Test C: Restoring deleted sub-scene restores deterministic, consistent lettering."""
        parent = Scene.objects.create(script=self.script, heading='INT. HOTEL - NIGHT', order=0, is_deleted=False)
        sub_a = Scene.objects.create(script=self.script, heading='LOBBY', parent_scene=parent, order=1, is_deleted=False)
        sub_b = Scene.objects.create(script=self.script, heading='ELEVATOR', parent_scene=parent, order=2, is_deleted=False)
        sub_c = Scene.objects.create(script=self.script, heading='ROOM 101', parent_scene=parent, order=3, is_deleted=False)
        resequence_script_scenes(self.script)

        # Trash 1.B
        res_del = self.client.post(reverse('api_delete_scene', args=[self.script.id, sub_b.id]))
        self.assertEqual(res_del.status_code, 200)

        sub_a.refresh_from_db()
        sub_c.refresh_from_db()
        self.assertEqual(sub_a.display_number, 'Scene 1.A')
        self.assertEqual(sub_c.display_number, 'Scene 1.B')

        # Restore 1.B
        res_res = self.client.post(reverse('api_restore_scene', args=[self.script.id, sub_b.id]), data='{}', content_type='application/json')
        self.assertEqual(res_res.status_code, 200)

        sub_a.refresh_from_db()
        sub_b.refresh_from_db()
        sub_c.refresh_from_db()

        self.assertFalse(sub_b.is_deleted)
        self.assertEqual(sub_a.display_number, 'Scene 1.A')
        self.assertEqual(sub_b.display_number, 'Scene 1.B')
        self.assertEqual(sub_c.display_number, 'Scene 1.C')

    def test_d_multiple_trashed_subscenes(self):
        """Test D: Trashing 1.A and 1.C leaves active scenes lettered 1.A and 1.B without consuming letters."""
        parent = Scene.objects.create(script=self.script, heading='INT. MANSION - DAY', order=0, is_deleted=False)
        sub_a = Scene.objects.create(script=self.script, heading='HALL', parent_scene=parent, order=1, is_deleted=False)
        sub_b = Scene.objects.create(script=self.script, heading='BALCONY', parent_scene=parent, order=2, is_deleted=False)
        sub_c = Scene.objects.create(script=self.script, heading='GARDEN', parent_scene=parent, order=3, is_deleted=False)
        sub_d = Scene.objects.create(script=self.script, heading='BASEMENT', parent_scene=parent, order=4, is_deleted=False)
        resequence_script_scenes(self.script)

        # Trash 1.A and 1.C
        self.client.post(reverse('api_delete_scene', args=[self.script.id, sub_a.id]))
        self.client.post(reverse('api_delete_scene', args=[self.script.id, sub_c.id]))

        sub_a.refresh_from_db()
        sub_b.refresh_from_db()
        sub_c.refresh_from_db()
        sub_d.refresh_from_db()

        self.assertTrue(sub_a.is_deleted)
        self.assertTrue(sub_c.is_deleted)
        self.assertEqual(sub_b.display_number, 'Scene 1.A')
        self.assertEqual(sub_d.display_number, 'Scene 1.B')

    def test_e_main_scene_trash_does_not_break_active_child_lettering(self):
        """Test E: Trashing another main scene does not break sub-scene lettering of remaining scenes."""
        main_1 = Scene.objects.create(script=self.script, heading='INT. SCENE 1 - DAY', order=0, is_deleted=False)
        sub_1a = Scene.objects.create(script=self.script, heading='SUB 1A', parent_scene=main_1, order=1, is_deleted=False)
        sub_1b = Scene.objects.create(script=self.script, heading='SUB 1B', parent_scene=main_1, order=2, is_deleted=False)

        main_2 = Scene.objects.create(script=self.script, heading='INT. SCENE 2 - DAY', order=3, is_deleted=False)
        sub_2a = Scene.objects.create(script=self.script, heading='SUB 2A', parent_scene=main_2, order=4, is_deleted=False)
        sub_2b = Scene.objects.create(script=self.script, heading='SUB 2B', parent_scene=main_2, order=5, is_deleted=False)
        resequence_script_scenes(self.script)

        # Trash Main 1 (cascades soft-delete to its sub-scenes)
        res = self.client.post(reverse('api_delete_scene', args=[self.script.id, main_1.id]))
        self.assertEqual(res.status_code, 200)

        main_2.refresh_from_db()
        sub_2a.refresh_from_db()
        sub_2b.refresh_from_db()

        # Main 2 is now Scene 1, its sub-scenes are Scene 1.A and Scene 1.B
        self.assertEqual(main_2.display_number, 'Scene 1')
        self.assertEqual(sub_2a.display_number, 'Scene 1.A')
        self.assertEqual(sub_2b.display_number, 'Scene 1.B')

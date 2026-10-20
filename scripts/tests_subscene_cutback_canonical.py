import json
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from scripts.models import Script, Scene
from scripts.services.scene_service import (
    create_sub_scene,
    create_sub_scene_2,
    create_intercut_scene,
    resequence_script_scenes,
)

User = get_user_model()


class SubSceneCutBackCanonicalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='cutback_writer',
            email='cutback@example.com',
            password='testpassword123'
        )
        self.client = Client()
        self.client.login(username='cutback_writer', password='testpassword123')
        self.script = Script.objects.create(
            user=self.user,
            title='CutBack SubScene Canon Test'
        )

        # Pre-seed scenes 1 to 16 so Scene 17 is genuinely Scene 17 under resequence_script_scenes
        for i in range(1, 17):
            Scene.objects.create(
                script=self.script,
                scene_number=i,
                heading=f'INT. SCENE {i} - DAY',
                order=i - 1
            )

        self.scene17 = Scene.objects.create(
            script=self.script,
            scene_number=17,
            heading='INT. APARTMENT - DAY',
            order=16
        )
        self.scene17a = create_sub_scene(
            self.script,
            parent_scene_id=self.scene17.id,
            heading='INT. APARTMENT - CORRIDOR'
        )
        self.scene18 = Scene.objects.create(
            script=self.script,
            scene_number=18,
            heading='EXT. STREET - NIGHT',
            order=18
        )
        resequence_script_scenes(self.script)
        self.scene17.refresh_from_db()
        self.scene17a.refresh_from_db()
        self.scene18.refresh_from_db()

    def test_a_sub_scene_after_cut_back_to_17a(self):
        """
        Test A: When the active scene is an intercut/Cut Back entry pointing to 17A,
        creating a new sub-scene:
        - Attaches to the canonical main Scene 17 (parent_scene_id = Scene 17.id)
        - Receives sub_letter 'B' and display number Scene 17.B / Scene 17B
        - Has is_intercut = True and intercut_source pointing to the original Scene 17A
        - Appears immediately after cutback_17a in timeline order (NOT in the Scene 17 top cluster)
        """
        # Story sequence: Scene 17 -> Scene 17A -> Scene 18 -> Cut Back 17A -> Cut Back 18 -> Cut Back 17A
        cutback_17a_1 = create_intercut_scene(
            self.script,
            source_scene_id=self.scene17a.id,
            current_scene_id=self.scene18.id
        )
        cutback_18 = create_intercut_scene(
            self.script,
            source_scene_id=self.scene18.id,
            current_scene_id=cutback_17a_1.id
        )
        cutback_17a_2 = create_intercut_scene(
            self.script,
            source_scene_id=self.scene17a.id,
            current_scene_id=cutback_18.id
        )

        self.assertTrue(cutback_17a_2.is_intercut)
        self.assertEqual(cutback_17a_2.intercut_source_id, self.scene17a.id)
        self.assertIsNone(cutback_17a_2.parent_scene)

        # Create a new sub-scene while focused on the final cutback_17a_2
        new_sub = create_sub_scene(
            self.script,
            parent_scene_id=cutback_17a_2.id,
            heading='INT. APARTMENT - BALCONY'
        )

        new_sub.refresh_from_db()
        self.scene17.refresh_from_db()
        self.scene17a.refresh_from_db()
        self.scene18.refresh_from_db()
        cutback_17a_1.refresh_from_db()
        cutback_18.refresh_from_db()
        cutback_17a_2.refresh_from_db()

        # 1. Must attach to canonical main Scene 17 for numbering
        self.assertEqual(new_sub.parent_scene_id, self.scene17.id)
        self.assertEqual(new_sub.scene_number, 17)
        self.assertEqual(new_sub.sub_letter, 'B')
        self.assertEqual(new_sub.nav_identifier, 'Scene 17B')
        self.assertEqual(new_sub.scene_identifier, 'Scene 17.B')

        # 2. Existing 17A must remain untouched
        self.assertEqual(self.scene17a.sub_letter, 'A')
        self.assertEqual(self.scene17a.nav_identifier, 'Scene 17A')

        # 3. Must be marked as an intercut timeline entry
        self.assertTrue(new_sub.is_intercut)
        self.assertTrue(new_sub.is_sub_scene)
        # 4. intercut_source must point to original source scene (scene17a), not intermediate cutback
        self.assertEqual(new_sub.intercut_source_id, self.scene17a.id)

        # 5. Timeline order: must appear immediately after cutback_17a_2
        self.assertEqual(new_sub.order, cutback_17a_2.order + 1)

        ordered = self.script.get_ordered_scenes()
        ordered_ids = [s.id for s in ordered]

        # Verify exact sequence: Scene 1..16, Scene 17, Scene 17A, Scene 18, cutback_17a_1, cutback_18, cutback_17a_2, new_sub (17B)
        expected_tail_ids = [
            self.scene17.id,
            self.scene17a.id,
            self.scene18.id,
            cutback_17a_1.id,
            cutback_18.id,
            cutback_17a_2.id,
            new_sub.id,
        ]
        self.assertEqual(ordered_ids[-7:], expected_tail_ids)

        # Ensure it does NOT appear between scene17a and scene18
        scene18_idx = ordered_ids.index(self.scene18.id)
        new_sub_idx = ordered_ids.index(new_sub.id)
        self.assertGreater(new_sub_idx, scene18_idx)

    def test_b_multiple_sub_scenes_sibling_progression(self):
        """
        Test B: Multiple siblings 17A, 17B, 17C remain correctly sequenced in reading order
        when created through intercut entries.
        """
        # Add 17B via cutback to 17A
        cutback_17a = create_intercut_scene(
            self.script,
            source_scene_id=self.scene17a.id,
            current_scene_id=self.scene18.id
        )
        sub_17b = create_sub_scene(
            self.script,
            parent_scene_id=cutback_17a.id,
            heading='INT. APARTMENT - BEDROOM'
        )
        self.assertEqual(sub_17b.sub_letter, 'B')
        self.assertEqual(sub_17b.parent_scene_id, self.scene17.id)
        self.assertTrue(sub_17b.is_intercut)

        # Create Cut Back to 17B after another scene
        scene19 = Scene.objects.create(
            script=self.script,
            scene_number=19,
            heading='EXT. PARK - DAY',
            order=sub_17b.order + 1
        )
        resequence_script_scenes(self.script)

        cutback_17b = create_intercut_scene(
            self.script,
            source_scene_id=sub_17b.id,
            current_scene_id=scene19.id
        )

        # Create next sub-scene using the Cut Back entry pointing to 17B
        sub_17c = create_sub_scene(
            self.script,
            parent_scene_id=cutback_17b.id,
            heading='INT. APARTMENT - KITCHEN'
        )
        sub_17c.refresh_from_db()
        cutback_17b.refresh_from_db()

        self.assertEqual(sub_17c.parent_scene_id, self.scene17.id)
        self.assertEqual(sub_17c.sub_letter, 'C')
        self.assertEqual(sub_17c.nav_identifier, 'Scene 17C')
        self.assertTrue(sub_17c.is_intercut)
        # intercut_source resolves to original sub_17b
        self.assertEqual(sub_17c.intercut_source_id, sub_17b.id)
        self.assertEqual(sub_17c.order, cutback_17b.order + 1)

        # Verify all siblings are correctly sequenced under Scene 17
        siblings = list(self.scene17.sub_scenes.filter(is_deleted=False).order_by('order', 'id'))
        letters = [s.sub_letter for s in siblings]
        self.assertEqual(letters, ['A', 'B', 'C'])

    def test_c_standard_creation_remains_unchanged(self):
        """
        Test C: Standard sub-scene creation directly under a main scene or under an existing sub-scene
        continues to resolve correctly with is_intercut=False and top cluster placement.
        """
        # 1. Under main scene
        sub1 = create_sub_scene(self.script, parent_scene_id=self.scene17.id, heading='INT. 17B')
        self.assertEqual(sub1.parent_scene_id, self.scene17.id)
        self.assertEqual(sub1.sub_letter, 'B')
        self.assertFalse(sub1.is_intercut)
        self.assertIsNone(sub1.intercut_source)

        # In timeline, sub1 is placed right after scene17a, before scene18
        ordered = self.script.get_ordered_scenes()
        ordered_ids = [s.id for s in ordered]
        s17a_idx = ordered_ids.index(self.scene17a.id)
        sub1_idx = ordered_ids.index(sub1.id)
        s18_idx = ordered_ids.index(self.scene18.id)
        self.assertEqual(sub1_idx, s17a_idx + 1)
        self.assertLess(sub1_idx, s18_idx)

        # 2. Under existing standard sub-scene
        sub2 = create_sub_scene(self.script, parent_scene_id=self.scene17a.id, heading='INT. 17C')
        self.assertEqual(sub2.parent_scene_id, self.scene17.id)
        self.assertEqual(sub2.sub_letter, 'C')
        self.assertFalse(sub2.is_intercut)

    def test_d_invalid_intercut_source(self):
        """
        Test D: Safe error handling when intercut source is deleted or missing.
        Does not silently attach a new sub-scene under an invalid intercut record.
        """
        cutback = create_intercut_scene(
            self.script,
            source_scene_id=self.scene17a.id,
            current_scene_id=self.scene18.id
        )

        # Soft-delete the intercut source
        self.scene17a.is_deleted = True
        self.scene17a.save(update_fields=['is_deleted'])
        cutback.refresh_from_db()

        initial_sub_count = Scene.objects.filter(script=self.script, is_deleted=False, parent_scene__isnull=False).count()

        with self.assertRaises(ValueError) as ctx:
            create_sub_scene(self.script, parent_scene_id=cutback.id, heading='INT. INVALID')

        self.assertIn("missing or deleted", str(ctx.exception))

        # Ensure no sub-scene was created under the invalid cutback scene
        self.assertEqual(cutback.sub_scenes.count(), 0)
        final_sub_count = Scene.objects.filter(script=self.script, is_deleted=False, parent_scene__isnull=False).count()
        self.assertEqual(initial_sub_count, final_sub_count)

    def test_e_api_behavior_with_intercut_scene_id(self):
        """
        Test E: Sub-scene API correctly handles an intercut scene ID as parent_scene_id,
        positions it directly after the cutback scene, and returns expected scene info.
        """
        cutback = create_intercut_scene(
            self.script,
            source_scene_id=self.scene17a.id,
            current_scene_id=self.scene18.id
        )

        url = reverse('api_create_sub_scene', kwargs={'script_id': self.script.id, 'parent_scene_id': cutback.id})
        res = self.client.post(
            url,
            data=json.dumps({'heading': 'INT. API SUB SCENE - NIGHT'}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['scene']['parent_scene_id'], self.scene17.id)
        self.assertEqual(data['scene']['display_number'], 'Scene 17.B')
        self.assertEqual(data['scene']['display_number_formatted'], 'Scene 17.B')
        self.assertEqual(data['scene']['scene_identifier'], 'Scene 17.B')
        self.assertTrue(data['scene']['is_sub_scene'])
        self.assertTrue(data['scene']['is_intercut'])

        # Verify created scene's position in scenes_tree returned by API
        tree = data['scenes_tree']
        tree_ids = [s['id'] for s in tree]
        cutback_idx = tree_ids.index(cutback.id)
        new_scene_idx = tree_ids.index(data['scene']['id'])
        self.assertEqual(new_scene_idx, cutback_idx + 1)

        # Test API error response when intercut source is deleted
        self.scene17a.is_deleted = True
        self.scene17a.save(update_fields=['is_deleted'])

        res_err = self.client.post(
            url,
            data=json.dumps({'heading': 'INT. SHOULD FAIL'}),
            content_type='application/json'
        )
        self.assertEqual(res_err.status_code, 400)
        err_data = res_err.json()
        self.assertEqual(err_data['status'], 'error')
        self.assertIn("missing or deleted", err_data['message'])

    def test_f_txt_export_order_preservation(self):
        """
        Test F: Plain-text export preserves the reading order and displays Scene 17.B
        immediately following the final Cut Back entry.
        """
        from scripts.services.txt_export import generate_screenplay_txt

        cutback_17a_1 = create_intercut_scene(
            self.script,
            source_scene_id=self.scene17a.id,
            current_scene_id=self.scene18.id
        )
        cutback_18 = create_intercut_scene(
            self.script,
            source_scene_id=self.scene18.id,
            current_scene_id=cutback_17a_1.id
        )
        cutback_17a_2 = create_intercut_scene(
            self.script,
            source_scene_id=self.scene17a.id,
            current_scene_id=cutback_18.id
        )
        new_sub = create_sub_scene(
            self.script,
            parent_scene_id=cutback_17a_2.id,
            heading='INT. APARTMENT - BALCONY'
        )

        txt_content = generate_screenplay_txt(self.script)
        # Verify headings appear in order in the exported text
        idx_17 = txt_content.find("Scene 17 :")
        idx_17a = txt_content.find("Scene 17.A : INT. APARTMENT - CORRIDOR")
        idx_18 = txt_content.find("Scene 18 : EXT. STREET - NIGHT")
        idx_17b = txt_content.find("Scene 17.B : INT. APARTMENT - BALCONY")

        self.assertNotEqual(idx_17, -1)
        self.assertNotEqual(idx_17a, -1)
        self.assertNotEqual(idx_18, -1)
        self.assertNotEqual(idx_17b, -1)

        # 17B must appear after 18 in the exported screenplay text
        self.assertGreater(idx_17b, idx_18)

    def test_g_template_context_menu_button_preserves_intercut_id(self):
        """
        Test G: Regression test for server-rendered editor.html template.
        Verifies that for an intercut entry / intercut sub-scene, the Add Sub-Scene context-menu
        button retains that entry's own ID in data-id, rather than collapsing to its canonical parent ID.
        Also verifies ordinary scenes and sub-scenes retain their expected canonical-parent behavior.
        """
        cutback_17a = create_intercut_scene(
            self.script,
            source_scene_id=self.scene17a.id,
            current_scene_id=self.scene18.id
        )
        sub_17b = create_sub_scene(
            self.script,
            parent_scene_id=cutback_17a.id,
            heading='INT. APARTMENT - BALCONY'
        )

        response = self.client.get(reverse('script_editor', kwargs={'script_id': self.script.id}))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')

        # 1. Standard sub-scene (17A): context menu 'Add Sub-Scene' button has data-id of canonical parent (17)
        expected_17a_pattern = f'class="dropdown-item btn-action-add-sub" data-id="{self.scene17.id}"'
        self.assertIn(expected_17a_pattern, html)

        # 2. Intercut sub-scene (17B): context menu 'Add Sub-Scene' button MUST have data-id of 17B (sub_17b.id),
        # NOT canonical parent 17!
        expected_17b_pattern = f'class="dropdown-item btn-action-add-sub" data-id="{sub_17b.id}"'
        self.assertIn(expected_17b_pattern, html)

        # 3. Intercut entry (cutback_17a): context menu button has data-id of cutback_17a.id
        expected_cutback_pattern = f'class="dropdown-item btn-action-add-sub" data-id="{cutback_17a.id}"'
        self.assertIn(expected_cutback_pattern, html)

        # 4. Verify both desktop sidebar and offcanvas sidebar contain the intercut sub-scene's button with sub_17b.id
        self.assertEqual(html.count(expected_17b_pattern), 2)
        self.assertEqual(html.count(expected_cutback_pattern), 2)


"""
Tests for KadhaScript Batch 3, Step 4 — Issue H: Scene Renaming and Reordering.

Covers:
Renaming:
1. Rename a top-level scene with an English location.
2. Rename a scene with a multi-part location.
3. Rename a scene using Malayalam Unicode.
4. Rename a sub-scene and verify its parent relationship remains unchanged.
5. Canonical heading and location values returned by api_save_scene.
6. Renaming does not move the scene or alter unrelated screenplay content.

Reordering:
7. Move a main scene up and down with sequential renumbering.
8. Attached sub-scenes move with their parent main scene.
9. Move a sub-scene within its parent (confined strictly to parent).
10. Sub-scene cannot escape its parent (noop at boundary).
11. Scene elements (action, dialogue, characters) remain attached to correct scenes after moves.
12. Active ordering completely excludes soft-deleted (trashed) scenes.

Special Scene Types:
13. Duplicate-scene ordering, (Duplicate) suffix, and display metadata preservation.
14. Intercut / CutBack scene numbering preservation across movements.

Synchronization:
15. Successful move responses include full updated scenes_tree with correct identifiers, orders, and parents.
16. Frontend editor.js includes synchronized timeTokens for real-time location parsing.
"""

import json
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.conf import settings
from scripts.models import Script, Scene, ScriptElement
from scripts.services.scene_service import (
    serialize_scenes_hierarchy,
    create_sub_scene,
    duplicate_scene,
    create_intercut_scene,
    move_scene,
    resequence_script_scenes,
)


class Batch3Step4SceneRenamingAndReorderingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='writer_h', password='password123')
        self.client = Client()
        self.client.login(username='writer_h', password='password123')
        self.script = Script.objects.create(
            user=self.user,
            title='Issue H Test Screenplay'
        )

    # ----------------------------------------------------
    # RENAMING TESTS
    # ----------------------------------------------------

    def test_01_rename_top_level_scene_english_location(self):
        """1. Renaming a top-level scene with an English location updates heading and clean_location."""
        s = Scene.objects.create(script=self.script, scene_number=1, heading='INT. OLD CABIN - DAY', order=0)
        ScriptElement.objects.create(scene=s, element_type='action', content='Footsteps outside.', order=0)

        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s.id})
        res = self.client.post(url, data=json.dumps({
            'heading': 'INT. MOUNTAIN CABIN - NIGHT',
            'elements': [
                {'element_type': 'scene_heading', 'content': 'INT. MOUNTAIN CABIN - NIGHT', 'order': 0},
                {'element_type': 'action', 'content': 'Footsteps outside.', 'order': 1}
            ]
        }), content_type='application/json')

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['heading'], 'INT. MOUNTAIN CABIN - NIGHT')
        self.assertEqual(data['clean_location'], 'MOUNTAIN CABIN')
        self.assertEqual(data['clean_heading'], 'INT. MOUNTAIN CABIN - NIGHT')

        s.refresh_from_db()
        self.assertEqual(s.heading, 'INT. MOUNTAIN CABIN - NIGHT')
        self.assertEqual(s.clean_location, 'MOUNTAIN CABIN')

    def test_02_rename_multi_part_location(self):
        """2. Renaming a scene to a multi-part location retains all internal location segments."""
        s = Scene.objects.create(script=self.script, scene_number=1, heading='INT. OFFICE - DAY', order=0)

        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s.id})
        res = self.client.post(url, data=json.dumps({
            'heading': 'INT. CENTRAL JAIL - CORRIDOR - DAY',
            'elements': [
                {'element_type': 'scene_heading', 'content': 'INT. CENTRAL JAIL - CORRIDOR - DAY', 'order': 0}
            ]
        }), content_type='application/json')

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['clean_location'], 'CENTRAL JAIL - CORRIDOR')

        s.refresh_from_db()
        self.assertEqual(s.clean_location, 'CENTRAL JAIL - CORRIDOR')

    def test_03_rename_scene_malayalam_unicode(self):
        """3. Renaming a scene using Malayalam Unicode preserves Malayalam characters and clean_location."""
        s = Scene.objects.create(script=self.script, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        mal_heading = 'INT. തറവാട് - പൂമുഖം - രാത്രി'

        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s.id})
        res = self.client.post(url, data=json.dumps({
            'heading': mal_heading,
            'elements': [
                {'element_type': 'scene_heading', 'content': mal_heading, 'order': 0}
            ]
        }), content_type='application/json')

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['heading'], mal_heading)
        self.assertEqual(data['clean_location'], 'തറവാട് - പൂമുഖം')

        s.refresh_from_db()
        self.assertEqual(s.heading, mal_heading)
        self.assertEqual(s.clean_location, 'തറവാട് - പൂമുഖം')

    def test_04_rename_sub_scene_preserves_parent(self):
        """4. Renaming a sub-scene updates its heading while keeping parent_scene intact."""
        parent = Scene.objects.create(script=self.script, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        sub = create_sub_scene(self.script, parent_scene_id=parent.id, heading='KITCHEN')

        self.assertEqual(sub.parent_scene_id, parent.id)
        self.assertEqual(sub.display_number, 'Scene 1.A')

        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': sub.id})
        res = self.client.post(url, data=json.dumps({
            'heading': 'DINING AREA',
            'elements': [
                {'element_type': 'scene_heading', 'content': 'DINING AREA', 'order': 0}
            ]
        }), content_type='application/json')

        self.assertEqual(res.status_code, 200)
        sub.refresh_from_db()
        self.assertEqual(sub.heading, 'DINING AREA')
        self.assertEqual(sub.clean_location, 'DINING AREA')
        self.assertEqual(sub.parent_scene_id, parent.id)
        self.assertEqual(sub.display_number, 'Scene 1.A')

    def test_05_canonical_heading_and_location_response_contract(self):
        """5. api_save_scene returns complete canonical metadata after renaming."""
        s = Scene.objects.create(script=self.script, scene_number=1, heading='INT. CABIN - DAY', order=0)
        ScriptElement.objects.create(scene=s, element_type='action', content='Silent forest.', order=0)

        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s.id})
        res = self.client.post(url, data=json.dumps({
            'heading': 'EXT. FOREST CLEARING - NIGHT',
            'elements': [
                {'element_type': 'scene_heading', 'content': 'EXT. FOREST CLEARING - NIGHT', 'order': 0},
                {'element_type': 'action', 'content': 'Silent forest.', 'order': 1}
            ]
        }), content_type='application/json')

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['clean_location'], 'FOREST CLEARING')
        self.assertEqual(data['clean_heading'], 'EXT. FOREST CLEARING - NIGHT')
        self.assertEqual(data['full_display_heading'], 'Scene 1 : EXT. FOREST CLEARING - NIGHT')
        self.assertEqual(data['scene_identifier'], 'Scene 1')
        self.assertEqual(data['nav_identifier'], 'Scene 1')
        self.assertEqual(data['action_preview'], 'Silent forest.')

    def test_06_renaming_does_not_move_scene_or_alter_content(self):
        """6. Renaming does not shift scene.order or alter other elements."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1 - DAY', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='INT. SCENE 2 - DAY', order=1)
        ScriptElement.objects.create(scene=s2, element_type='action', content='Preserved content line.', order=0)
        ScriptElement.objects.create(scene=s2, element_type='dialogue', content='Important dialogue.', order=1)

        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s2.id})
        res = self.client.post(url, data=json.dumps({
            'heading': 'INT. RENAMED SCENE 2 - NIGHT',
            'elements': [
                {'element_type': 'scene_heading', 'content': 'INT. RENAMED SCENE 2 - NIGHT', 'order': 0},
                {'element_type': 'action', 'content': 'Preserved content line.', 'order': 1},
                {'element_type': 'dialogue', 'content': 'Important dialogue.', 'order': 2}
            ]
        }), content_type='application/json')

        self.assertEqual(res.status_code, 200)
        s1.refresh_from_db()
        s2.refresh_from_db()

        self.assertEqual(s1.order, 0)
        self.assertEqual(s1.scene_number, 1)
        self.assertEqual(s2.order, 1)
        self.assertEqual(s2.scene_number, 2)
        self.assertEqual(s2.heading, 'INT. RENAMED SCENE 2 - NIGHT')

        contents = list(s2.elements.order_by('order').values_list('content', flat=True))
        self.assertIn('Preserved content line.', contents)
        self.assertIn('Important dialogue.', contents)

    # ----------------------------------------------------
    # REORDERING TESTS
    # ----------------------------------------------------

    def test_07_move_main_scene_up_and_down(self):
        """7. Moving main scenes up/down resequences base numbers sequentially."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='SCENE 1', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='SCENE 2', order=1)
        s3 = Scene.objects.create(script=self.script, scene_number=3, heading='SCENE 3', order=2)

        # Move Scene 2 up past Scene 1 via API
        url_move = reverse('api_move_scene', kwargs={'script_id': self.script.id, 'scene_id': s2.id})
        res = self.client.post(url_move, data=json.dumps({'direction': 'up'}), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['status'], 'ok')

        ordered = self.script.get_ordered_scenes()
        self.assertEqual([sc.id for sc in ordered], [s2.id, s1.id, s3.id])
        self.assertEqual([sc.scene_number for sc in ordered], [1, 2, 3])
        self.assertEqual([sc.display_number for sc in ordered], ['Scene 1', 'Scene 2', 'Scene 3'])

        # Move Scene 2 down past Scene 1
        res2 = self.client.post(url_move, data=json.dumps({'direction': 'down'}), content_type='application/json')
        self.assertEqual(res2.status_code, 200)

        ordered2 = self.script.get_ordered_scenes()
        self.assertEqual([sc.id for sc in ordered2], [s1.id, s2.id, s3.id])
        self.assertEqual([sc.scene_number for sc in ordered2], [1, 2, 3])

    def test_08_attached_sub_scenes_move_with_parent(self):
        """8. Attached sub-scenes move with their parent main scene when the parent moves."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='SCENE 1', order=0)
        sub_1a = create_sub_scene(self.script, parent_scene_id=s1.id, heading='SUB 1A')
        sub_1b = create_sub_scene(self.script, parent_scene_id=s1.id, heading='SUB 1B')

        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='SCENE 2', order=3)
        resequence_script_scenes(self.script)

        # Move Scene 2 up past Scene 1 and its sub-scenes
        url_move = reverse('api_move_scene', kwargs={'script_id': self.script.id, 'scene_id': s2.id})
        res = self.client.post(url_move, data=json.dumps({'direction': 'up'}), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        ordered = self.script.get_ordered_scenes()
        # Scene 2 is now first, followed by Scene 1 (now Scene 2) and its sub-scenes 2.A, 2.B
        self.assertEqual([sc.id for sc in ordered], [s2.id, s1.id, sub_1a.id, sub_1b.id])

        s2.refresh_from_db()
        s1.refresh_from_db()
        sub_1a.refresh_from_db()
        sub_1b.refresh_from_db()

        self.assertEqual(s2.display_number, 'Scene 1')
        self.assertEqual(s1.display_number, 'Scene 2')
        self.assertEqual(sub_1a.display_number, 'Scene 2.A')
        self.assertEqual(sub_1b.display_number, 'Scene 2.B')
        self.assertEqual(sub_1a.parent_scene_id, s1.id)
        self.assertEqual(sub_1b.parent_scene_id, s1.id)

    def test_09_move_sub_scene_within_parent(self):
        """9. Sub-scenes reorder within their parent and update sub-letters sequentially."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='SCENE 1', order=0)
        sub_1a = create_sub_scene(self.script, parent_scene_id=s1.id, heading='SUB A')
        sub_1b = create_sub_scene(self.script, parent_scene_id=s1.id, heading='SUB B')
        sub_1c = create_sub_scene(self.script, parent_scene_id=s1.id, heading='SUB C')

        # Move SUB B up past SUB A
        url_move = reverse('api_move_scene', kwargs={'script_id': self.script.id, 'scene_id': sub_1b.id})
        res = self.client.post(url_move, data=json.dumps({'direction': 'up'}), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        ordered = self.script.get_ordered_scenes()
        self.assertEqual([sc.id for sc in ordered], [s1.id, sub_1b.id, sub_1a.id, sub_1c.id])

        sub_1b.refresh_from_db()
        sub_1a.refresh_from_db()
        sub_1c.refresh_from_db()

        self.assertEqual(sub_1b.display_number, 'Scene 1.A')
        self.assertEqual(sub_1a.display_number, 'Scene 1.B')
        self.assertEqual(sub_1c.display_number, 'Scene 1.C')

    def test_10_sub_scene_cannot_escape_parent_boundary(self):
        """10. Attempting to move the first sub-scene up returns noop and preserves parent."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='SCENE 1', order=0)
        sub_1a = create_sub_scene(self.script, parent_scene_id=s1.id, heading='SUB A')
        sub_1b = create_sub_scene(self.script, parent_scene_id=s1.id, heading='SUB B')

        # Move SUB A up (already top sub-scene)
        url_move = reverse('api_move_scene', kwargs={'script_id': self.script.id, 'scene_id': sub_1a.id})
        res = self.client.post(url_move, data=json.dumps({'direction': 'up'}), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['status'], 'noop')

        sub_1a.refresh_from_db()
        self.assertEqual(sub_1a.parent_scene_id, s1.id)
        self.assertEqual(sub_1a.display_number, 'Scene 1.A')

    def test_11_scene_elements_remain_attached_after_movement(self):
        """11. Screenplay elements remain strictly attached to their owning scene after movement."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='SCENE 1', order=0)
        ScriptElement.objects.create(scene=s1, element_type='action', content='EXCLUSIVE S1 ACTION', order=0)

        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='SCENE 2', order=1)
        ScriptElement.objects.create(scene=s2, element_type='action', content='EXCLUSIVE S2 ACTION', order=0)
        ScriptElement.objects.create(scene=s2, element_type='dialogue', content='EXCLUSIVE S2 DIALOGUE', order=1)

        # Move Scene 2 up past Scene 1
        url_move = reverse('api_move_scene', kwargs={'script_id': self.script.id, 'scene_id': s2.id})
        res = self.client.post(url_move, data=json.dumps({'direction': 'up'}), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        s1.refresh_from_db()
        s2.refresh_from_db()

        s1_contents = list(s1.elements.values_list('content', flat=True))
        s2_contents = list(s2.elements.values_list('content', flat=True))

        self.assertEqual(s1_contents, ['EXCLUSIVE S1 ACTION'])
        self.assertEqual(s2_contents, ['EXCLUSIVE S2 ACTION', 'EXCLUSIVE S2 DIALOGUE'])

    def test_12_reordering_excludes_trashed_scenes(self):
        """12. Trashed (is_deleted=True) scenes are excluded from movement and resequencing."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='SCENE 1', order=0)
        s_trashed = Scene.objects.create(script=self.script, scene_number=2, heading='TRASHED SCENE', order=1, is_deleted=True)
        s2 = Scene.objects.create(script=self.script, scene_number=3, heading='SCENE 2', order=2)

        resequence_script_scenes(self.script)
        s2.refresh_from_db()
        self.assertEqual(s2.scene_number, 2)

        # Move s2 up
        url_move = reverse('api_move_scene', kwargs={'script_id': self.script.id, 'scene_id': s2.id})
        res = self.client.post(url_move, data=json.dumps({'direction': 'up'}), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        ordered = self.script.get_ordered_scenes()
        self.assertEqual([sc.id for sc in ordered], [s2.id, s1.id])
        self.assertNotIn(s_trashed.id, [sc.id for sc in ordered])

    # ----------------------------------------------------
    # SPECIAL SCENE TYPES TESTS
    # ----------------------------------------------------

    def test_13_duplicate_scene_ordering_and_metadata_preservation(self):
        """13. Duplicate scene retains base scene number and (Duplicate) suffix across movements."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. JAIL - DAY', order=0)
        dup1 = duplicate_scene(self.script, source_scene=s1)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='EXT. STREET - NIGHT', order=2)
        resequence_script_scenes(self.script)

        self.assertEqual(dup1.scene_number, 1)
        self.assertIn('(Duplicate)', dup1.display_number)

        # Move s2 up past dup1
        url_move = reverse('api_move_scene', kwargs={'script_id': self.script.id, 'scene_id': s2.id})
        res = self.client.post(url_move, data=json.dumps({'direction': 'up'}), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        ordered = self.script.get_ordered_scenes()
        self.assertEqual([sc.id for sc in ordered], [s1.id, s2.id, dup1.id])

        dup1.refresh_from_db()
        self.assertIn('(Duplicate)', dup1.display_number)

    def test_14_intercut_numbering_preservation_across_movement(self):
        """14. CutBack/Intercut scene retains source scene numbering when surrounding scenes move."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='EXT. STREET - NIGHT', order=1)
        cutback = create_intercut_scene(self.script, source_scene_id=s1.id, current_scene_id=s2.id)
        s3 = Scene.objects.create(script=self.script, scene_number=3, heading='INT. OFFICE - DAY', order=3)
        resequence_script_scenes(self.script)

        self.assertEqual(cutback.scene_number, 1)
        self.assertEqual(cutback.display_number, 'Scene 1')

        # Move Scene 3 up past CutBack
        url_move = reverse('api_move_scene', kwargs={'script_id': self.script.id, 'scene_id': s3.id})
        res = self.client.post(url_move, data=json.dumps({'direction': 'up'}), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        cutback.refresh_from_db()
        self.assertEqual(cutback.scene_number, 1)
        self.assertEqual(cutback.display_number, 'Scene 1')

    # ----------------------------------------------------
    # SYNCHRONIZATION TESTS
    # ----------------------------------------------------

    def test_15_move_response_returns_authoritative_scenes_tree(self):
        """15. api_move_scene returns the updated scenes_tree with correct identifiers and locations."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. CABIN - DAY', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='EXT. FOREST - NIGHT', order=1)

        url_move = reverse('api_move_scene', kwargs={'script_id': self.script.id, 'scene_id': s2.id})
        res = self.client.post(url_move, data=json.dumps({'direction': 'up'}), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertIn('scenes_tree', data)
        tree = data['scenes_tree']
        self.assertEqual(len(tree), 2)

        # First tree item should be s2 (now Scene 1)
        self.assertEqual(tree[0]['id'], s2.id)
        self.assertEqual(tree[0]['nav_identifier'], 'Scene 1')
        self.assertEqual(tree[0]['clean_location'], 'FOREST')

        # Second tree item should be s1 (now Scene 2)
        self.assertEqual(tree[1]['id'], s1.id)
        self.assertEqual(tree[1]['nav_identifier'], 'Scene 2')
        self.assertEqual(tree[1]['clean_location'], 'CABIN')

    def test_16_frontend_editor_js_time_tokens_match_backend_clean_location(self):
        """16. Inspect editor.js to ensure timeTokens matches backend Scene.clean_location tokens."""
        import os
        js_path = os.path.join(settings.BASE_DIR, 'static', 'js', 'editor.js')
        with open(js_path, 'r', encoding='utf-8') as f:
            js_content = f.read()

        # Check that the tokens present in models.py TIME_TOKENS are also in editor.js
        required_tokens = ['DAY', 'NIGHT', 'DAWN', 'DUSK', 'RAIN', 'STORM', 'SNOW', 'FOG', 'WIND', 'മഴ']
        for token in required_tokens:
            self.assertIn(f"'{token}'", js_content, f"Token {token} must be present in editor.js timeTokens set")

    # ----------------------------------------------------
    # BATCH 3 ISSUE H FIX: RENAME DROPDOWN TESTS
    # ----------------------------------------------------

    def test_17_rename_option_in_desktop_and_mobile_menus(self):
        """17. Verify Rename option is rendered in both desktop and mobile menus for main and sub-scenes."""
        import os
        from django.template.loader import render_to_string

        html_path = os.path.join(settings.BASE_DIR, 'templates', 'scripts', 'editor.html')
        with open(html_path, 'r', encoding='utf-8') as f:
            html = f.read()

        # Verify presence of btn-action-rename in editor.html
        self.assertIn('btn-action-rename', html)
        self.assertIn('editorRenameModal', html)
        self.assertIn('editorRenameForm', html)
        self.assertIn('btnEditorSubmitRename', html)
        self.assertIn('btnEditorCancelRename', html)

        # Verify JS dynamically renders btn-action-rename
        js_path = os.path.join(settings.BASE_DIR, 'static', 'js', 'editor.js')
        with open(js_path, 'r', encoding='utf-8') as f:
            js = f.read()
        self.assertIn('btn-action-rename', js)
        self.assertIn('openRenameModal', js)
        self.assertIn('submitRenameScene', js)

    def test_18_rename_persists_heading_without_wiping_elements(self):
        """18. Renaming via api_save_scene with only heading persists new heading without deleting existing elements."""
        s = Scene.objects.create(script=self.script, scene_number=1, heading='INT. OLD STUDY - DAY', order=0)
        ScriptElement.objects.create(scene=s, element_type='action', content='Old clock ticks loudly.', order=0)
        ScriptElement.objects.create(scene=s, element_type='dialogue', content='Anyone there?', order=1)

        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s.id})
        # Note: 'elements' is omitted, as sent from the scene dropdown rename dialog
        res = self.client.post(url, data=json.dumps({
            'heading': 'INT. MODERN STUDY - NIGHT'
        }), content_type='application/json')

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['heading'], 'INT. MODERN STUDY - NIGHT')
        self.assertEqual(data['clean_location'], 'MODERN STUDY')
        self.assertEqual(data['action_preview'], 'Old clock ticks loudly.')

        s.refresh_from_db()
        self.assertEqual(s.heading, 'INT. MODERN STUDY - NIGHT')
        self.assertEqual(s.clean_location, 'MODERN STUDY')
        # Existing elements must be completely preserved!
        self.assertEqual(s.elements.count(), 2)
        self.assertEqual(s.elements.first().content, 'Old clock ticks loudly.')

    def test_19_rename_preserves_scene_ordering_and_number(self):
        """19. Renaming a scene keeps its scene_number, order, and identifier unchanged."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1 - DAY', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='INT. SCENE 2 - DAY', order=1)
        s3 = Scene.objects.create(script=self.script, scene_number=3, heading='INT. SCENE 3 - DAY', order=2)

        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s2.id})
        res = self.client.post(url, data=json.dumps({
            'heading': 'EXT. RENAMED SCENE 2 - NIGHT'
        }), content_type='application/json')

        self.assertEqual(res.status_code, 200)
        s2.refresh_from_db()
        self.assertEqual(s2.scene_number, 2)
        self.assertEqual(s2.order, 1)
        self.assertEqual(s2.scene_identifier, 'Scene 2')
        self.assertEqual(s2.clean_location, 'RENAMED SCENE 2')

        # Siblings unaffected
        s1.refresh_from_db()
        s3.refresh_from_db()
        self.assertEqual(s1.order, 0)
        self.assertEqual(s3.order, 2)

    def test_20_rename_sub_scene_preserves_hierarchy(self):
        """20. Renaming a sub-scene maintains its parent relationship and sub_letter identifier."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1 - DAY', order=0)
        parent = Scene.objects.create(script=self.script, scene_number=2, heading='INT. MANSION - DAY', order=1)
        sub = create_sub_scene(self.script, parent_scene_id=parent.id, heading='INT. CELLAR - NIGHT')

        self.assertEqual(sub.parent_scene_id, parent.id)
        self.assertEqual(sub.display_number, 'Scene 2.A')

        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': sub.id})
        res = self.client.post(url, data=json.dumps({
            'heading': 'EXT. CELLAR ENTRY - NIGHT'
        }), content_type='application/json')

        self.assertEqual(res.status_code, 200)
        sub.refresh_from_db()
        self.assertEqual(sub.parent_scene_id, parent.id)
        self.assertEqual(sub.display_number, 'Scene 2.A')
        self.assertEqual(sub.clean_location, 'CELLAR ENTRY')

    def test_21_rename_empty_heading_validation_error(self):
        """21. An empty or whitespace-only heading is rejected with HTTP 400 and does not report success."""
        s = Scene.objects.create(script=self.script, scene_number=1, heading='INT. ROOM - DAY', order=0)

        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s.id})
        res = self.client.post(url, data=json.dumps({
            'heading': '   '
        }), content_type='application/json')

        self.assertEqual(res.status_code, 400)
        data = res.json()
        self.assertEqual(data['status'], 'error')
        self.assertIn('Scene heading cannot be empty', data['message'])

        s.refresh_from_db()
        self.assertEqual(s.heading, 'INT. ROOM - DAY')

    def test_22_rename_preserves_malayalam_unicode(self):
        """22. Renaming a scene with Malayalam Unicode text preserves all characters and clean_location."""
        s = Scene.objects.create(script=self.script, scene_number=1, heading='INT. CABIN - DAY', order=0)
        mal_heading = 'EXT. കടൽത്തീരം - രാത്രി'

        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s.id})
        res = self.client.post(url, data=json.dumps({
            'heading': mal_heading
        }), content_type='application/json')

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['heading'], mal_heading)
        self.assertEqual(data['clean_location'], 'കടൽത്തീരം')

        s.refresh_from_db()
        self.assertEqual(s.heading, mal_heading)
        self.assertEqual(s.clean_location, 'കടൽത്തീരം')

    def test_23_move_actions_still_function_alongside_rename(self):
        """23. Existing move up and move down operations continue working as expected."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1 - DAY', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='INT. SCENE 2 - DAY', order=1)

        url_move = reverse('api_move_scene', kwargs={'script_id': self.script.id, 'scene_id': s2.id})
        res = self.client.post(url_move, data=json.dumps({'direction': 'up'}), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        s2.refresh_from_db()
        s1.refresh_from_db()
        self.assertEqual(s2.scene_number, 1)
        self.assertEqual(s1.scene_number, 2)

    def test_24_scene_card_typography_contracts_preserved(self):
        """24. Verify that scene card typography CSS contracts remain intact."""
        import os
        css_path = os.path.join(settings.BASE_DIR, 'static', 'css', 'editor.css')
        with open(css_path, 'r', encoding='utf-8') as f:
            css = f.read()

        # Scene number: 12px, bold
        self.assertIn('.scene-nav-number', css)
        self.assertIn('font-size: 12px', css)
        self.assertIn('font-weight: 700', css)

        # Scene location: 12px, bold
        self.assertIn('.scene-nav-location', css)

        # Action preview: 10px, max 2 lines
        self.assertIn('.scene-nav-action-preview', css)
        self.assertIn('font-size: 10px', css)
        self.assertIn('-webkit-line-clamp: 2', css)

    def test_25_move_scene_from_position_2_to_position_4(self):
        """25. Moving a scene from position 2 to position 4 renumbers all affected main scenes sequentially."""
        scenes = [
            Scene.objects.create(script=self.script, scene_number=i, heading=f'INT. SCENE {i} - DAY', order=i-1)
            for i in range(1, 6)
        ]
        s2 = scenes[1]
        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s2.id})
        res = self.client.post(url, data=json.dumps({
            'heading': s2.heading,
            'scene_number': 4
        }), content_type='application/json')

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['scene_number'], 4)
        self.assertEqual(data['scene_identifier'], 'Scene 4')

        # Check DB states
        for sc in scenes:
            sc.refresh_from_db()

        # Expected:
        # Scene 1: 1
        # Scene 3: 2
        # Scene 4: 3
        # Scene 2: 4
        # Scene 5: 5
        self.assertEqual(scenes[0].scene_number, 1)
        self.assertEqual(scenes[2].scene_number, 2)
        self.assertEqual(scenes[3].scene_number, 3)
        self.assertEqual(scenes[1].scene_number, 4)
        self.assertEqual(scenes[4].scene_number, 5)

        # Ordering check
        ordered_ids = [sc.id for sc in self.script.get_ordered_scenes()]
        self.assertEqual(ordered_ids, [scenes[0].id, scenes[2].id, scenes[3].id, scenes[1].id, scenes[4].id])

    def test_26_move_scene_from_position_4_to_position_2(self):
        """26. Moving a scene from position 4 to position 2 renumbers intermediate scenes."""
        scenes = [
            Scene.objects.create(script=self.script, scene_number=i, heading=f'INT. SCENE {i} - DAY', order=i-1)
            for i in range(1, 6)
        ]
        s4 = scenes[3]
        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s4.id})
        res = self.client.post(url, data=json.dumps({
            'heading': s4.heading,
            'scene_number': 2
        }), content_type='application/json')

        self.assertEqual(res.status_code, 200)
        for sc in scenes:
            sc.refresh_from_db()

        # Expected:
        # Scene 1: 1
        # Scene 4: 2
        # Scene 2: 3
        # Scene 3: 4
        # Scene 5: 5
        self.assertEqual(scenes[0].scene_number, 1)
        self.assertEqual(scenes[3].scene_number, 2)
        self.assertEqual(scenes[1].scene_number, 3)
        self.assertEqual(scenes[2].scene_number, 4)
        self.assertEqual(scenes[4].scene_number, 5)

    def test_27_requesting_current_position_is_noop_for_ordering(self):
        """27. Requesting the current scene number leaves ordering untouched but allows heading save."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1 - DAY', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='INT. SCENE 2 - DAY', order=1)
        s3 = Scene.objects.create(script=self.script, scene_number=3, heading='INT. SCENE 3 - DAY', order=2)

        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s2.id})
        res = self.client.post(url, data=json.dumps({
            'heading': 'INT. SCENE 2 RENAMED - NIGHT',
            'scene_number': 2
        }), content_type='application/json')

        self.assertEqual(res.status_code, 200)
        s1.refresh_from_db()
        s2.refresh_from_db()
        s3.refresh_from_db()

        self.assertEqual(s1.scene_number, 1)
        self.assertEqual(s2.scene_number, 2)
        self.assertEqual(s3.scene_number, 3)
        self.assertEqual(s2.heading, 'INT. SCENE 2 RENAMED - NIGHT')
        self.assertEqual([sc.id for sc in self.script.get_ordered_scenes()], [s1.id, s2.id, s3.id])

    def test_28_reject_zero_negative_decimal_empty_non_numeric(self):
        """28. Reject invalid scene_number inputs (0, negative, decimal, non-numeric, empty)."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1 - DAY', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='INT. SCENE 2 - DAY', order=1)

        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s1.id})

        invalid_values = [0, -1, -5, 2.5, '2.5', 'abc', '', 'zero', True, False]
        for val in invalid_values:
            res = self.client.post(url, data=json.dumps({
                'heading': 'INT. SCENE 1 - DAY',
                'scene_number': val
            }), content_type='application/json')
            self.assertEqual(res.status_code, 400, f"Expected 400 for scene_number={val}")
            data = res.json()
            self.assertEqual(data['status'], 'error')

    def test_29_reject_position_beyond_available_main_scene_count(self):
        """29. Reject requested scene_number beyond the total active main scenes count."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1 - DAY', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='INT. SCENE 2 - DAY', order=1)
        s3 = Scene.objects.create(script=self.script, scene_number=3, heading='INT. SCENE 3 - DAY', order=2)

        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s1.id})
        res = self.client.post(url, data=json.dumps({
            'heading': 'INT. SCENE 1 - DAY',
            'scene_number': 4
        }), content_type='application/json')

        self.assertEqual(res.status_code, 400)
        data = res.json()
        self.assertEqual(data['status'], 'error')
        self.assertIn('cannot exceed the total number of main scenes', data['message'])

    def test_30_renumbering_with_multiple_sub_scenes(self):
        """30. Moving a main scene with multiple sub-scenes carries sub-scenes along and recalculates their identifiers."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1 - DAY', order=0)
        sub_1a = Scene.objects.create(script=self.script, parent_scene=s1, scene_number=1, heading='INT. SUB 1A - DAY', order=1)
        sub_1b = Scene.objects.create(script=self.script, parent_scene=s1, scene_number=1, heading='INT. SUB 1B - DAY', order=2)

        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='INT. SCENE 2 - DAY', order=3)
        sub_2a = Scene.objects.create(script=self.script, parent_scene=s2, scene_number=2, heading='INT. SUB 2A - DAY', order=4)

        s3 = Scene.objects.create(script=self.script, scene_number=3, heading='INT. SCENE 3 - DAY', order=5)

        # Move Scene 1 to position 3
        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s1.id})
        res = self.client.post(url, data=json.dumps({
            'heading': s1.heading,
            'scene_number': 3
        }), content_type='application/json')

        self.assertEqual(res.status_code, 200)

        s1.refresh_from_db()
        sub_1a.refresh_from_db()
        sub_1b.refresh_from_db()
        s2.refresh_from_db()
        sub_2a.refresh_from_db()
        s3.refresh_from_db()

        # Expected:
        # Scene 2 -> Scene 1 (with 1.A)
        # Scene 3 -> Scene 2
        # Scene 1 -> Scene 3 (with 3.A, 3.B)
        self.assertEqual(s2.scene_number, 1)
        self.assertEqual(sub_2a.scene_number, 1)
        self.assertEqual(sub_2a.scene_identifier, 'Scene 1.A')

        self.assertEqual(s3.scene_number, 2)

        self.assertEqual(s1.scene_number, 3)
        self.assertEqual(sub_1a.scene_number, 3)
        self.assertEqual(sub_1a.scene_identifier, 'Scene 3.A')
        self.assertEqual(sub_1b.scene_number, 3)
        self.assertEqual(sub_1b.scene_identifier, 'Scene 3.B')

        # Reading order
        ordered = self.script.get_ordered_scenes()
        expected_ids = [s2.id, sub_2a.id, s3.id, s1.id, sub_1a.id, sub_1b.id]
        self.assertEqual([sc.id for sc in ordered], expected_ids)

    def test_31_preserving_sub_scene_parent_relationships(self):
        """31. Sub-scene parent_scene foreign keys and relative orders remain intact after renumbering."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1 - DAY', order=0)
        sub_1a = Scene.objects.create(script=self.script, parent_scene=s1, scene_number=1, heading='INT. SUB 1A - DAY', order=1)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='INT. SCENE 2 - DAY', order=2)

        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s1.id})
        self.client.post(url, data=json.dumps({'heading': s1.heading, 'scene_number': 2}), content_type='application/json')

        sub_1a.refresh_from_db()
        s1.refresh_from_db()
        self.assertEqual(sub_1a.parent_scene_id, s1.id)
        self.assertEqual(sub_1a.parent_scene, s1)
        self.assertIn(sub_1a, s1.sub_scenes.all())

    def test_32_preserving_scene_headings_elements_and_malayalam_dialogue(self):
        """32. Screenplay elements, dialogue, and Malayalam Unicode remain attached to original scenes."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. മുറി - DAY', order=0)
        e1 = ScriptElement.objects.create(scene=s1, element_type='character', content='രാജു', order=0)
        e2 = ScriptElement.objects.create(scene=s1, element_type='dialogue', content='നമസ്കാരം, സുഖമാണോ?', order=1)

        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='EXT. തെരുവ് - DAY', order=1)

        # Move Scene 1 to position 2
        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s1.id})
        res = self.client.post(url, data=json.dumps({
            'heading': 'INT. മുറി - DAY',
            'scene_number': 2
        }), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        s1.refresh_from_db()
        self.assertEqual(s1.scene_number, 2)
        self.assertEqual(s1.elements.count(), 2)
        elems = list(s1.elements.all().order_by('order'))
        self.assertEqual(elems[0].id, e1.id)
        self.assertEqual(elems[0].content, 'രാജു')
        self.assertEqual(elems[1].id, e2.id)
        self.assertEqual(elems[1].content, 'നമസ്കാരം, സുഖമാണോ?')

    def test_33_preserving_intercut_relationships(self):
        """33. Intercut scenes pointing to a renumbered scene retain their source reference and reflect updated number."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1 - DAY', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='INT. CABIN - DAY', order=1)
        s3 = Scene.objects.create(script=self.script, scene_number=3, heading='INT. SCENE 3 - DAY', order=2)
        intercut = Scene.objects.create(
            script=self.script,
            parent_scene=None,
            scene_number=2,
            heading='INT. CABIN - DAY',
            order=3,
            is_intercut=True,
            intercut_source=s2
        )

        # Move Scene 2 to position 1
        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s2.id})
        res = self.client.post(url, data=json.dumps({
            'heading': s2.heading,
            'scene_number': 1
        }), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        s2.refresh_from_db()
        intercut.refresh_from_db()
        self.assertEqual(s2.scene_number, 1)
        self.assertEqual(intercut.intercut_source_id, s2.id)
        self.assertEqual(intercut.scene_number, 1)

    def test_34_preserving_duplicate_scene_behavior(self):
        """34. Duplicate scenes stay grouped with their base scene and update their numbering."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1 - DAY', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='INT. SCENE 2 - DAY', order=1)
        s2_dup = Scene.objects.create(
            script=self.script,
            parent_scene=None,
            scene_number=2,
            heading='INT. SCENE 2 - DAY',
            order=2,
            is_duplicate=True,
            duplicate_number=1
        )
        s3 = Scene.objects.create(script=self.script, scene_number=3, heading='INT. SCENE 3 - DAY', order=3)

        # Resequence to verify baseline
        resequence_script_scenes(self.script)

        # Move Scene 2 to position 3
        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s2.id})
        res = self.client.post(url, data=json.dumps({
            'heading': s2.heading,
            'scene_number': 3
        }), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        s2.refresh_from_db()
        s2_dup.refresh_from_db()
        self.assertEqual(s2.scene_number, 3)
        self.assertEqual(s2_dup.scene_number, 3)
        self.assertEqual(s2_dup.scene_identifier, 'Scene 3 (Duplicate)')

    def test_35_preserving_existing_move_up_and_down_behavior(self):
        """35. Move Up and Move Down API still operates consistently alongside direct renumbering."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1 - DAY', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='INT. SCENE 2 - DAY', order=1)
        s3 = Scene.objects.create(script=self.script, scene_number=3, heading='INT. SCENE 3 - DAY', order=2)

        # Move s3 up -> s3 becomes 2, s2 becomes 3
        url_move = reverse('api_move_scene', kwargs={'script_id': self.script.id, 'scene_id': s3.id})
        res = self.client.post(url_move, data=json.dumps({'direction': 'up'}), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        s3.refresh_from_db()
        s2.refresh_from_db()
        self.assertEqual(s3.scene_number, 2)
        self.assertEqual(s2.scene_number, 3)

        # Move s3 down -> s3 becomes 3, s2 becomes 2
        res2 = self.client.post(url_move, data=json.dumps({'direction': 'down'}), content_type='application/json')
        self.assertEqual(res2.status_code, 200)
        s3.refresh_from_db()
        s2.refresh_from_db()
        self.assertEqual(s3.scene_number, 3)
        self.assertEqual(s2.scene_number, 2)

    def test_36_ensuring_desktop_and_mobile_lists_receive_same_updated_scenes_tree(self):
        """36. API save response contains scenes_tree containing authoritative hierarchical metadata for both desktop & mobile."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1 - DAY', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='INT. SCENE 2 - DAY', order=1)

        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s1.id})
        res = self.client.post(url, data=json.dumps({
            'heading': s1.heading,
            'scene_number': 2
        }), content_type='application/json')

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('scenes_tree', data)
        tree = data['scenes_tree']
        self.assertEqual(len(tree), 2)
        # Tree ordering: s2 first (Scene 1), s1 second (Scene 2)
        self.assertEqual(tree[0]['id'], s2.id)
        self.assertEqual(tree[0]['scene_number'], 1)
        self.assertEqual(tree[1]['id'], s1.id)
        self.assertEqual(tree[1]['scene_number'], 2)

    def test_37_ensuring_invalid_requests_leave_database_unchanged(self):
        """37. Failed validation does not save heading or modify database order."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. ORIGINAL - DAY', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='INT. SCENE 2 - DAY', order=1)

        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s1.id})
        res = self.client.post(url, data=json.dumps({
            'heading': 'INT. CHANGED - NIGHT',
            'scene_number': 999  # Invalid: beyond count of 2
        }), content_type='application/json')

        self.assertEqual(res.status_code, 400)
        s1.refresh_from_db()
        s2.refresh_from_db()
        self.assertEqual(s1.heading, 'INT. ORIGINAL - DAY')
        self.assertEqual(s1.scene_number, 1)
        self.assertEqual(s1.order, 0)
        self.assertEqual(s2.scene_number, 2)
        self.assertEqual(s2.order, 1)

    def test_38_ensuring_selected_scene_retains_identity_and_content_after_moving(self):
        """38. Moving a scene preserves its primary key ID, UUID, and elements without recreating records."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1 - DAY', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='INT. SCENE 2 - DAY', order=1)
        orig_s1_id = s1.id
        orig_s1_uuid = s1.scene_uuid

        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s1.id})
        res = self.client.post(url, data=json.dumps({
            'heading': s1.heading,
            'scene_number': 2
        }), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        s1.refresh_from_db()
        self.assertEqual(s1.id, orig_s1_id)
        self.assertEqual(s1.scene_uuid, orig_s1_uuid)

    def test_39_ensuring_exported_screenplay_order_and_identifiers_remain_correct(self):
        """39. get_ordered_scenes() returns correctly resequenced scenes for PDF/DOCX exporters."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1 - DAY', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='INT. SCENE 2 - DAY', order=1)
        s3 = Scene.objects.create(script=self.script, scene_number=3, heading='INT. SCENE 3 - DAY', order=2)

        url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': s1.id})
        self.client.post(url, data=json.dumps({'heading': s1.heading, 'scene_number': 3}), content_type='application/json')

        ordered = self.script.get_ordered_scenes()
        self.assertEqual([sc.id for sc in ordered], [s2.id, s3.id, s1.id])
        self.assertEqual([sc.scene_number for sc in ordered], [1, 2, 3])
        self.assertEqual([sc.scene_identifier for sc in ordered], ['Scene 1', 'Scene 2', 'Scene 3'])

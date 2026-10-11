"""
Tests for KadhaScript Batch 3, Step 3 — Issue G: Scene Card Details.

Covers:
1. Single-part location.
2. Multi-part location.
3. Trailing time-of-day removal.
4. Malayalam location.
5. First meaningful Action selection.
6. Empty Action elements ignored.
7. No Action content (empty preview).
8. Main scene identifier.
9. Sub-scene identifier.
10. Duplicate identifier.
11. CutBack numbering preservation.
12. action_preview API / serialization contract.
13. Step 2 save synchronization compatibility.
"""

import json
import os
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from scripts.models import Script, Scene, ScriptElement
from scripts.services.scene_service import (
    serialize_scenes_hierarchy,
    create_sub_scene,
    duplicate_scene,
    create_intercut_scene,
)


class Batch3Step3SceneCardDetailsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='writer_g', password='password123')
        self.client = Client()
        self.client.login(username='writer_g', password='password123')
        self.script = Script.objects.create(
            user=self.user,
            title='Scene Card Details Script'
        )

    def test_01_single_part_location(self):
        """1. Single-part location correctly removes prefix and time suffix."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. CABIN - DAY', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='EXT. FOREST - NIGHT', order=1)
        s3 = Scene.objects.create(script=self.script, scene_number=3, heading='POLICE STATION', order=2)

        self.assertEqual(s1.clean_location, 'CABIN')
        self.assertEqual(s2.clean_location, 'FOREST')
        self.assertEqual(s3.clean_location, 'POLICE STATION')

    def test_02_multi_part_location(self):
        """2. Multi-part location retains all location segments."""
        s1 = Scene.objects.create(
            script=self.script,
            scene_number=1,
            heading='INT. CENTRAL JAIL - CORRIDOR - DAY',
            order=0
        )
        s2 = Scene.objects.create(
            script=self.script,
            scene_number=2,
            heading='EXT. HOUSE - FRONT YARD - NIGHT',
            order=1
        )
        s3 = Scene.objects.create(
            script=self.script,
            scene_number=3,
            heading='INT. MANSION - 2ND FLOOR - MASTER BEDROOM - DAWN',
            order=2
        )

        self.assertEqual(s1.clean_location, 'CENTRAL JAIL - CORRIDOR')
        self.assertEqual(s2.clean_location, 'HOUSE - FRONT YARD')
        self.assertEqual(s3.clean_location, 'MANSION - 2ND FLOOR - MASTER BEDROOM')

    def test_03_trailing_time_of_day_removal(self):
        """3. Recognized time-of-day tokens are removed, non-time tokens are preserved."""
        # Standard time tokens removed
        for time_token in ['DAY', 'NIGHT', 'DAWN', 'DUSK', 'CONTINUOUS', 'LATER', 'SAME TIME', 'MOMENTS LATER']:
            sc = Scene.objects.create(
                script=self.script,
                scene_number=10,
                heading=f'INT. WAREHOUSE - {time_token}',
                order=10
            )
            self.assertEqual(sc.clean_location, 'WAREHOUSE')

        # Non-time trailing segments are preserved
        sc_nontime = Scene.objects.create(
            script=self.script,
            scene_number=11,
            heading='INT. POLICE HEADQUARTERS - ROOM 402',
            order=11
        )
        self.assertEqual(sc_nontime.clean_location, 'POLICE HEADQUARTERS - ROOM 402')

    def test_04_malayalam_location(self):
        """4. Malayalam location handling preserves Malayalam Unicode and removes Malayalam time tokens."""
        s_mal_time = Scene.objects.create(
            script=self.script,
            scene_number=1,
            heading='INT. തറവാട് - പൂമുഖം - പകൽ',
            order=0
        )
        s_mal_notime = Scene.objects.create(
            script=self.script,
            scene_number=2,
            heading='തറവാട് - അടുക്കള',
            order=1
        )
        s_mal_single = Scene.objects.create(
            script=self.script,
            scene_number=3,
            heading='തറവാട്',
            order=2
        )

        self.assertEqual(s_mal_time.clean_location, 'തറവാട് - പൂമുഖം')
        self.assertEqual(s_mal_notime.clean_location, 'തറവാട് - അടുക്കള')
        self.assertEqual(s_mal_single.clean_location, 'തറവാട്')

    def test_05_first_meaningful_action_selection(self):
        """5. First meaningful Action element is selected; non-action elements are ignored."""
        s = Scene.objects.create(script=self.script, scene_number=1, heading='INT. OFFICE - DAY', order=0)
        ScriptElement.objects.create(scene=s, element_type='scene_heading', content='INT. OFFICE - DAY', order=0)
        ScriptElement.objects.create(scene=s, element_type='character', content='RAGHAVAN', order=1)
        ScriptElement.objects.create(scene=s, element_type='dialogue', content='ഹലോ സാർ.', order=2)
        ScriptElement.objects.create(scene=s, element_type='note', content='Writer note here.', order=3)
        ScriptElement.objects.create(scene=s, element_type='action', content='രാഘവൻ പതുക്കെ വാതിൽ തുറന്ന് അകത്തേക്ക് കടക്കുന്നു.', order=4)
        ScriptElement.objects.create(scene=s, element_type='action', content='രണ്ടാമത്തെ ആക്ഷൻ വരി.', order=5)

        self.assertEqual(s.action_preview, 'രാഘവൻ പതുക്കെ വാതിൽ തുറന്ന് അകത്തേക്ക് കടക്കുന്നു.')

    def test_06_empty_action_elements_ignored(self):
        """6. Empty or whitespace-only Action elements are ignored until meaningful content is found."""
        s = Scene.objects.create(script=self.script, scene_number=1, heading='INT. ROOM - DAY', order=0)
        ScriptElement.objects.create(scene=s, element_type='action', content='', order=0)
        ScriptElement.objects.create(scene=s, element_type='action', content='   ', order=1)
        ScriptElement.objects.create(scene=s, element_type='action', content='The rain pours down heavily against the window.', order=2)
        ScriptElement.objects.create(scene=s, element_type='action', content='Later action line.', order=3)

        self.assertEqual(s.action_preview, 'The rain pours down heavily against the window.')

    def test_07_no_action_content(self):
        """7. Scenes without Action content safely return an empty string."""
        s = Scene.objects.create(script=self.script, scene_number=1, heading='INT. ROOM - DAY', order=0)
        ScriptElement.objects.create(scene=s, element_type='scene_heading', content='INT. ROOM - DAY', order=0)
        ScriptElement.objects.create(scene=s, element_type='character', content='VIKRAM', order=1)
        ScriptElement.objects.create(scene=s, element_type='dialogue', content='Are you there?', order=2)

        self.assertEqual(s.action_preview, '')

    def test_08_main_scene_identifier(self):
        """8. Main scene retains Scene N identifier semantics."""
        s = Scene.objects.create(script=self.script, scene_number=3, heading='INT. JAIL - DAY', order=2)
        self.assertEqual(s.nav_identifier, 'Scene 3')
        self.assertEqual(s.scene_identifier, 'Scene 3')

    def test_09_sub_scene_identifier(self):
        """9. Sub-scene retains Scene N.A and Scene NA identifier semantics."""
        Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1 - DAY', order=0)
        Scene.objects.create(script=self.script, scene_number=2, heading='INT. SCENE 2 - DAY', order=1)
        s3 = Scene.objects.create(script=self.script, scene_number=3, heading='INT. JAIL - DAY', order=2)
        sub = create_sub_scene(self.script, parent_scene_id=s3.id, heading='CORRIDOR')

        self.assertEqual(sub.nav_identifier, 'Scene 3A')
        self.assertEqual(sub.scene_identifier, 'Scene 3.A')

    def test_10_duplicate_identifier(self):
        """10. Duplicate scene retains (Duplicate) identifier semantics."""
        s = Scene.objects.create(script=self.script, scene_number=1, heading='INT. JAIL - DAY', order=0)
        dup = duplicate_scene(self.script, source_scene=s)

        self.assertIn('(Duplicate)', dup.nav_identifier)
        self.assertIn('(Duplicate)', dup.scene_identifier)

    def test_11_cutback_numbering_preservation(self):
        """11. CutBack scene retains source scene numbering semantics."""
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='EXT. STREET - DAY', order=1)
        cutback = create_intercut_scene(self.script, source_scene_id=s1.id, current_scene_id=s2.id)

        self.assertEqual(cutback.nav_identifier, 'Scene 1')
        self.assertEqual(cutback.scene_identifier, 'Scene 1')

    def test_12_action_preview_api_serialization_contract(self):
        """12. serialize_scenes_hierarchy, api_get_scene, api_save_scene, and api_duplicate_scene expose action_preview."""
        s = Scene.objects.create(script=self.script, scene_number=1, heading='INT. HARBOR - NIGHT', order=0)
        ScriptElement.objects.create(scene=s, element_type='action', content='കാറ്റ് ശക്തമായി വീശുന്നു.', order=0)

        # 1. serialize_scenes_hierarchy
        tree = serialize_scenes_hierarchy(self.script)
        self.assertTrue(len(tree) >= 1)
        tree_item = next(item for item in tree if item['id'] == s.id)
        self.assertIn('action_preview', tree_item)
        self.assertEqual(tree_item['action_preview'], 'കാറ്റ് ശക്തമായി വീശുന്നു.')
        self.assertEqual(tree_item['clean_location'], 'HARBOR')

        # 2. api_get_scene
        res_get = self.client.get(reverse('api_get_scene', args=[self.script.id, s.id]))
        self.assertEqual(res_get.status_code, 200)
        data_get = res_get.json()
        self.assertIn('action_preview', data_get['scene'])
        self.assertEqual(data_get['scene']['action_preview'], 'കാറ്റ് ശക്തമായി വീശുന്നു.')

        # 3. api_save_scene
        res_save = self.client.post(
            reverse('api_save_scene', args=[self.script.id, s.id]),
            data=json.dumps({
                'heading': 'INT. HARBOR - DOCKS - NIGHT',
                'elements': [
                    {'element_type': 'action', 'content': 'മഴ തുടങ്ങുന്നു.'}
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(res_save.status_code, 200)
        data_save = res_save.json()
        self.assertIn('action_preview', data_save)
        self.assertEqual(data_save['action_preview'], 'മഴ തുടങ്ങുന്നു.')
        self.assertEqual(data_save['clean_location'], 'HARBOR - DOCKS')

        # 4. api_duplicate_scene
        res_dup = self.client.post(reverse('api_duplicate_scene', args=[self.script.id, s.id]))
        self.assertEqual(res_dup.status_code, 200)
        data_dup = res_dup.json()
        self.assertIn('action_preview', data_dup['scene'])
        self.assertEqual(data_dup['scene']['action_preview'], 'മഴ തുടങ്ങുന്നു.')

    def test_13_step2_save_synchronization_compatibility(self):
        """13. Step 2 save synchronization compatibility: editor.js and css contracts."""
        # 1. Verify editor.js contracts
        js_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'js', 'editor.js')
        with open(js_path, 'r', encoding='utf-8') as f:
            js = f.read()

        self.assertIn('treeItem.action_preview = result.action_preview', js)
        self.assertIn('.scene-nav-action-preview', js)
        self.assertIn('scene-nav-location', js)
        self.assertIn('scene-nav-number', js)

        # 2. Verify editor.css contracts
        css_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'css', 'editor.css')
        with open(css_path, 'r', encoding='utf-8') as f:
            css = f.read()

        self.assertIn('.scene-nav-action-preview', css)
        self.assertIn('-webkit-line-clamp: 2', css)
        self.assertIn('overflow-wrap: anywhere', css)

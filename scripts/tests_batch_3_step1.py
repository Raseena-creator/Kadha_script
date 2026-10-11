import json
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from scripts.models import Script, Scene, ScriptElement
from scripts.services.scene_service import (
    resequence_script_scenes,
    duplicate_scene,
    create_sub_scene,
    create_intercut_scene,
)


class Batch3Step1SceneDuplicationAndIdentityTests(TestCase):
    """
    Focused regression test suite for Batch 3 Step 1 (Issue I):
    1. Duplicating the final main scene returns complete, authoritative scene metadata.
    2. Duplicating a main scene with sub-scenes preserves relationships and produces clean sequential sibling ordering.
    3. Missing scene identifier does not mislabel scenes as Scene 1.
    4. CutBack to Scene 1 retains its legitimate source relationship and numbering behavior.
    5. Existing scene content, IDs, and element counts are preserved.
    """

    def setUp(self):
        self.user = User.objects.create_user(username='screenwriter_step1', password='testpassword123')
        self.client = Client()
        self.client.login(username='screenwriter_step1', password='testpassword123')

        self.script = Script.objects.create(
            title='Marunnu - The Medicine',
            user=self.user,
            description='A gripping Malayalam psychological thriller.'
        )

    def test_01_duplicate_final_main_scene_api_metadata_contract(self):
        """
        Duplicating the final main scene must return complete, authoritative scene metadata
        consistent with the create-scene contract (scene_identifier, nav_identifier, clean_heading, etc.).
        """
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='EXT. FOREST - NIGHT', order=1)
        ScriptElement.objects.create(scene=s2, element_type='action', content='Footsteps echo in darkness.', order=0)
        resequence_script_scenes(self.script)

        url = reverse('api_duplicate_scene', args=[self.script.id, s2.id])
        res = self.client.post(url)
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertEqual(data['status'], 'ok')
        scene_data = data['scene']

        # Verify all contract fields are present and authoritative
        self.assertIn('scene_identifier', scene_data)
        self.assertIn('nav_identifier', scene_data)
        self.assertIn('full_display_heading', scene_data)
        self.assertIn('clean_heading', scene_data)
        self.assertIn('clean_location', scene_data)
        self.assertIn('transition', scene_data)
        self.assertIn('is_intercut', scene_data)

        # Authoritative values for duplicated Scene 2
        self.assertEqual(scene_data['scene_number'], 2)
        self.assertTrue(scene_data['is_duplicate'])
        self.assertEqual(scene_data['duplicate_number'], 1)
        self.assertEqual(scene_data['scene_identifier'], 'Scene 2 (Duplicate)')
        self.assertEqual(scene_data['nav_identifier'], 'Scene 2 (Duplicate)')
        self.assertEqual(scene_data['clean_heading'], 'EXT. FOREST - NIGHT')
        self.assertEqual(scene_data['clean_location'], 'FOREST')
        self.assertEqual(scene_data['full_display_heading'], 'Scene 2 (Duplicate) : EXT. FOREST - NIGHT')

    def test_02_duplicate_main_scene_with_subscenes_produces_valid_sibling_ordering(self):
        """
        Duplicating a main scene with sub-scenes must place the new main scene and all cloned
        sub-scenes immediately after the source hierarchy with distinct, sequential orders.
        No order collisions should occur.
        """
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. POLICE STATION - DAY', order=0)
        sub_1a = create_sub_scene(self.script, parent_scene_id=s1.id, heading='SUB INTERROGATION ROOM')
        sub_1b = create_sub_scene(self.script, parent_scene_id=s1.id, heading='SUB FORENSIC LAB')
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='EXT. STREET - NIGHT', order=3)
        resequence_script_scenes(self.script)

        # Duplicate Scene 1 (which has 2 sub-scenes)
        url = reverse('api_duplicate_scene', args=[self.script.id, s1.id])
        res = self.client.post(url)
        self.assertEqual(res.status_code, 200)

        ordered = self.script.get_ordered_scenes()

        # Check total scene count: s1, sub_1a, sub_1b, dup_s1, dup_sub_1a, dup_sub_1b, s2
        self.assertEqual(len(ordered), 7)

        # Verify strictly increasing, collision-free order values
        orders = [sc.order for sc in ordered]
        self.assertEqual(orders, list(range(len(ordered))))

        # Verify sequence of display numbers
        display_numbers = [sc.display_number for sc in ordered]
        expected_numbers = [
            'Scene 1',
            'Scene 1.A',
            'Scene 1.B',
            'Scene 1 (Duplicate)',
            'Scene 1.A (Duplicate)',
            'Scene 1.B (Duplicate)',
            'Scene 2',
        ]
        self.assertEqual(display_numbers, expected_numbers)

        # Verify cloned sub-scenes are correctly parented under dup_s1
        dup_parent = Scene.objects.get(id=res.json()['scene']['id'])
        self.assertEqual(dup_parent.sub_scenes.count(), 2)
        for cloned_sub in dup_parent.sub_scenes.all():
            self.assertEqual(cloned_sub.parent_scene_id, dup_parent.id)
            self.assertNotEqual(cloned_sub.id, sub_1a.id)
            self.assertNotEqual(cloned_sub.id, sub_1b.id)

    def test_03_cutback_to_scene_1_retains_legitimate_source_relationship(self):
        """
        Legitimate CutBack (intercut) to Scene 1 must retain its source relationship,
        is_intercut=True, and source scene reference without interference.
        """
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. LIVING ROOM - DAY', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='INT. OFFICE - DAY', order=1)
        s3 = Scene.objects.create(script=self.script, scene_number=3, heading='EXT. CAR - DAY', order=2)
        resequence_script_scenes(self.script)

        # Writer at Scene 3 creates CutBack to Scene 1
        cutback_scene = create_intercut_scene(self.script, source_scene_id=s1.id, current_scene_id=s3.id)

        self.assertTrue(cutback_scene.is_intercut)
        self.assertEqual(cutback_scene.intercut_source_id, s1.id)
        self.assertEqual(cutback_scene.scene_number, 1)
        self.assertEqual(cutback_scene.display_number, 'Scene 1')

        # Resequencing preserves intercut semantics
        resequence_script_scenes(self.script)
        cutback_scene.refresh_from_db()
        self.assertTrue(cutback_scene.is_intercut)
        self.assertEqual(cutback_scene.intercut_source_id, s1.id)

    def test_04_elements_and_content_preserved_during_duplication(self):
        """
        Cloned scenes and sub-scenes preserve all elements, element types, and Malayalam text exactly.
        """
        mal_heading = 'INT. തറവാട് - NIGHT'
        mal_action = 'ചുമരിലെ പഴയ ഘടികാരം ടിക് ടിക് ശബ്ദമുണ്ടാക്കുന്നു.'
        mal_character = 'രാഘവൻ'
        mal_dialogue = 'ആരാണ് അവിടെ?'
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading=mal_heading, order=0)
        ScriptElement.objects.create(scene=s1, element_type='action', content=mal_action, order=0)
        ScriptElement.objects.create(scene=s1, element_type='character', content=mal_character, order=1)
        ScriptElement.objects.create(scene=s1, element_type='dialogue', content=mal_dialogue, order=2)

        dup_s1 = duplicate_scene(self.script, s1)

        self.assertNotEqual(dup_s1.id, s1.id)
        self.assertEqual(dup_s1.heading, mal_heading)
        self.assertEqual(dup_s1.elements.count(), 3)

        elems = list(dup_s1.elements.order_by('order'))
        self.assertEqual(elems[0].element_type, 'action')
        self.assertEqual(elems[0].content, mal_action)
        self.assertEqual(elems[1].element_type, 'character')
        self.assertEqual(elems[1].content, mal_character)
        self.assertEqual(elems[2].element_type, 'dialogue')
        self.assertEqual(elems[2].content, mal_dialogue)

    def test_05_api_get_scene_and_duplicate_contract_consistency(self):
        """
        Verify that api_get_scene and api_duplicate_scene provide matching identifier contracts.
        """
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1 - DAY', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='INT. SCENE 2 - DAY', order=1)
        resequence_script_scenes(self.script)

        # GET Scene 2
        res_get = self.client.get(reverse('api_get_scene', args=[self.script.id, s2.id]))
        self.assertEqual(res_get.status_code, 200)
        get_data = res_get.json()['scene']

        # Duplicate Scene 2
        res_dup = self.client.post(reverse('api_duplicate_scene', args=[self.script.id, s2.id]))
        self.assertEqual(res_dup.status_code, 200)
        dup_data = res_dup.json()['scene']

        # Both endpoints must guarantee presence of all crucial identifier fields
        contract_keys = [
            'scene_number',
            'scene_identifier',
            'nav_identifier',
            'display_number',
            'display_number_formatted',
            'full_display_heading',
            'clean_heading',
            'clean_location',
            'transition',
            'is_intercut',
        ]
        for key in contract_keys:
            self.assertIn(key, get_data, f"api_get_scene missing {key}")
            self.assertIn(key, dup_data, f"api_duplicate_scene missing {key}")

        # Ensure duplicate is not mislabeled as Scene 1
        self.assertEqual(dup_data['scene_number'], 2)
        self.assertEqual(dup_data['scene_identifier'], 'Scene 2 (Duplicate)')
        self.assertEqual(dup_data['nav_identifier'], 'Scene 2 (Duplicate)')
        self.assertNotEqual(dup_data['scene_identifier'], 'Scene 1')

    def test_06_sub_scene_duplicate_contract_consistency(self):
        """
        Verify duplicating a sub-scene retains correct parent numbering and does not fall back to Scene 1.
        """
        s1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. SCENE 1 - DAY', order=0)
        s2 = Scene.objects.create(script=self.script, scene_number=2, heading='INT. SCENE 2 - DAY', order=1)
        s3 = Scene.objects.create(script=self.script, scene_number=3, heading='INT. SCENE 3 - DAY', order=2)
        sub_3a = create_sub_scene(self.script, parent_scene_id=s3.id, heading='SUB 3A')
        resequence_script_scenes(self.script)

        res_dup = self.client.post(reverse('api_duplicate_scene', args=[self.script.id, sub_3a.id]))
        self.assertEqual(res_dup.status_code, 200)
        dup_data = res_dup.json()['scene']

        self.assertTrue(dup_data['is_sub_scene'])
        self.assertEqual(dup_data['parent_scene_id'], s3.id)
        self.assertEqual(dup_data['scene_number'], 3)
        self.assertEqual(dup_data['scene_identifier'], 'Scene 3.A (Duplicate)')
        self.assertEqual(dup_data['nav_identifier'], 'Scene 3A (Duplicate)')

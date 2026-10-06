from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
import json

from scripts.models import Script, Scene, ScriptElement
from scripts.services.scene_service import (
    resequence_script_scenes,
    insert_scene_relative,
    create_sub_scene,
    move_scene,
)
from scripts.services.pdf_export import generate_screenplay_pdf
from scripts.services.docx_export import generate_screenplay_docx
from scripts.services.txt_export import generate_screenplay_txt


class SceneManagementAndMobileTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username='usera', password='password123')
        self.user_b = User.objects.create_user(username='userb', password='password123')

        self.script_a = Script.objects.create(
            user=self.user_a,
            title='ആനന്ദം (Anandam)',
            genre='Drama',
            script_type='Feature Film',
            language='Malayalam'
        )
        self.script_b = Script.objects.create(
            user=self.user_b,
            title='User B Script',
            genre='Thriller',
            script_type='Short Film',
        )

        self.client_a = Client()
        self.client_a.login(username='usera', password='password123')

        self.client_b = Client()
        self.client_b.login(username='userb', password='password123')

    def test_01_create_scene(self):
        """1. Create scene and verify exact single-line display format"""
        sc = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. LIVING ROOM - DAY', order=0)
        ScriptElement.objects.create(scene=sc, element_type='scene_heading', content=sc.heading, order=0)
        ScriptElement.objects.create(scene=sc, element_type='action', content='അനു വാതിൽ തുറക്കുന്നു.', order=1)

        self.assertEqual(sc.scene_number, 1)
        self.assertEqual(sc.display_number, 'Scene 1')
        self.assertEqual(sc.scene_identifier, 'Scene 1')
        self.assertEqual(sc.clean_heading, 'INT. LIVING ROOM - DAY')
        self.assertEqual(sc.full_display_heading, 'Scene 1 : INT. LIVING ROOM - DAY')
        self.assertFalse(sc.is_sub_scene)

    def test_02_03_04_insert_scene_after_scene_6(self):
        """
        2. Insert scene after Scene 6
        3. Existing Scene 7 becomes Scene 8
        4. Existing Scene 8 becomes Scene 9
        """
        # Create 8 initial scenes
        scenes = []
        for i in range(1, 9):
            sc = Scene.objects.create(
                script=self.script_a,
                scene_number=i,
                heading=f'INT. LOCATION {i} - DAY',
                order=i - 1
            )
            ScriptElement.objects.create(scene=sc, element_type='scene_heading', content=sc.heading, order=0)
            scenes.append(sc)

        scene_6 = scenes[5] # 0-indexed -> Scene 6
        scene_7_old = scenes[6]
        scene_8_old = scenes[7]

        # Insert after Scene 6
        new_scene = insert_scene_relative(
            self.script_a,
            reference_scene_id=scene_6.id,
            position='after',
            heading='EXT. PARK - SUNSET'
        )

        # Refresh all
        scene_7_old.refresh_from_db()
        scene_8_old.refresh_from_db()
        new_scene.refresh_from_db()

        self.assertEqual(new_scene.scene_number, 7)
        self.assertEqual(new_scene.display_number, 'Scene 7')
        self.assertEqual(new_scene.full_display_heading, 'Scene 7 : EXT. PARK - SUNSET')
        self.assertEqual(scene_7_old.scene_number, 8)
        self.assertEqual(scene_7_old.display_number, 'Scene 8')
        self.assertEqual(scene_8_old.scene_number, 9)
        self.assertEqual(scene_8_old.display_number, 'Scene 9')

        ordered = self.script_a.get_ordered_scenes()
        self.assertEqual(len(ordered), 9)
        self.assertEqual(ordered[6].id, new_scene.id)
        self.assertEqual(ordered[7].id, scene_7_old.id)
        self.assertEqual(ordered[8].id, scene_8_old.id)

    def test_05_06_delete_middle_scene_and_renumber(self):
        """
        5. Delete a middle scene
        6. Remaining scenes renumber correctly
        """
        scenes = []
        for i in range(1, 9):
            sc = Scene.objects.create(
                script=self.script_a,
                scene_number=i,
                heading=f'INT. LOCATION {i} - DAY',
                order=i - 1
            )
            scenes.append(sc)

        # Delete Scene 4 via API endpoint
        scene_4 = scenes[3]
        response = self.client_a.post(reverse('api_delete_scene', args=[self.script_a.id, scene_4.id]))
        self.assertEqual(response.status_code, 200)

        # Remaining scenes should be 1 to 7
        ordered = self.script_a.get_ordered_scenes()
        self.assertEqual(len(ordered), 7)
        for idx, sc in enumerate(ordered):
            self.assertEqual(sc.scene_number, idx + 1)
            self.assertEqual(sc.display_number, f'Scene {idx + 1}')
            self.assertEqual(sc.order, idx)

    def test_07_08_move_scene_up_and_down(self):
        """
        7. Move scene up
        8. Move scene down
        """
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        s2 = Scene.objects.create(script=self.script_a, scene_number=2, heading='EXT. ROAD - NIGHT', order=1)
        s3 = Scene.objects.create(script=self.script_a, scene_number=3, heading='INT. OFFICE - DAY', order=2)

        # Move s2 up -> s2 becomes Scene 1, s1 becomes Scene 2
        moved_up = move_scene(self.script_a, s2.id, 'up')
        self.assertTrue(moved_up)
        s1.refresh_from_db()
        s2.refresh_from_db()
        self.assertEqual(s2.display_number, 'Scene 1')
        self.assertEqual(s1.display_number, 'Scene 2')

        # Move s2 down -> s2 becomes Scene 2 again
        moved_down = move_scene(self.script_a, s2.id, 'down')
        self.assertTrue(moved_down)
        s1.refresh_from_db()
        s2.refresh_from_db()
        self.assertEqual(s1.display_number, 'Scene 1')
        self.assertEqual(s2.display_number, 'Scene 2')

    def test_09_10_11_sub_scene_creation_parent_and_numbering(self):
        """
        9. Create sub-scene
        10. Sub-scene has correct parent
        11. Sub-scenes have correct display numbering (e.g. Scene 3.A, Scene 3.B)
        """
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        s2 = Scene.objects.create(script=self.script_a, scene_number=2, heading='EXT. ROAD - NIGHT', order=1)
        s3 = Scene.objects.create(script=self.script_a, scene_number=3, heading='INT. OFFICE - DAY', order=2)
        s4 = Scene.objects.create(script=self.script_a, scene_number=4, heading='EXT. GARDEN - DAY', order=3)

        # Create sub-scenes 3.A, 3.B under Scene 3
        sub_3a = create_sub_scene(self.script_a, parent_scene_id=s3.id, heading='MEETING ROOM')
        sub_3b = create_sub_scene(self.script_a, parent_scene_id=s3.id, heading='CORRIDOR')

        self.assertEqual(sub_3a.parent_scene_id, s3.id)
        self.assertEqual(sub_3b.parent_scene_id, s3.id)
        self.assertTrue(sub_3a.is_sub_scene)
        self.assertEqual(sub_3a.display_number, 'Scene 3.A')
        self.assertEqual(sub_3a.full_display_heading, 'Scene 3.A : MEETING ROOM')
        self.assertEqual(sub_3b.display_number, 'Scene 3.B')
        self.assertEqual(sub_3b.full_display_heading, 'Scene 3.B : CORRIDOR')

        # Scene 4 should remain Scene 4
        s4.refresh_from_db()
        self.assertEqual(s4.scene_number, 4)
        self.assertEqual(s4.display_number, 'Scene 4')

        # Logical order should be: Scene 1, Scene 2, Scene 3, Scene 3.A, Scene 3.B, Scene 4
        ordered = self.script_a.get_ordered_scenes()
        self.assertEqual([sc.display_number for sc in ordered], ['Scene 1', 'Scene 2', 'Scene 3', 'Scene 3.A', 'Scene 3.B', 'Scene 4'])

    def test_12_delete_sub_scene(self):
        """12. Delete sub-scene"""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        sub_1a = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='LIVING ROOM')
        sub_1b = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='BEDROOM')
        s2 = Scene.objects.create(script=self.script_a, scene_number=2, heading='EXT. ROAD - NIGHT', order=1)

        # Delete sub_1a
        res = self.client_a.post(reverse('api_delete_scene', args=[self.script_a.id, sub_1a.id]))
        self.assertEqual(res.status_code, 200)

        # Sub 1b now becomes Scene 1.A
        sub_1b.refresh_from_db()
        self.assertEqual(sub_1b.display_number, 'Scene 1.A')
        self.assertEqual(sub_1b.full_display_heading, 'Scene 1.A : BEDROOM')
        s2.refresh_from_db()
        self.assertEqual(s2.display_number, 'Scene 2')

    def test_13_user_a_cannot_manipulate_user_b_scenes(self):
        """13. User A cannot manipulate User B scenes (Security & Ownership)"""
        s_b = Scene.objects.create(script=self.script_b, scene_number=1, heading='USER B SCENE', order=0)

        # User A tries to delete User B scene
        res = self.client_a.post(reverse('api_delete_scene', args=[self.script_b.id, s_b.id]))
        self.assertEqual(res.status_code, 404)

        # User A tries to insert into User B script
        res = self.client_a.post(
            reverse('api_insert_scene', args=[self.script_b.id]),
            data=json.dumps({'heading': 'HACKED'}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 404)

        # User A tries to save User B scene
        res = self.client_a.post(
            reverse('api_save_scene', args=[self.script_b.id, s_b.id]),
            data=json.dumps({'heading': 'HACKED'}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 404)

        # User B scene remains unchanged
        s_b.refresh_from_db()
        self.assertEqual(s_b.heading, 'USER B SCENE')

    def test_14_scene_elements_remain_attached_after_reordering(self):
        """14. Scene elements remain attached after reordering"""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        e1 = ScriptElement.objects.create(scene=s1, element_type='action', content='Action 1 in Scene 1', order=0)

        s2 = Scene.objects.create(script=self.script_a, scene_number=2, heading='EXT. ROAD - NIGHT', order=1)
        e2 = ScriptElement.objects.create(scene=s2, element_type='action', content='Action 2 in Scene 2', order=0)

        move_scene(self.script_a, s2.id, 'up')

        self.assertEqual(s1.elements.first().content, 'Action 1 in Scene 1')
        self.assertEqual(s2.elements.first().content, 'Action 2 in Scene 2')

    def test_15_export_order_remains_correct(self):
        """15. Export order remains correct (Scene 1, Scene 2, Scene 2.A, Scene 3)"""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        s2 = Scene.objects.create(script=self.script_a, scene_number=2, heading='EXT. ROAD - NIGHT', order=1)
        sub_2a = create_sub_scene(self.script_a, parent_scene_id=s2.id, heading='OUTSIDE HOUSE')
        s3 = Scene.objects.create(script=self.script_a, scene_number=3, heading='INT. OFFICE - DAY', order=2)

        ordered = self.script_a.get_ordered_scenes()
        expected = ['Scene 1', 'Scene 2', 'Scene 2.A', 'Scene 3']
        self.assertEqual([s.display_number for s in ordered], expected)

    def test_16_existing_editor_autosave_works(self):
        """16. Existing editor autosave still works and cleanly separates metadata from heading"""
        sc = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. HOUSE - NIGHT', order=0)
        
        payload = {
            'heading': 'INT. PALACE - NIGHT',
            'summary': 'A tense meeting',
            'elements': [
                {'element_type': 'scene_heading', 'content': 'INT. PALACE - NIGHT'},
                {'element_type': 'character', 'content': 'രാജാവ് (KING)'},
                {'element_type': 'dialogue', 'content': 'നമുക്ക് ഉടൻ തീരുമാനമെടുക്കണം.'},
            ]
        }

        res = self.client_a.post(
            reverse('api_save_scene', args=[self.script_a.id, sc.id]),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        sc.refresh_from_db()
        self.assertEqual(sc.heading, 'INT. PALACE - NIGHT')
        self.assertEqual(sc.clean_heading, 'INT. PALACE - NIGHT')
        self.assertEqual(sc.full_display_heading, 'Scene 1 : INT. PALACE - NIGHT')
        self.assertEqual(sc.elements.count(), 3)
        self.assertEqual(sc.elements.filter(element_type='character').first().content, 'രാജാവ് (KING)')

    def test_17_malayalam_text_preserved(self):
        """17. Malayalam text still works and is accurately saved and retrieved with full formatting"""
        sc = Scene.objects.create(script=self.script_a, scene_number=1, heading='വീടിന്റെ അകത്ത് - പകൽ', order=0)
        ScriptElement.objects.create(scene=sc, element_type='action', content='അനു നിശബ്ദയായി ഇരിക്കുന്നു.', order=0)
        sub = create_sub_scene(self.script_a, parent_scene_id=sc.id, heading='സ്വീകരണമുറി')

        res = self.client_a.get(reverse('api_get_scene', args=[self.script_a.id, sc.id]))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['scene']['heading'], 'വീടിന്റെ അകത്ത് - പകൽ')
        self.assertEqual(data['scene']['scene_identifier'], 'Scene 1')
        self.assertEqual(data['scene']['full_display_heading'], 'Scene 1 : വീടിന്റെ അകത്ത് - പകൽ')

        res_sub = self.client_a.get(reverse('api_get_scene', args=[self.script_a.id, sub.id]))
        self.assertEqual(res_sub.status_code, 200)
        data_sub = res_sub.json()
        self.assertEqual(data_sub['scene']['heading'], 'സ്വീകരണമുറി')
        self.assertEqual(data_sub['scene']['scene_identifier'], 'Scene 1.A')
        self.assertEqual(data_sub['scene']['full_display_heading'], 'Scene 1.A : സ്വീകരണമുറി')

    def test_18_pdf_export_with_subscenes(self):
        """18. Existing PDF export generates valid bytes with sub-scenes in Scene X : HEADING format"""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        ScriptElement.objects.create(scene=s1, element_type='action', content='മലയാളം വിവരണം.', order=0)
        sub = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='BALCONY')
        ScriptElement.objects.create(scene=sub, element_type='action', content='കാറ്റ് വീശുന്നു.', order=0)

        pdf_bytes = generate_screenplay_pdf(self.script_a)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))
        self.assertGreater(len(pdf_bytes), 1000)

    def test_19_docx_export_with_subscenes(self):
        """19. DOCX export generates valid docx with sub-scenes"""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        sub = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='BALCONY')

        docx_bytes = generate_screenplay_docx(self.script_a)
        self.assertTrue(docx_bytes.startswith(b'PK'))
        self.assertGreater(len(docx_bytes), 1000)

    def test_20_txt_export_with_subscenes(self):
        """20. TXT export generates formatted plain text with Scene 1 : HEADING and Scene 1.A : SUB-HEADING"""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        ScriptElement.objects.create(scene=s1, element_type='action', content='The sun rises.', order=0)
        sub = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='BALCONY - CONTINUOUS')
        ScriptElement.objects.create(scene=sub, element_type='action', content='He looks outside.', order=0)

        txt_content = generate_screenplay_txt(self.script_a)
        self.assertIn('Scene 1 : INT. HOUSE - DAY', txt_content)
        self.assertIn('Scene 1.A : BALCONY - CONTINUOUS', txt_content)

    def test_21_duplicate_scene_1(self):
        """Duplicate Scene 1 -> Scene 1 (Duplicate), subsequent scenes remain unchanged"""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        s2 = Scene.objects.create(script=self.script_a, scene_number=2, heading='EXT. STREET - NIGHT', order=1)
        s3 = Scene.objects.create(script=self.script_a, scene_number=3, heading='INT. CAR - DAY', order=2)

        res = self.client_a.post(reverse('api_duplicate_scene', args=[self.script_a.id, s1.id]))
        self.assertEqual(res.status_code, 200)

        ordered = self.script_a.get_ordered_scenes()
        self.assertEqual(len(ordered), 4)
        self.assertEqual(ordered[0].display_number, 'Scene 1')
        self.assertEqual(ordered[1].display_number, 'Scene 1 (Duplicate)')
        self.assertEqual(ordered[2].display_number, 'Scene 2')
        self.assertEqual(ordered[3].display_number, 'Scene 3')

    def test_22_duplicate_scene_3(self):
        """Duplicate Scene 3 -> Scene 3 (Duplicate)"""
        for i in range(1, 6):
            Scene.objects.create(script=self.script_a, scene_number=i, heading=f'SCENE {i}', order=i - 1)

        s3 = self.script_a.scenes.get(scene_number=3)
        res = self.client_a.post(reverse('api_duplicate_scene', args=[self.script_a.id, s3.id]))
        self.assertEqual(res.status_code, 200)

        ordered = self.script_a.get_ordered_scenes()
        self.assertEqual([s.display_number for s in ordered], ['Scene 1', 'Scene 2', 'Scene 3', 'Scene 3 (Duplicate)', 'Scene 4', 'Scene 5'])

    def test_23_duplicate_scene_7_preserves_scene_8(self):
        """
        Duplicate Scene 7 -> Scene 7 (Duplicate).
        Scene 8 must remain Scene 8, NOT renumbered to 9.
        """
        for i in range(1, 10):
            Scene.objects.create(script=self.script_a, scene_number=i, heading=f'SCENE {i}', order=i - 1)

        s7 = self.script_a.scenes.get(scene_number=7)
        res = self.client_a.post(reverse('api_duplicate_scene', args=[self.script_a.id, s7.id]))
        self.assertEqual(res.status_code, 200)

        ordered = self.script_a.get_ordered_scenes()
        self.assertEqual([s.display_number for s in ordered], ['Scene 1', 'Scene 2', 'Scene 3', 'Scene 4', 'Scene 5', 'Scene 6', 'Scene 7', 'Scene 7 (Duplicate)', 'Scene 8', 'Scene 9'])
        
        # Verify scene_number integer fields directly
        s8 = next(s for s in ordered if s.heading == 'SCENE 8')
        self.assertEqual(s8.scene_number, 8)

    def test_24_duplicate_scene_12(self):
        """Duplicate Scene 12 -> Scene 12 (Duplicate)"""
        for i in range(1, 15):
            Scene.objects.create(script=self.script_a, scene_number=i, heading=f'SCENE {i}', order=i - 1)

        s12 = self.script_a.scenes.get(scene_number=12)
        res = self.client_a.post(reverse('api_duplicate_scene', args=[self.script_a.id, s12.id]))
        self.assertEqual(res.status_code, 200)

        ordered = self.script_a.get_ordered_scenes()
        self.assertEqual(ordered[11].display_number, 'Scene 12')
        self.assertEqual(ordered[12].display_number, 'Scene 12 (Duplicate)')
        self.assertEqual(ordered[13].display_number, 'Scene 13')
        self.assertEqual(ordered[14].display_number, 'Scene 14')

    def test_25_26_multiple_duplicates_and_duplicating_duplicate(self):
        """
        Multiple duplicates produce Scene 7, Scene 7 (Duplicate), Scene 7 (Duplicate 2), Scene 7 (Duplicate 3).
        Duplicating a duplicate produces next sequential number based on original.
        """
        for i in range(1, 9):
            Scene.objects.create(script=self.script_a, scene_number=i, heading=f'SCENE {i}', order=i - 1)

        s7 = self.script_a.scenes.get(scene_number=7)

        # 1st Duplicate
        res1 = self.client_a.post(reverse('api_duplicate_scene', args=[self.script_a.id, s7.id]))
        self.assertEqual(res1.status_code, 200)
        dup1_id = res1.json()['scene']['id']

        # 2nd Duplicate: Duplicate the duplicate itself
        res2 = self.client_a.post(reverse('api_duplicate_scene', args=[self.script_a.id, dup1_id]))
        self.assertEqual(res2.status_code, 200)

        # 3rd Duplicate: Duplicate original again
        res3 = self.client_a.post(reverse('api_duplicate_scene', args=[self.script_a.id, s7.id]))
        self.assertEqual(res3.status_code, 200)

        ordered = self.script_a.get_ordered_scenes()
        expected = ['Scene 1', 'Scene 2', 'Scene 3', 'Scene 4', 'Scene 5', 'Scene 6', 'Scene 7', 'Scene 7 (Duplicate)', 'Scene 7 (Duplicate 2)', 'Scene 7 (Duplicate 3)', 'Scene 8']
        self.assertEqual([s.display_number for s in ordered], expected)

    def test_27_duplicate_content_independent_ids_and_malayalam(self):
        """
        Original content copied completely with Malayalam support.
        Elements receive distinct DB IDs.
        Editing duplicate does not modify original.
        Deleting original does not delete duplicate.
        """
        s7 = Scene.objects.create(script=self.script_a, scene_number=7, heading='INT. ചായക്കട - DAY', summary='ചർച്ച', order=0)
        e1 = ScriptElement.objects.create(scene=s7, element_type='scene_heading', content=s7.heading, order=0)
        e2 = ScriptElement.objects.create(scene=s7, element_type='action', content='ചായ തിളയ്ക്കുന്നു.', order=1)
        e3 = ScriptElement.objects.create(scene=s7, element_type='character', content='രാഘവൻ (RAGHAVAN)', order=2)
        e4 = ScriptElement.objects.create(scene=s7, element_type='dialogue', content='രണ്ട് ചായ പറയട്ടെ?', order=3)

        res = self.client_a.post(reverse('api_duplicate_scene', args=[self.script_a.id, s7.id]))
        self.assertEqual(res.status_code, 200)
        dup_id = res.json()['scene']['id']
        dup_scene = Scene.objects.get(id=dup_id)

        # 1. Check duplicate heading and elements
        self.assertEqual(dup_scene.heading, 'INT. ചായക്കട - DAY')
        self.assertEqual(dup_scene.summary, 'ചർച്ച')
        self.assertEqual(dup_scene.elements.count(), 4)

        orig_ids = set(s7.elements.values_list('id', flat=True))
        dup_ids = set(dup_scene.elements.values_list('id', flat=True))
        # 2. Database IDs must be completely distinct
        self.assertEqual(len(orig_ids.intersection(dup_ids)), 0)

        # 3. Edit duplicate scene element
        dup_action = dup_scene.elements.filter(element_type='action').first()
        dup_action.content = 'പുതിയ വിവരണം.'
        dup_action.save()

        # Original must remain unchanged
        e2.refresh_from_db()
        self.assertEqual(e2.content, 'ചായ തിളയ്ക്കുന്നു.')

        # 4. Delete original scene
        s7.delete()
        resequence_script_scenes(self.script_a)

        # Duplicate still exists independently
        dup_scene.refresh_from_db()
        self.assertTrue(Scene.objects.filter(id=dup_id).exists())

    def test_28_exports_display_duplicate_labels(self):
        """PDF, DOCX, and TXT exports display duplicate labels correctly"""
        for i in range(1, 7):
            Scene.objects.create(script=self.script_a, scene_number=i, heading=f'SCENE {i}', order=i - 1)

        s7 = Scene.objects.create(script=self.script_a, scene_number=7, heading='INT. TEA SHOP - DAY', order=6)
        ScriptElement.objects.create(scene=s7, element_type='action', content='Tea boiling.', order=0)

        res = self.client_a.post(reverse('api_duplicate_scene', args=[self.script_a.id, s7.id]))
        self.assertEqual(res.status_code, 200)

        # PDF Export
        pdf_bytes = generate_screenplay_pdf(self.script_a)
        self.assertTrue(len(pdf_bytes) > 500)

        # DOCX Export
        docx_bytes = generate_screenplay_docx(self.script_a)
        self.assertTrue(len(docx_bytes) > 500)

        # TXT Export
        txt_content = generate_screenplay_txt(self.script_a)
        self.assertIn('Scene 7 : INT. TEA SHOP - DAY', txt_content)
        self.assertIn('Scene 7 (Duplicate) : INT. TEA SHOP - DAY', txt_content)

    def test_29_duplicate_subscene(self):
        """Duplicate sub-scene Scene 3.A -> Scene 3.A (Duplicate)"""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='SCENE 1', order=0)
        s2 = Scene.objects.create(script=self.script_a, scene_number=2, heading='SCENE 2', order=1)
        s3 = Scene.objects.create(script=self.script_a, scene_number=3, heading='SCENE 3', order=2)
        sub_3a = create_sub_scene(self.script_a, parent_scene_id=s3.id, heading='SUB 3A')
        sub_3b = create_sub_scene(self.script_a, parent_scene_id=s3.id, heading='SUB 3B')

        res = self.client_a.post(reverse('api_duplicate_scene', args=[self.script_a.id, sub_3a.id]))
        self.assertEqual(res.status_code, 200)

        ordered = self.script_a.get_ordered_scenes()
        self.assertEqual([s.display_number for s in ordered], ['Scene 1', 'Scene 2', 'Scene 3', 'Scene 3.A', 'Scene 3.A (Duplicate)', 'Scene 3.B'])

    def test_30_duplicate_scene_with_subscenes(self):
        """Duplicate Scene with sub-scenes creates cloned sub-scenes under duplicate parent"""
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='SCENE 1', order=0)
        sub_1a = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='SUB 1A')
        ScriptElement.objects.create(scene=sub_1a, element_type='action', content='Sub element', order=0)

        res = self.client_a.post(reverse('api_duplicate_scene', args=[self.script_a.id, s1.id]))
        self.assertEqual(res.status_code, 200)
        dup_parent_id = res.json()['scene']['id']
        dup_parent = Scene.objects.get(id=dup_parent_id)

        self.assertEqual(dup_parent.display_number, 'Scene 1 (Duplicate)')
        self.assertEqual(dup_parent.sub_scenes.count(), 1)
        cloned_sub = dup_parent.sub_scenes.first()
        self.assertNotEqual(cloned_sub.id, sub_1a.id)
        self.assertEqual(cloned_sub.elements.count(), sub_1a.elements.count())
        self.assertNotEqual(cloned_sub.elements.first().id, sub_1a.elements.first().id)

    def test_31_subscene_actions_ui_rendering(self):
        """Verify scenes_management redirects to editor, and editor retains scenes section without standalone Scene Management page."""
        s7 = Scene.objects.create(script=self.script_a, scene_number=7, heading='SCENE 7', order=0)
        sub_7a = create_sub_scene(self.script_a, parent_scene_id=s7.id, heading='SUB 7A')

        # scenes_management URL safely redirects to editor (Req #4)
        res = self.client_a.get(reverse('scenes_management', args=[self.script_a.id]))
        self.assertEqual(res.status_code, 302)
        self.assertRedirects(res, reverse('script_editor', args=[self.script_a.id]))

        # Editor renders scenes and subscenes in offcanvasScenesList
        editor_res = self.client_a.get(reverse('script_editor', args=[self.script_a.id]))
        self.assertEqual(editor_res.status_code, 200)
        content = editor_res.content.decode('utf-8')
        self.assertIn('SCENE 7', content)
        self.assertIn('SUB 7A', content)
        self.assertIn('id="btnNavScenes"', content)
        self.assertIn('data-bs-target="#scenesOffcanvas"', content)

        # Test editor.html page - scene creation controls remain fully functional in editor toolbar (Part C)
        res_ed = self.client_a.get(f"{reverse('script_editor', args=[self.script_a.id])}?scene={sub_7a.id}")
        content_ed = res_ed.content.decode('utf-8')
        self.assertIn('btnTopAddScene', content_ed)
        self.assertIn('btnTopAddSubScene', content_ed)
        # Redundant action buttons are removed from the navigation sidebar/offcanvas
        self.assertNotIn('Insert Sub Scene Before', content_ed)
        self.assertNotIn('Insert Sub Scene After', content_ed)
        self.assertIn('scene-nav-item', content_ed)

    def _create_scenes_1_to_8_with_subs(self):
        for i in range(1, 7):
            Scene.objects.create(script=self.script_a, scene_number=i, heading=f'SCENE {i}', order=i-1)
        s7 = Scene.objects.create(script=self.script_a, scene_number=7, heading='SCENE 7', order=6)
        sub_7a = create_sub_scene(self.script_a, parent_scene_id=s7.id, heading='SUB 7A')
        sub_7b = create_sub_scene(self.script_a, parent_scene_id=s7.id, heading='SUB 7B')
        sub_7c = create_sub_scene(self.script_a, parent_scene_id=s7.id, heading='SUB 7C')
        s8 = Scene.objects.create(script=self.script_a, scene_number=8, heading='SCENE 8', order=7)
        resequence_script_scenes(self.script_a)
        return s7, sub_7a, sub_7b, sub_7c, s8

    def test_32_insert_sub_scene_before(self):
        """Insert Sub Scene Before 7B -> creates sibling before 7B under Scene 7 (7A, NEW, 7B, 7C)"""
        s7, sub_7a, sub_7b, sub_7c, s8 = self._create_scenes_1_to_8_with_subs()

        # Insert before 7B
        res = self.client_a.post(
            reverse('api_insert_scene', args=[self.script_a.id]),
            data=json.dumps({
                'reference_scene_id': sub_7b.id,
                'position': 'before',
                'heading': 'NEW SUB SCENE'
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)

        ordered = self.script_a.get_ordered_scenes()
        display_nums = [s.display_number for s in ordered if s.display_number.startswith('Scene 7') or s.display_number == 'Scene 8']
        self.assertEqual(display_nums, ['Scene 7', 'Scene 7.A', 'Scene 7.B', 'Scene 7.C', 'Scene 7.D', 'Scene 8'])
        
        # Verify parent
        new_scene = Scene.objects.get(heading='NEW SUB SCENE')
        self.assertEqual(new_scene.parent_scene_id, s7.id)
        self.assertEqual(new_scene.display_number, 'Scene 7.B')

    def test_33_insert_sub_scene_after(self):
        """Insert Sub Scene After 7B -> creates sibling after 7B under Scene 7 (7A, 7B, NEW, 7C)"""
        s7, sub_7a, sub_7b, sub_7c, s8 = self._create_scenes_1_to_8_with_subs()

        # Insert after 7B
        res = self.client_a.post(
            reverse('api_insert_scene', args=[self.script_a.id]),
            data=json.dumps({
                'reference_scene_id': sub_7b.id,
                'position': 'after',
                'heading': 'AFTER 7B SUB'
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)

        ordered = self.script_a.get_ordered_scenes()
        display_nums = [s.display_number for s in ordered if s.display_number.startswith('Scene 7') or s.display_number == 'Scene 8']
        self.assertEqual(display_nums, ['Scene 7', 'Scene 7.A', 'Scene 7.B', 'Scene 7.C', 'Scene 7.D', 'Scene 8'])

        new_scene = Scene.objects.get(heading='AFTER 7B SUB')
        self.assertEqual(new_scene.parent_scene_id, s7.id)
        self.assertEqual(new_scene.display_number, 'Scene 7.C')

    def test_34_sub_scene_move_confined_to_parent(self):
        """Move up/down stays strictly within parent's sub-scenes, never promotes to main scene"""
        s7, sub_7a, sub_7b, sub_7c, s8 = self._create_scenes_1_to_8_with_subs()

        # Move 7B Up -> 7B becomes first sub-scene
        res = self.client_a.post(
            reverse('api_move_scene', args=[self.script_a.id, sub_7b.id]),
            data=json.dumps({'direction': 'up'}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['status'], 'ok')
        sub_7b.refresh_from_db()
        self.assertEqual(sub_7b.parent_scene_id, s7.id)
        self.assertEqual(sub_7b.display_number, 'Scene 7.A')

        # Move 7B Up again (now at top) -> noop, cannot promote to main scene
        res2 = self.client_a.post(
            reverse('api_move_scene', args=[self.script_a.id, sub_7b.id]),
            data=json.dumps({'direction': 'up'}),
            content_type='application/json'
        )
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()['status'], 'noop')
        sub_7b.refresh_from_db()
        self.assertEqual(sub_7b.parent_scene_id, s7.id)

    def test_35_sub_scene_delete_preserves_parent_and_siblings(self):
        """Deleting 7B leaves Scene 7 and siblings intact"""
        s7, sub_7a, sub_7b, sub_7c, s8 = self._create_scenes_1_to_8_with_subs()

        res = self.client_a.post(reverse('api_delete_scene', args=[self.script_a.id, sub_7b.id]))
        self.assertEqual(res.status_code, 200)

        self.assertTrue(Scene.objects.filter(id=s7.id).exists())
        self.assertTrue(Scene.objects.filter(id=sub_7a.id).exists())
        self.assertFalse(Scene.objects.filter(id=sub_7b.id).exists())
        self.assertTrue(Scene.objects.filter(id=sub_7c.id).exists())

        ordered = self.script_a.get_ordered_scenes()
        s7_and_subs = [s.display_number for s in ordered if s.display_number.startswith('Scene 7')]
        self.assertEqual(s7_and_subs, ['Scene 7', 'Scene 7.A', 'Scene 7.B'])

    def test_36_exact_requirements_scenario(self):
        """
        Comprehensive test of exact user requirement sequence:
        Scene 1 : INT. HOUSE - DAY
        Scene 1.A : LIVING ROOM
        Scene 1.B : BEDROOM
        Scene 1.C : KITCHEN
        Scene 2 : EXT. ROAD - NIGHT
        Scene 2.A : OUTSIDE HOUSE
        Scene 2.B : ROAD JUNCTION
        Scene 3 : INT. OFFICE - DAY
        Scene 3.A : RECEPTION
        Scene 3.B : MANAGER'S ROOM
        """
        # Create Scene 1
        s1 = Scene.objects.create(script=self.script_a, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        sub_1a = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='LIVING ROOM')
        sub_1b = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='BEDROOM')
        sub_1c = create_sub_scene(self.script_a, parent_scene_id=s1.id, heading='KITCHEN')

        # Create Scene 2
        s2 = Scene.objects.create(script=self.script_a, scene_number=2, heading='EXT. ROAD - NIGHT', order=4)
        sub_2a = create_sub_scene(self.script_a, parent_scene_id=s2.id, heading='OUTSIDE HOUSE')
        sub_2b = create_sub_scene(self.script_a, parent_scene_id=s2.id, heading='ROAD JUNCTION')

        # Create Scene 3
        s3 = Scene.objects.create(script=self.script_a, scene_number=3, heading='INT. OFFICE - DAY', order=7)
        sub_3a = create_sub_scene(self.script_a, parent_scene_id=s3.id, heading='RECEPTION')
        sub_3b = create_sub_scene(self.script_a, parent_scene_id=s3.id, heading="MANAGER'S ROOM")

        resequence_script_scenes(self.script_a)

        ordered = self.script_a.get_ordered_scenes()
        self.assertEqual(len(ordered), 10)

        expected_headings = [
            'Scene 1 : INT. HOUSE - DAY',
            'Scene 1.A : LIVING ROOM',
            'Scene 1.B : BEDROOM',
            'Scene 1.C : KITCHEN',
            'Scene 2 : EXT. ROAD - NIGHT',
            'Scene 2.A : OUTSIDE HOUSE',
            'Scene 2.B : ROAD JUNCTION',
            'Scene 3 : INT. OFFICE - DAY',
            'Scene 3.A : RECEPTION',
            "Scene 3.B : MANAGER'S ROOM",
        ]

        actual_headings = [sc.full_display_heading for sc in ordered]
        self.assertEqual(actual_headings, expected_headings)

        # Verify script_detail and scenes_management compatibility redirects to editor (Req #2, #3, #4)
        detail_res = self.client_a.get(reverse('script_detail', args=[self.script_a.id]))
        self.assertEqual(detail_res.status_code, 302)
        self.assertRedirects(detail_res, reverse('script_editor', args=[self.script_a.id]))

        scenes_res = self.client_a.get(reverse('scenes_management', args=[self.script_a.id]))
        self.assertEqual(scenes_res.status_code, 302)
        self.assertRedirects(scenes_res, reverse('script_editor', args=[self.script_a.id]))

        # Verify editor page (editor.html) contains all scenes and sub-scenes
        editor_res = self.client_a.get(reverse('script_editor', args=[self.script_a.id]))
        self.assertEqual(editor_res.status_code, 200)
        import html
        editor_content = html.unescape(editor_res.content.decode('utf-8'))
        for expected in expected_headings:
            self.assertIn(expected, editor_content)

        # Verify TXT Export
        txt_export = generate_screenplay_txt(self.script_a)
        for expected in expected_headings:
            self.assertIn(expected, txt_export)

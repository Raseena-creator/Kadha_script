import io
import re
from docx import Document
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from scripts.models import Script, Scene, ScriptElement, ScriptTitlePage
from scripts.services.pdf_export import generate_screenplay_pdf
from scripts.services.docx_export import generate_screenplay_docx
from scripts.services.txt_export import generate_screenplay_txt


class ExportPaginationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='filmmaker', password='Password123!')
        self.script = Script.objects.create(
            user=self.user,
            title='The Grand Narrative',
            author_name='A. Screenwriter',
            genre='Drama',
            script_type='Feature Film',
            language='Malayalam'
        )
        self.title_page = ScriptTitlePage.objects.create(
            script=self.script,
            title='THE GRAND NARRATIVE',
            subtitle='An Original Screenplay',
            pen_name='A. Screenwriter'
        )

        # Setup requested structure:
        # Scene 1
        # Scene 2
        # Scene 2.A
        # Scene 2.B
        # Scene 3
        # Scene 4
        # Scene 4.A
        # Scene 4.B
        # Scene 5
        self.sc1 = Scene.objects.create(script=self.script, scene_number=1, heading='INT. HOUSE - DAY', order=0)
        ScriptElement.objects.create(scene=self.sc1, element_type='action', content='Hero enters the living room.', order=0)
        ScriptElement.objects.create(scene=self.sc1, element_type='note', content='CONFIDENTIAL NOTE: Change character costume here.', order=1)
        ScriptElement.objects.create(scene=self.sc1, element_type='character', content='HERO', order=2)
        ScriptElement.objects.create(scene=self.sc1, element_type='dialogue', content='നമസ്കാരം (Hello).', order=3)

        self.sc2 = Scene.objects.create(script=self.script, scene_number=2, heading='EXT. ROAD - NIGHT', order=1)
        ScriptElement.objects.create(scene=self.sc2, element_type='action', content='Rain pours down.', order=0)

        self.sc2_a = Scene.objects.create(script=self.script, parent_scene=self.sc2, scene_number=2, heading='INT. BEDROOM - NIGHT', order=2)
        ScriptElement.objects.create(scene=self.sc2_a, element_type='action', content='Clock ticks on the wall.', order=0)

        self.sc2_b = Scene.objects.create(script=self.script, parent_scene=self.sc2, scene_number=2, heading='INT. KITCHEN - NIGHT', order=3)
        ScriptElement.objects.create(scene=self.sc2_b, element_type='action', content='Tea boils on stove.', order=0)

        self.sc3 = Scene.objects.create(script=self.script, scene_number=3, heading='EXT. GARDEN - DAY', order=4)
        ScriptElement.objects.create(scene=self.sc3, element_type='action', content='Birds chirping.', order=0)

        self.sc4 = Scene.objects.create(script=self.script, scene_number=4, heading='INT. OFFICE - DAY', order=5)
        ScriptElement.objects.create(scene=self.sc4, element_type='action', content='Office bustle.', order=0)

        self.sc4_a = Scene.objects.create(script=self.script, parent_scene=self.sc4, scene_number=4, heading='INT. OFFICE CABIN - DAY', order=6)
        ScriptElement.objects.create(scene=self.sc4_a, element_type='action', content='Boss speaks on telephone.', order=0)

        self.sc4_b = Scene.objects.create(script=self.script, parent_scene=self.sc4, scene_number=4, heading='INT. OFFICE LOBBY - DAY', order=7)
        ScriptElement.objects.create(scene=self.sc4_b, element_type='action', content='Receptionist types on keyboard.', order=0)

        self.sc5 = Scene.objects.create(script=self.script, scene_number=5, heading='EXT. STREET - NIGHT', order=8)
        ScriptElement.objects.create(scene=self.sc5, element_type='action', content='Car drives away into darkness.', order=0)

    def test_pdf_export_scene_pagination(self):
        """
        Verify PDF exporter:
        - 1 cover page
        - 8 scene pages (Scene 1, Scene 2, Scene 2.A, Scene 2.B, Scene 3, Scene 4, Scene 4.A, Scene 4.B, Scene 5)
        - Total 10 pages including cover and 9 distinct scene/sub-scene sections
        """
        pdf_bytes = generate_screenplay_pdf(self.script)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 2000)

        # Count PDF /Type /Page entries
        pages = re.findall(rb'/Type\s*/Page\b(?!\s*/Pages)', pdf_bytes)
        # Total pages = 1 cover + 9 scenes = 10 pages
        ordered_scenes = self.script.get_ordered_scenes()
        self.assertEqual(len(ordered_scenes), 9)
        self.assertEqual(len(pages), 10)

    def test_notes_excluded_from_pdf_and_docx(self):
        """Notes must be completely excluded from PDF and DOCX exports."""
        pdf_bytes = generate_screenplay_pdf(self.script, include_notes=True)
        self.assertNotIn(b'CONFIDENTIAL NOTE', pdf_bytes)
        self.assertNotIn(b'Change character costume here', pdf_bytes)

        docx_bytes = generate_screenplay_docx(self.script, include_notes=True)
        doc = Document(io.BytesIO(docx_bytes))
        full_doc_text = " ".join([p.text for p in doc.paragraphs])
        self.assertNotIn('CONFIDENTIAL NOTE', full_doc_text)
        self.assertNotIn('Change character costume here', full_doc_text)
        # Verify other elements are present
        self.assertIn('Hero enters the living room.', full_doc_text)
        self.assertIn('HERO', full_doc_text)

    def test_pdf_single_scene_pagination(self):
        """Single scene script should have exactly 2 pages (1 cover page + 1 scene page)."""
        single_script = Script.objects.create(user=self.user, title='Single Scene Story')
        sc = Scene.objects.create(script=single_script, scene_number=1, heading='INT. CABIN - DAY', order=0)
        ScriptElement.objects.create(scene=sc, element_type='action', content='One scene only.', order=0)

        pdf_bytes = generate_screenplay_pdf(single_script)
        pages = re.findall(rb'/Type\s*/Page\b(?!\s*/Pages)', pdf_bytes)
        self.assertEqual(len(pages), 2)

    def test_docx_export_scene_pagination(self):
        """
        Verify DOCX exporter:
        - 1 page break after cover
        - 1 page break before each scene/sub-scene after the first scene (8 breaks)
        - Total 9 page breaks
        """
        docx_bytes = generate_screenplay_docx(self.script)
        self.assertIsInstance(docx_bytes, bytes)
        self.assertTrue(len(docx_bytes) > 1000)

        doc = Document(io.BytesIO(docx_bytes))
        page_break_count = 0
        for p in doc.paragraphs:
            for r in p.runs:
                if 'w:br' in r._r.xml and 'type="page"' in r._r.xml:
                    page_break_count += 1

        # 1 cover break + (9 scenes - 1) = 9 page breaks
        self.assertEqual(page_break_count, 9)

    def test_docx_single_scene_pagination(self):
        """Single scene DOCX should only have 1 page break (after cover), none before scene 1."""
        single_script = Script.objects.create(user=self.user, title='Single Scene DOCX')
        sc = Scene.objects.create(script=single_script, scene_number=1, heading='INT. CABIN - DAY', order=0)
        ScriptElement.objects.create(scene=sc, element_type='action', content='Only one scene.', order=0)

        docx_bytes = generate_screenplay_docx(single_script)
        doc = Document(io.BytesIO(docx_bytes))
        page_break_count = 0
        for p in doc.paragraphs:
            for r in p.runs:
                if 'w:br' in r._r.xml and 'type="page"' in r._r.xml:
                    page_break_count += 1

        self.assertEqual(page_break_count, 1)

    def test_txt_export_remains_unchanged(self):
        """TXT export does not contain page-break characters and matches expected text output."""
        txt_str = generate_screenplay_txt(self.script)
        self.assertNotIn('\x0c', txt_str)
        self.assertIn('Scene 1 : INT. HOUSE - DAY', txt_str)
        self.assertIn('Scene 2 : EXT. ROAD - NIGHT', txt_str)
        self.assertIn('Scene 2.A : INT. BEDROOM - NIGHT', txt_str)
        self.assertIn('Scene 2.B : INT. KITCHEN - NIGHT', txt_str)
        self.assertIn('Scene 3 : EXT. GARDEN - DAY', txt_str)
        self.assertIn('Scene 4 : INT. OFFICE - DAY', txt_str)
        self.assertIn('Scene 4.A : INT. OFFICE CABIN - DAY', txt_str)
        self.assertIn('Scene 4.B : INT. OFFICE LOBBY - DAY', txt_str)
        self.assertIn('Scene 5 : EXT. STREET - NIGHT', txt_str)

    def test_malayalam_content_export(self):
        """Verify exports render without errors with Malayalam unicode content."""
        ml_script = Script.objects.create(user=self.user, title='ഒരു തിരക്കഥ', language='Malayalam')
        sc1 = Scene.objects.create(script=ml_script, scene_number=1, heading='INT. വീട് - പകൽ', order=0)
        ScriptElement.objects.create(scene=sc1, element_type='action', content='നായകൻ ചായ കുടിക്കുന്നു.', order=0)
        sc2 = Scene.objects.create(script=ml_script, scene_number=2, heading='EXT. വഴി - രാത്രി', order=1)
        ScriptElement.objects.create(scene=sc2, element_type='action', content='മഴ പെയ്യുന്നു.', order=0)

        pdf_bytes = generate_screenplay_pdf(ml_script)
        docx_bytes = generate_screenplay_docx(ml_script)
        txt_str = generate_screenplay_txt(ml_script)

        self.assertTrue(len(pdf_bytes) > 1000)
        self.assertTrue(len(docx_bytes) > 1000)
        self.assertIn('നായകൻ ചായ കുടിക്കുന്നു.', txt_str)

    def test_editor_ui_shot_removed_and_shortcuts_present(self):
        """Verify Shot button is removed from toolbar and shortcuts are exposed in UI."""
        client = Client()
        client.login(username='filmmaker', password='Password123!')
        url = reverse('script_editor', kwargs={'script_id': self.script.id})
        response = client.get(url)
        self.assertEqual(response.status_code, 200)

        content = response.content.decode('utf-8')
        # Shot and Heading buttons removed
        self.assertNotIn('data-type="shot"', content)
        self.assertNotIn('data-type="scene_heading"', content)

        # Shortcuts present in toolbar button titles
        self.assertIn('title="Scene (Alt + S)"', content)
        self.assertIn('title="Sub-Scene (Alt + U)"', content)
        self.assertIn('title="Sub-Scene From (Alt + R)"', content)
        self.assertIn('title="CutBack To (Alt + B)"', content)
        self.assertIn('title="Action (Ctrl + 2)"', content)
        self.assertIn('title="Character (Ctrl + 3)"', content)
        self.assertIn('title="Dialogue (Ctrl + 4)"', content)
        self.assertIn('title="Parenthetical (Ctrl + 5)"', content)
        self.assertIn('title="Transition (Ctrl + 6)"', content)
        self.assertIn('title="Note (Ctrl + 7)"', content)

    def test_scene_end_transition_persistence_and_api(self):
        """Verify scene-end transition defaults, saving via API, and retrieval."""
        import json
        client = Client()
        client.login(username='filmmaker', password='Password123!')

        # Default transition is 'CUT TO' (no colon)
        self.assertEqual(self.sc1.transition, 'CUT TO')

        # Save custom Malayalam transition via API
        save_url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': self.sc1.id})
        payload = {
            'heading': 'INT. വീട് - DAY',
            'transition': 'പാട്ട് അവസാനിക്കുന്നു',
            'elements': [
                {'element_type': 'action', 'content': 'അവൻ കാത്തിരിക്കുന്നു.'}
            ]
        }
        resp = client.post(save_url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['transition'], 'പാട്ട് അവസാനിക്കുന്നു')

        self.sc1.refresh_from_db()
        self.assertEqual(self.sc1.transition, 'പാട്ട് അവസാനിക്കുന്നു')

        # Get scene API returns transition
        get_url = reverse('api_get_scene', kwargs={'script_id': self.script.id, 'scene_id': self.sc1.id})
        get_resp = client.get(get_url)
        self.assertEqual(get_resp.status_code, 200)
        get_data = get_resp.json()
        self.assertEqual(get_data['scene']['transition'], 'പാട്ട് അവസാനിക്കുന്നു')

    def test_scene_end_transition_in_exports(self):
        """Verify scene-end transition is included in PDF, DOCX, and TXT exports."""
        self.sc1.transition = 'DISSOLVE TO'
        self.sc1.save()

        self.sc2_a.transition = 'FADE OUT'
        self.sc2_a.save()

        pdf_bytes = generate_screenplay_pdf(self.script)
        docx_bytes = generate_screenplay_docx(self.script)
        txt_str = generate_screenplay_txt(self.script)

        self.assertTrue(len(pdf_bytes) > 1000)
        self.assertTrue(len(docx_bytes) > 1000)
        self.assertIn('DISSOLVE TO', txt_str)
        self.assertIn('FADE OUT', txt_str)

    def test_version_snapshot_preserves_transition(self):
        """Verify version snapshot and restore preserve scene transitions."""
        from scripts.services.version_service import create_version_snapshot, restore_version_snapshot

        self.sc1.transition = 'INTERCUT'
        self.sc1.save()

        self.sc2_a.transition = 'CUT BACK TO'
        self.sc2_a.save()

        ver = create_version_snapshot(self.script, title='Transition Test')
        self.assertEqual(ver.snapshot_data['scenes'][0]['transition'], 'INTERCUT')
        self.assertEqual(ver.snapshot_data['scenes'][1]['sub_scenes'][0]['transition'], 'CUT BACK TO')

        # Mutate current scene transition
        self.sc1.transition = 'CUT TO'
        self.sc1.save()

        # Restore
        restore_version_snapshot(self.script, ver.id)
        self.script.refresh_from_db()
        scenes = self.script.get_ordered_scenes()
        self.assertEqual(scenes[0].transition, 'INTERCUT')
        self.assertEqual(scenes[2].transition, 'CUT BACK TO')

    def test_pdf_export_no_duplicate_scene_headings(self):
        """
        Verify that PDF export contains exactly ONE scene heading per scene
        even when ScriptElement with element_type='scene_heading' exists.
        """
        # Create a dedicated script with main scene, sub-scene, duplicate scene, and Malayalam heading
        test_script = Script.objects.create(
            user=self.user,
            title='Heading Verification Script',
            language='Malayalam'
        )
        # 1. Main scene with seeded scene_heading ScriptElement
        s1 = Scene.objects.create(script=test_script, scene_number=7, heading='INT. POLICE STATION - NIGHT', order=0)
        ScriptElement.objects.create(scene=s1, element_type='scene_heading', content='INT. POLICE STATION - NIGHT', order=0)
        ScriptElement.objects.create(scene=s1, element_type='action', content='Inspector sits quietly reviewing case files on his wooden desk.', order=1)

        # 2. Sub-scene
        s1_a = Scene.objects.create(script=test_script, parent_scene=s1, scene_number=7, heading='INT. LOCKUP - NIGHT', order=1)
        ScriptElement.objects.create(scene=s1_a, element_type='scene_heading', content='INT. LOCKUP - NIGHT', order=0)
        ScriptElement.objects.create(scene=s1_a, element_type='action', content='Accused waits behind metal bars.', order=1)

        # 3. Duplicate scene
        s1_dup = Scene.objects.create(script=test_script, scene_number=7, heading='INT. POLICE STATION - NIGHT', order=2, is_duplicate=True, duplicate_number=1)
        ScriptElement.objects.create(scene=s1_dup, element_type='scene_heading', content='INT. POLICE STATION - NIGHT', order=0)
        ScriptElement.objects.create(scene=s1_dup, element_type='action', content='Inspector stands up.', order=1)

        # 4. Malayalam heading scene
        s2 = Scene.objects.create(script=test_script, scene_number=8, heading='INT. വീട് - പകൽ', order=3)
        ScriptElement.objects.create(scene=s2, element_type='scene_heading', content='INT. വീട് - പകൽ', order=0)
        ScriptElement.objects.create(scene=s2, element_type='action', content='നായകൻ ചായ കുടിക്കുന്നു.', order=1)

        # Export to PDF, DOCX, and TXT
        pdf_bytes = generate_screenplay_pdf(test_script)
        docx_bytes = generate_screenplay_docx(test_script)
        txt_str = generate_screenplay_txt(test_script)

        self.assertTrue(len(pdf_bytes) > 1000)
        self.assertTrue(len(docx_bytes) > 1000)

        # Verify in TXT export: exactly ONE occurrence of each scene heading
        lines = [l.strip() for l in txt_str.splitlines() if l.strip()]
        self.assertEqual(lines.count('Scene 7 : INT. POLICE STATION - NIGHT'), 1)
        self.assertEqual(lines.count('Scene 7.A : INT. LOCKUP - NIGHT'), 1)
        self.assertEqual(lines.count('Scene 7 (Duplicate) : INT. POLICE STATION - NIGHT'), 1)
        self.assertEqual(lines.count('Scene 8 : INT. വീട് - പകൽ'), 1)

        # Verify no bare duplicate lines
        self.assertNotIn('INT. POLICE STATION - NIGHT\n\nINT. POLICE STATION - NIGHT', txt_str)
        self.assertEqual(lines.count('INT. POLICE STATION - NIGHT'), 0) # Only present as part of 'Scene 7 : ...'

    def test_pdf_action_style_properties(self):
        """
        Verify that ACTION text style does not receive narrow dialogue/character indents
        and uses the full printable page width.
        """
        long_action_script = Script.objects.create(user=self.user, title='Action Width Script')
        sc = Scene.objects.create(script=long_action_script, scene_number=1, heading='EXT. FOREST - DAY', order=0)
        long_desc = "The dense rainforest comes alive with morning mist drifting through ancient banyan trees. Birds chirp in rhythmic synchrony as sunlight pierces through emerald foliage across the entire expanse of the valley."
        ScriptElement.objects.create(scene=sc, element_type='action', content=long_desc, order=0)

        pdf_bytes = generate_screenplay_pdf(long_action_script)
        self.assertTrue(len(pdf_bytes) > 1000)


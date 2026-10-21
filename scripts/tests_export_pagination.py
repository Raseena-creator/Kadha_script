import io
import re
import pypdfium2 as pdfium
from docx import Document
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from scripts.models import Script, Scene, ScriptElement, ScriptTitlePage
from scripts.services.pdf_export import generate_screenplay_pdf, get_screenplay_pdf_styles
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
        """Notes must be completely excluded by default from PDF and DOCX exports, and included when requested."""
        # 1. Default exclusion (include_notes=False)
        pdf_bytes = generate_screenplay_pdf(self.script)
        pdf_doc = pdfium.PdfDocument(pdf_bytes)
        pdf_text = " ".join([page.get_textpage().get_text_range() for page in pdf_doc])
        self.assertNotIn('CONFIDENTIAL NOTE', pdf_text)
        self.assertNotIn('Change character costume here', pdf_text)

        docx_bytes = generate_screenplay_docx(self.script)
        doc = Document(io.BytesIO(docx_bytes))
        full_doc_text = " ".join([p.text for p in doc.paragraphs])
        self.assertNotIn('CONFIDENTIAL NOTE', full_doc_text)
        self.assertNotIn('Change character costume here', full_doc_text)
        # Verify other elements are present
        self.assertIn('Hero enters the living room.', full_doc_text)
        self.assertIn('HERO', full_doc_text)

        # 2. Explicit inclusion (include_notes=True)
        pdf_bytes_with_notes = generate_screenplay_pdf(self.script, include_notes=True)
        pdf_doc_notes = pdfium.PdfDocument(pdf_bytes_with_notes)
        pdf_text_notes = " ".join([page.get_textpage().get_text_range() for page in pdf_doc_notes])
        self.assertIn('CONFIDENTIAL NOTE', pdf_text_notes)
        self.assertIn('Change character costume here', pdf_text_notes)

        docx_bytes_with_notes = generate_screenplay_docx(self.script, include_notes=True)
        doc_with_notes = Document(io.BytesIO(docx_bytes_with_notes))
        full_doc_text_with_notes = " ".join([p.text for p in doc_with_notes.paragraphs])
        self.assertIn('CONFIDENTIAL NOTE', full_doc_text_with_notes)
        self.assertIn('Change character costume here', full_doc_text_with_notes)

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

    def test_transition_deduplication_single_visible_transition(self):
        """
        Verify that an explicit CUT TO: element + scene.transition='CUT TO'
        produces exactly one visible transition in TXT, DOCX, and PDF exports.
        """
        script = Script.objects.create(user=self.user, title='Transition Dedup Script')
        scene = Scene.objects.create(script=script, scene_number=1, heading='INT. OFFICE - DAY', order=0, transition='CUT TO')
        ScriptElement.objects.create(scene=scene, element_type='action', content='John looks at the clock.', order=0)
        ScriptElement.objects.create(scene=scene, element_type='transition', content='CUT TO:', order=1)

        # TXT export
        txt_str = generate_screenplay_txt(script)
        txt_lines = [l.strip().upper() for l in txt_str.splitlines() if l.strip()]
        cut_to_occurrences = [l for l in txt_lines if l in ('CUT TO:', 'CUT TO')]
        self.assertEqual(len(cut_to_occurrences), 1)

        # DOCX export
        docx_bytes = generate_screenplay_docx(script)
        doc = Document(io.BytesIO(docx_bytes))
        docx_transitions = [p.text.strip().upper() for p in doc.paragraphs if p.text.strip().upper() in ('CUT TO:', 'CUT TO')]
        self.assertEqual(len(docx_transitions), 1)

        # PDF export
        pdf_bytes = generate_screenplay_pdf(script)
        self.assertTrue(len(pdf_bytes) > 1000)

    def test_explicit_transition_earlier_in_scene_followed_by_elements(self):
        """
        Verify that an explicit transition earlier in the scene followed by narrative elements
        does NOT suppress the scene-ending fallback transition.
        """
        script = Script.objects.create(user=self.user, title='Mid Transition Script')
        scene = Scene.objects.create(script=script, scene_number=1, heading='INT. LAB - DAY', order=0, transition='CUT TO')
        ScriptElement.objects.create(scene=scene, element_type='action', content='Scientist examines specimen.', order=0)
        ScriptElement.objects.create(scene=scene, element_type='transition', content='DISSOLVE TO:', order=1)
        ScriptElement.objects.create(scene=scene, element_type='action', content='Hours later, microscope reveals mutation.', order=2)

        # TXT export: both DISSOLVE TO: and the scene-end CUT TO appear
        txt_str = generate_screenplay_txt(script)
        txt_lines = [l.strip().upper() for l in txt_str.splitlines() if l.strip()]
        self.assertIn('DISSOLVE TO:', txt_lines)
        self.assertIn('CUT TO', txt_lines)
        dissolve_idx = txt_lines.index('DISSOLVE TO:')
        cut_idx = txt_lines.index('CUT TO')
        self.assertTrue(dissolve_idx < cut_idx)

        # DOCX export: both transitions appear in sequence
        docx_bytes = generate_screenplay_docx(script)
        doc = Document(io.BytesIO(docx_bytes))
        docx_lines = [p.text.strip().upper() for p in doc.paragraphs if p.text.strip()]
        self.assertIn('DISSOLVE TO:', docx_lines)
        self.assertIn('CUT TO', docx_lines)

        # PDF export builds successfully
        pdf_bytes = generate_screenplay_pdf(script)
        self.assertTrue(len(pdf_bytes) > 1000)

    def test_transition_fallback_when_no_explicit_element(self):
        """
        Verify that a scene without an explicit transition element still renders its
        scene.transition fallback in TXT, DOCX, and PDF exports.
        """
        script = Script.objects.create(user=self.user, title='Transition Fallback Script')
        scene = Scene.objects.create(script=script, scene_number=1, heading='EXT. PARK - DAY', order=0, transition='CUT TO')
        ScriptElement.objects.create(scene=scene, element_type='action', content='A dog runs across the grass.', order=0)

        # TXT export
        txt_str = generate_screenplay_txt(script)
        txt_lines = [l.strip().upper() for l in txt_str.splitlines() if l.strip()]
        cut_to_occurrences = [l for l in txt_lines if l in ('CUT TO:', 'CUT TO')]
        self.assertEqual(len(cut_to_occurrences), 1)

        # DOCX export
        docx_bytes = generate_screenplay_docx(script)
        doc = Document(io.BytesIO(docx_bytes))
        docx_transitions = [p.text.strip().upper() for p in doc.paragraphs if p.text.strip().upper() in ('CUT TO:', 'CUT TO')]
        self.assertEqual(len(docx_transitions), 1)

        # PDF export
        pdf_bytes = generate_screenplay_pdf(script)
        self.assertTrue(len(pdf_bytes) > 1000)

    def test_distinct_transition_precedence(self):
        """
        Verify that when a scene has an explicit transition element (e.g., 'FADE OUT.')
        and a default/different scene-level transition (e.g., 'CUT TO'),
        the explicit element takes precedence and the scene-level transition is suppressed.
        """
        script = Script.objects.create(user=self.user, title='Distinct Transition Script')
        scene = Scene.objects.create(script=script, scene_number=1, heading='INT. CABIN - NIGHT', order=0, transition='CUT TO')
        ScriptElement.objects.create(scene=scene, element_type='action', content='Fire fades out.', order=0)
        ScriptElement.objects.create(scene=scene, element_type='transition', content='FADE OUT.', order=1)

        # TXT export
        txt_str = generate_screenplay_txt(script)
        txt_lines = [l.strip().upper() for l in txt_str.splitlines() if l.strip()]
        self.assertIn('FADE OUT.', txt_lines)
        self.assertNotIn('CUT TO', txt_lines)
        self.assertNotIn('CUT TO:', txt_lines)

        # DOCX export
        docx_bytes = generate_screenplay_docx(script)
        doc = Document(io.BytesIO(docx_bytes))
        docx_lines = [p.text.strip().upper() for p in doc.paragraphs if p.text.strip()]
        self.assertIn('FADE OUT.', docx_lines)
        self.assertNotIn('CUT TO', docx_lines)
        self.assertNotIn('CUT TO:', docx_lines)

        # PDF export
        pdf_bytes = generate_screenplay_pdf(script)
        self.assertTrue(len(pdf_bytes) > 1000)

    def test_scene_model_transition_properties(self):
        """
        Verify Scene model properties: has_scene_ending_transition, has_ending_transition,
        has_transition_element, and trailing_transition_content.
        """
        script = Script.objects.create(user=self.user, title='Properties Test Script')

        # 1. Scene with no transition
        s_none = Scene.objects.create(script=script, scene_number=1, heading='INT. ROOM - DAY', order=0)
        ScriptElement.objects.create(scene=s_none, element_type='action', content='Silent room.', order=0)
        self.assertFalse(s_none.has_transition_element)
        self.assertFalse(s_none.has_ending_transition)
        self.assertFalse(s_none.has_scene_ending_transition())
        self.assertEqual(s_none.trailing_transition_content, '')

        # 2. Scene with transition at the end
        s_end = Scene.objects.create(script=script, scene_number=2, heading='EXT. STREET - NIGHT', order=1)
        ScriptElement.objects.create(scene=s_end, element_type='action', content='Car speeds away.', order=0)
        ScriptElement.objects.create(scene=s_end, element_type='transition', content='SMASH CUT TO:', order=1)
        self.assertTrue(s_end.has_transition_element)
        self.assertTrue(s_end.has_ending_transition)
        self.assertTrue(s_end.has_scene_ending_transition())
        self.assertEqual(s_end.trailing_transition_content, 'SMASH CUT TO:')

        # 3. Scene with transition earlier, followed by action
        s_mid = Scene.objects.create(script=script, scene_number=3, heading='INT. CORRIDOR - DAY', order=2)
        ScriptElement.objects.create(scene=s_mid, element_type='action', content='Footsteps approach.', order=0)
        ScriptElement.objects.create(scene=s_mid, element_type='transition', content='DISSOLVE TO:', order=1)
        ScriptElement.objects.create(scene=s_mid, element_type='action', content='Now inside vault.', order=2)
        self.assertTrue(s_mid.has_transition_element)
        self.assertFalse(s_mid.has_ending_transition)
        self.assertFalse(s_mid.has_scene_ending_transition())
        self.assertEqual(s_mid.trailing_transition_content, '')

        # 4. Scene with transition at end followed by editorial note
        s_note = Scene.objects.create(script=script, scene_number=4, heading='EXT. ROOFTOP - NIGHT', order=3)
        ScriptElement.objects.create(scene=s_note, element_type='action', content='Lightning flashes.', order=0)
        ScriptElement.objects.create(scene=s_note, element_type='transition', content='FADE OUT.', order=1)
        ScriptElement.objects.create(scene=s_note, element_type='note', content='Director note: check sound fx.', order=2)
        self.assertTrue(s_note.has_transition_element)
        self.assertTrue(s_note.has_ending_transition)
        self.assertTrue(s_note.has_scene_ending_transition())
        self.assertEqual(s_note.trailing_transition_content, 'FADE OUT.')

    def test_read_mode_initial_rendering_transition_deduplication(self):
        """
        Verify that Read Mode initial template rendering:
        - Does NOT produce duplicate transition blocks when a transition element ends the scene.
        - Renders both when a transition is mid-scene and followed by other elements.
        - Still renders the scene-level fallback when no transition element exists.
        - Respects explicit element precedence for distinct transitions.
        """
        client = Client()
        client.login(username='filmmaker', password='Password123!')

        test_script = Script.objects.create(user=self.user, title='Read Mode Transition Script')
        # Scene 1: Explicit transition element 'CUT TO:' at end + scene.transition='CUT TO'
        sc_dup = Scene.objects.create(script=test_script, scene_number=1, heading='INT. CAFE - DAY', order=0, transition='CUT TO')
        ScriptElement.objects.create(scene=sc_dup, element_type='action', content='Drinking coffee.', order=0)
        ScriptElement.objects.create(scene=sc_dup, element_type='transition', content='CUT TO:', order=1)

        # Scene 2: Fallback only (no transition element)
        sc_fallback = Scene.objects.create(script=test_script, scene_number=2, heading='EXT. BEACH - SUNSET', order=1, transition='DISSOLVE TO')
        ScriptElement.objects.create(scene=sc_fallback, element_type='action', content='Waves crash.', order=0)

        # Scene 3: Distinct transition 'FADE OUT.' at end + scene.transition='CUT TO'
        sc_distinct = Scene.objects.create(script=test_script, scene_number=3, heading='INT. BEDROOM - NIGHT', order=2, transition='CUT TO')
        ScriptElement.objects.create(scene=sc_distinct, element_type='action', content='Falling asleep.', order=0)
        ScriptElement.objects.create(scene=sc_distinct, element_type='transition', content='FADE OUT.', order=1)

        # Scene 4: Transition in the middle, followed by action -> fallback should render at end
        sc_mid = Scene.objects.create(script=test_script, scene_number=4, heading='INT. GYM - DAY', order=3, transition='CUT TO')
        ScriptElement.objects.create(scene=sc_mid, element_type='action', content='Boxer punches bag.', order=0)
        ScriptElement.objects.create(scene=sc_mid, element_type='transition', content='MATCH CUT TO:', order=1)
        ScriptElement.objects.create(scene=sc_mid, element_type='action', content='Boxer drinking water.', order=2)

        response = client.get(reverse('script_editor', kwargs={'script_id': test_script.id}))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')

        # Scene 1: Exactly ONE element-type-transition block
        sec1_match = re.search(rf'<section[^>]*id="read-scene-{sc_dup.id}"[^>]*>(.*?)</section>', html, re.DOTALL)
        self.assertIsNotNone(sec1_match)
        sec1_html = sec1_match.group(1)
        self.assertEqual(sec1_html.count('element-type-transition'), 1)
        self.assertIn('CUT TO:', sec1_html)

        # Scene 2: Fallback only
        sec2_match = re.search(rf'<section[^>]*id="read-scene-{sc_fallback.id}"[^>]*>(.*?)</section>', html, re.DOTALL)
        self.assertIsNotNone(sec2_match)
        sec2_html = sec2_match.group(1)
        self.assertEqual(sec2_html.count('element-type-transition'), 1)
        self.assertIn('DISSOLVE TO', sec2_html)

        # Scene 3: Distinct transition at end suppresses scene.transition fallback
        sec3_match = re.search(rf'<section[^>]*id="read-scene-{sc_distinct.id}"[^>]*>(.*?)</section>', html, re.DOTALL)
        self.assertIsNotNone(sec3_match)
        sec3_html = sec3_match.group(1)
        self.assertEqual(sec3_html.count('element-type-transition'), 1)
        self.assertIn('FADE OUT.', sec3_html)
        self.assertNotIn('CUT TO', sec3_html)

        # Scene 4: Mid-scene transition + fallback at end (TWO transitions)
        sec4_match = re.search(rf'<section[^>]*id="read-scene-{sc_mid.id}"[^>]*>(.*?)</section>', html, re.DOTALL)
        self.assertIsNotNone(sec4_match)
        sec4_html = sec4_match.group(1)
        self.assertEqual(sec4_html.count('element-type-transition'), 2)
        self.assertIn('MATCH CUT TO:', sec4_html)
        self.assertIn('CUT TO', sec4_html)

    def test_api_save_scene_nullable_and_missing_transition(self):
        """
        Verify that api_save_scene handles nullable, omitted, empty, and custom transition payloads
        without server-side errors.
        """
        import json
        client = Client()
        client.login(username='filmmaker', password='Password123!')

        save_url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': self.sc1.id})

        # 1. Payload with transition: None
        res_null = client.post(
            save_url,
            data=json.dumps({'heading': 'INT. OFFICE - DAY', 'transition': None}),
            content_type='application/json'
        )
        self.assertEqual(res_null.status_code, 200)
        self.sc1.refresh_from_db()
        self.assertEqual(self.sc1.transition, 'CUT TO')

        # 2. Payload with transition omitted
        res_omitted = client.post(
            save_url,
            data=json.dumps({'heading': 'INT. OFFICE - DAY'}),
            content_type='application/json'
        )
        self.assertEqual(res_omitted.status_code, 200)

        # 3. Payload with empty string transition
        res_empty = client.post(
            save_url,
            data=json.dumps({'heading': 'INT. OFFICE - DAY', 'transition': '   '}),
            content_type='application/json'
        )
        self.assertEqual(res_empty.status_code, 200)
        self.sc1.refresh_from_db()
        self.assertEqual(self.sc1.transition, 'CUT TO')

        # 4. Payload with custom transition
        res_custom = client.post(
            save_url,
            data=json.dumps({'heading': 'INT. OFFICE - DAY', 'transition': 'DISSOLVE TO:'}),
            content_type='application/json'
        )
        self.assertEqual(res_custom.status_code, 200)
        self.sc1.refresh_from_db()
        self.assertEqual(self.sc1.transition, 'DISSOLVE TO:')

    def test_screenplay_pdf_paragraph_styles_typography(self):
        """
        Verify that main screenplay PDF paragraph styles use the intended font sizes (~12 pt),
        leading (15-16 pt), parenthetical (10.5 pt, 13 pt leading), and Unicode shaping is preserved.
        """
        styles = get_screenplay_pdf_styles()

        # Scene heading: 12 pt, 16 pt leading, shaping=True
        self.assertEqual(styles['SceneHeading'].fontSize, 12)
        self.assertEqual(styles['SceneHeading'].leading, 16)
        self.assertTrue(styles['SceneHeading'].shaping)

        # Action: 12 pt, 16 pt leading, shaping=True
        self.assertEqual(styles['Action'].fontSize, 12)
        self.assertEqual(styles['Action'].leading, 16)
        self.assertTrue(styles['Action'].shaping)

        # Character: 12 pt, 15 pt leading, shaping=True
        self.assertEqual(styles['Character'].fontSize, 12)
        self.assertEqual(styles['Character'].leading, 15)
        self.assertTrue(styles['Character'].shaping)

        # Dialogue: 12 pt, 16 pt leading, shaping=True
        self.assertEqual(styles['Dialogue'].fontSize, 12)
        self.assertEqual(styles['Dialogue'].leading, 16)
        self.assertTrue(styles['Dialogue'].shaping)

        # Parenthetical: 10.5 pt, 13 pt leading, shaping=True
        self.assertEqual(styles['Parenthetical'].fontSize, 10.5)
        self.assertEqual(styles['Parenthetical'].leading, 13)
        self.assertTrue(styles['Parenthetical'].shaping)

        # Transition: 12 pt, 15 pt leading, shaping=True
        self.assertEqual(styles['Transition'].fontSize, 12)
        self.assertEqual(styles['Transition'].leading, 15)
        self.assertTrue(styles['Transition'].shaping)

        # Shot: 12 pt, 15 pt leading, shaping=True
        self.assertEqual(styles['Shot'].fontSize, 12)
        self.assertEqual(styles['Shot'].leading, 15)
        self.assertTrue(styles['Shot'].shaping)

    def test_long_dialogue_across_page_boundaries_english_and_malayalam(self):
        """
        Verify that long English and Malayalam dialogue can cross page boundaries
        without layout errors or content truncation, without persistent machine-specific file writes.
        """
        dialogue_script = Script.objects.create(user=self.user, title='Long Dialogue Script', language='Malayalam')
        sc = Scene.objects.create(script=dialogue_script, scene_number=1, heading='INT. COURTROOM - DAY', order=0)

        # English long speech
        ScriptElement.objects.create(scene=sc, element_type='character', content='LAWYER', order=0)
        long_english_dialogue = " ".join([
            f"Your Honor, statement paragraph number {i} demonstrates beyond any reasonable doubt that the sequence of events as described by the prosecution is fundamentally flawed and contradicts the photographic evidence."
            for i in range(1, 35)
        ])
        ScriptElement.objects.create(scene=sc, element_type='dialogue', content=long_english_dialogue, order=1)

        # Malayalam long speech
        ScriptElement.objects.create(scene=sc, element_type='character', content='ജഡ്ജി (JUDGE)', order=2)
        long_malayalam_dialogue = " ".join([
            f"കോടതി ഈ വിഷയത്തിൽ വ്യക്തമായ നിലപാട് സ്വീകരിക്കുന്നു {i}. നിയമപരമായ എല്ലാ രേഖകളും പരിശോധിച്ചതിനു ശേഷമേ അന്തിമ തീരുമാനം എടുക്കാൻ സാധിക്കൂ."
            for i in range(1, 35)
        ])
        ScriptElement.objects.create(scene=sc, element_type='dialogue', content=long_malayalam_dialogue, order=3)

        pdf_bytes = generate_screenplay_pdf(dialogue_script)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 2000)

        # Count pages: 1 title page + multi-page scene
        pages = re.findall(rb'/Type\s*/Page\b(?!\s*/Pages)', pdf_bytes)
        # Should span across at least 3 pages (title page + 2 or more scene pages)
        self.assertTrue(len(pages) >= 3)

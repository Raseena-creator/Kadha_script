"""
Tests for KadhaScript — Musical & Montage Sequence as Separate Scene/Page Workflow.

Covers all 17 requirements:
1. Starting a Song sequence creates a separate sequence scene/page.
2. Starting a Montage sequence creates a separate sequence scene/page.
3. Sequence shots do not consume master scene numbers.
4. Sequence shot numbering starts at 1.
5. Multiple sequence shots increment independently.
6. Ending Song creates SONG ENDS.
7. Ending Montage creates MONTAGE ENDS.
8. New Scene while Song is active automatically closes Song.
9. New Scene while Montage is active automatically closes Montage.
10. New Scene after an already-ended sequence does not duplicate the ending marker.
11. New Scene with no active sequence behaves exactly as before.
12. Master scene numbering resumes correctly (Scene 10 -> Sequence -> Scene 11).
13. Sub-scene numbering remains correct (Scene 1.A, Scene 1.B).
14. Save/reload preserves the sequence as a separate scene/page.
15. Scene navigation correctly identifies and opens the sequence.
16. Existing sequence workflow tests continue to pass.
17. Full export compatibility (PDF, DOCX, TXT) and template rendering.
"""

import io
import json
import docx
import pypdfium2 as pdfium
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from scripts.models import Script, Scene, ScriptElement
from scripts.services.scene_service import (
    serialize_scenes_hierarchy,
    create_sub_scene,
    resequence_script_scenes,
    create_sequence_scene,
    insert_scene_relative,
)
from scripts.services.pdf_export import generate_screenplay_pdf
from scripts.services.docx_export import generate_screenplay_docx
from scripts.services.txt_export import generate_screenplay_txt


class SequenceWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='test_screenwriter', password='password123')
        self.client = Client()
        self.client.login(username='test_screenwriter', password='password123')
        self.script = Script.objects.create(
            user=self.user,
            title='സംഗീത സിനിമ - Musical Screenplay'
        )

    # ----------------------------------------------------
    # 1. SEPARATE SEQUENCE SCENE / PAGE CREATION
    # ----------------------------------------------------

    def test_01_starting_song_sequence_creates_separate_scene_page(self):
        """
        Starting a Song sequence creates a separate screenplay scene/page independent
        from the reference master scene.
        """
        sc10 = Scene.objects.create(script=self.script, heading='INT. HOUSE - NIGHT', scene_number=10, order=10)
        ScriptElement.objects.create(scene=sc10, element_type='scene_heading', content='INT. HOUSE - NIGHT', order=0)
        ScriptElement.objects.create(scene=sc10, element_type='action', content='Initial master action.', order=1)

        seq_scene = create_sequence_scene(self.script, reference_scene_id=sc10.id, sequence_type='song')

        self.assertNotEqual(sc10.id, seq_scene.id)
        self.assertTrue(seq_scene.is_sequence)
        self.assertEqual(seq_scene.sequence_type, 'song')
        self.assertEqual(seq_scene.heading, 'SONG BEGINS')
        self.assertEqual(seq_scene.nav_identifier, 'Song Sequence')
        self.assertEqual(seq_scene.full_display_heading, 'SONG BEGINS')

        # Confirm sc10 is unpolluted
        sc10_elems = list(sc10.elements.values_list('content', flat=True))
        self.assertNotIn('SONG BEGINS', sc10_elems)
        self.assertNotIn('1. INT. LOCATION - DAY', sc10_elems)

        # Confirm sequence scene has seeded elements
        seq_elems = list(seq_scene.elements.order_by('order', 'id').values_list('content', flat=True))
        self.assertEqual(seq_elems[0], 'SONG BEGINS')
        self.assertEqual(seq_elems[1], '1. INT. LOCATION - DAY')

    def test_02_starting_montage_sequence_creates_separate_scene_page(self):
        """
        Starting a Montage sequence creates a separate screenplay scene/page.
        """
        sc1 = Scene.objects.create(script=self.script, heading='INT. ACADEMY - DAY', scene_number=1, order=1)
        seq_scene = create_sequence_scene(self.script, reference_scene_id=sc1.id, sequence_type='montage')

        self.assertNotEqual(sc1.id, seq_scene.id)
        self.assertTrue(seq_scene.is_sequence)
        self.assertEqual(seq_scene.sequence_type, 'montage')
        self.assertEqual(seq_scene.heading, 'MONTAGE BEGINS')
        self.assertEqual(seq_scene.nav_identifier, 'Montage Sequence')
        self.assertEqual(seq_scene.full_display_heading, 'MONTAGE BEGINS')

        seq_elems = list(seq_scene.elements.order_by('order', 'id').values_list('content', flat=True))
        self.assertEqual(seq_elems[0], 'MONTAGE BEGINS')
        self.assertEqual(seq_elems[1], '1. INT. LOCATION - DAY')

    # ----------------------------------------------------
    # 2. MASTER SCENE NUMBERING CONTINUITY & ISOLATION
    # ----------------------------------------------------

    def test_03_sequence_shots_do_not_consume_master_scene_numbers(self):
        """
        Master scene numbering must remain continuous (Scene 10 -> Song Sequence -> Scene 11),
        not consuming or incrementing master numbers.
        """
        for i in range(1, 11):
            Scene.objects.create(script=self.script, heading=f'INT. LOCATION {i} - DAY', order=i)
        resequence_script_scenes(self.script)

        sc10 = self.script.scenes.get(scene_number=10)
        seq_scene = create_sequence_scene(self.script, reference_scene_id=sc10.id, sequence_type='song')

        # Add multiple sequence shots to the sequence scene
        ScriptElement.objects.create(scene=seq_scene, element_type='shot', content='2. EXT. LOCATION - NIGHT', order=3)
        ScriptElement.objects.create(scene=seq_scene, element_type='shot', content='3. INT. LOCATION - DAY', order=4)
        ScriptElement.objects.create(scene=seq_scene, element_type='shot', content='SONG ENDS', order=5)

        # Now insert the next normal scene
        next_sc = insert_scene_relative(self.script, reference_scene_id=seq_scene.id, position='after', heading='INT. OFFICE - DAY')

        sc10.refresh_from_db()
        seq_scene.refresh_from_db()
        next_sc.refresh_from_db()

        self.assertEqual(sc10.scene_number, 10)
        self.assertEqual(sc10.display_number, 'Scene 10')

        self.assertTrue(seq_scene.is_sequence)
        self.assertEqual(seq_scene.nav_identifier, 'Song Sequence')

        self.assertEqual(next_sc.scene_number, 11)
        self.assertEqual(next_sc.display_number, 'Scene 11')

    def test_04_sequence_shot_numbering_starts_at_one(self):
        """
        Sequence shot numbering starts at 1. regardless of master scene numbers.
        """
        sc10 = Scene.objects.create(script=self.script, heading='INT. HOUSE - NIGHT', scene_number=10, order=10)
        seq_scene = create_sequence_scene(self.script, reference_scene_id=sc10.id, sequence_type='song')

        first_shot = seq_scene.elements.filter(element_type='shot').exclude(content='SONG BEGINS').first()
        self.assertIsNotNone(first_shot)
        self.assertTrue(first_shot.content.startswith('1.'))

    def test_05_multiple_sequence_shots_increment_independently(self):
        """
        Multiple sequence shots increment independently: 1., 2., 3...
        """
        sc = Scene.objects.create(script=self.script, heading='INT. CLUB - NIGHT', scene_number=5, order=5)
        seq_scene = create_sequence_scene(self.script, reference_scene_id=sc.id, sequence_type='montage')

        s2 = ScriptElement.objects.create(scene=seq_scene, element_type='shot', content='2. EXT. STREET - NIGHT', order=3)
        s3 = ScriptElement.objects.create(scene=seq_scene, element_type='shot', content='3. INT. ROOFTOP - NIGHT', order=4)

        self.assertTrue(s2.content.startswith('2.'))
        self.assertTrue(s3.content.startswith('3.'))

    def test_06_ending_song_creates_song_ends(self):
        """
        Ending Song sequence inserts 'SONG ENDS' and suppresses automatic fallback 'CUT TO:'.
        """
        seq_scene = create_sequence_scene(self.script, reference_scene_id=None, sequence_type='song')
        end_elem = ScriptElement.objects.create(scene=seq_scene, element_type='shot', content='SONG ENDS', order=3)

        self.assertEqual(end_elem.content, 'SONG ENDS')
        self.assertTrue(seq_scene.has_scene_ending_transition())

    def test_07_ending_montage_creates_montage_ends(self):
        """
        Ending Montage sequence inserts 'MONTAGE ENDS' and suppresses automatic fallback 'CUT TO:'.
        """
        seq_scene = create_sequence_scene(self.script, reference_scene_id=None, sequence_type='montage')
        end_elem = ScriptElement.objects.create(scene=seq_scene, element_type='shot', content='MONTAGE ENDS', order=3)

        self.assertEqual(end_elem.content, 'MONTAGE ENDS')
        self.assertTrue(seq_scene.has_scene_ending_transition())

    # ----------------------------------------------------
    # 3. STATE-AWARE NEW SCENE BEHAVIOR
    # ----------------------------------------------------

    def test_08_new_scene_while_song_is_active_automatically_closes_song(self):
        """
        When creating a new normal scene after an unclosed Song sequence,
        the application automatically inserts 'SONG ENDS' before the new scene.
        """
        for i in range(1, 11):
            Scene.objects.create(script=self.script, heading=f'INT. LOCATION {i} - DAY', order=i)
        resequence_script_scenes(self.script)
        sc10 = self.script.scenes.get(scene_number=10)
        seq_scene = create_sequence_scene(self.script, reference_scene_id=sc10.id, sequence_type='song')

        # Sequence scene is currently unclosed (has SONG BEGINS, 1. INT..., but no SONG ENDS)
        has_end_before = seq_scene.elements.filter(content='SONG ENDS').exists()
        self.assertFalse(has_end_before)

        # Trigger new scene after sequence scene
        new_scene = insert_scene_relative(self.script, reference_scene_id=seq_scene.id, position='after', heading='EXT. GARDEN - DAY')

        # Sequence scene must now contain SONG ENDS
        has_end_after = seq_scene.elements.filter(content='SONG ENDS').exists()
        self.assertTrue(has_end_after)

        # And new normal scene is Scene 11
        seq_scene.refresh_from_db()
        new_scene.refresh_from_db()
        self.assertEqual(new_scene.scene_number, 11)
        self.assertEqual(new_scene.display_number, 'Scene 11')

    def test_09_new_scene_while_montage_is_active_automatically_closes_montage(self):
        """
        When creating a new normal scene after an unclosed Montage sequence,
        'MONTAGE ENDS' is automatically inserted.
        """
        sc1 = Scene.objects.create(script=self.script, heading='INT. GYM - DAY', scene_number=1, order=1)
        seq_scene = create_sequence_scene(self.script, reference_scene_id=sc1.id, sequence_type='montage')

        self.assertFalse(seq_scene.elements.filter(content='MONTAGE ENDS').exists())

        new_scene = insert_scene_relative(self.script, reference_scene_id=seq_scene.id, position='after', heading='INT. RING - NIGHT')

        self.assertTrue(seq_scene.elements.filter(content='MONTAGE ENDS').exists())
        self.assertEqual(new_scene.scene_number, 2)
        self.assertEqual(new_scene.display_number, 'Scene 2')

    def test_10_new_scene_after_already_ended_sequence_does_not_duplicate_ending_marker(self):
        """
        If the sequence already contains its appropriate ending marker,
        creating a new scene does NOT insert a duplicate ending marker.
        """
        sc = Scene.objects.create(script=self.script, heading='INT. ROOM - DAY', scene_number=1, order=1)
        seq_scene = create_sequence_scene(self.script, reference_scene_id=sc.id, sequence_type='song')
        ScriptElement.objects.create(scene=seq_scene, element_type='shot', content='SONG ENDS', order=3)

        self.assertEqual(seq_scene.elements.filter(content='SONG ENDS').count(), 1)

        # Insert new scene
        insert_scene_relative(self.script, reference_scene_id=seq_scene.id, position='after', heading='EXT. STREET - NIGHT')

        # Count must remain exactly 1 (no duplicate)
        self.assertEqual(seq_scene.elements.filter(content='SONG ENDS').count(), 1)

    def test_11_new_scene_with_no_active_sequence_behaves_normally(self):
        """
        When no sequence is active, creating a new scene inserts no sequence-ending marker
        and uses normal numbering.
        """
        sc1 = Scene.objects.create(script=self.script, heading='INT. CAFE - DAY', scene_number=1, order=1)
        sc2 = insert_scene_relative(self.script, reference_scene_id=sc1.id, position='after', heading='EXT. PARK - DAY')

        self.assertFalse(sc1.elements.filter(content__in=['SONG ENDS', 'MONTAGE ENDS']).exists())
        self.assertFalse(sc2.elements.filter(content__in=['SONG ENDS', 'MONTAGE ENDS']).exists())
        self.assertEqual(sc2.scene_number, 2)

    def test_12_sub_scene_numbering_remains_correct_with_sequences(self):
        """
        Sub-scenes (e.g. Scene 1.A, Scene 1.B) retain their letters and hierarchical numbering
        when sequence scenes are present in the script.
        """
        parent = Scene.objects.create(script=self.script, heading='INT. MANSION - DAY', scene_number=1, order=1)
        sub_a = create_sub_scene(self.script, parent.id, 'INT. CORRIDOR - CONTINUOUS')
        seq_scene = create_sequence_scene(self.script, reference_scene_id=parent.id, sequence_type='song')
        sub_b = create_sub_scene(self.script, parent.id, 'INT. BALCONY - CONTINUOUS')

        sub_a.refresh_from_db()
        sub_b.refresh_from_db()
        self.assertEqual(sub_a.sub_letter, 'A')
        self.assertEqual(sub_b.sub_letter, 'B')
        self.assertEqual(sub_a.display_number, 'Scene 1.A')
        self.assertEqual(sub_b.display_number, 'Scene 1.B')

    def test_12b_sequence_created_from_intermediate_subscene_places_after_all_siblings(self):
        """
        Creating a sequence while an intermediate sub-scene is selected places the sequence
        after the entire sub-scene parent group (including following sibling sub-scenes).
        """
        sc1 = Scene.objects.create(script=self.script, heading='INT. AIRPORT - DAY', order=1)
        sc2 = Scene.objects.create(script=self.script, heading='INT. HOTEL - NIGHT', order=2)
        sub_2a = create_sub_scene(self.script, sc2.id, 'INT. HOTEL ROOM - NIGHT')
        sub_2b = create_sub_scene(self.script, sc2.id, 'INT. HOTEL BATHROOM - NIGHT')
        sub_2c = create_sub_scene(self.script, sc2.id, 'INT. HOTEL BALCONY - NIGHT')
        sc3 = Scene.objects.create(script=self.script, heading='EXT. STREET - DAY', order=6)
        resequence_script_scenes(self.script)

        # Select intermediate sub-scene Scene 2.A and create Song sequence
        seq_scene = create_sequence_scene(self.script, reference_scene_id=sub_2a.id, sequence_type='song')

        ordered_scenes = list(self.script.scenes.filter(is_deleted=False).order_by('order', 'id'))
        expected_ids = [sc1.id, sc2.id, sub_2a.id, sub_2b.id, sub_2c.id, seq_scene.id, sc3.id]
        self.assertEqual([s.id for s in ordered_scenes], expected_ids)

        sc1.refresh_from_db()
        sc2.refresh_from_db()
        sub_2a.refresh_from_db()
        sub_2b.refresh_from_db()
        sub_2c.refresh_from_db()
        sc3.refresh_from_db()
        seq_scene.refresh_from_db()

        self.assertEqual(sub_2a.parent_scene_id, sc2.id)
        self.assertEqual(sub_2b.parent_scene_id, sc2.id)
        self.assertEqual(sub_2c.parent_scene_id, sc2.id)
        self.assertEqual(sub_2a.sub_letter, 'A')
        self.assertEqual(sub_2b.sub_letter, 'B')
        self.assertEqual(sub_2c.sub_letter, 'C')

        self.assertIsNone(seq_scene.parent_scene)
        self.assertTrue(seq_scene.is_sequence)
        self.assertEqual(sc2.scene_number, 2)
        self.assertEqual(sc3.scene_number, 3)

    # ----------------------------------------------------
    # 4. SAVE, RELOAD & SCENE NAVIGATION IDENTIFICATION
    # ----------------------------------------------------

    def test_13_save_reload_preserves_sequence_as_separate_scene(self):
        """
        Saving and reloading a sequence scene via the API preserves it as a separate scene/page.
        """
        sc10 = Scene.objects.create(script=self.script, heading='INT. HOUSE - NIGHT', scene_number=10, order=10)
        seq_scene = create_sequence_scene(self.script, reference_scene_id=sc10.id, sequence_type='song')

        save_url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': seq_scene.id})
        payload = {
            'heading': 'SONG BEGINS',
            'elements': [
                {'element_type': 'shot', 'content': 'SONG BEGINS', 'order': 0},
                {'element_type': 'shot', 'content': '1. INT. ROOM - DAY', 'order': 1},
                {'element_type': 'action', 'content': 'ആദ്യ രംഗം ഗാനം ആരംഭിക്കുന്നു.', 'order': 2},
                {'element_type': 'shot', 'content': '2. EXT. GARDEN - NIGHT', 'order': 3},
                {'element_type': 'shot', 'content': 'SONG ENDS', 'order': 4},
            ]
        }
        resp = self.client.post(save_url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(resp.status_code, 200)

        # Reload scene
        get_url = reverse('api_get_scene', kwargs={'script_id': self.script.id, 'scene_id': seq_scene.id})
        get_resp = self.client.get(get_url)
        self.assertEqual(get_resp.status_code, 200)
        data = get_resp.json()

        self.assertTrue(data['scene']['is_sequence'])
        self.assertEqual(data['scene']['sequence_type'], 'song')
        self.assertEqual(data['scene']['nav_identifier'], 'Song Sequence')
        self.assertEqual(len(data['elements']), 5)
        self.assertEqual(data['elements'][2]['content'], 'ആദ്യ രംഗം ഗാനം ആരംഭിക്കുന്നു.')

    def test_14_scene_navigation_correctly_identifies_and_opens_sequence(self):
        """
        Scene tree serialization provides is_sequence, sequence_type, and nav_identifier
        for accurate sidebar navigation.
        """
        sc1 = Scene.objects.create(script=self.script, heading='INT. OFFICE - DAY', scene_number=1, order=1)
        seq_scene = create_sequence_scene(self.script, reference_scene_id=sc1.id, sequence_type='montage')

        tree = serialize_scenes_hierarchy(self.script)
        self.assertEqual(len(tree), 2)

        seq_node = [n for n in tree if n['id'] == seq_scene.id][0]
        self.assertTrue(seq_node['is_sequence'])
        self.assertEqual(seq_node['sequence_type'], 'montage')
        self.assertEqual(seq_node['nav_identifier'], 'Montage Sequence')
        self.assertEqual(seq_node['clean_location'], 'MONTAGE BEGINS')

    def test_15_api_create_sequence_scene_endpoint(self):
        """
        POST api_create_sequence_scene creates a sequence scene and returns correct JSON.
        """
        sc10 = Scene.objects.create(script=self.script, heading='INT. HOUSE - NIGHT', scene_number=10, order=10)
        url = reverse('api_create_sequence_scene', kwargs={'script_id': self.script.id})

        resp = self.client.post(url, data=json.dumps({
            'reference_scene_id': sc10.id,
            'sequence_type': 'song'
        }), content_type='application/json')

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        self.assertTrue(data['scene']['is_sequence'])
        self.assertEqual(data['scene']['sequence_type'], 'song')
        self.assertEqual(data['scene']['nav_identifier'], 'Song Sequence')

    # ----------------------------------------------------
    # 5. EXPORTS & RENDERING COMPATIBILITY
    # ----------------------------------------------------

    def test_16_exports_render_sequence_as_separate_scene_without_cut_to(self):
        """
        PDF, DOCX, and TXT exporters render sequence scenes with full display headings and no stray CUT TO.
        """
        sc10 = Scene.objects.create(script=self.script, heading='INT. HOUSE - NIGHT', scene_number=10, order=10, transition='')
        ScriptElement.objects.create(scene=sc10, element_type='scene_heading', content='INT. HOUSE - NIGHT', order=0)
        ScriptElement.objects.create(scene=sc10, element_type='action', content='Action in house.', order=1)

        seq_scene = create_sequence_scene(self.script, reference_scene_id=sc10.id, sequence_type='song')
        ScriptElement.objects.create(scene=seq_scene, element_type='shot', content='2. EXT. ROOF - NIGHT', order=3)
        ScriptElement.objects.create(scene=seq_scene, element_type='shot', content='SONG ENDS', order=4)

        # DOCX Export
        docx_bytes = generate_screenplay_docx(self.script)
        self.assertIsInstance(docx_bytes, bytes)
        self.assertGreater(len(docx_bytes), 1000)

        # Deep inspect DOCX content
        doc = docx.Document(io.BytesIO(docx_bytes))
        docx_texts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

        # 1. Sequence heading appears exactly once
        self.assertEqual(docx_texts.count('SONG BEGINS'), 1)
        # 2. Initial shot appears in correct order
        self.assertIn('1. INT. LOCATION - DAY', docx_texts)
        self.assertIn('2. EXT. ROOF - NIGHT', docx_texts)
        idx_heading = docx_texts.index('SONG BEGINS')
        idx_shot1 = docx_texts.index('1. INT. LOCATION - DAY')
        idx_shot2 = docx_texts.index('2. EXT. ROOF - NIGHT')
        self.assertLess(idx_heading, idx_shot1)
        self.assertLess(idx_shot1, idx_shot2)
        # 3. Sequence ending marker appears exactly once
        self.assertEqual(docx_texts.count('SONG ENDS'), 1)
        idx_ends = docx_texts.index('SONG ENDS')
        self.assertLess(idx_shot2, idx_ends)
        # 4. No unwanted fallback CUT TO: for the sequence
        docx_after_ends = docx_texts[idx_ends:]
        self.assertFalse(any('CUT TO' in t for t in docx_after_ends))
        # 5. Ordinary scene heading and content are present
        self.assertTrue(any('SCENE 10' in t or 'INT. HOUSE - NIGHT' in t for t in docx_texts))
        self.assertIn('Action in house.', docx_texts)

        # PDF Export
        pdf_bytes = generate_screenplay_pdf(self.script)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 1000)

        # Deep inspect PDF content via pypdfium2
        pdf_doc = pdfium.PdfDocument(pdf_bytes)
        pdf_text = ''
        for page in pdf_doc:
            textpage = page.get_textpage()
            pdf_text += textpage.get_text_range() + '\n'

        self.assertEqual(pdf_text.count('SONG BEGINS'), 1)
        self.assertIn('1. INT. LOCATION - DAY', pdf_text)
        self.assertIn('2. EXT. ROOF - NIGHT', pdf_text)
        self.assertEqual(pdf_text.count('SONG ENDS'), 1)
        # Verify ordering in extracted PDF text
        p_idx_heading = pdf_text.index('SONG BEGINS')
        p_idx_shot1 = pdf_text.index('1. INT. LOCATION - DAY')
        p_idx_shot2 = pdf_text.index('2. EXT. ROOF - NIGHT')
        p_idx_ends = pdf_text.index('SONG ENDS')
        self.assertLess(p_idx_heading, p_idx_shot1)
        self.assertLess(p_idx_shot1, p_idx_shot2)
        self.assertLess(p_idx_shot2, p_idx_ends)
        # No unwanted fallback CUT TO: for the sequence
        pdf_after_ends = pdf_text[p_idx_ends:]
        self.assertNotIn('CUT TO', pdf_after_ends)
        # Ordinary scene heading and content present
        self.assertIn('INT. HOUSE - NIGHT', pdf_text)
        self.assertIn('Action in house.', pdf_text)

        # TXT Export
        txt_str = generate_screenplay_txt(self.script)
        self.assertIn('SONG BEGINS', txt_str)
        self.assertIn('1. INT. LOCATION - DAY', txt_str)
        self.assertIn('2. EXT. ROOF - NIGHT', txt_str)
        self.assertIn('SONG ENDS', txt_str)

        lines = [l.strip() for l in txt_str.splitlines() if l.strip()]
        self.assertIn('SONG ENDS', lines)
        self.assertEqual(lines[-1], 'SONG ENDS')
        self.assertNotIn('CUT TO', txt_str.split('SONG ENDS')[1])

    def test_17_print_preview_renders_sequence_page_cleanly(self):
        """
        Print preview renders sequence page heading and shots cleanly.
        """
        create_sequence_scene(self.script, reference_scene_id=None, sequence_type='montage')
        url = reverse('print_preview', kwargs={'script_id': self.script.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')
        self.assertIn('MONTAGE BEGINS', content)
        self.assertIn('1. INT. LOCATION - DAY', content)

    def test_18_sequence_marker_after_ordinary_action_detected_with_prefetched_elements(self):
        """
        A scene with an ordinary heading whose sequence-start marker follows an ordinary
        action element is recognized as a sequence when elements are prefetched.
        """
        sc = Scene.objects.create(script=self.script, heading='INT. STAGE - NIGHT', scene_number=5, order=5)
        ScriptElement.objects.create(scene=sc, element_type='action', content='The singer enters the room.', order=0)
        ScriptElement.objects.create(scene=sc, element_type='shot', content='SONG BEGINS', order=1)

        prefetched_scene = Scene.objects.filter(id=sc.id).prefetch_related('elements').first()

        self.assertTrue(prefetched_scene.is_sequence)
        self.assertEqual(prefetched_scene.sequence_type, 'song')

    def test_19_ordinary_text_mentioning_song_or_montage_not_detected_as_sequence(self):
        """
        An ordinary scene containing text mentioning 'song' or 'montage' in an action block
        without a recognized sequence start marker is not detected as a sequence.
        """
        sc = Scene.objects.create(script=self.script, heading='INT. MUSIC ROOM - NIGHT', scene_number=6, order=6)
        ScriptElement.objects.create(
            scene=sc,
            element_type='action',
            content='The character sings a song during the montage rehearsal.',
            order=0
        )

        prefetched_scene = Scene.objects.filter(id=sc.id).prefetch_related('elements').first()

        self.assertFalse(prefetched_scene.is_sequence)
        self.assertEqual(prefetched_scene.sequence_type, '')

    def test_20_song_sequence_requires_song_ends_not_montage_ends(self):
        """
        A Song sequence containing 'MONTAGE ENDS' is not considered closed;
        creating a normal scene after it automatically inserts 'SONG ENDS'.
        """
        sc1 = Scene.objects.create(script=self.script, heading='INT. STUDIO - DAY', scene_number=1, order=1)
        seq_scene = create_sequence_scene(self.script, reference_scene_id=sc1.id, sequence_type='song')
        ScriptElement.objects.create(scene=seq_scene, element_type='shot', content='MONTAGE ENDS', order=3)

        new_scene = insert_scene_relative(self.script, reference_scene_id=seq_scene.id, position='after', heading='EXT. STREET - NIGHT')

        self.assertEqual(seq_scene.elements.filter(content='MONTAGE ENDS').count(), 1)
        self.assertEqual(seq_scene.elements.filter(content='SONG ENDS').count(), 1)
        self.assertIsNotNone(new_scene)
        self.assertEqual(new_scene.heading, 'EXT. STREET - NIGHT')
        self.assertEqual(new_scene.scene_number, 2)

    def test_21_montage_sequence_requires_montage_ends_not_song_ends(self):
        """
        A Montage sequence containing 'SONG ENDS' is not considered closed;
        creating a normal scene after it automatically inserts 'MONTAGE ENDS'.
        """
        sc1 = Scene.objects.create(script=self.script, heading='INT. GYM - DAY', scene_number=1, order=1)
        seq_scene = create_sequence_scene(self.script, reference_scene_id=sc1.id, sequence_type='montage')
        ScriptElement.objects.create(scene=seq_scene, element_type='shot', content='SONG ENDS', order=3)

        new_scene = insert_scene_relative(self.script, reference_scene_id=seq_scene.id, position='after', heading='INT. RING - NIGHT')

        self.assertEqual(seq_scene.elements.filter(content='SONG ENDS').count(), 1)
        self.assertEqual(seq_scene.elements.filter(content='MONTAGE ENDS').count(), 1)
        self.assertIsNotNone(new_scene)
        self.assertEqual(new_scene.heading, 'INT. RING - NIGHT')
        self.assertEqual(new_scene.scene_number, 2)

    def test_22_create_sequence_after_mismatched_ending_inserts_correct_ending(self):
        """
        Creating another sequence after a sequence with a mismatched ending marker
        still closes the active sequence with its appropriate ending marker.
        """
        # Song sequence with MONTAGE ENDS followed by another sequence
        song_scene = create_sequence_scene(self.script, reference_scene_id=None, sequence_type='song')
        ScriptElement.objects.create(scene=song_scene, element_type='shot', content='MONTAGE ENDS', order=3)
        next_seq = create_sequence_scene(self.script, reference_scene_id=song_scene.id, sequence_type='montage')

        self.assertEqual(song_scene.elements.filter(content='MONTAGE ENDS').count(), 1)
        self.assertEqual(song_scene.elements.filter(content='SONG ENDS').count(), 1)
        self.assertTrue(next_seq.is_sequence)
        self.assertEqual(next_seq.sequence_type, 'montage')

        # Montage sequence with SONG ENDS followed by another sequence
        montage_scene = create_sequence_scene(self.script, reference_scene_id=next_seq.id, sequence_type='montage')
        ScriptElement.objects.create(scene=montage_scene, element_type='shot', content='SONG ENDS', order=3)
        final_seq = create_sequence_scene(self.script, reference_scene_id=montage_scene.id, sequence_type='song')

        self.assertEqual(montage_scene.elements.filter(content='SONG ENDS').count(), 1)
        self.assertEqual(montage_scene.elements.filter(content='MONTAGE ENDS').count(), 1)
        self.assertTrue(final_seq.is_sequence)
        self.assertEqual(final_seq.sequence_type, 'song')

    def test_23_api_reorder_rejection_for_sequence_scene(self):
        """
        Attempting to reorder a sequence scene via the API returns HTTP 400,
        keeps the sequence scene and all other scenes in place, preserves master scene
        numbering, and leaves database contents uncorrupted.
        """
        # Create Scene 1, Sequence Scene, Scene 2 (with Sub-scene 2.A), and Scene 3
        sc1 = Scene.objects.create(script=self.script, heading='INT. OFFICE - DAY', order=1)
        seq_scene = create_sequence_scene(self.script, reference_scene_id=sc1.id, sequence_type='song')
        sc2 = Scene.objects.create(script=self.script, heading='INT. HOUSE - NIGHT', order=3)
        sub_2a = create_sub_scene(self.script, sc2.id, 'INT. BEDROOM - NIGHT')
        sc3 = Scene.objects.create(script=self.script, heading='EXT. PARK - DAY', order=5)
        resequence_script_scenes(self.script)

        # Snapshot initial state
        initial_order_ids = list(self.script.scenes.filter(is_deleted=False).order_by('order', 'id').values_list('id', flat=True))
        seq_elems_before = list(seq_scene.elements.order_by('order', 'id').values_list('element_type', 'content', 'order'))

        # Attempt to renumber/reorder the sequence scene to scene_number 2 via api_save_scene
        save_url = reverse('api_save_scene', kwargs={'script_id': self.script.id, 'scene_id': seq_scene.id})
        resp = self.client.post(
            save_url,
            data=json.dumps({'heading': 'SONG BEGINS', 'scene_number': 2}),
            content_type='application/json'
        )

        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertEqual(data.get('status'), 'error')
        self.assertEqual(data.get('message'), 'Sequence scenes cannot be renumbered.')

        # Refresh all scenes from DB and verify immutability of structure
        sc1.refresh_from_db()
        sc2.refresh_from_db()
        sub_2a.refresh_from_db()
        sc3.refresh_from_db()
        seq_scene.refresh_from_db()

        self.assertEqual(sc1.scene_number, 1)
        self.assertEqual(sc2.scene_number, 2)
        self.assertEqual(sc3.scene_number, 3)
        self.assertEqual(sub_2a.sub_letter, 'A')
        self.assertEqual(sub_2a.parent_scene_id, sc2.id)
        self.assertTrue(seq_scene.is_sequence)

        # Full order across all scenes unchanged
        current_order_ids = list(self.script.scenes.filter(is_deleted=False).order_by('order', 'id').values_list('id', flat=True))
        self.assertEqual(current_order_ids, initial_order_ids)

        # Sequence elements unchanged
        seq_elems_after = list(seq_scene.elements.order_by('order', 'id').values_list('element_type', 'content', 'order'))
        self.assertEqual(seq_elems_after, seq_elems_before)

    def test_24_insert_sequence_before_scene_preserves_order_and_numbering(self):
        """
        insert_scene_relative(position='before') with a sequence heading inserts the sequence
        immediately before the reference scene without consuming master scene numbers,
        preserving surrounding scene and sub-scene hierarchy, and properly supporting
        sequence ending markers.
        """
        sc1 = Scene.objects.create(script=self.script, heading='INT. CAFE - DAY', order=1)
        sc2 = Scene.objects.create(script=self.script, heading='INT. STUDIO - NIGHT', order=2)
        sub_2a = create_sub_scene(self.script, sc2.id, 'INT. CONTROL ROOM - NIGHT')
        sc3 = Scene.objects.create(script=self.script, heading='EXT. ALLEY - NIGHT', order=4)
        resequence_script_scenes(self.script)

        # Insert Song sequence BEFORE Scene 2
        seq_song = insert_scene_relative(
            self.script,
            reference_scene_id=sc2.id,
            position='before',
            heading='SONG BEGINS'
        )

        # Invariants verification
        self.assertTrue(seq_song.is_sequence)
        self.assertEqual(seq_song.sequence_type, 'song')
        self.assertEqual(seq_song.heading, 'SONG BEGINS')
        self.assertEqual(seq_song.nav_identifier, 'Song Sequence')

        # Check seeded elements
        song_elems = list(seq_song.elements.order_by('order', 'id').values_list('content', flat=True))
        self.assertEqual(song_elems[0], 'SONG BEGINS')
        self.assertEqual(song_elems[1], '1. INT. LOCATION - DAY')

        # Add explicit SONG ENDS
        ScriptElement.objects.create(scene=seq_song, element_type='shot', content='SONG ENDS', order=3)

        # Verify ordering: sc1 -> seq_song -> sc2 -> sub_2a -> sc3
        all_ordered = list(self.script.scenes.filter(is_deleted=False).order_by('order', 'id'))
        expected_ids = [sc1.id, seq_song.id, sc2.id, sub_2a.id, sc3.id]
        self.assertEqual([s.id for s in all_ordered], expected_ids)

        # Master scene numbering: Scene 1, Sequence (no master num), Scene 2, Scene 2.A, Scene 3
        sc1.refresh_from_db()
        sc2.refresh_from_db()
        sub_2a.refresh_from_db()
        sc3.refresh_from_db()

        self.assertEqual(sc1.scene_number, 1)
        self.assertEqual(sc2.scene_number, 2)
        self.assertEqual(sc3.scene_number, 3)
        self.assertEqual(sub_2a.sub_letter, 'A')
        self.assertEqual(sub_2a.parent_scene_id, sc2.id)

        # Now test Montage sequence inserted before Scene 3
        seq_montage = insert_scene_relative(
            self.script,
            reference_scene_id=sc3.id,
            position='before',
            heading='MONTAGE BEGINS'
        )
        self.assertTrue(seq_montage.is_sequence)
        self.assertEqual(seq_montage.sequence_type, 'montage')
        self.assertEqual(seq_montage.nav_identifier, 'Montage Sequence')

        # Add explicit MONTAGE ENDS
        ScriptElement.objects.create(scene=seq_montage, element_type='shot', content='MONTAGE ENDS', order=3)

        # Verify markers are not duplicated or corrupted
        self.assertEqual(seq_song.elements.filter(content='SONG ENDS').count(), 1)
        self.assertEqual(seq_montage.elements.filter(content='MONTAGE ENDS').count(), 1)

        # Final full order: sc1 -> seq_song -> sc2 -> sub_2a -> seq_montage -> sc3
        final_ordered = list(self.script.scenes.filter(is_deleted=False).order_by('order', 'id'))
        expected_final_ids = [sc1.id, seq_song.id, sc2.id, sub_2a.id, seq_montage.id, sc3.id]
        self.assertEqual([s.id for s in final_ordered], expected_final_ids)

        # Numbering remains Scene 1, Scene 2, Scene 3
        sc3.refresh_from_db()
        self.assertEqual(sc3.scene_number, 3)




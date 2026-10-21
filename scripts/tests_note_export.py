"""
Tests for KadhaScript — Optional Note Inclusion in PDF and DOCX Exports.

Verifies:
1. PDF excludes Note content when include_notes=False (and by default).
2. PDF includes Note content when include_notes=True.
3. DOCX excludes Note content when include_notes=False (and by default).
4. DOCX includes Note content when include_notes=True.
5. Ordinary Action, Character, Dialogue content remains present in both cases.
6. Malayalam Note text survives when notes are included.
7. Song/Montage markers and ordinary screenplay formatting remain unchanged.
"""

import io
from docx import Document
import pypdfium2 as pdfium
from django.test import TestCase
from django.contrib.auth.models import User

from scripts.models import Script, Scene, ScriptElement
from scripts.services.pdf_export import generate_screenplay_pdf
from scripts.services.docx_export import generate_screenplay_docx
from scripts.services.txt_export import generate_screenplay_txt
from scripts.services.scene_service import create_sequence_scene


class NoteExportInclusionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='director', password='password123')
        self.script = Script.objects.create(
            user=self.user,
            title='കുറിപ്പ് ടെസ്റ്റ് തിരക്കഥ (Note Export Script)',
            language='Malayalam'
        )

        # Scene 1: Standard scene with Action, Character, Dialogue, and Notes (English + Malayalam)
        self.scene1 = Scene.objects.create(
            script=self.script,
            scene_number=1,
            heading='INT. STUDY ROOM - DAY',
            order=0
        )
        self.elem_action = ScriptElement.objects.create(
            scene=self.scene1,
            element_type='action',
            content='The professor reviews old ancient manuscripts on his wooden table.',
            order=0
        )
        self.elem_note_en = ScriptElement.objects.create(
            scene=self.scene1,
            element_type='note',
            content='SECRET_DIRECTOR_NOTE: Place close-up camera on the quill pen.',
            order=1
        )
        self.elem_char = ScriptElement.objects.create(
            scene=self.scene1,
            element_type='character',
            content='പ്രൊഫസർ (PROFESSOR)',
            order=2
        )
        self.elem_dialogue = ScriptElement.objects.create(
            scene=self.scene1,
            element_type='dialogue',
            content='ഈ രഹസ്യം ആരും അറിയരുത് (Nobody must know this secret).',
            order=3
        )
        self.elem_note_ml = ScriptElement.objects.create(
            scene=self.scene1,
            element_type='note',
            content='സംവിധായകന്റെ_കുറിപ്പ്: പശ്ചാത്തല സംഗീതം സാവധാനം ഉയരണം.',
            order=4
        )

        # Scene 2: Song Sequence to test Sequence markers along with notes
        self.seq_scene = create_sequence_scene(self.script, sequence_type='song', reference_scene_id=self.scene1.id)
        # Add a note inside the sequence scene
        ScriptElement.objects.create(
            scene=self.seq_scene,
            element_type='note',
            content='SEQUENCE_CHOREOGRAPHY_NOTE: Dancers enter from frame right.',
            order=10
        )
        # Add sequence closing marker
        ScriptElement.objects.create(
            scene=self.seq_scene,
            element_type='shot',
            content='SONG ENDS',
            order=20
        )

    def _extract_pdf_text(self, pdf_bytes: bytes) -> str:
        pdf_doc = pdfium.PdfDocument(pdf_bytes)
        pdf_text = ''
        for page in pdf_doc:
            textpage = page.get_textpage()
            pdf_text += textpage.get_text_range() + '\n'
        return pdf_text

    def _extract_docx_text(self, docx_bytes: bytes) -> str:
        doc = Document(io.BytesIO(docx_bytes))
        return " \n".join([p.text.strip() for p in doc.paragraphs if p.text.strip()])

    def test_pdf_excludes_notes_by_default_and_when_explicitly_false(self):
        """1. PDF excludes Note content when include_notes=False and by default."""
        # Default argument
        pdf_default = generate_screenplay_pdf(self.script)
        pdf_text_default = self._extract_pdf_text(pdf_default)
        self.assertNotIn('SECRET_DIRECTOR_NOTE', pdf_text_default)
        self.assertNotIn('സംഗീതം സാവധാനം ഉയരണം', pdf_text_default)
        self.assertNotIn('SEQUENCE_CHOREOGRAPHY_NOTE', pdf_text_default)

        # Explicit False
        pdf_false = generate_screenplay_pdf(self.script, include_notes=False)
        pdf_text_false = self._extract_pdf_text(pdf_false)
        self.assertNotIn('SECRET_DIRECTOR_NOTE', pdf_text_false)
        self.assertNotIn('സംഗീതം സാവധാനം ഉയരണം', pdf_text_false)
        self.assertNotIn('SEQUENCE_CHOREOGRAPHY_NOTE', pdf_text_false)

        # Ordinary Action, Character, Dialogue remain present
        self.assertIn('The professor reviews old ancient manuscripts', pdf_text_default)
        self.assertIn('PROFESSOR', pdf_text_default)
        self.assertIn('The professor reviews old ancient manuscripts', pdf_text_false)

    def test_pdf_includes_notes_when_include_notes_is_true(self):
        """2 & 6. PDF includes Note content and preserves Malayalam Unicode when include_notes=True."""
        pdf_true = generate_screenplay_pdf(self.script, include_notes=True)
        pdf_text = self._extract_pdf_text(pdf_true)

        # English note present
        self.assertIn('SECRET_DIRECTOR_NOTE: Place close-up camera on the quill pen.', pdf_text)

        # Malayalam note text present (stem and non-conjunct words)
        self.assertIn('സംവിധായക', pdf_text)
        self.assertIn('സംഗീതം സാവധാനം ഉയരണം', pdf_text)

        # Sequence note present
        self.assertIn('SEQUENCE_CHOREOGRAPHY_NOTE: Dancers enter from frame right.', pdf_text)

        # Ordinary screenplay content remains present
        self.assertIn('The professor reviews old ancient manuscripts', pdf_text)
        self.assertIn('PROFESSOR', pdf_text)

    def test_docx_excludes_notes_by_default_and_when_explicitly_false(self):
        """3. DOCX excludes Note content when include_notes=False and by default."""
        # Default argument
        docx_default = generate_screenplay_docx(self.script)
        docx_text_default = self._extract_docx_text(docx_default)
        self.assertNotIn('SECRET_DIRECTOR_NOTE', docx_text_default)
        self.assertNotIn('സംവിധായകന്റെ_കുറിപ്പ്', docx_text_default)
        self.assertNotIn('SEQUENCE_CHOREOGRAPHY_NOTE', docx_text_default)

        # Explicit False
        docx_false = generate_screenplay_docx(self.script, include_notes=False)
        docx_text_false = self._extract_docx_text(docx_false)
        self.assertNotIn('SECRET_DIRECTOR_NOTE', docx_text_false)
        self.assertNotIn('സംവിധായകന്റെ_കുറിപ്പ്', docx_text_false)
        self.assertNotIn('SEQUENCE_CHOREOGRAPHY_NOTE', docx_text_false)

        # Ordinary Action, Character, Dialogue remain present
        self.assertIn('The professor reviews old ancient manuscripts', docx_text_default)
        self.assertIn('PROFESSOR', docx_text_default)

    def test_docx_includes_notes_when_include_notes_is_true(self):
        """4 & 6. DOCX includes Note content and preserves Malayalam Unicode when include_notes=True."""
        docx_true = generate_screenplay_docx(self.script, include_notes=True)
        docx_text = self._extract_docx_text(docx_true)

        # English note present
        self.assertIn('SECRET_DIRECTOR_NOTE: Place close-up camera on the quill pen.', docx_text)

        # Malayalam note present
        self.assertIn('സംവിധായകന്റെ_കുറിപ്പ്: പശ്ചാത്തല സംഗീതം സാവധാനം ഉയരണം.', docx_text)

        # Sequence note present
        self.assertIn('SEQUENCE_CHOREOGRAPHY_NOTE: Dancers enter from frame right.', docx_text)

        # Ordinary screenplay elements present
        self.assertIn('The professor reviews old ancient manuscripts', docx_text)
        self.assertIn('ഈ രഹസ്യം ആരും അറിയരുത്', docx_text)

    def test_song_montage_markers_and_formatting_remain_unchanged(self):
        """7. Sequence markers (SONG BEGINS, SONG ENDS) and formatting remain intact with notes on/off."""
        # Test PDF with notes off and on (PDF uses 'Song Begins:' and 'Song Ends' as canonical ReportLab sequence headers)
        pdf_off = self._extract_pdf_text(generate_screenplay_pdf(self.script, include_notes=False))
        pdf_on = self._extract_pdf_text(generate_screenplay_pdf(self.script, include_notes=True))

        self.assertIn('Song Begins:', pdf_off)
        self.assertIn('Song Ends', pdf_off)
        self.assertIn('Song Begins:', pdf_on)
        self.assertIn('Song Ends', pdf_on)

        # Test DOCX with notes off and on
        docx_off = self._extract_docx_text(generate_screenplay_docx(self.script, include_notes=False))
        docx_on = self._extract_docx_text(generate_screenplay_docx(self.script, include_notes=True))

        self.assertIn('SONG BEGINS', docx_off)
        self.assertIn('SONG ENDS', docx_off)
        self.assertIn('SONG BEGINS', docx_on)
        self.assertIn('SONG ENDS', docx_on)

        # TXT export compatibility
        txt_off = generate_screenplay_txt(self.script, include_notes=False)
        txt_on = generate_screenplay_txt(self.script, include_notes=True)

        self.assertNotIn('SECRET_DIRECTOR_NOTE', txt_off)
        self.assertIn('/* NOTE: SECRET_DIRECTOR_NOTE', txt_on)
        self.assertIn('/* NOTE: സംവിധായകന്റെ_കുറിപ്പ്', txt_on)
        self.assertIn('SONG BEGINS', txt_off)
        self.assertIn('SONG ENDS', txt_off)

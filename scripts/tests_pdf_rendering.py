"""
Tests for PDF export typography and mixed Malayalam/Latin HarfBuzz script shaping.
"""

import io
import unittest
from django.test import TestCase
from django.contrib.auth import get_user_model
from scripts.models import Script, Scene, ScriptElement
from scripts.services.pdf_export import (
    generate_screenplay_pdf,
    get_screenplay_pdf_styles,
    _segment_text_into_script_runs,
    _get_char_script,
    _get_font_for_script,
    format_screenplay_text,
    enable_mixed_script_shaping,
    _COURIER_FONT_REGULAR,
    _COURIER_FONT_BOLD,
    _COURIER_FONT_OBLIQUE,
    _COURIER_FONT_BOLDOBLIQUE,
    _MALAYALAM_FONT_NAME,
    _MALAYALAM_FONT_BOLD,
)

User = get_user_model()

try:
    import pypdfium2 as pdfium
    HAS_PDFIUM = True
except ImportError:
    HAS_PDFIUM = False


class PDFRenderingTypographyAndShapingTests(TestCase):
    """
    Tests ensuring mixed Malayalam/Latin text (such as SHO-യോട്) shapes correctly
    without vowel-sign collision or script confusion, and that approved ~13pt typography
    is applied to screenplay elements.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='typotester',
            email='typotester@example.com',
            password='Password123!'
        )

    def setUp(self):
        enable_mixed_script_shaping()

    def test_script_run_segmentation(self):
        """
        Verify that mixed-script tokens are properly segmented into distinct script runs
        while preserving character order and attaching punctuation appropriately.
        """
        # SHO-യോട് -> Latin/punct 'SHO-', Malayalam 'യോട്'
        runs = _segment_text_into_script_runs('SHO-യോട്')
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0], ('SHO-', 'Latn'))
        self.assertEqual(runs[1], ('യോട്', 'Mlym'))

        # ABC/യോട് -> 'ABC/', 'യോട്'
        runs_slash = _segment_text_into_script_runs('ABC/യോട്')
        self.assertEqual(runs_slash, [('ABC/', 'Latn'), ('യോട്', 'Mlym')])

        # ABC:യോട് -> 'ABC:', 'യോട്'
        runs_colon = _segment_text_into_script_runs('ABC:യോട്')
        self.assertEqual(runs_colon, [('ABC:', 'Latn'), ('യോട്', 'Mlym')])

        # Malayalam-only: no splitting
        runs_mlym = _segment_text_into_script_runs('ജ്യോതി')
        self.assertEqual(runs_mlym, [('ജ്യോതി', 'Mlym')])

        # Latin-only: no splitting
        runs_latn = _segment_text_into_script_runs('COFFEE')
        self.assertEqual(runs_latn, [('COFFEE', 'Latn')])

    def test_typography_styles_specification(self):
        """
        Verify PDF paragraph styles adhere to the approved ~13pt typography specification.
        """
        styles = get_screenplay_pdf_styles()

        # SceneHeading: 13pt bold, ~17.5pt leading
        self.assertEqual(styles['SceneHeading'].fontSize, 13)
        self.assertEqual(styles['SceneHeading'].leading, 17.5)
        self.assertTrue(styles['SceneHeading'].shaping)

        # Action: 13pt regular, ~17.5pt leading
        self.assertEqual(styles['Action'].fontSize, 13)
        self.assertEqual(styles['Action'].leading, 17.5)
        self.assertTrue(styles['Action'].shaping)

        # Character: 13pt bold, ~16pt leading
        self.assertEqual(styles['Character'].fontSize, 13)
        self.assertEqual(styles['Character'].leading, 16)
        self.assertTrue(styles['Character'].shaping)

        # Dialogue: 13pt regular, ~17.5pt leading
        self.assertEqual(styles['Dialogue'].fontSize, 13)
        self.assertEqual(styles['Dialogue'].leading, 17.5)
        self.assertTrue(styles['Dialogue'].shaping)

        # Parenthetical: 11pt regular, ~14pt leading
        self.assertEqual(styles['Parenthetical'].fontSize, 11)
        self.assertEqual(styles['Parenthetical'].leading, 14)
        self.assertTrue(styles['Parenthetical'].shaping)

        # Transition: 13pt bold, ~16pt leading
        self.assertEqual(styles['Transition'].fontSize, 13)
        self.assertEqual(styles['Transition'].leading, 16)
        self.assertTrue(styles['Transition'].shaping)

        # Shot: 13pt bold, ~16pt leading
        self.assertEqual(styles['Shot'].fontSize, 13)
        self.assertEqual(styles['Shot'].leading, 16)
        self.assertTrue(styles['Shot'].shaping)

    def test_pdf_generation_mixed_script_tokens_and_phrases(self):
        """
        Verify PDF export generates valid PDF bytes containing the required test phrases:
        SHO-യോട്, SHO യോട്, SHO-യോട് പറഞ്ഞു, SHO-യോട് സംസാരിക്കുന്നു, ABC-യോട്, etc.
        """
        script = Script.objects.create(
            user=self.user,
            title='Mixed Script Shaping Test',
            language='Malayalam'
        )
        scene = Scene.objects.create(
            script=script,
            scene_number=1,
            heading='INT. POLICE STATION - DAY',
            order=0
        )

        test_phrases = [
            'SHO-യോട്',
            'SHO യോട്',
            'SHO-യോട് പറഞ്ഞു',
            'SHO-യോട് സംസാരിക്കുന്നു',
            'ABC-യോട്',
            'ABC/യോട്',
            'ABC:യോട്',
            'ജ്യോതി ഒന്നും മിണ്ടുന്നില്ല',
            'കുഞ്ഞുവിന്റെ കവിളിൽ ഉമ്മ വച്ചുകൊണ്ട്',
            'ഇതിനിടയിൽ പരിഭ്രമത്തോടെ',
        ]

        order = 0
        for phrase in test_phrases:
            ScriptElement.objects.create(
                scene=scene,
                element_type='action',
                content=phrase,
                order=order
            )
            order += 1

        pdf_bytes = generate_screenplay_pdf(script)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))
        self.assertGreater(len(pdf_bytes), 1000)

        if HAS_PDFIUM:
            doc = pdfium.PdfDocument(io.BytesIO(pdf_bytes))
            self.assertGreaterEqual(len(doc), 2)  # Cover page + scene page
            scene_page = doc[1]
            textpage = scene_page.get_textpage()
            extracted_text = textpage.get_text_range()

            # Verify that HarfBuzz properly shaped SHO-യോട്:
            # Under Malayalam shaping, vowel sign ോ (U+0D4B) decomposes and reorders
            # into pre-base േ (U+0D47) + യ (U+0D2F) + post-base ാ (U+0D3E).
            # The raw unshaped sequence (\u0d2f\u0d4b) must not remain in the shaped glyph stream.
            self.assertIn('SHO-', extracted_text)
            self.assertIn('\u0d47\u0d2f\u0d3e\u0d1f\u0d4d', extracted_text)
            self.assertNotIn('SHO-\u0d2f\u0d4b', extracted_text)

            # Check that other complex Malayalam phrases rendered into the document
            # 'ജ്യോതി' -> േ + ജ + ്യ + ാ + ത + ി (\u0d47\u0d1c\u0d4d\u0d2f\u0d3e\u0d24\u0d3f)
            self.assertIn('\u0d47\u0d1c', extracted_text)

            # Verify page rendering succeeds
            bitmap = scene_page.render(scale=1)
            pil_image = bitmap.to_pil()
            self.assertGreater(pil_image.width, 100)
            self.assertGreater(pil_image.height, 100)

    def test_controls_english_and_malayalam_only(self):
        """
        Verify pure English and pure Malayalam controls generate without issues.
        """
        script = Script.objects.create(
            user=self.user,
            title='Controls Script',
            language='English'
        )
        scene = Scene.objects.create(
            script=script,
            scene_number=1,
            heading='EXT. PARK - DAY',
            order=0
        )
        # English control
        ScriptElement.objects.create(
            scene=scene,
            element_type='action',
            content='The quick brown fox jumps over the lazy dog.',
            order=0
        )
        # Malayalam control
        ScriptElement.objects.create(
            scene=scene,
            element_type='action',
            content='ഇത് ഒരു സാധാരണ മലയാളം വാചകമാണ്.',
            order=1
        )

        pdf_bytes = generate_screenplay_pdf(script)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))

        if HAS_PDFIUM:
            doc = pdfium.PdfDocument(io.BytesIO(pdf_bytes))
            scene_page = doc[1]
            textpage = scene_page.get_textpage()
            text = textpage.get_text_range()
            self.assertIn('The quick brown fox jumps over the lazy dog.', text)
            # Render page
            bitmap = scene_page.render(scale=1)
            self.assertIsNotNone(bitmap)

    def test_font_resolution_by_script_and_style(self):
        """
        Verify Courier family selection for Latin/English and Noto Sans Malayalam for Malayalam.
        Respects regular, bold, italic, and bold-italic variants.
        """
        # Latin / English variants
        self.assertEqual(_get_font_for_script('Latn', is_bold=False, is_italic=False), _COURIER_FONT_REGULAR)
        self.assertEqual(_get_font_for_script('Latn', is_bold=True, is_italic=False), _COURIER_FONT_BOLD)
        self.assertEqual(_get_font_for_script('Latn', is_bold=False, is_italic=True), _COURIER_FONT_OBLIQUE)
        self.assertEqual(_get_font_for_script('Latn', is_bold=True, is_italic=True), _COURIER_FONT_BOLDOBLIQUE)

        # Malayalam variants
        self.assertEqual(_get_font_for_script('Mlym', is_bold=False, is_italic=False), _MALAYALAM_FONT_NAME)
        self.assertEqual(_get_font_for_script('Mlym', is_bold=True, is_italic=False), _MALAYALAM_FONT_BOLD)
        self.assertEqual(_get_font_for_script('Mlym', is_bold=False, is_italic=True), _MALAYALAM_FONT_NAME)
        self.assertEqual(_get_font_for_script('Mlym', is_bold=True, is_italic=True), _MALAYALAM_FONT_BOLD)

    def test_format_screenplay_text_script_tagging(self):
        """
        Verify format_screenplay_text correctly tags text segments into Courier and MalayalamFont.
        """
        # Pure English -> Courier
        self.assertEqual(
            format_screenplay_text('HOUSE'),
            f'<font name="{_COURIER_FONT_REGULAR}">HOUSE</font>'
        )

        # Pure Malayalam -> MalayalamFont
        self.assertEqual(
            format_screenplay_text('വീട്'),
            f'<font name="{_MALAYALAM_FONT_NAME}">വീട്</font>'
        )

        # Mixed script: SHO-യോട്
        self.assertEqual(
            format_screenplay_text('SHO-യോട്'),
            f'<font name="{_COURIER_FONT_REGULAR}">SHO-</font><font name="{_MALAYALAM_FONT_NAME}">യോട്</font>'
        )

        # Mixed script: ABC/യോട്
        self.assertEqual(
            format_screenplay_text('ABC/യോട്'),
            f'<font name="{_COURIER_FONT_REGULAR}">ABC/</font><font name="{_MALAYALAM_FONT_NAME}">യോട്</font>'
        )

        # Bold English -> Courier-Bold
        self.assertEqual(
            format_screenplay_text('INT. HOUSE - DAY', is_bold=True),
            f'<font name="{_COURIER_FONT_BOLD}">INT. HOUSE - DAY</font>'
        )

        # Bold Malayalam -> MalayalamFont-Bold
        self.assertEqual(
            format_screenplay_text('ജ്യോതി', is_bold=True),
            f'<font name="{_MALAYALAM_FONT_BOLD}">ജ്യോതി</font>'
        )

        # Bold mixed script
        self.assertEqual(
            format_screenplay_text('SHO-യോട്', is_bold=True),
            f'<font name="{_COURIER_FONT_BOLD}">SHO-</font><font name="{_MALAYALAM_FONT_BOLD}">യോട്</font>'
        )

        # Italic English -> Courier-Oblique
        self.assertEqual(
            format_screenplay_text('(smiling)', is_italic=True),
            f'<font name="{_COURIER_FONT_OBLIQUE}">(smiling)</font>'
        )

        # XML entity escaping
        self.assertEqual(
            format_screenplay_text('TOM & JERRY <SCRIPT>'),
            f'<font name="{_COURIER_FONT_REGULAR}">TOM &amp; JERRY &lt;SCRIPT&gt;</font>'
        )

    def test_step8_sample_screenplay_pdf_generation_and_verification(self):
        """
        STEP 8 Verification:
        Generate a test PDF containing:
            INT. HOUSE - DAY
            ജ്യോതി വീട്ടിലേക്ക് നടക്കുന്നു.
            SHO-യോട്:
            "വരൂ."
            ABC/യോട് സംസാരിക്കുന്നു.
        Verify:
            - English is Courier (Courier / Courier-Bold referenced in PDF).
            - Malayalam is Noto Sans Malayalam.
            - Mixed-script words remain correctly shaped.
            - No missing glyphs or unshaped vowels.
        """
        import re
        script = Script.objects.create(
            user=self.user,
            title='Step 8 Verification Screenplay',
            language='Malayalam'
        )
        scene = Scene.objects.create(
            script=script,
            scene_number=1,
            heading='INT. HOUSE - DAY',
            order=0
        )
        # 1. Action: Malayalam
        ScriptElement.objects.create(
            scene=scene,
            element_type='action',
            content='ജ്യോതി വീട്ടിലേക്ക് നടക്കുന്നു.',
            order=0
        )
        # 2. Character: Mixed-script
        ScriptElement.objects.create(
            scene=scene,
            element_type='character',
            content='SHO-യോട്',
            order=1
        )
        # 3. Dialogue: Malayalam with quotes
        ScriptElement.objects.create(
            scene=scene,
            element_type='dialogue',
            content='"വരൂ."',
            order=2
        )
        # 4. Action: Mixed-script phrase
        ScriptElement.objects.create(
            scene=scene,
            element_type='action',
            content='ABC/യോട് സംസാരിക്കുന്നു.',
            order=3
        )

        pdf_bytes = generate_screenplay_pdf(script)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))
        self.assertGreater(len(pdf_bytes), 1000)

        # Verify embedded/referenced font names in PDF stream
        base_fonts = re.findall(rb'/BaseFont\s*/([A-Za-z0-9_\-+]+)', pdf_bytes)
        base_font_names = [f.decode('latin1', errors='ignore') for f in base_fonts]

        # Courier or Courier-Bold must be among the fonts
        has_courier = any('Courier' in fn for fn in base_font_names)
        self.assertTrue(has_courier, f"Expected Courier font in PDF, found: {base_font_names}")

        # Noto Sans Malayalam or MalayalamFont must be among the fonts
        has_malayalam = any(('Malayalam' in fn or 'NotoSansMalayalam' in fn) for fn in base_font_names)
        self.assertTrue(has_malayalam, f"Expected Malayalam font in PDF, found: {base_font_names}")

        if HAS_PDFIUM:
            doc = pdfium.PdfDocument(io.BytesIO(pdf_bytes))
            self.assertGreaterEqual(len(doc), 2)  # Cover page + scene page
            scene_page = doc[1]
            textpage = scene_page.get_textpage()
            extracted_text = textpage.get_text_range()

            # Verify English / Latin parts
            self.assertIn('INT. HOUSE - DAY', extracted_text)
            self.assertIn('SHO-', extracted_text)
            self.assertIn('ABC/', extracted_text)

            # Verify Malayalam shaping
            # 'SHO-യോട്': \u0d4b decomposes into \u0d47 + \u0d2f + \u0d3e
            self.assertIn('\u0d47\u0d2f\u0d3e\u0d1f\u0d4d', extracted_text)
            self.assertNotIn('SHO-\u0d2f\u0d4b', extracted_text)

            # 'ജ്യോതി': \u0d47\u0d1c is present
            self.assertIn('\u0d47\u0d1c', extracted_text)

            # Dialogue: '"വരൂ."'
            self.assertIn('വരൂ', extracted_text)

            # Render scene page to ensure no bitmap rendering failure
            bitmap = scene_page.render(scale=1)
            pil_image = bitmap.to_pil()
            self.assertGreater(pil_image.width, 100)
            self.assertGreater(pil_image.height, 100)

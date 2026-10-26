import io
import os
from pathlib import Path
from django.conf import settings
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, KeepTogether, HRFlowable, Table, TableStyle
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

import html
import unicodedata
import uharfbuzz
from reportlab.pdfbase.ttfonts import (
    ShapedFragWord, ShapedStr, ShapeData, makeShapedFragWord
)

# Font registration helper
_FONT_REGISTERED = False
_MALAYALAM_FONT_NAME = 'MalayalamFont'
_MALAYALAM_FONT_BOLD = 'MalayalamFont-Bold'
_COURIER_FONT_REGULAR = 'Courier'
_COURIER_FONT_BOLD = 'Courier-Bold'
_COURIER_FONT_OBLIQUE = 'Courier-Oblique'
_COURIER_FONT_BOLDOBLIQUE = 'Courier-BoldOblique'
_MIXED_SCRIPT_SHAPING_ENABLED = False
_ORIG_SHAPE_FRAG_WORD = None


# =============================================================================
# KadhaScript Mixed-Script Unicode Shaping Engine
#
# Tested on: ReportLab 5.0.1 + uharfbuzz 0.56.2 (Python 3.13)
#
# Why this integration is required:
# In ReportLab, Paragraph line-breaking splits text into whitespace-delimited
# tokens (FragWords). When a hyphenated or punctuation-joined mixed-script token
# such as "SHO-യോട്" or "ABC/യോട്" is encountered (having no whitespace), ReportLab's
# built-in `shapeFragWord` (reportlab.pdfbase.ttfonts) sends the entire string
# into a single uharfbuzz.Buffer and calls `guess_segment_properties()`.
# Because the leading characters ('SHO-') are Latin, HarfBuzz tags the entire buffer
# as `script: Latn` and routes it through the Latin OpenType shaper.
# In the Latin shaper, Malayalam Indic layout rules (such as decomposing the two-part
# vowel sign U+0D4B 'ോ' into pre-base 'േ' and post-base 'ാ') are completely skipped.
# The unshaped vowel sign glyph 'oovowelsignmlym' is rendered with an advance width
# of 0, collapsing directly over the consonant 'യ' and creating severe character collision.
#
# What this corrects:
# It segments mixed-script tokens into coherent Unicode script runs ('SHO-' as Latn,
# 'യോട്' as Mlym). Neutral punctuation binds to the active script context.
# Latin segments render using standard Courier fonts, while Malayalam segments
# shape through HarfBuzz with native Noto Sans Malayalam.
#
# Why this is limited and safe:
# Tokens that contain only one script (e.g. pure Malayalam, pure English,
# numbers, or space-separated words) delegate directly with zero modification.
# If any unexpected exception occurs, it safely falls back to ReportLab's original shaper.
# =============================================================================

def _get_char_script(ch):
    cp = ord(ch)
    if 0x0D00 <= cp <= 0x0D7F:
        return 'Mlym'
    if (0x0041 <= cp <= 0x005A) or (0x0061 <= cp <= 0x007A) or (0x00C0 <= cp <= 0x024F):
        return 'Latn'
    return 'Common'


def _segment_text_into_script_runs(text):
    if not text:
        return []
    tagged = [(ch, _get_char_script(ch)) for ch in text]
    non_common_scripts = {s for _, s in tagged if s != 'Common'}
    if len(non_common_scripts) <= 1:
        script = non_common_scripts.pop() if non_common_scripts else 'Latn'
        return [(text, script)]

    first_explicit = next((s for _, s in tagged if s != 'Common'), 'Latn')
    current_script = first_explicit
    resolved = []
    for ch, sc in tagged:
        if sc == 'Common':
            resolved.append((ch, current_script))
        else:
            current_script = sc
            resolved.append((ch, sc))

    runs = []
    for ch, sc in resolved:
        if runs and runs[-1][1] == sc:
            runs[-1] = (runs[-1][0] + ch, sc)
        else:
            runs.append((ch, sc))

    return runs


def _get_font_for_script(script, is_bold=False, is_italic=False):
    """Resolves the appropriate font variant for a given script and style variant."""
    if script == 'Latn':
        if is_bold and is_italic:
            return _COURIER_FONT_BOLDOBLIQUE
        elif is_bold:
            return _COURIER_FONT_BOLD
        elif is_italic:
            return _COURIER_FONT_OBLIQUE
        else:
            return _COURIER_FONT_REGULAR
    else:
        # Malayalam ('Mlym') or other scripts fallback to Noto Sans Malayalam
        if is_bold:
            return _MALAYALAM_FONT_BOLD
        else:
            return _MALAYALAM_FONT_NAME


def format_screenplay_text(text, is_bold=False, is_italic=False):
    """
    Formats text for ReportLab Paragraphs by segmenting it into script runs
    and tagging Latin/English with Courier variants and Malayalam with Noto Sans Malayalam.
    Safely escapes XML entities (&, <, >) and preserves line breaks (<br/>).
    """
    if not text:
        return ""
    normalized = text.replace('\r\n', '\n').replace('<br/>', '\n').replace('<br>', '\n')
    normalized = html.unescape(normalized)

    lines = normalized.split('\n')
    formatted_lines = []
    for line in lines:
        if not line:
            formatted_lines.append("")
            continue
        runs = _segment_text_into_script_runs(line)
        line_parts = []
        for run_text, script in runs:
            escaped = run_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            font_name = _get_font_for_script(script, is_bold=is_bold, is_italic=is_italic)
            line_parts.append(f'<font name="{font_name}">{escaped}</font>')
        formatted_lines.append(''.join(line_parts))
    return '<br/>'.join(formatted_lines)


def _shape_single_ttfont_run(f, text, script, features):
    """Shapes a single text run with a TTFont using HarfBuzz."""
    ttf = pdfmetrics.getFont(f.fontName)
    hbf = ttf.hbFont(f.fontSize)
    ttfs = f.fontSize / 1000

    buf = uharfbuzz.Buffer()
    buf.cluster_level = uharfbuzz.BufferClusterLevel.MONOTONE_CHARACTERS
    buf.add_str(text)
    buf.script = script
    buf.direction = 'ltr'
    uharfbuzz.shape(hbf, buf, features)

    items = []
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        items.append((info.codepoint, info.cluster, pos))

    shapeData = []
    ns = ''
    total_w = 0
    for gid, cluster, pos in items:
        name = hbf.glyph_to_string(gid)
        x_advance = pos.x_advance
        x_offset = pos.x_offset
        y_advance = pos.y_advance
        y_offset = pos.y_offset
        try:
            uchar = ttf.face.glyphToChar[gid][0]
        except KeyError:
            uchar = ttf.hbAddPrivate(name, gid, x_advance)
        ucharWidth = ttf.face.charWidths[uchar]
        uchar = chr(uchar)
        ns += uchar
        x_advance = ttf.pdfScale(x_advance)
        x_offset = ttf.pdfScale(x_offset)
        y_advance = ttf.pdfScale(y_advance)
        y_offset = ttf.pdfScale(y_offset)
        if x_advance:
            total_w += x_advance * ttfs
        shapeData.append(ShapeData(cluster, x_advance, y_advance, x_offset, y_offset, ucharWidth))

    return total_w, (f, ShapedStr(ns, shapeData=shapeData))


def _kadhascript_shapeFragWord(w, features=dict(kern=True, liga=True, dlig=True), force=False):
    global _ORIG_SHAPE_FRAG_WORD
    if isinstance(w, ShapedFragWord) or len(w) <= 1:
        return w

    # Inspect all fragments
    fonts = []
    has_tt = False
    has_type1 = False
    for f, s in w[1:]:
        if hasattr(f, 'cbDefn'):
            continue
        font = pdfmetrics.getFont(f.fontName)
        if hasattr(font, 'hbFont'):
            has_tt = True
        else:
            has_type1 = True
        fonts.append((f, s, font))

    # If no fragments or all are non-TT (e.g. pure Courier), delegate to standard shaper
    if not has_tt:
        return _ORIG_SHAPE_FRAG_WORD(w, features=features, force=force)

    # If all fragments are TTFont and share the same font:
    # If the combined text has <= 1 script run, delegate to _ORIG_SHAPE_FRAG_WORD
    if not has_type1 and len(set(f.fontName for f, _, _ in fonts)) == 1:
        combined_text = ''.join(s for _, s, _ in fonts)
        runs = _segment_text_into_script_runs(combined_text)
        if len(runs) <= 1:
            return _ORIG_SHAPE_FRAG_WORD(w, features=features, force=force)

    # Mixed-font or mixed-script TTFont token
    try:
        new = makeShapedFragWord(w)([])
        total_w = 0
        for f, s, font in fonts:
            if not s:
                continue
            if not hasattr(font, 'hbFont'):
                # Non-TTFont (Type 1 font, e.g. Courier)
                w_sub = pdfmetrics.stringWidth(s, f.fontName, f.fontSize)
                total_w += w_sub
                new.append((f, s))
            else:
                # TTFont (e.g. MalayalamFont)
                runs = _segment_text_into_script_runs(s)
                if len(runs) <= 1:
                    # Single script in this fragment: standard shape
                    sub_w = _ORIG_SHAPE_FRAG_WORD([0, (f, s)], features=features, force=force)
                    if isinstance(sub_w, (list, tuple)):
                        total_w += sub_w[0]
                        new.extend(sub_w[1:])
                    else:
                        total_w += pdfmetrics.stringWidth(s, f.fontName, f.fontSize)
                        new.append((f, s))
                else:
                    # Mixed script within this TTFont fragment
                    for run_text, run_script in runs:
                        run_w, run_item = _shape_single_ttfont_run(f, run_text, run_script, features)
                        total_w += run_w
                        new.append(run_item)

        new.insert(0, total_w)
        return new
    except Exception:
        return _ORIG_SHAPE_FRAG_WORD(w, features=features, force=force)


def enable_mixed_script_shaping():
    """Installs KadhaScript's script-aware mixed-script shaper into ReportLab."""
    global _MIXED_SCRIPT_SHAPING_ENABLED, _ORIG_SHAPE_FRAG_WORD
    if _MIXED_SCRIPT_SHAPING_ENABLED:
        return

    import reportlab.pdfbase.ttfonts as rlb_ttfonts
    import reportlab.platypus.paragraph as rlb_paragraph

    _ORIG_SHAPE_FRAG_WORD = rlb_ttfonts.shapeFragWord
    rlb_ttfonts.shapeFragWord = _kadhascript_shapeFragWord
    rlb_paragraph.shapeFragWord = _kadhascript_shapeFragWord

    try:
        import reportlab.platypus.tables as rlb_tables
        if hasattr(rlb_tables, 'shapeFragWord'):
            rlb_tables.shapeFragWord = _kadhascript_shapeFragWord
    except (ImportError, AttributeError):
        pass

    _MIXED_SCRIPT_SHAPING_ENABLED = True


def register_malayalam_fonts():
    global _FONT_REGISTERED, _MALAYALAM_FONT_NAME, _MALAYALAM_FONT_BOLD
    if _FONT_REGISTERED:
        return _MALAYALAM_FONT_NAME, _MALAYALAM_FONT_BOLD

    # Ensure script-aware mixed-script shaping is active
    enable_mixed_script_shaping()

    fonts_dir = Path(settings.BASE_DIR) / 'static' / 'fonts'
    noto_regular = fonts_dir / 'NotoSansMalayalam-Regular.ttf'
    noto_bold = fonts_dir / 'NotoSansMalayalam-Bold.ttf'
    manjari_regular = fonts_dir / 'Manjari-Regular.ttf'

    # Primary: Project-bundled Malayalam fonts (Production & Cross-Platform)
    if noto_regular.exists():
        try:
            pdfmetrics.registerFont(TTFont('MalayalamFont', str(noto_regular), shapable=True))
            if noto_bold.exists():
                pdfmetrics.registerFont(TTFont('MalayalamFont-Bold', str(noto_bold), shapable=True))
            else:
                pdfmetrics.registerFont(TTFont('MalayalamFont-Bold', str(noto_regular), shapable=True))
            _MALAYALAM_FONT_NAME = 'MalayalamFont'
            _MALAYALAM_FONT_BOLD = 'MalayalamFont-Bold'
            _FONT_REGISTERED = True
            return _MALAYALAM_FONT_NAME, _MALAYALAM_FONT_BOLD
        except Exception as e:
            pass

    if manjari_regular.exists():
        try:
            pdfmetrics.registerFont(TTFont('MalayalamFont', str(manjari_regular), shapable=True))
            pdfmetrics.registerFont(TTFont('MalayalamFont-Bold', str(manjari_regular), shapable=True))
            _MALAYALAM_FONT_NAME = 'MalayalamFont'
            _MALAYALAM_FONT_BOLD = 'MalayalamFont-Bold'
            _FONT_REGISTERED = True
            return _MALAYALAM_FONT_NAME, _MALAYALAM_FONT_BOLD
        except Exception as e:
            pass

    # Secondary: Windows system fonts (Development fallback)
    candidate_windows_fonts = [
        ('C:/Windows/Fonts/Nirmala.ttc', 0, 'C:/Windows/Fonts/NirmalaB.ttc', 0),
        ('C:/Windows/Fonts/Kartika.ttf', None, 'C:/Windows/Fonts/Kartikab.ttf', None),
    ]

    for reg_path, reg_sub, bold_path, bold_sub in candidate_windows_fonts:
        if os.path.exists(reg_path):
            try:
                if reg_sub is not None:
                    pdfmetrics.registerFont(TTFont('MalayalamFont', reg_path, subfontIndex=reg_sub, shapable=True))
                else:
                    pdfmetrics.registerFont(TTFont('MalayalamFont', reg_path, shapable=True))

                if bold_path and os.path.exists(bold_path):
                    if bold_sub is not None:
                        pdfmetrics.registerFont(TTFont('MalayalamFont-Bold', bold_path, subfontIndex=bold_sub, shapable=True))
                    else:
                        pdfmetrics.registerFont(TTFont('MalayalamFont-Bold', bold_path, shapable=True))
                else:
                    if reg_sub is not None:
                        pdfmetrics.registerFont(TTFont('MalayalamFont-Bold', reg_path, subfontIndex=reg_sub, shapable=True))
                    else:
                        pdfmetrics.registerFont(TTFont('MalayalamFont-Bold', reg_path, shapable=True))

                _MALAYALAM_FONT_NAME = 'MalayalamFont'
                _MALAYALAM_FONT_BOLD = 'MalayalamFont-Bold'
                _FONT_REGISTERED = True
                return _MALAYALAM_FONT_NAME, _MALAYALAM_FONT_BOLD
            except Exception as e:
                continue

    if not _FONT_REGISTERED:
        raise RuntimeError(
            "No Malayalam Unicode font could be loaded for PDF export. "
            "Please ensure 'NotoSansMalayalam-Regular.ttf' is placed in 'static/fonts/'."
        )

    return _MALAYALAM_FONT_NAME, _MALAYALAM_FONT_BOLD


class NumberedCanvas(canvas.Canvas):
    """Adds screenplay standard running header and page numbers (Top right, e.g. '2.')"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            if self._pageNumber > 1:
                # Top header for screenplay: Page number on the upper right margin
                self.setFont(_COURIER_FONT_REGULAR, 10)
                self.drawRightString(8.5 * inch - 1.0 * inch, 11 * inch - 0.5 * inch, f"{self._pageNumber}.")
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)


def get_screenplay_pdf_styles(font_regular=None, font_bold=None):
    """Returns the dictionary of paragraph styles configured for screenplay PDF export."""
    if font_regular is None or font_bold is None:
        reg, bold = register_malayalam_fonts()
        font_regular = font_regular or reg
        font_bold = font_bold or bold

    styles = getSampleStyleSheet()

    return {
        'TitleStyle': ParagraphStyle(
            'TitleStyle',
            parent=styles['Normal'],
            fontName=font_bold,
            fontSize=24,
            leading=30,
            alignment=TA_CENTER,
            spaceAfter=12,
            shaping=True,
        ),
        'SubtitleStyle': ParagraphStyle(
            'SubtitleStyle',
            parent=styles['Normal'],
            fontName=font_regular,
            fontSize=12,
            leading=16,
            alignment=TA_CENTER,
            textColor='#444444',
            spaceAfter=12,
            shaping=True,
        ),
        'ByStyle': ParagraphStyle(
            'ByStyle',
            parent=styles['Normal'],
            fontName=font_regular,
            fontSize=11,
            leading=15,
            alignment=TA_CENTER,
            spaceAfter=6,
            shaping=True,
        ),
        'AuthorStyle': ParagraphStyle(
            'AuthorStyle',
            parent=styles['Normal'],
            fontName=font_bold,
            fontSize=14,
            leading=18,
            alignment=TA_CENTER,
            spaceAfter=14,
            shaping=True,
        ),
        'CreditsStyle': ParagraphStyle(
            'CreditsStyle',
            parent=styles['Normal'],
            fontName=font_regular,
            fontSize=10,
            leading=14,
            alignment=TA_CENTER,
            textColor='#333333',
            spaceAfter=18,
            shaping=True,
        ),
        'MetaStyle': ParagraphStyle(
            'MetaStyle',
            parent=styles['Normal'],
            fontName=font_regular,
            fontSize=10,
            leading=14,
            alignment=TA_CENTER,
            textColor='#555555',
            shaping=True,
        ),
        'MetaLeftStyle': ParagraphStyle(
            'MetaLeftStyle',
            parent=styles['Normal'],
            fontName=font_regular,
            fontSize=9.5,
            leading=13.5,
            alignment=TA_LEFT,
            textColor='#222222',
            shaping=True,
        ),
        'MetaRightStyle': ParagraphStyle(
            'MetaRightStyle',
            parent=styles['Normal'],
            fontName=font_regular,
            fontSize=9.5,
            leading=13.5,
            alignment=TA_RIGHT,
            textColor='#222222',
            shaping=True,
        ),
        'SceneHeading': ParagraphStyle(
            'SceneHeading',
            parent=styles['Normal'],
            fontName=font_bold,
            fontSize=13,
            leading=17.5,
            spaceBefore=16,
            spaceAfter=8,
            keepWithNext=True,
            shaping=True,
            backColor=colors.HexColor('#ECECEC'),
            borderPadding=(3, 5, 3, 5),
        ),
        'Action': ParagraphStyle(
            'Action',
            parent=styles['Normal'],
            fontName=font_regular,
            fontSize=13,
            leading=17.5,
            leftIndent=0,
            rightIndent=0,
            firstLineIndent=0,
            spaceBefore=6,
            spaceAfter=8,
            alignment=TA_LEFT,
            shaping=True,
        ),
        'Character': ParagraphStyle(
            'Character',
            parent=styles['Normal'],
            fontName=font_bold,
            fontSize=13,
            leading=16,
            leftIndent=2.0 * inch,
            spaceBefore=12,
            spaceAfter=2,
            keepWithNext=True,
            shaping=True,
        ),
        'Dialogue': ParagraphStyle(
            'Dialogue',
            parent=styles['Normal'],
            fontName=font_regular,
            fontSize=13,
            leading=17.5,
            leftIndent=1.0 * inch,
            rightIndent=1.0 * inch,
            spaceBefore=0,
            spaceAfter=8,
            shaping=True,
        ),
        'Parenthetical': ParagraphStyle(
            'Parenthetical',
            parent=styles['Normal'],
            fontName=font_regular,
            fontSize=11,
            leading=14,
            leftIndent=1.5 * inch,
            rightIndent=1.5 * inch,
            spaceBefore=0,
            spaceAfter=2,
            keepWithNext=True,
            shaping=True,
        ),
        'Transition': ParagraphStyle(
            'Transition',
            parent=styles['Normal'],
            fontName=font_bold,
            fontSize=13,
            leading=16,
            alignment=TA_RIGHT,
            spaceBefore=14,
            spaceAfter=14,
            shaping=True,
        ),
        'Shot': ParagraphStyle(
            'Shot',
            parent=styles['Normal'],
            fontName=font_bold,
            fontSize=13,
            leading=16,
            spaceBefore=10,
            spaceAfter=6,
            shaping=True,
        ),
        'Note': ParagraphStyle(
            'Note',
            parent=styles['Normal'],
            fontName=font_regular,
            fontSize=9.5,
            leading=13,
            textColor='#777777',
            leftIndent=0.5 * inch,
            spaceBefore=4,
            spaceAfter=6,
            shaping=True,
        ),
        'SequenceHeading': ParagraphStyle(
            'SequenceHeading',
            parent=styles['Normal'],
            fontName=font_bold,
            fontSize=13,
            leading=17.5,
            alignment=TA_CENTER,
            spaceBefore=16,
            spaceAfter=8,
            keepWithNext=True,
            shaping=True,
            backColor=colors.HexColor('#ECECEC'),
            borderPadding=(3, 5, 3, 5),
        ),
        'SequenceBeginLabel': ParagraphStyle(
            'SequenceBeginLabel',
            parent=styles['Normal'],
            fontName=font_bold,
            fontSize=13,
            leading=17.5,
            alignment=TA_LEFT,
            spaceBefore=8,
            spaceAfter=14,
            keepWithNext=True,
            shaping=True,
        ),
        'SequenceEndLabel': ParagraphStyle(
            'SequenceEndLabel',
            parent=styles['Normal'],
            fontName=font_bold,
            fontSize=13,
            leading=17.5,
            alignment=TA_LEFT,
            spaceBefore=20,
            spaceAfter=12,
            shaping=True,
        ),
    }


def generate_screenplay_pdf(script, include_notes=False) -> bytes:
    """Generates standard screenplay formatted PDF for Malayalam scripts with Unicode shaping."""
    font_regular, font_bold = register_malayalam_fonts()
    buffer = io.BytesIO()

    # Standard Screenplay margins: Left 1.5 in, Right 1.0 in, Top 1.0 in, Bottom 1.0 in
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=1.5 * inch,
        rightMargin=1.0 * inch,
        topMargin=1.0 * inch,
        bottomMargin=1.0 * inch,
    )

    pdf_styles = get_screenplay_pdf_styles(font_regular, font_bold)
    title_style = pdf_styles['TitleStyle']
    subtitle_style = pdf_styles['SubtitleStyle']
    by_style = pdf_styles['ByStyle']
    author_style = pdf_styles['AuthorStyle']
    credits_style = pdf_styles['CreditsStyle']
    meta_style = pdf_styles['MetaStyle']
    meta_left_style = pdf_styles['MetaLeftStyle']
    meta_right_style = pdf_styles['MetaRightStyle']
    scene_heading_style = pdf_styles['SceneHeading']
    sequence_heading_style = pdf_styles['SequenceHeading']
    sequence_begin_style = pdf_styles['SequenceBeginLabel']
    sequence_end_style = pdf_styles['SequenceEndLabel']
    action_style = pdf_styles['Action']
    character_style = pdf_styles['Character']
    dialogue_style = pdf_styles['Dialogue']
    parenthetical_style = pdf_styles['Parenthetical']
    transition_style = pdf_styles['Transition']
    shot_style = pdf_styles['Shot']
    note_style = pdf_styles['Note']

    story = []

    # Title Page / Cover Section
    title_page = getattr(script, 'title_page', None)
    effective_title = title_page.get_effective_title() if title_page else script.title
    effective_author = title_page.get_effective_author() if title_page else (
        script.author_name or (script.user.profile.pen_name if hasattr(script.user, 'profile') else (script.user.get_full_name() or script.user.username))
    )

    story.append(Spacer(1, 2.0 * inch))
    story.append(Paragraph(format_screenplay_text(effective_title.strip().upper(), is_bold=True), title_style))

    story.append(Spacer(1, 0.25 * inch))
    story.append(Paragraph(format_screenplay_text(effective_author.strip(), is_bold=True), author_style))

    story.append(PageBreak())

    # Screenplay Scenes and Elements
    scenes = script.get_ordered_scenes()

    for idx, scene in enumerate(scenes):
        if idx > 0:
            story.append(PageBreak())

        if scene.is_sequence:
            seq_type = getattr(scene, 'sequence_type', None)
            if not seq_type:
                h = (scene.heading or '').upper()
                seq_type = 'montage' if 'MONTAGE' in h else 'song'

            if seq_type == 'montage':
                seq_heading_text = "Montage Sequence"
                seq_begin_text = "Montage Begins:"
                seq_end_text = "Montage Ends"
            else:
                seq_heading_text = "Song Sequence"
                seq_begin_text = "Song Begins:"
                seq_end_text = "Song Ends"

            story.append(Paragraph(format_screenplay_text(seq_heading_text, is_bold=True), sequence_heading_style))
            story.append(Paragraph(format_screenplay_text(seq_begin_text, is_bold=True), sequence_begin_style))
        else:
            heading_text = f"{scene.scene_identifier} : {scene.clean_heading.upper()}"
            story.append(Paragraph(format_screenplay_text(heading_text, is_bold=True), scene_heading_style))

        elements = scene.elements.all().order_by('order', 'id')
        rendered_seq_end = False

        for elem in elements:
            text = (elem.content or '').strip()
            if not text:
                continue

            if elem.element_type == 'scene_heading':
                # Skip duplicate primary scene heading already rendered at the scene header
                clean_heading_upper = scene.clean_heading.strip().upper()
                raw_heading_upper = (scene.heading or '').strip().upper()
                elem_text_upper = text.strip().upper()
                if elem.order == 0 and (
                    elem_text_upper == clean_heading_upper
                    or elem_text_upper == raw_heading_upper
                ):
                    continue
                story.append(Paragraph(format_screenplay_text(text.upper(), is_bold=True), scene_heading_style))
            elif elem.element_type == 'action':
                raw_paras = [p.strip() for p in text.split('\n\n') if p.strip()]
                if not raw_paras:
                    raw_paras = [text]
                for p_text in raw_paras:
                    story.append(Paragraph(format_screenplay_text(p_text, is_bold=False), action_style))
            elif elem.element_type == 'character':
                story.append(Paragraph(format_screenplay_text(text.upper(), is_bold=True), character_style))
            elif elem.element_type == 'dialogue':
                story.append(Paragraph(format_screenplay_text(text, is_bold=False), dialogue_style))
            elif elem.element_type == 'parenthetical':
                clean_paren = text
                if not (clean_paren.startswith('(') and clean_paren.endswith(')')):
                    clean_paren = f"({clean_paren})"
                story.append(Paragraph(format_screenplay_text(clean_paren, is_bold=False), parenthetical_style))
            elif elem.element_type == 'transition':
                story.append(Paragraph(format_screenplay_text(text.upper(), is_bold=True), transition_style))
            elif elem.element_type == 'shot':
                uc_text = text.upper()
                if scene.is_sequence:
                    if uc_text in ('SONG BEGINS', 'MONTAGE BEGINS', 'SONG BEGINS:', 'MONTAGE BEGINS:'):
                        continue
                    if uc_text in ('SONG ENDS', 'MONTAGE ENDS'):
                        story.append(Paragraph(format_screenplay_text(seq_end_text, is_bold=True), sequence_end_style))
                        rendered_seq_end = True
                        continue

                story.append(Paragraph(format_screenplay_text(text.upper(), is_bold=True), shot_style))
            elif elem.element_type == 'note' and include_notes:
                raw_paras = [p.strip() for p in text.split('\n\n') if p.strip()]
                if not raw_paras:
                    raw_paras = [text]
                for p_text in raw_paras:
                    p_clean = p_text if (p_text.startswith('[[') and p_text.endswith(']]')) else f"[[ {p_text} ]]"
                    story.append(Paragraph(format_screenplay_text(p_clean, is_bold=False), note_style))

        # For sequence scenes, ensure ending label is present if not already rendered
        if scene.is_sequence and not rendered_seq_end:
            story.append(Paragraph(format_screenplay_text(seq_end_text, is_bold=True), sequence_end_style))

        # Scene-end transition fallback:
        # If the scene does not already end with an explicit transition element, render scene.transition fallback.
        if not scene.is_sequence and not scene.has_scene_ending_transition(elements):
            scene_trans = (scene.transition or 'CUT TO').strip()
            if scene_trans:
                story.append(Paragraph(format_screenplay_text(scene_trans.upper(), is_bold=True), transition_style))

    # Build PDF with standard screenplay page numbers
    doc.build(story, canvasmaker=NumberedCanvas)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

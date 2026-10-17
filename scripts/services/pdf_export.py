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

# Font registration helper
_FONT_REGISTERED = False
_MALAYALAM_FONT_NAME = 'MalayalamFont'
_MALAYALAM_FONT_BOLD = 'MalayalamFont-Bold'


def register_malayalam_fonts():
    global _FONT_REGISTERED, _MALAYALAM_FONT_NAME, _MALAYALAM_FONT_BOLD
    if _FONT_REGISTERED:
        return _MALAYALAM_FONT_NAME, _MALAYALAM_FONT_BOLD

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
                self.setFont(_MALAYALAM_FONT_NAME, 10)
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
            fontSize=12,
            leading=16,
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
            fontSize=12,
            leading=16,
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
            fontSize=12,
            leading=15,
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
            fontSize=12,
            leading=16,
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
            fontSize=10.5,
            leading=13,
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
            fontSize=12,
            leading=15,
            alignment=TA_RIGHT,
            spaceBefore=14,
            spaceAfter=14,
            shaping=True,
        ),
        'Shot': ParagraphStyle(
            'Shot',
            parent=styles['Normal'],
            fontName=font_bold,
            fontSize=12,
            leading=15,
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
            fontSize=12,
            leading=16,
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
            fontSize=12,
            leading=16,
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
            fontSize=12,
            leading=16,
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
    clean_title = effective_title.strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br/>')
    story.append(Paragraph(clean_title.upper(), title_style))

    if title_page and title_page.subtitle:
        subtitle_clean = title_page.subtitle.strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br/>')
        story.append(Paragraph(subtitle_clean, subtitle_style))
        story.append(Spacer(1, 0.1 * inch))

    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph("എഴുതിയത് / Written by", by_style))
    clean_author = effective_author.strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    story.append(Paragraph(clean_author, author_style))

    if title_page and title_page.adaptation_credits:
        credits_clean = title_page.adaptation_credits.strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br/>')
        story.append(Paragraph(credits_clean, credits_style))

    has_bottom_metadata = title_page and (
        title_page.draft_revision or title_page.draft_date or
        title_page.copyright_registration or
        title_page.contact_name or title_page.contact_email or title_page.contact_phone
    )

    story.append(Spacer(1, 1.8 * inch))

    if has_bottom_metadata:
        left_lines = []
        if title_page.draft_revision:
            dr_clean = title_page.draft_revision.strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            left_lines.append(f"<b>{dr_clean}</b>")
        if title_page.draft_date:
            dd_clean = title_page.draft_date.strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            left_lines.append(dd_clean)
        if title_page.copyright_registration:
            if left_lines:
                left_lines.append("")
            cr_clean = title_page.copyright_registration.strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br/>')
            left_lines.append(f"<font color='#555555'>{cr_clean}</font>")

        right_lines = []
        if title_page.contact_name:
            cn_clean = title_page.contact_name.strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            right_lines.append(f"<b>{cn_clean}</b>")
        if title_page.contact_email:
            ce_clean = title_page.contact_email.strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            right_lines.append(ce_clean)
        if title_page.contact_phone:
            cp_clean = title_page.contact_phone.strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            right_lines.append(cp_clean)

        left_para = Paragraph("<br/>".join(left_lines), meta_left_style) if left_lines else Paragraph("", meta_left_style)
        right_para = Paragraph("<br/>".join(right_lines), meta_right_style) if right_lines else Paragraph("", meta_right_style)

        table_data = [[left_para, right_para]]
        footer_table = Table(table_data, colWidths=[3.0 * inch, 3.0 * inch])
        footer_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(footer_table)
    else:
        meta_text = f"Genre: {script.genre} &nbsp;|&nbsp; Format: {script.script_type} &nbsp;|&nbsp; Language: {script.language}"
        story.append(Paragraph(meta_text, meta_style))
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph("KadhaScript Screenplay Management Platform", meta_style))

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

            story.append(Paragraph(seq_heading_text, sequence_heading_style))
            story.append(Paragraph(seq_begin_text, sequence_begin_style))
        else:
            heading_text = f"{scene.scene_identifier} : {scene.clean_heading.upper()}"
            story.append(Paragraph(heading_text, scene_heading_style))

        elements = scene.elements.all().order_by('order', 'id')
        rendered_seq_end = False

        for elem in elements:
            text = (elem.content or '').strip()
            if not text:
                continue

            # XML escape safeguard
            clean_text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br/>')

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
                story.append(Paragraph(clean_text.upper(), scene_heading_style))
            elif elem.element_type == 'action':
                raw_paras = [p.strip() for p in text.split('\n\n') if p.strip()]
                if not raw_paras:
                    raw_paras = [text]
                for p_text in raw_paras:
                    clean_para = p_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br/>')
                    story.append(Paragraph(clean_para, action_style))
            elif elem.element_type == 'character':
                story.append(Paragraph(clean_text.upper(), character_style))
            elif elem.element_type == 'dialogue':
                story.append(Paragraph(clean_text, dialogue_style))
            elif elem.element_type == 'parenthetical':
                if not (clean_text.startswith('(') and clean_text.endswith(')')):
                    clean_text = f"({clean_text})"
                story.append(Paragraph(clean_text, parenthetical_style))
            elif elem.element_type == 'transition':
                story.append(Paragraph(clean_text.upper(), transition_style))
            elif elem.element_type == 'shot':
                uc_text = clean_text.upper()
                if scene.is_sequence:
                    if uc_text in ('SONG BEGINS', 'MONTAGE BEGINS', 'SONG BEGINS:', 'MONTAGE BEGINS:'):
                        continue
                    if uc_text in ('SONG ENDS', 'MONTAGE ENDS'):
                        story.append(Paragraph(seq_end_text, sequence_end_style))
                        rendered_seq_end = True
                        continue

                story.append(Paragraph(clean_text.upper(), shot_style))

        # For sequence scenes, ensure ending label is present if not already rendered
        if scene.is_sequence and not rendered_seq_end:
            story.append(Paragraph(seq_end_text, sequence_end_style))

        # Scene-end transition fallback:
        # If the scene does not already end with an explicit transition element, render scene.transition fallback.
        if not scene.is_sequence and not scene.has_scene_ending_transition(elements):
            scene_trans = (scene.transition or 'CUT TO').strip()
            if scene_trans:
                clean_trans = scene_trans.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br/>')
                story.append(Paragraph(clean_trans.upper(), transition_style))

    # Build PDF with standard screenplay page numbers
    doc.build(story, canvasmaker=NumberedCanvas)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

def generate_screenplay_txt(script, include_notes=False) -> str:
    """Generates plain text formatted screenplay with standard character and dialogue indentation."""
    title_page = getattr(script, 'title_page', None)
    effective_title = title_page.get_effective_title() if title_page else script.title
    effective_author = title_page.get_effective_author() if title_page else (
        script.author_name or (script.user.profile.pen_name if hasattr(script.user, 'profile') else (script.user.get_full_name() or script.user.username))
    )

    lines = []
    lines.append("=" * 60)
    lines.append(effective_title.upper().center(60))
    if title_page and title_page.subtitle:
        lines.append(title_page.subtitle.center(60))
    lines.append("-" * 60)
    lines.append(f"Written by: {effective_author}".center(60))
    if title_page and title_page.adaptation_credits:
        lines.append(title_page.adaptation_credits.center(60))
    
    if title_page and (title_page.draft_revision or title_page.draft_date):
        draft_str = f"Draft: {title_page.draft_revision} {('(' + title_page.draft_date + ')') if title_page.draft_date else ''}".strip()
        lines.append(draft_str.center(60))
    if title_page and title_page.copyright_registration:
        lines.append(title_page.copyright_registration.center(60))
    if title_page and (title_page.contact_name or title_page.contact_email or title_page.contact_phone):
        c_info = " | ".join(filter(None, [title_page.contact_name, title_page.contact_email, title_page.contact_phone]))
        lines.append(f"Contact: {c_info}".center(60))

    lines.append(f"Format: {script.script_type} | Genre: {script.genre} | Language: {script.language}".center(60))
    lines.append("=" * 60)
    lines.append("")
    lines.append("")

    scenes = script.get_ordered_scenes()

    for scene in scenes:
        lines.append(f"{scene.scene_identifier} : {scene.clean_heading.upper()}")
        lines.append("")

        elements = scene.elements.all().order_by('order')
        for elem in elements:
            text = (elem.content or '').strip()
            if not text:
                continue

            if elem.element_type == 'scene_heading':
                clean_heading_upper = scene.clean_heading.strip().upper()
                raw_heading_upper = (scene.heading or '').strip().upper()
                elem_text_upper = text.strip().upper()
                if elem.order == 0 and (
                    elem_text_upper == clean_heading_upper
                    or elem_text_upper == raw_heading_upper
                ):
                    continue
                lines.append(text.upper())
                lines.append("")
            elif elem.element_type == 'action':
                for para in text.split('\n\n'):
                    if para.strip():
                        lines.append(para.strip())
                        lines.append("")
            elif elem.element_type == 'character':
                lines.append(f"{' ' * 22}{text.upper()}")
            elif elem.element_type == 'parenthetical':
                clean_text = text if (text.startswith('(') and text.endswith(')')) else f"({text})"
                lines.append(f"{' ' * 16}{clean_text}")
            elif elem.element_type == 'dialogue':
                for d_line in text.splitlines():
                    if d_line.strip():
                        lines.append(f"{' ' * 10}{d_line.strip()}")
                lines.append("")
            elif elem.element_type == 'transition':
                lines.append(f"{' ' * 45}{text.upper()}")
                lines.append("")
            elif elem.element_type == 'shot':
                lines.append(text.upper())
                lines.append("")
            elif elem.element_type == 'note' and include_notes:
                lines.append(f"   /* NOTE: {text} */")
                lines.append("")

        # Scene-end transition
        scene_trans = (scene.transition or 'CUT TO').strip()
        if scene_trans:
            lines.append(f"{' ' * 45}{scene_trans.upper()}")
            lines.append("")

    result = "\n".join(lines).strip()
    return result + "\n"


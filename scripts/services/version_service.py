from django.db import transaction
from scripts.models import Script, Scene, ScriptElement, ScriptVersion
from scripts.services.scene_service import resequence_script_scenes

def create_version_snapshot(script: Script, title: str = 'Draft Snapshot', description: str = '') -> ScriptVersion:
    """Takes a full snapshot of the script's scenes, elements, sub-scenes, and characters."""
    scenes_data = []
    
    # We serialize main scenes with their sub-scenes nested
    main_scenes = script.scenes.filter(parent_scene__isnull=True).order_by('order', 'id')
    
    for main_idx, scene in enumerate(main_scenes):
        elements_data = []
        for elem in scene.elements.all().order_by('order'):
            elements_data.append({
                'element_type': elem.element_type,
                'content': elem.content,
                'order': elem.order,
            })
        
        sub_scenes_data = []
        for sub_idx, sub in enumerate(scene.sub_scenes.all().order_by('order', 'id')):
            sub_elements_data = []
            for sub_elem in sub.elements.all().order_by('order'):
                sub_elements_data.append({
                    'element_type': sub_elem.element_type,
                    'content': sub_elem.content,
                    'order': sub_elem.order,
                })
            sub_scenes_data.append({
                'scene_number': sub.scene_number,
                'is_duplicate': sub.is_duplicate,
                'duplicate_number': sub.duplicate_number,
                'heading': sub.heading,
                'transition': sub.transition or 'CUT TO',
                'summary': sub.summary,
                'order': sub.order,
                'elements': sub_elements_data,
            })

        scenes_data.append({
            'scene_number': scene.scene_number,
            'is_duplicate': scene.is_duplicate,
            'duplicate_number': scene.duplicate_number,
            'heading': scene.heading,
            'transition': scene.transition or 'CUT TO',
            'summary': scene.summary,
            'order': scene.order,
            'elements': elements_data,
            'sub_scenes': sub_scenes_data,
        })

    characters_data = []
    for ch in script.characters.all():
        characters_data.append({
            'name': ch.name,
            'age': ch.age,
            'gender': ch.gender,
            'description': ch.description,
            'notes': ch.notes,
        })

    title_page_data = None
    if hasattr(script, 'title_page') and script.title_page:
        tp = script.title_page
        title_page_data = {
            'title': tp.title,
            'subtitle': tp.subtitle,
            'author_name': tp.author_name,
            'pen_name': tp.pen_name,
            'adaptation_credits': tp.adaptation_credits,
            'copyright_registration': tp.copyright_registration,
            'draft_revision': tp.draft_revision,
            'draft_date': tp.draft_date,
            'contact_name': tp.contact_name,
            'contact_email': tp.contact_email,
            'contact_phone': tp.contact_phone,
        }

    snapshot = {
        'title': script.title,
        'genre': script.genre,
        'script_type': script.script_type,
        'author_name': script.author_name,
        'language': script.language,
        'scenes': scenes_data,
        'characters': characters_data,
        'title_page': title_page_data,
    }

    last_ver = script.versions.order_by('-version_number').first()
    ver_num = (last_ver.version_number + 1) if last_ver else 1

    version = ScriptVersion.objects.create(
        script=script,
        version_number=ver_num,
        title=title or f'Version {ver_num}',
        description=description,
        snapshot_data=snapshot
    )
    return version


def restore_version_snapshot(script: Script, version_id: int):
    """Restores the screenplay's scenes and elements to the state saved in the specified version."""
    version = script.versions.get(id=version_id)
    snapshot = version.snapshot_data

    with transaction.atomic():
        # First save an auto-snapshot of current state
        create_version_snapshot(script, title=f'Auto-backup before restoring v{version.version_number}')

        # Clear existing scenes (cascades to sub-scenes & elements)
        script.scenes.all().delete()

        # Recreate scenes & elements from snapshot
        for s_idx, s_data in enumerate(snapshot.get('scenes', [])):
            main_scene = Scene.objects.create(
                script=script,
                parent_scene=None,
                scene_number=s_data.get('scene_number', s_idx + 1),
                is_duplicate=s_data.get('is_duplicate', False),
                duplicate_number=s_data.get('duplicate_number', 0),
                heading=s_data.get('heading', 'INT. LOCATION - DAY'),
                transition=s_data.get('transition', 'CUT TO'),
                summary=s_data.get('summary', ''),
                order=s_data.get('order', s_idx)
            )
            for e_idx, e_data in enumerate(s_data.get('elements', [])):
                ScriptElement.objects.create(
                    scene=main_scene,
                    element_type=e_data.get('element_type', 'action'),
                    content=e_data.get('content', ''),
                    order=e_data.get('order', e_idx)
                )

            # Recreate sub-scenes if present
            for sub_idx, sub_data in enumerate(s_data.get('sub_scenes', [])):
                sub_scene = Scene.objects.create(
                    script=script,
                    parent_scene=main_scene,
                    scene_number=main_scene.scene_number,
                    is_duplicate=sub_data.get('is_duplicate', False),
                    duplicate_number=sub_data.get('duplicate_number', 0),
                    heading=sub_data.get('heading', 'INT. LOCATION - DAY'),
                    transition=sub_data.get('transition', 'CUT TO'),
                    summary=sub_data.get('summary', ''),
                    order=sub_data.get('order', sub_idx)
                )
                for se_idx, se_data in enumerate(sub_data.get('elements', [])):
                    ScriptElement.objects.create(
                        scene=sub_scene,
                        element_type=se_data.get('element_type', 'action'),
                        content=se_data.get('content', ''),
                        order=se_data.get('order', se_idx)
                    )

        if 'title_page' in snapshot and snapshot['title_page'] is not None:
            tp_data = snapshot['title_page']
            from scripts.models import ScriptTitlePage
            tp, _ = ScriptTitlePage.objects.get_or_create(script=script)
            tp.title = tp_data.get('title', '')
            tp.subtitle = tp_data.get('subtitle', '')
            tp.author_name = tp_data.get('author_name', '')
            tp.pen_name = tp_data.get('pen_name', '')
            tp.adaptation_credits = tp_data.get('adaptation_credits', '')
            tp.copyright_registration = tp_data.get('copyright_registration', '')
            tp.draft_revision = tp_data.get('draft_revision', '')
            tp.draft_date = tp_data.get('draft_date', '')
            tp.contact_name = tp_data.get('contact_name', '')
            tp.contact_email = tp_data.get('contact_email', '')
            tp.contact_phone = tp_data.get('contact_phone', '')
            tp.save()

        resequence_script_scenes(script)
        script.save()  # update updated_at
    return True


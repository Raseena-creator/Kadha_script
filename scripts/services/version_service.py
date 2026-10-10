import uuid
from django.db import transaction
from scripts.models import Script, Scene, ScriptElement, ScriptVersion, ScriptTitlePage
from scripts.services.scene_service import resequence_script_scenes

def create_version_snapshot(script: Script, title: str = 'Draft Snapshot', description: str = '') -> ScriptVersion:
    """
    Takes a full snapshot of the screenplay's active scenes, elements, sub-scenes, characters, and title page.
    Strictly excludes trashed main scenes and trashed sub-scenes.
    Preserves scene UUIDs, active ordering, hierarchy, and intercut metadata.
    """
    scenes_data = []

    # Serialize active main scenes (including active intercut main scenes)
    main_scenes = script.scenes.filter(parent_scene__isnull=True, is_deleted=False).order_by('order', 'id')

    for main_idx, scene in enumerate(main_scenes):
        elements_data = []
        for elem in scene.elements.all().order_by('order', 'id'):
            elements_data.append({
                'element_type': elem.element_type,
                'content': elem.content,
                'order': elem.order,
            })

        sub_scenes_data = []
        for sub_idx, sub in enumerate(scene.sub_scenes.filter(is_deleted=False).order_by('order', 'id')):
            sub_elements_data = []
            for sub_elem in sub.elements.all().order_by('order', 'id'):
                sub_elements_data.append({
                    'element_type': sub_elem.element_type,
                    'content': sub_elem.content,
                    'order': sub_elem.order,
                })

            sub_intercut_source_uuid = None
            if sub.is_intercut and sub.intercut_source and not sub.intercut_source.is_deleted:
                sub_intercut_source_uuid = str(sub.intercut_source.scene_uuid)

            sub_scenes_data.append({
                'scene_uuid': str(sub.scene_uuid),
                'scene_number': sub.scene_number,
                'is_duplicate': sub.is_duplicate,
                'duplicate_number': sub.duplicate_number,
                'is_intercut': sub.is_intercut,
                'intercut_source_uuid': sub_intercut_source_uuid,
                'parent_uuid': str(scene.scene_uuid),
                'heading': sub.heading,
                'transition': sub.transition or 'CUT TO',
                'summary': sub.summary,
                'order': sub.order,
                'elements': sub_elements_data,
            })

        main_intercut_source_uuid = None
        if scene.is_intercut and scene.intercut_source and not scene.intercut_source.is_deleted:
            main_intercut_source_uuid = str(scene.intercut_source.scene_uuid)

        scenes_data.append({
            'scene_uuid': str(scene.scene_uuid),
            'scene_number': scene.scene_number,
            'is_duplicate': scene.is_duplicate,
            'duplicate_number': scene.duplicate_number,
            'is_intercut': scene.is_intercut,
            'intercut_source_uuid': main_intercut_source_uuid,
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


def restore_version_snapshot(script: Script, version_id: int) -> bool:
    """
    Restores the screenplay's active scenes and elements to the state saved in the specified version.
    Crucially:
    - Preserves all trashed scenes (is_deleted=True) and their associated ScriptElements.
    - Disconnects foreign-key cascade paths on trashed sub-scenes to prevent SQL CASCADE deletion.
    - Reconciles UUIDs: if a snapshot UUID is already in use by a trashed scene or duplicate, assigns a fresh UUID.
    - Reconstructs intercut links safely without ambiguous guessing.
    - Supports legacy snapshots lacking UUIDs or intercut metadata.
    - Retains the automatic pre-restoration snapshot.
    """
    version = script.versions.get(id=version_id)
    snapshot = version.snapshot_data

    if not isinstance(snapshot, dict) or 'scenes' not in snapshot or not isinstance(snapshot.get('scenes'), list):
        raise ValueError(f"Corrupt or invalid snapshot data in version {version.version_number}.")

    # Pre-validate snapshot: detect duplicate raw UUIDs and intercut reference ambiguity
    seen_raw_uuids = set()
    duplicate_raw_uuids = set()
    intercut_target_uuids = set()

    for s in snapshot.get('scenes', []):
        if not isinstance(s, dict):
            raise ValueError(f"Invalid scene data in snapshot for version {version.version_number}.")
        raw_u = s.get('scene_uuid')
        if raw_u:
            raw_u_str = str(raw_u).strip()
            if raw_u_str in seen_raw_uuids:
                duplicate_raw_uuids.add(raw_u_str)
            else:
                seen_raw_uuids.add(raw_u_str)

        if s.get('is_intercut') and s.get('intercut_source_uuid'):
            intercut_target_uuids.add(str(s.get('intercut_source_uuid')).strip())

        for sub in s.get('sub_scenes', []):
            if not isinstance(sub, dict):
                raise ValueError(f"Invalid sub-scene data in snapshot for version {version.version_number}.")
            raw_sub_u = sub.get('scene_uuid')
            if raw_sub_u:
                raw_sub_u_str = str(raw_sub_u).strip()
                if raw_sub_u_str in seen_raw_uuids:
                    duplicate_raw_uuids.add(raw_sub_u_str)
                else:
                    seen_raw_uuids.add(raw_sub_u_str)

            if sub.get('is_intercut') and sub.get('intercut_source_uuid'):
                intercut_target_uuids.add(str(sub.get('intercut_source_uuid')).strip())

    # If any duplicate UUID is referenced by an intercut relationship, reject immediately before any mutations
    ambiguous_references = duplicate_raw_uuids.intersection(intercut_target_uuids)
    if ambiguous_references:
        ambiguous_list = ", ".join(sorted(ambiguous_references))
        raise ValueError(
            f"Cannot restore version {version.version_number}: Snapshot contains ambiguous duplicate UUID(s) "
            f"referenced by intercut relationships: {ambiguous_list}."
        )

    # First take an auto-snapshot of current active state before restore
    create_version_snapshot(script, title=f'Auto-backup before restoring v{version.version_number}')

    with transaction.atomic():
        # Identify current active scenes
        active_scenes = list(script.scenes.filter(is_deleted=False))
        active_scene_ids = {s.id for s in active_scenes}

        # Identify all trashed scenes belonging to this script
        trashed_scenes = list(script.scenes.filter(is_deleted=True))
        trashed_scene_uuids = {s.scene_uuid for s in trashed_scenes}

        # Step A: Disconnect parent_scene on trashed scenes pointing to active scenes to prevent CASCADE deletion!
        for t_sc in trashed_scenes:
            if t_sc.parent_scene_id and t_sc.parent_scene_id in active_scene_ids:
                if not t_sc.original_parent_uuid and t_sc.parent_scene:
                    t_sc.original_parent_uuid = t_sc.parent_scene.scene_uuid
                    t_sc.original_parent_scene_number = t_sc.parent_scene.scene_number
                    t_sc.original_parent_heading = t_sc.parent_scene.heading
                t_sc.parent_scene = None
                t_sc.save(update_fields=[
                    'parent_scene',
                    'original_parent_uuid',
                    'original_parent_scene_number',
                    'original_parent_heading',
                ])
            # Also preserve original_intercut_source_uuid if pointing to an active scene
            if t_sc.intercut_source_id and t_sc.intercut_source_id in active_scene_ids:
                if not t_sc.original_intercut_source_uuid and t_sc.intercut_source:
                    t_sc.original_intercut_source_uuid = t_sc.intercut_source.scene_uuid
                    t_sc.save(update_fields=['original_intercut_source_uuid'])

        # Step B: Delete ONLY active scenes (cascades to ScriptElements of active scenes only)
        # Trashed scenes are completely untouched because none have parent_scene pointing to active scenes.
        script.scenes.filter(is_deleted=False).delete()

        # Step C: Recreate active scenes from snapshot
        used_active_uuids = set()
        uuid_to_scene_map = {}
        pending_intercuts = []  # list of (scene_instance, target_source_uuid_str)

        def resolve_uuid(raw_val) -> uuid.UUID:
            cand = None
            if raw_val:
                try:
                    cand = uuid.UUID(str(raw_val))
                except (ValueError, TypeError, AttributeError):
                    cand = None
            if cand and cand not in trashed_scene_uuids and cand not in used_active_uuids:
                used_active_uuids.add(cand)
                return cand
            # Collision with trashed scene, duplicate in snapshot, or invalid/missing: generate fresh UUID
            new_u = uuid.uuid4()
            used_active_uuids.add(new_u)
            return new_u

        for s_idx, s_data in enumerate(snapshot.get('scenes', [])):
            raw_s_uuid = s_data.get('scene_uuid')
            main_uuid = resolve_uuid(raw_s_uuid)

            is_intercut_val = bool(s_data.get('is_intercut', False))
            intercut_source_uuid_str = s_data.get('intercut_source_uuid')

            main_scene = Scene.objects.create(
                script=script,
                parent_scene=None,
                scene_uuid=main_uuid,
                scene_number=s_data.get('scene_number', s_idx + 1),
                is_duplicate=s_data.get('is_duplicate', False),
                duplicate_number=s_data.get('duplicate_number', 0),
                is_intercut=is_intercut_val,
                intercut_source=None,  # will link in 2nd pass if source resolves
                heading=s_data.get('heading', 'INT. LOCATION - DAY'),
                transition=s_data.get('transition', 'CUT TO'),
                summary=s_data.get('summary', ''),
                order=s_data.get('order', s_idx),
                is_deleted=False,
            )

            # Map raw snapshot UUID only if unambiguous (not a duplicate)
            if raw_s_uuid:
                raw_s_str = str(raw_s_uuid).strip()
                if raw_s_str not in duplicate_raw_uuids:
                    uuid_to_scene_map[raw_s_str] = main_scene
            uuid_to_scene_map[str(main_uuid)] = main_scene

            if is_intercut_val and intercut_source_uuid_str:
                pending_intercuts.append((main_scene, str(intercut_source_uuid_str)))

            # Recreate elements of main scene
            elements_to_create = []
            for e_idx, e_data in enumerate(s_data.get('elements', [])):
                elements_to_create.append(ScriptElement(
                    scene=main_scene,
                    element_type=e_data.get('element_type', 'action'),
                    content=e_data.get('content', ''),
                    order=e_data.get('order', e_idx)
                ))
            if elements_to_create:
                ScriptElement.objects.bulk_create(elements_to_create)

            # Recreate sub-scenes
            for sub_idx, sub_data in enumerate(s_data.get('sub_scenes', [])):
                raw_sub_uuid = sub_data.get('scene_uuid')
                sub_uuid = resolve_uuid(raw_sub_uuid)

                sub_is_intercut = bool(sub_data.get('is_intercut', False))
                sub_intercut_source_uuid_str = sub_data.get('intercut_source_uuid')

                sub_scene = Scene.objects.create(
                    script=script,
                    parent_scene=main_scene,
                    scene_uuid=sub_uuid,
                    scene_number=main_scene.scene_number,
                    is_duplicate=sub_data.get('is_duplicate', False),
                    duplicate_number=sub_data.get('duplicate_number', 0),
                    is_intercut=sub_is_intercut,
                    intercut_source=None,
                    heading=sub_data.get('heading', 'INT. LOCATION - DAY'),
                    transition=sub_data.get('transition', 'CUT TO'),
                    summary=sub_data.get('summary', ''),
                    order=sub_data.get('order', sub_idx),
                    is_deleted=False,
                )

                if raw_sub_uuid:
                    raw_sub_str = str(raw_sub_uuid).strip()
                    if raw_sub_str not in duplicate_raw_uuids:
                        uuid_to_scene_map[raw_sub_str] = sub_scene
                uuid_to_scene_map[str(sub_uuid)] = sub_scene

                if sub_is_intercut and sub_intercut_source_uuid_str:
                    pending_intercuts.append((sub_scene, str(sub_intercut_source_uuid_str)))

                sub_elements_to_create = []
                for se_idx, se_data in enumerate(sub_data.get('elements', [])):
                    sub_elements_to_create.append(ScriptElement(
                        scene=sub_scene,
                        element_type=se_data.get('element_type', 'action'),
                        content=se_data.get('content', ''),
                        order=se_data.get('order', se_idx)
                    ))
                if sub_elements_to_create:
                    ScriptElement.objects.bulk_create(sub_elements_to_create)

        # Step D: Second pass to link intercut sources safely
        for sc_item, src_uuid_str in pending_intercuts:
            if src_uuid_str in uuid_to_scene_map:
                source_sc = uuid_to_scene_map[src_uuid_str]
                if source_sc.id != sc_item.id and not source_sc.is_deleted:
                    sc_item.intercut_source = source_sc
                    sc_item.save(update_fields=['intercut_source'])
                else:
                    # Unsafe or self-referential: revert intercut
                    sc_item.is_intercut = False
                    sc_item.save(update_fields=['is_intercut'])
            else:
                # Source cannot be resolved among restored active scenes: revert intercut safely
                sc_item.is_intercut = False
                sc_item.save(update_fields=['is_intercut'])

        # Step E: Restore title page if present in snapshot
        if 'title_page' in snapshot and snapshot['title_page'] is not None:
            tp_data = snapshot['title_page']
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

        # Step F: Resequence active scenes
        resequence_script_scenes(script)
        script.save()  # update updated_at

    return True

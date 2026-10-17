from django.db import transaction, models
from django.utils import timezone
from scripts.models import Script, Scene, ScriptElement


def resequence_script_scenes(script: Script):
    """
    Safely and atomically renumbers and reorders all scenes in a script:
    1. Main scenes (parent_scene__isnull=True) are ordered by (order, id).
       Non-duplicate, non-intercut main scenes receive sequential base scene numbers: 1, 2, 3...
       Duplicate main scenes retain the scene_number of their base scene.
       Intercut main scenes retain the scene_number of their source scene and do NOT increment the next scene's number.
       Sequential duplicates of the same base scene receive duplicate_number = 1, 2, 3...
    2. Sub-scenes under each parent are ordered by (order, id).
       They receive scene_number = parent.scene_number.
       Non-duplicate sub-scenes receive sequential sub-letters: A, B, C...
       Duplicate sub-scenes retain the base sub-letter and receive duplicate_number = 1, 2, 3...
    """
    with transaction.atomic():
        # Top-level items: main scenes, duplicate main scenes, intercut main scenes, and intercut sub-scenes
        top_items = list(script.scenes.filter(
            is_deleted=False
        ).filter(
            models.Q(parent_scene__isnull=True) | models.Q(is_intercut=True)
        ).order_by('order', 'id'))

        ordered_scenes = []
        seen_ids = set()

        for item in top_items:
            if item.id in seen_ids:
                continue
            ordered_scenes.append(item)
            seen_ids.add(item.id)

            # If it's a main scene (not a sub-scene), append its standard (non-intercut) sub-scenes immediately after
            if not item.is_sub_scene:
                for sub in item.sub_scenes.filter(is_deleted=False, is_intercut=False).order_by('order', 'id'):
                    if sub.id not in seen_ids:
                        ordered_scenes.append(sub)
                        seen_ids.add(sub.id)

        # Include any remaining active scenes if any
        all_remaining = script.scenes.filter(is_deleted=False).exclude(id__in=seen_ids).order_by('order', 'id')
        for rem in all_remaining:
            ordered_scenes.append(rem)
            seen_ids.add(rem.id)

        # 1. Update order and main scene numbers
        current_base_num = 0
        dup_counts = {}
        for idx, sc in enumerate(ordered_scenes):
            sc.order = idx
            if sc.parent_scene_id is None:
                if sc.is_intercut and sc.intercut_source_id:
                    source = sc.intercut_source
                    if source and not source.is_deleted:
                        sc.scene_number = source.scene_number
                    sc.duplicate_number = 0
                elif sc.is_sequence:
                    # Sequence scene does NOT consume or change master scene numbers
                    sc.scene_number = current_base_num if current_base_num > 0 else 1
                    sc.duplicate_number = 0
                elif not sc.is_duplicate and not sc.is_intercut:
                    current_base_num += 1
                    sc.scene_number = current_base_num
                    sc.duplicate_number = 0
                    dup_counts[current_base_num] = 0
                elif sc.is_duplicate:
                    base = current_base_num if current_base_num > 0 else 1
                    sc.scene_number = base
                    dup_counts[base] = dup_counts.get(base, 0) + 1
                    sc.duplicate_number = dup_counts[base]

            sc.save(update_fields=['scene_number', 'order', 'is_duplicate', 'duplicate_number'])

        # 2. Resequence sub-scenes for each parent scene
        parents = script.scenes.filter(is_deleted=False, parent_scene__isnull=True)
        for parent_sc in parents:
            sub_scenes = list(parent_sc.sub_scenes.filter(is_deleted=False).order_by('order', 'id'))
            sub_dup_counts = {}
            current_sub_letter_idx = 0
            has_non_dup = False
            for sub_idx, sub_sc in enumerate(sub_scenes):
                sub_sc.scene_number = parent_sc.scene_number
                if not sub_sc.is_duplicate:
                    sub_dup_counts[current_sub_letter_idx] = 0
                    current_sub_letter_idx += 1
                    sub_sc.duplicate_number = 0
                    has_non_dup = True
                else:
                    target_key = max(0, current_sub_letter_idx - 1) if has_non_dup else 0
                    sub_dup_counts[target_key] = sub_dup_counts.get(target_key, 0) + 1
                    sub_sc.duplicate_number = sub_dup_counts[target_key]

                sub_sc.save(update_fields=['scene_number', 'is_duplicate', 'duplicate_number'])


def duplicate_scene(script: Script, source_scene: Scene) -> Scene:
    """
    Duplicates any scene (main scene or sub-scene), creating a complete independent copy:
    - Maintains the base scene number of the original scene.
    - Displays '(Duplicate)', '(Duplicate 2)', etc.
    - Does NOT renumber subsequent scenes.
    - Clones all ScriptElements with new database IDs and preserved order/types.
    - If duplicating a main scene with sub-scenes, duplicates all sub-scenes and their elements.
    """
    with transaction.atomic():
        all_scenes = list(script.scenes.filter(is_deleted=False).order_by('order', 'id'))

        if source_scene.is_sub_scene and source_scene.parent_scene:
            try:
                ref_idx = [s.id for s in all_scenes].index(source_scene.id)
                insert_order = ref_idx + 1
            except ValueError:
                insert_order = len(all_scenes)

            for s in all_scenes:
                if s.order >= insert_order:
                    s.order += 1
                    s.save(update_fields=['order'])

            parent = source_scene.parent_scene
            siblings = list(parent.sub_scenes.filter(is_deleted=False).order_by('order', 'id'))

            base_letter = source_scene.sub_letter
            existing_dups = [s for s in siblings if s.sub_letter == base_letter and s.is_duplicate]
            next_dup_num = len(existing_dups) + 1

            new_sub = Scene.objects.create(
                script=script,
                parent_scene=parent,
                scene_number=parent.scene_number,
                heading=source_scene.heading,
                summary=source_scene.summary,
                order=insert_order,
                is_duplicate=True,
                duplicate_number=next_dup_num
            )

            # Copy elements
            elements_to_create = []
            for elem in source_scene.elements.all().order_by('order'):
                elements_to_create.append(
                    ScriptElement(
                        scene=new_sub,
                        element_type=elem.element_type,
                        content=elem.content,
                        order=elem.order
                    )
                )
            if elements_to_create:
                ScriptElement.objects.bulk_create(elements_to_create)

            resequence_script_scenes(script)
            new_sub.refresh_from_db()
            script.updated_at = timezone.now()
            script.save(update_fields=['updated_at'])
            return new_sub

        else:
            base_scene_number = source_scene.scene_number
            active_subs = list(source_scene.sub_scenes.filter(is_deleted=False).order_by('order', 'id'))
            ref_scene = active_subs[-1] if active_subs else source_scene

            try:
                ref_idx = [s.id for s in all_scenes].index(ref_scene.id)
                insert_order = ref_idx + 1
            except ValueError:
                insert_order = len(all_scenes)

            total_new_scenes = 1 + len(active_subs)
            for s in all_scenes:
                if s.order >= insert_order:
                    s.order += total_new_scenes
                    s.save(update_fields=['order'])

            main_scenes = list(script.scenes.filter(is_deleted=False, parent_scene__isnull=True).order_by('order', 'id'))

            existing_dups = [s for s in main_scenes if s.scene_number == base_scene_number and s.is_duplicate]
            next_dup_num = len(existing_dups) + 1

            new_main = Scene.objects.create(
                script=script,
                parent_scene=None,
                scene_number=base_scene_number,
                heading=source_scene.heading,
                summary=source_scene.summary,
                order=insert_order,
                is_duplicate=True,
                duplicate_number=next_dup_num
            )

            # Copy elements of main scene
            elements_to_create = []
            for elem in source_scene.elements.all().order_by('order'):
                elements_to_create.append(
                    ScriptElement(
                        scene=new_main,
                        element_type=elem.element_type,
                        content=elem.content,
                        order=elem.order
                    )
                )
            if elements_to_create:
                ScriptElement.objects.bulk_create(elements_to_create)

            # If source_scene has sub-scenes, clone each active sub-scene and its elements under new_main with distinct sequential orders
            for sub_idx, sub_sc in enumerate(active_subs, start=1):
                new_cloned_sub = Scene.objects.create(
                    script=script,
                    parent_scene=new_main,
                    scene_number=new_main.scene_number,
                    heading=sub_sc.heading,
                    summary=sub_sc.summary,
                    order=insert_order + sub_idx,
                    is_duplicate=sub_sc.is_duplicate,
                    duplicate_number=sub_sc.duplicate_number
                )
                sub_elements = []
                for sub_elem in sub_sc.elements.all().order_by('order'):
                    sub_elements.append(
                        ScriptElement(
                            scene=new_cloned_sub,
                            element_type=sub_elem.element_type,
                            content=sub_elem.content,
                            order=sub_elem.order
                        )
                    )
                if sub_elements:
                    ScriptElement.objects.bulk_create(sub_elements)

            resequence_script_scenes(script)
            new_main.refresh_from_db()
            script.updated_at = timezone.now()
            script.save(update_fields=['updated_at'])
            return new_main


def insert_scene_relative(script: Script, reference_scene_id: int = None, position: str = 'after', heading: str = 'INT. LOCATION - DAY', summary: str = '') -> Scene:
    """
    Inserts a new scene before or after a reference scene:
    - If reference scene is a sub-scene, inserts a new sibling sub-scene under the same parent.
    - If reference scene is a main scene, inserts a new main scene before/after it.
    Automatically shifts subsequent scenes and resequences the screenplay.
    """
    heading = (heading or 'INT. LOCATION - DAY').strip()
    summary = (summary or '').strip()

    with transaction.atomic():
        ref_scene = None
        if reference_scene_id:
            try:
                ref_scene = script.scenes.get(id=reference_scene_id, is_deleted=False)
            except Scene.DoesNotExist:
                ref_scene = None

        all_scenes = list(script.scenes.filter(is_deleted=False).order_by('order', 'id'))

        if ref_scene:
            subs = list(ref_scene.sub_scenes.filter(is_deleted=False).order_by('order', 'id'))
            if position == 'after' and subs:
                target_ref = subs[-1]
            else:
                target_ref = ref_scene
            target_order = target_ref.order if position == 'before' else target_ref.order + 1
        else:
            target_order = max([s.order for s in all_scenes], default=-1) + 1

        # If reference scene is an active sequence that has not already ended, close it automatically before adding the next scene
        if ref_scene and ref_scene.is_sequence and position == 'after':
            expected_end_marker = 'MONTAGE ENDS' if ref_scene.sequence_type == 'montage' else 'SONG ENDS'
            elems = list(ref_scene.elements.all().order_by('order', 'id'))
            has_ended = any((e.content or '').strip().upper() == expected_end_marker for e in elems)
            if not has_ended:
                next_order = len(elems)
                ScriptElement.objects.create(scene=ref_scene, element_type='shot', content=expected_end_marker, order=next_order)

        # Shift all scenes at or after target_order
        for s in all_scenes:
            if s.order >= target_order:
                s.order += 1
                s.save(update_fields=['order'])

        if ref_scene and ref_scene.parent_scene:
            parent = ref_scene.parent_scene
            new_scene = Scene.objects.create(
                script=script,
                parent_scene=parent,
                scene_number=parent.scene_number,
                heading=heading,
                summary=summary,
                order=target_order
            )
        else:
            new_scene = Scene.objects.create(
                script=script,
                parent_scene=None,
                scene_number=target_order + 1,
                heading=heading,
                summary=summary,
                order=target_order
            )

        # Seed initial elements
        h_upper = heading.strip().upper()
        if h_upper in ('SONG BEGINS', 'MONTAGE BEGINS'):
            ScriptElement.objects.create(scene=new_scene, element_type='shot', content=heading, order=0)
            ScriptElement.objects.create(scene=new_scene, element_type='shot', content='1. INT. LOCATION - DAY', order=1)
            ScriptElement.objects.create(scene=new_scene, element_type='action', content='', order=2)
        else:
            ScriptElement.objects.create(scene=new_scene, element_type='scene_heading', content=heading, order=0)
            ScriptElement.objects.create(scene=new_scene, element_type='action', content='', order=1)

        # Resequence to guarantee clean numbering
        resequence_script_scenes(script)
        new_scene.refresh_from_db()

        script.updated_at = timezone.now()
        script.save(update_fields=['updated_at'])

        return new_scene


def create_sequence_scene(script: Script, reference_scene_id: int = None, sequence_type: str = 'song') -> Scene:
    """
    Creates a new independent sequence scene (Song or Montage) as a separate screenplay scene/page:
    - Positioned immediately after the reference scene (or its sub-scenes if it is a parent).
    - If the reference scene is an active sequence that has not ended, closes it automatically.
    - Seeding:
        Order 0: shot: 'SONG BEGINS' or 'MONTAGE BEGINS'
        Order 1: shot: '1. INT. LOCATION - DAY'
        Order 2: action: ''
    - Sequence shots do NOT consume or change master scene numbering.
    - Automatically resequences the screenplay.
    """
    seq_type = 'montage' if sequence_type == 'montage' else 'song'
    marker_begin = 'MONTAGE BEGINS' if seq_type == 'montage' else 'SONG BEGINS'

    with transaction.atomic():
        ref_scene = None
        if reference_scene_id:
            try:
                ref_scene = script.scenes.get(id=reference_scene_id, is_deleted=False)
            except Scene.DoesNotExist:
                ref_scene = None

        all_scenes = list(script.scenes.filter(is_deleted=False).order_by('order', 'id'))

        # If reference scene is an active sequence that has not already ended, close it
        if ref_scene and ref_scene.is_sequence:
            expected_end_marker = 'MONTAGE ENDS' if ref_scene.sequence_type == 'montage' else 'SONG ENDS'
            elems = list(ref_scene.elements.all().order_by('order', 'id'))
            has_ended = any((e.content or '').strip().upper() == expected_end_marker for e in elems)
            if not has_ended:
                next_order = len(elems)
                ScriptElement.objects.create(scene=ref_scene, element_type='shot', content=expected_end_marker, order=next_order)

        if ref_scene:
            # If ref_scene is a sub-scene, resolve to its parent group to place sequence after all siblings
            parent = ref_scene.parent_scene if ref_scene.is_sub_scene and ref_scene.parent_scene else ref_scene
            subs = list(parent.sub_scenes.filter(is_deleted=False).order_by('order', 'id'))
            target_ref = subs[-1] if subs else parent
            target_order = target_ref.order + 1
        else:
            target_order = max([s.order for s in all_scenes], default=-1) + 1

        for s in all_scenes:
            if s.order >= target_order:
                s.order += 1
                s.save(update_fields=['order'])

        new_scene = Scene.objects.create(
            script=script,
            parent_scene=None,
            scene_number=ref_scene.scene_number if ref_scene else 1,
            heading=marker_begin,
            summary='',
            order=target_order
        )

        # Seed initial elements
        ScriptElement.objects.create(scene=new_scene, element_type='shot', content=marker_begin, order=0)
        ScriptElement.objects.create(scene=new_scene, element_type='shot', content='1. INT. LOCATION - DAY', order=1)
        ScriptElement.objects.create(scene=new_scene, element_type='action', content='', order=2)

        resequence_script_scenes(script)
        new_scene.refresh_from_db()

        script.updated_at = timezone.now()
        script.save(update_fields=['updated_at'])

        return new_scene


def create_sub_scene(script: Script, parent_scene_id: int, heading: str = 'INT. LOCATION - DAY', summary: str = '') -> Scene:
    """
    Creates a new sub-scene under the specified parent scene.
    """
    heading = (heading or 'INT. LOCATION - DAY').strip()
    summary = (summary or '').strip()

    with transaction.atomic():
        parent = script.scenes.get(id=parent_scene_id, is_deleted=False)
        if parent.parent_scene and not parent.parent_scene.is_deleted:
            parent = parent.parent_scene

        # Find the last active sub-scene of this parent or the parent itself
        last_sub = parent.sub_scenes.filter(is_deleted=False).order_by('-order', '-id').first()
        ref_scene = last_sub if last_sub else parent

        all_scenes = list(script.scenes.filter(is_deleted=False).order_by('order', 'id'))
        try:
            ref_idx = [s.id for s in all_scenes].index(ref_scene.id)
            target_order = ref_idx + 1
        except ValueError:
            target_order = len(all_scenes)

        for s in all_scenes:
            if s.order >= target_order:
                s.order += 1
                s.save(update_fields=['order'])

        new_sub = Scene.objects.create(
            script=script,
            parent_scene=parent,
            scene_number=parent.scene_number,
            heading=heading,
            summary=summary,
            order=target_order
        )

        ScriptElement.objects.create(scene=new_sub, element_type='scene_heading', content=heading, order=0)
        ScriptElement.objects.create(scene=new_sub, element_type='action', content='', order=1)

        resequence_script_scenes(script)
        new_sub.refresh_from_db()

        script.updated_at = timezone.now()
        script.save(update_fields=['updated_at'])

        return new_sub


def create_sub_scene_2(script: Script, source_scene_id: int, current_scene_id: int = None) -> Scene:
    """
    Creates a new sub-scene associated with source_scene (e.g. Scene 2 -> Scene 2.A or 2.B or 2.C),
    inserted at the current writing position (immediately below current_scene_id).
    Heading is copied from source_scene.
    """
    with transaction.atomic():
        source_scene = script.scenes.get(id=source_scene_id, is_deleted=False)
        parent = source_scene.parent_scene if (source_scene.parent_scene and not source_scene.parent_scene.is_deleted) else source_scene

        all_scenes = list(script.scenes.filter(is_deleted=False).order_by('order', 'id'))
        current_scene = None
        if current_scene_id:
            try:
                current_scene = script.scenes.get(id=current_scene_id, is_deleted=False)
            except Scene.DoesNotExist:
                current_scene = None

        if current_scene:
            try:
                ref_idx = [s.id for s in all_scenes].index(current_scene.id)
                target_order = ref_idx + 1
            except ValueError:
                target_order = len(all_scenes)
        else:
            target_order = len(all_scenes)

        for s in all_scenes:
            if s.order >= target_order:
                s.order += 1
                s.save(update_fields=['order'])

        heading = source_scene.heading or 'INT. LOCATION - DAY'

        new_sub = Scene.objects.create(
            script=script,
            parent_scene=parent,
            scene_number=parent.scene_number,
            heading=heading,
            summary='',
            order=target_order,
            is_intercut=True,
            intercut_source=source_scene
        )

        ScriptElement.objects.create(scene=new_sub, element_type='scene_heading', content=heading, order=0)
        ScriptElement.objects.create(scene=new_sub, element_type='action', content='', order=1)

        resequence_script_scenes(script)
        new_sub.refresh_from_db()

        script.updated_at = timezone.now()
        script.save(update_fields=['updated_at'])

        return new_sub


def create_intercut_scene(script: Script, source_scene_id: int, current_scene_id: int = None) -> Scene:
    """
    Creates a new intercut scene instance copied from source_scene (retains source scene number, heading, location, time),
    inserted at the current writing position (immediately below current_scene_id).
    Displays as 'Scene X : HEADING'.
    """
    with transaction.atomic():
        source_scene = script.scenes.get(id=source_scene_id, is_deleted=False)

        all_scenes = list(script.scenes.filter(is_deleted=False).order_by('order', 'id'))
        current_scene = None
        if current_scene_id:
            try:
                current_scene = script.scenes.get(id=current_scene_id, is_deleted=False)
            except Scene.DoesNotExist:
                current_scene = None

        if current_scene:
            try:
                ref_idx = [s.id for s in all_scenes].index(current_scene.id)
                target_order = ref_idx + 1
            except ValueError:
                target_order = len(all_scenes)
        else:
            target_order = len(all_scenes)

        for s in all_scenes:
            if s.order >= target_order:
                s.order += 1
                s.save(update_fields=['order'])

        heading = source_scene.heading or 'INT. LOCATION - DAY'

        new_scene = Scene.objects.create(
            script=script,
            parent_scene=None,
            scene_number=source_scene.scene_number,
            heading=heading,
            summary='',
            order=target_order,
            is_intercut=True,
            intercut_source=source_scene
        )

        ScriptElement.objects.create(scene=new_scene, element_type='scene_heading', content=heading, order=0)
        ScriptElement.objects.create(scene=new_scene, element_type='action', content='', order=1)

        resequence_script_scenes(script)
        new_scene.refresh_from_db()

        script.updated_at = timezone.now()
        script.save(update_fields=['updated_at'])

        return new_scene


def move_scene(script: Script, scene_id: int, direction: str) -> bool:
    """
    Moves a scene up or down:
    - Standard sub-scene: moves strictly within parent's sub-scenes.
    - Intercut sub-scene / Main scene: moves within screenplay top-level blocks,
      preserving all ordinary sub-scenes attached to their parent scene.
    """
    with transaction.atomic():
        try:
            scene = script.scenes.get(id=scene_id, is_deleted=False)
        except Scene.DoesNotExist:
            return False

        if scene.is_sub_scene and not scene.is_intercut:
            # Standard sub-scene: move within parent's sub-scenes only
            if not scene.parent_scene or scene.parent_scene.is_deleted:
                return False
            siblings = list(scene.parent_scene.sub_scenes.filter(is_intercut=False, is_deleted=False).order_by('order', 'id'))
            try:
                idx = siblings.index(scene)
            except ValueError:
                return False

            if direction == 'up' and idx > 0:
                target_idx = idx - 1
            elif direction == 'down' and idx < len(siblings) - 1:
                target_idx = idx + 1
            else:
                return False

            target = siblings[target_idx]
            if scene.order == target.order:
                if target_idx < idx:
                    scene.order = target.order - 1
                else:
                    scene.order = target.order + 1
            else:
                scene.order, target.order = target.order, scene.order
            scene.save(update_fields=['order'])
            target.save(update_fields=['order'])
        else:
            # Main scene, intercut scene, or intercut sub-scene:
            # Moves across top-level blocks in screenplay flow.
            top_items = list(script.scenes.filter(
                is_deleted=False
            ).filter(
                models.Q(parent_scene__isnull=True) | models.Q(is_intercut=True)
            ).order_by('order', 'id'))

            try:
                idx = top_items.index(scene)
            except ValueError:
                return False

            if direction == 'up' and idx > 0:
                target_idx = idx - 1
            elif direction == 'down' and idx < len(top_items) - 1:
                target_idx = idx + 1
            else:
                return False

            # Swap the two top-level items
            top_items[idx], top_items[target_idx] = top_items[target_idx], top_items[idx]

            # Reconstruct the flat sequence of all scenes in the script:
            # Each top-level item followed by its ordinary sub-scenes
            ordered_scenes = []
            seen_ids = set()

            for item in top_items:
                if item.id in seen_ids:
                    continue
                ordered_scenes.append(item)
                seen_ids.add(item.id)

                # If it's a main scene (not a sub-scene), append its standard (non-intercut) sub-scenes immediately after
                if not item.is_sub_scene:
                    for sub in item.sub_scenes.filter(is_intercut=False, is_deleted=False).order_by('order', 'id'):
                        if sub.id not in seen_ids:
                            ordered_scenes.append(sub)
                            seen_ids.add(sub.id)

            # Include any remaining active scenes if any exist (safety fallback)
            all_remaining = script.scenes.filter(is_deleted=False).exclude(id__in=seen_ids).order_by('order', 'id')
            for rem in all_remaining:
                ordered_scenes.append(rem)
                seen_ids.add(rem.id)

            # Assign new sequential order values
            for new_order, sc in enumerate(ordered_scenes):
                if sc.order != new_order:
                    sc.order = new_order
                    sc.save(update_fields=['order'])

        resequence_script_scenes(script)
        script.updated_at = timezone.now()
        script.save(update_fields=['updated_at'])
        return True


def reorder_main_scene(script: Script, scene: Scene, target_number: int) -> tuple[bool, str]:
    """
    Reorders a main scene to target_number (1-indexed) and resequences all scenes in the screenplay.
    Preserves:
    - Attached sub-scenes (and their relative sub-letters/ordering under the parent)
    - Duplicate scenes and intercuts
    - Content elements, IDs, and screenplay integrity
    """
    if scene.is_sub_scene:
        raise ValueError("Sub-scenes cannot be renumbered as main scenes.")
    if scene.is_intercut:
        raise ValueError("Intercut scenes cannot be directly renumbered.")
    if scene.is_duplicate:
        raise ValueError("Duplicate scenes retain their base scene number and cannot be directly renumbered.")
    if scene.is_sequence:
        raise ValueError("Sequence scenes do not consume master scene numbers and cannot be directly renumbered.")

    base_main_scenes = [
        s for s in script.scenes.filter(
            is_deleted=False,
            parent_scene__isnull=True,
            is_intercut=False,
            is_duplicate=False
        ).order_by('order', 'id')
        if not s.is_sequence
    ]
    total_main = len(base_main_scenes)
    if total_main == 0:
        raise ValueError("No active main scenes found in this screenplay.")

    if not isinstance(target_number, int) or isinstance(target_number, bool):
        raise ValueError("Scene number must be a valid integer.")

    if target_number < 1:
        raise ValueError("Scene number must be a positive integer greater than zero.")

    if target_number > total_main:
        raise ValueError(f"Scene number cannot exceed the total number of main scenes ({total_main}).")

    try:
        current_idx = [s.id for s in base_main_scenes].index(scene.id)
    except ValueError:
        raise ValueError("The selected scene is not an active main scene in this screenplay.")

    current_position = current_idx + 1
    if target_number == current_position:
        return False, f"Scene is already at position {target_number}."

    target_idx = target_number - 1

    with transaction.atomic():
        top_items = list(script.scenes.filter(
            is_deleted=False
        ).filter(
            models.Q(parent_scene__isnull=True) | models.Q(is_intercut=True)
        ).order_by('order', 'id'))

        moved_scene = base_main_scenes.pop(current_idx)
        base_main_scenes.insert(target_idx, moved_scene)

        new_top_items = []
        seen_top_ids = set()
        for base_m in base_main_scenes:
            new_top_items.append(base_m)
            seen_top_ids.add(base_m.id)
            dups = [t for t in top_items if t.parent_scene_id is None and t.is_duplicate and t.scene_number == base_m.scene_number and t.id not in seen_top_ids]
            for d in dups:
                new_top_items.append(d)
                seen_top_ids.add(d.id)

        for t in top_items:
            if t.id not in seen_top_ids:
                new_top_items.append(t)
                seen_top_ids.add(t.id)

        ordered_scenes = []
        seen_all_ids = set()
        for item in new_top_items:
            if item.id in seen_all_ids:
                continue
            ordered_scenes.append(item)
            seen_all_ids.add(item.id)

            if not item.is_sub_scene:
                for sub in item.sub_scenes.filter(is_intercut=False, is_deleted=False).order_by('order', 'id'):
                    if sub.id not in seen_all_ids:
                        ordered_scenes.append(sub)
                        seen_all_ids.add(sub.id)

        remaining = script.scenes.filter(is_deleted=False).exclude(id__in=seen_all_ids).order_by('order', 'id')
        for rem in remaining:
            ordered_scenes.append(rem)
            seen_all_ids.add(rem.id)

        for new_order, sc in enumerate(ordered_scenes):
            if sc.order != new_order:
                sc.order = new_order
                sc.save(update_fields=['order'])

        resequence_script_scenes(script)
        script.updated_at = timezone.now()
        script.save(update_fields=['updated_at'])

    return True, "Scene reordered successfully."


def promote_sub_scene(script: Script, scene: Scene) -> tuple[bool, str]:
    """
    Promotes an eligible sub-scene to become a main scene.
    1. Preserves scene record, primary key, UUID, elements, heading, content, Malayalam text.
    2. Detaches parent relationship (parent_scene = None).
    3. Places it immediately after its former parent's complete scene block (former parent + surviving sub-scenes/duplicates).
    4. Renumbers all eligible main scenes sequentially (P.scene_number + 1, subsequent main scenes increment).
    5. Renumbers remaining sub-scenes under the former parent (A, B, C...).
    6. Preserves duplicate/intercut semantics.
    7. Wrapped in a database transaction.
    """
    if scene.script_id != script.id:
        raise ValueError("Scene does not belong to the specified screenplay.")
    if scene.is_deleted:
        raise ValueError("Cannot promote a deleted scene.")
    if not scene.is_sub_scene or not scene.parent_scene:
        raise ValueError("Only active sub-scenes can be promoted to a main scene.")
    if scene.is_intercut:
        raise ValueError("Intercut sub-scenes cannot be promoted to a main scene.")
    if scene.is_duplicate:
        raise ValueError("Duplicate sub-scenes cannot be promoted to a main scene directly.")

    with transaction.atomic():
        former_parent = scene.parent_scene
        if former_parent.is_deleted:
            raise ValueError("Cannot promote a sub-scene whose parent scene is deleted.")

        # Detach parent
        scene.parent_scene = None
        scene.save(update_fields=['parent_scene'])

        # Top items excluding the promoted scene (which was a sub-scene before)
        top_items = list(script.scenes.filter(
            is_deleted=False
        ).filter(
            models.Q(parent_scene__isnull=True) | models.Q(is_intercut=True)
        ).exclude(id=scene.id).order_by('order', 'id'))

        try:
            parent_idx = [t.id for t in top_items].index(former_parent.id)
        except ValueError:
            parent_idx = len(top_items) - 1

        # Advance past any top-level duplicates of former_parent
        insert_idx = parent_idx + 1
        while insert_idx < len(top_items):
            item = top_items[insert_idx]
            if item.parent_scene_id is None and item.is_duplicate and item.scene_number == former_parent.scene_number:
                insert_idx += 1
            else:
                break

        top_items.insert(insert_idx, scene)

        # Reconstruct flat sequence of all scenes in script:
        # Each top-level item followed by its surviving sub-scenes
        ordered_scenes = []
        seen_ids = set()

        for item in top_items:
            if item.id in seen_ids:
                continue
            ordered_scenes.append(item)
            seen_ids.add(item.id)

            if not item.is_sub_scene:
                for sub in item.sub_scenes.filter(is_deleted=False, is_intercut=False).order_by('order', 'id'):
                    if sub.id not in seen_ids:
                        ordered_scenes.append(sub)
                        seen_ids.add(sub.id)

        all_remaining = script.scenes.filter(is_deleted=False).exclude(id__in=seen_ids).order_by('order', 'id')
        for rem in all_remaining:
            ordered_scenes.append(rem)
            seen_ids.add(rem.id)

        # Update order values
        for new_order, sc in enumerate(ordered_scenes):
            if sc.order != new_order:
                sc.order = new_order
                sc.save(update_fields=['order'])

        # Resequence scene numbers and sub-letters
        resequence_script_scenes(script)

        script.updated_at = timezone.now()
        script.save(update_fields=['updated_at'])

        scene.refresh_from_db()
        return True, "Sub-scene promoted to main scene successfully."


def reorder_sub_scene(script: Script, scene: Scene, target_position: int) -> tuple[bool, str]:
    """
    Reorders a sub-scene to target_position (1-indexed) among its active siblings under the same parent scene.
    Preserves:
    - Parent scene's scene_number and identity
    - Sub-scene primary key, UUID, elements, heading, content, and parent relationship
    - Content elements, IDs, and screenplay integrity
    - Excludes soft-deleted sub-scenes
    """
    if scene.script_id != script.id:
        raise ValueError("Scene does not belong to the specified screenplay.")
    if scene.is_deleted:
        raise ValueError("Cannot reorder a deleted scene.")
    if not scene.is_sub_scene or not scene.parent_scene:
        raise ValueError("Only sub-scenes can be reordered using sub-scene reordering.")
    if scene.is_intercut:
        raise ValueError("Intercut sub-scenes cannot be directly renumbered.")
    if scene.is_duplicate:
        raise ValueError("Duplicate sub-scenes retain their base sub-scene position and cannot be directly renumbered.")

    parent = scene.parent_scene
    if parent.is_deleted:
        raise ValueError("Cannot reorder sub-scenes under a deleted parent scene.")

    siblings = list(
        parent.sub_scenes.filter(
            is_deleted=False,
            is_intercut=False,
            is_duplicate=False
        ).order_by('order', 'id')
    )
    total_siblings = len(siblings)
    if total_siblings == 0:
        raise ValueError("No active sibling sub-scenes found.")

    if not isinstance(target_position, int) or isinstance(target_position, bool):
        raise ValueError("Sub-scene position must be a valid integer.")

    if target_position < 1:
        raise ValueError("Sub-scene position must be a positive integer greater than zero.")

    if target_position > total_siblings:
        raise ValueError(f"Sub-scene position cannot exceed the total number of sibling sub-scenes ({total_siblings}).")

    try:
        current_idx = [s.id for s in siblings].index(scene.id)
    except ValueError:
        raise ValueError("The selected sub-scene is not an active sub-scene under its parent.")

    current_position = current_idx + 1
    if target_position == current_position:
        return False, f"Sub-scene is already at position {target_position}."

    target_idx = target_position - 1

    with transaction.atomic():
        moved = siblings.pop(current_idx)
        siblings.insert(target_idx, moved)

        all_parent_subs = list(parent.sub_scenes.filter(is_deleted=False).order_by('order', 'id'))
        new_sub_items = []
        seen_sub_ids = set()
        for base_s in siblings:
            new_sub_items.append(base_s)
            seen_sub_ids.add(base_s.id)
            dups = [s for s in all_parent_subs if s.is_duplicate and s.sub_letter == base_s.sub_letter and s.id not in seen_sub_ids]
            for d in dups:
                new_sub_items.append(d)
                seen_sub_ids.add(d.id)

        for s in all_parent_subs:
            if s.id not in seen_sub_ids:
                new_sub_items.append(s)
                seen_sub_ids.add(s.id)

        top_items = list(script.scenes.filter(
            is_deleted=False
        ).filter(
            models.Q(parent_scene__isnull=True) | models.Q(is_intercut=True)
        ).order_by('order', 'id'))

        ordered_scenes = []
        seen_all_ids = set()

        for item in top_items:
            if item.id in seen_all_ids:
                continue
            ordered_scenes.append(item)
            seen_all_ids.add(item.id)

            if not item.is_sub_scene:
                if item.id == parent.id:
                    for sub in new_sub_items:
                        if sub.id not in seen_all_ids:
                            ordered_scenes.append(sub)
                            seen_all_ids.add(sub.id)
                else:
                    for sub in item.sub_scenes.filter(is_deleted=False, is_intercut=False).order_by('order', 'id'):
                        if sub.id not in seen_all_ids:
                            ordered_scenes.append(sub)
                            seen_all_ids.add(sub.id)

        all_remaining = script.scenes.filter(is_deleted=False).exclude(id__in=seen_all_ids).order_by('order', 'id')
        for rem in all_remaining:
            ordered_scenes.append(rem)
            seen_all_ids.add(rem.id)

        for new_order, sc in enumerate(ordered_scenes):
            if sc.order != new_order:
                sc.order = new_order
                sc.save(update_fields=['order'])

        resequence_script_scenes(script)

        script.updated_at = timezone.now()
        script.save(update_fields=['updated_at'])

        scene.refresh_from_db()
        return True, "Sub-scene reordered successfully."



def serialize_scenes_hierarchy(script: Script) -> list:
    """
    Returns a structured list of scenes for navigation, sidebars, and mobile menus.
    """
    ordered_scenes = list(script.scenes.filter(is_deleted=False).prefetch_related('parent_scene', 'elements').order_by('order', 'id'))
    result = []
    
    for sc in ordered_scenes:
        result.append({
            'id': sc.id,
            'parent_scene_id': sc.parent_scene_id,
            'is_sub_scene': sc.is_sub_scene,
            'is_duplicate': sc.is_duplicate,
            'duplicate_number': sc.duplicate_number,
            'is_intercut': sc.is_intercut,
            'is_sequence': sc.is_sequence,
            'sequence_type': sc.sequence_type,
            'scene_number': sc.scene_number,
            'scene_identifier': sc.scene_identifier,
            'nav_identifier': sc.nav_identifier,
            'clean_location': sc.clean_location,
            'action_preview': sc.action_preview,
            'display_number': sc.display_number,
            'display_number_formatted': sc.display_number_formatted,
            'full_display_heading': sc.full_display_heading,
            'clean_heading': sc.clean_heading,
            'heading': sc.heading,
            'transition': sc.transition or 'CUT TO',
            'summary': sc.summary,
            'order': sc.order,
            'word_count': sc.word_count,
            'sub_scenes': [],
        })

    return result


def restore_scene_to_script(
    script: Script,
    scene: Scene,
    restore_as: str = 'auto',
    target_parent_id: int = None
) -> tuple[Scene, bool, str]:
    """
    Safely restores a soft-deleted scene to an active screenplay.

    Parent Resolution:
    - If scene was a sub-scene:
      - If restore_as == 'main_scene': detach parent_scene (restore as a top-level main scene).
      - If restore_as == 'specified_parent': attach to target_parent_id (must be an active main scene in this script).
      - Otherwise (restore_as in ['auto', 'original_parent']):
        - Try to resolve original parent:
          - If original_parent_uuid is present: search active main scenes by scene_uuid.
          - If not found or not unique: search by parent_scene_id if active.
          - If original parent is active: attach to it.
          - If original parent is trashed, missing, or ambiguous: raise ValueError requiring writer choice.
    - If scene was a main scene:
      - parent_scene remains None. Sub-scenes in trash remain in trash.

    Intercut Resolution:
    - If scene was an intercut:
      - Try to resolve original source:
        - If original_intercut_source_uuid is present: search active scenes by scene_uuid.
        - Fallback: check intercut_source_id if active.
        - If source is active and unambiguous: preserve intercut_source.
        - If source is trashed, missing, or ambiguous: fallback to normal scene (is_intercut=False, intercut_source=None)
          and report intercut_fallback=True.

    Ordering & Resequencing:
    - Positions the restored scene at original_order if valid, shifting existing active scenes >= target_order by +1.
    - If original_order is None or out of bounds, appends at the end.
    - Atomically runs resequence_script_scenes(script).

    Returns:
    (restored_scene, intercut_fallback_occurred, message)
    """
    with transaction.atomic():
        # Lock scene record to prevent race conditions
        scene = Scene.objects.select_for_update().get(id=scene.id, script=script)

        if not scene.is_deleted:
            raise ValueError(f"Scene {scene.id} is already active.")

        intercut_fallback = False
        message_notes = []

        # 1. Parent Resolution for Sub-scenes
        if scene.original_parent_uuid or scene.parent_scene_id or scene.is_sub_scene:
            if restore_as == 'main_scene':
                scene.parent_scene = None
                message_notes.append("restored as a main scene")
            elif restore_as == 'specified_parent':
                if not target_parent_id:
                    raise ValueError("Target parent ID is required when restore_as is 'specified_parent'.")
                try:
                    target_parent = script.scenes.get(id=target_parent_id, is_deleted=False)
                except Scene.DoesNotExist:
                    raise ValueError(f"Specified parent scene ID {target_parent_id} does not exist or is not active.")
                if target_parent.parent_scene_id is not None:
                    raise ValueError("Target parent cannot be a sub-scene; it must be an active main scene.")
                scene.parent_scene = target_parent
                message_notes.append(f"attached to main scene {target_parent.display_number or target_parent.scene_number}")
            elif restore_as == 'auto':
                # Automatic / original parent resolution
                resolved_parent = None

                # Search by UUID first if present
                if scene.original_parent_uuid:
                    parent_matches = list(script.scenes.filter(
                        scene_uuid=scene.original_parent_uuid,
                        is_deleted=False,
                        parent_scene__isnull=True
                    ))
                    if len(parent_matches) == 1:
                        resolved_parent = parent_matches[0]
                    elif len(parent_matches) > 1:
                        raise ValueError(
                            "Original parent resolution is ambiguous (multiple active scenes match original UUID). "
                            "Please choose whether to restore as a main scene or select an active parent."
                        )
                elif scene.parent_scene_id:
                    # Fallback to parent_scene_id ONLY if original_parent_uuid is missing
                    try:
                        candidate_parent = script.scenes.get(id=scene.parent_scene_id)
                        if not candidate_parent.is_deleted and candidate_parent.parent_scene_id is None:
                            resolved_parent = candidate_parent
                    except Scene.DoesNotExist:
                        resolved_parent = None

                if resolved_parent:
                    scene.parent_scene = resolved_parent
                    message_notes.append(f"restored under parent scene {resolved_parent.display_number or resolved_parent.scene_number}")
                else:
                    # Check if original parent is in trash or completely missing
                    is_parent_trashed = False
                    if scene.original_parent_uuid:
                        is_parent_trashed = script.scenes.filter(scene_uuid=scene.original_parent_uuid, is_deleted=True).exists()
                    elif scene.parent_scene_id:
                        is_parent_trashed = script.scenes.filter(id=scene.parent_scene_id, is_deleted=True).exists()

                    parent_state_str = "in Trash" if is_parent_trashed else "missing"
                    raise ValueError(
                        f"Original parent scene is {parent_state_str}. "
                        "Please choose whether to restore as a main scene or attach to an active main scene."
                    )
            else:
                raise ValueError(f"Invalid restore_as option: '{restore_as}'. Must be 'auto', 'main_scene', or 'specified_parent'.")
        else:
            scene.parent_scene = None

        # 2. Intercut Source Resolution
        if scene.is_intercut or scene.original_intercut_source_uuid or scene.intercut_source_id:
            resolved_source = None

            if scene.original_intercut_source_uuid:
                source_matches = list(script.scenes.filter(
                    scene_uuid=scene.original_intercut_source_uuid,
                    is_deleted=False
                ))
                if len(source_matches) == 1:
                    resolved_source = source_matches[0]
                elif len(source_matches) > 1:
                    # Ambiguous UUID matches
                    resolved_source = None
            elif scene.intercut_source_id:
                try:
                    cand_source = script.scenes.get(id=scene.intercut_source_id)
                    if not cand_source.is_deleted:
                        resolved_source = cand_source
                except Scene.DoesNotExist:
                    resolved_source = None

            if resolved_source and resolved_source.id != scene.id:
                scene.is_intercut = True
                scene.intercut_source = resolved_source
            else:
                # Revert to normal scene
                scene.is_intercut = False
                scene.intercut_source = None
                intercut_fallback = True
                message_notes.append("intercut source could not be resolved, restored as a normal scene")

        # 3. Order Placement
        all_active_scenes = list(script.scenes.filter(is_deleted=False).order_by('order', 'id'))

        target_order = None
        if scene.original_order is not None and 0 <= scene.original_order <= len(all_active_scenes):
            target_order = scene.original_order
        else:
            target_order = len(all_active_scenes)

        # Shift active scenes at or after target_order by +1
        for act_sc in all_active_scenes:
            if act_sc.order >= target_order:
                act_sc.order += 1
                act_sc.save(update_fields=['order'])

        # 4. Update Scene State
        scene.is_deleted = False
        scene.deleted_at = None
        scene.order = target_order
        scene.save(update_fields=[
            'is_deleted',
            'deleted_at',
            'order',
            'parent_scene',
            'is_intercut',
            'intercut_source'
        ])

        # 5. Resequence Screenplay
        resequence_script_scenes(script)
        scene.refresh_from_db()
        script.updated_at = timezone.now()
        script.save(update_fields=['updated_at'])

        summary_msg = f"Scene restored successfully ({', '.join(message_notes)})." if message_notes else "Scene restored successfully."
        return scene, intercut_fallback, summary_msg

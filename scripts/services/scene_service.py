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
                for sub in item.sub_scenes.filter(is_intercut=False).order_by('order', 'id'):
                    if sub.id not in seen_ids:
                        ordered_scenes.append(sub)
                        seen_ids.add(sub.id)

        # Include any remaining scenes if any
        all_remaining = script.scenes.exclude(id__in=seen_ids).order_by('order', 'id')
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
                    sc.scene_number = source.scene_number if source else sc.scene_number
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
        parents = script.scenes.filter(parent_scene__isnull=True)
        for parent_sc in parents:
            sub_scenes = list(parent_sc.sub_scenes.all().order_by('order', 'id'))
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
        all_scenes = list(script.scenes.all().order_by('order', 'id'))
        try:
            ref_idx = [s.id for s in all_scenes].index(source_scene.id)
            insert_order = ref_idx + 1
        except ValueError:
            insert_order = len(all_scenes)

        for s in all_scenes:
            if s.order >= insert_order:
                s.order += 1
                s.save(update_fields=['order'])

        if source_scene.is_sub_scene and source_scene.parent_scene:
            parent = source_scene.parent_scene
            siblings = list(parent.sub_scenes.all().order_by('order', 'id'))

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
            main_scenes = list(script.scenes.filter(parent_scene__isnull=True).order_by('order', 'id'))

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

            # If source_scene has sub-scenes, clone each sub-scene and its elements under new_main
            for sub_sc in source_scene.sub_scenes.all().order_by('order', 'id'):
                new_cloned_sub = Scene.objects.create(
                    script=script,
                    parent_scene=new_main,
                    scene_number=new_main.scene_number,
                    heading=sub_sc.heading,
                    summary=sub_sc.summary,
                    order=sub_sc.order,
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
                ref_scene = script.scenes.get(id=reference_scene_id)
            except Scene.DoesNotExist:
                ref_scene = None

        all_scenes = list(script.scenes.all().order_by('order', 'id'))

        if ref_scene:
            try:
                ref_index = [s.id for s in all_scenes].index(ref_scene.id)
                target_order = ref_index if position == 'before' else ref_index + 1
            except ValueError:
                target_order = len(all_scenes)
        else:
            target_order = len(all_scenes)

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
        ScriptElement.objects.create(scene=new_scene, element_type='scene_heading', content=heading, order=0)
        ScriptElement.objects.create(scene=new_scene, element_type='action', content='', order=1)

        # Resequence to guarantee clean numbering
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
        parent = script.scenes.get(id=parent_scene_id)
        if parent.parent_scene:
            parent = parent.parent_scene

        # Find the last sub-scene of this parent or the parent itself
        last_sub = parent.sub_scenes.all().order_by('-order', '-id').first()
        ref_scene = last_sub if last_sub else parent

        all_scenes = list(script.scenes.all().order_by('order', 'id'))
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
        source_scene = script.scenes.get(id=source_scene_id)
        parent = source_scene.parent_scene if source_scene.parent_scene else source_scene

        all_scenes = list(script.scenes.all().order_by('order', 'id'))
        current_scene = None
        if current_scene_id:
            try:
                current_scene = script.scenes.get(id=current_scene_id)
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
        source_scene = script.scenes.get(id=source_scene_id)

        all_scenes = list(script.scenes.all().order_by('order', 'id'))
        current_scene = None
        if current_scene_id:
            try:
                current_scene = script.scenes.get(id=current_scene_id)
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
    - Intercut sub-scene / Main scene: moves within screenplay top order.
    """
    with transaction.atomic():
        try:
            scene = script.scenes.get(id=scene_id)
        except Scene.DoesNotExist:
            return False

        if scene.is_sub_scene and not scene.is_intercut:
            # Standard sub-scene: move within parent's sub-scenes only
            siblings = list(scene.parent_scene.sub_scenes.filter(is_intercut=False).order_by('order', 'id'))
            try:
                idx = siblings.index(scene)
            except ValueError:
                return False

            if direction == 'up' and idx > 0:
                target = siblings[idx - 1]
                scene.order, target.order = target.order, scene.order
                scene.save(update_fields=['order'])
                target.save(update_fields=['order'])
            elif direction == 'down' and idx < len(siblings) - 1:
                target = siblings[idx + 1]
                scene.order, target.order = target.order, scene.order
                scene.save(update_fields=['order'])
                target.save(update_fields=['order'])
            else:
                return False
        else:
            # Main scene, intercut scene, or intercut sub-scene
            all_scenes = list(script.scenes.all().order_by('order', 'id'))
            try:
                idx = all_scenes.index(scene)
            except ValueError:
                return False

            if direction == 'up' and idx > 0:
                target = all_scenes[idx - 1]
                scene.order, target.order = target.order, scene.order
                scene.save(update_fields=['order'])
                target.save(update_fields=['order'])
            elif direction == 'down' and idx < len(all_scenes) - 1:
                target = all_scenes[idx + 1]
                scene.order, target.order = target.order, scene.order
                scene.save(update_fields=['order'])
                target.save(update_fields=['order'])
            else:
                return False

        resequence_script_scenes(script)
        script.updated_at = timezone.now()
        script.save(update_fields=['updated_at'])
        return True


def serialize_scenes_hierarchy(script: Script) -> list:
    """
    Returns a structured list of scenes for navigation, sidebars, and mobile menus.
    """
    ordered_scenes = list(script.scenes.all().prefetch_related('parent_scene', 'elements').order_by('order', 'id'))
    result = []
    
    for sc in ordered_scenes:
        result.append({
            'id': sc.id,
            'parent_scene_id': sc.parent_scene_id,
            'is_sub_scene': sc.is_sub_scene,
            'is_duplicate': sc.is_duplicate,
            'duplicate_number': sc.duplicate_number,
            'is_intercut': sc.is_intercut,
            'scene_number': sc.scene_number,
            'scene_identifier': sc.scene_identifier,
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

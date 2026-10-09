import json
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.utils import timezone
from .models import Script, Scene, ScriptElement, Character
from .services.scene_service import (
    resequence_script_scenes,
    insert_scene_relative,
    create_sub_scene,
    create_sub_scene_2,
    create_intercut_scene,
    duplicate_scene,
    move_scene,
    serialize_scenes_hierarchy,
)


def get_user_script(user, script_id):
    """Enforce strict ownership: user can only access their own scripts."""
    return get_object_or_404(Script, id=script_id, user=user)


@login_required
@require_http_methods(["GET"])
def api_get_scene(request, script_id, scene_id):
    script = get_user_script(request.user, script_id)
    scene = get_object_or_404(Scene, id=scene_id, script=script)

    elements_data = []
    for elem in scene.elements.all().order_by('order', 'id'):
        elements_data.append({
            'id': elem.id,
            'element_type': elem.element_type,
            'content': elem.content,
            'order': elem.order,
        })

    # If scene has no elements yet, seed with initial Scene Heading and Action
    if not elements_data:
        elem1 = ScriptElement.objects.create(scene=scene, element_type='scene_heading', content=scene.heading, order=0)
        elem2 = ScriptElement.objects.create(scene=scene, element_type='action', content='', order=1)
        elements_data = [
            {'id': elem1.id, 'element_type': elem1.element_type, 'content': elem1.content, 'order': elem1.order},
            {'id': elem2.id, 'element_type': elem2.element_type, 'content': elem2.content, 'order': elem2.order},
        ]

    characters = list(script.characters.values_list('name', flat=True))

    return JsonResponse({
        'status': 'ok',
        'scene': {
            'id': scene.id,
            'parent_scene_id': scene.parent_scene_id,
            'is_sub_scene': scene.is_sub_scene,
            'is_intercut': scene.is_intercut,
            'intercut_source_id': scene.intercut_source_id,
            'scene_number': scene.scene_number,
            'scene_identifier': scene.scene_identifier,
            'display_number': scene.display_number,
            'display_number_formatted': scene.display_number_formatted,
            'full_display_heading': scene.full_display_heading,
            'clean_heading': scene.clean_heading,
            'heading': scene.heading,
            'transition': scene.transition or 'CUT TO',
            'summary': scene.summary,
            'order': scene.order,
        },
        'elements': elements_data,
        'characters': characters,
        'scenes_tree': serialize_scenes_hierarchy(script),
        'script_stats': {
            'word_count': script.word_count,
            'char_count': script.char_count,
            'scene_count': script.scene_count,
            'primary_scene_count': script.primary_scene_count,
            'sub_scene_count': script.sub_scene_count,
            'estimated_pages': script.estimated_pages,
        }
    })


@login_required
@require_http_methods(["POST"])
def api_save_scene(request, script_id, scene_id):
    """Atomic auto-save endpoint for scene heading and elements."""
    script = get_user_script(request.user, script_id)
    scene = get_object_or_404(Scene, id=scene_id, script=script)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON format'}, status=400)

    heading = data.get('heading', scene.heading).strip()
    elements = data.get('elements', [])

    try:
        with transaction.atomic():
            if heading:
                scene.heading = heading
            if 'summary' in data:
                scene.summary = data.get('summary', '')
            if 'transition' in data:
                scene.transition = data.get('transition', 'CUT TO').strip() or 'CUT TO'
            scene.save()

            # Update or recreate elements
            scene.elements.all().delete()
            new_elements = []
            for idx, elem in enumerate(elements):
                el_type = elem.get('element_type', 'action')
                el_content = elem.get('content', '')
                new_elements.append(
                    ScriptElement(
                        scene=scene,
                        element_type=el_type,
                        content=el_content,
                        order=idx
                    )
                )
            if new_elements:
                ScriptElement.objects.bulk_create(new_elements)

            # Touch script's updated_at
            script.updated_at = timezone.now()
            script.save(update_fields=['updated_at'])

        return JsonResponse({
            'status': 'ok',
            'scene_id': scene.id,
            'scene_identifier': scene.scene_identifier,
            'display_number': scene.display_number,
            'display_number_formatted': scene.display_number_formatted,
            'full_display_heading': scene.full_display_heading,
            'clean_heading': scene.clean_heading,
            'heading': scene.heading,
            'transition': scene.transition or 'CUT TO',
            'updated_at': script.updated_at.strftime('%H:%M:%S'),
            'script_stats': {
                'word_count': script.word_count,
                'char_count': script.char_count,
                'scene_count': script.scene_count,
                'primary_scene_count': script.primary_scene_count,
                'sub_scene_count': script.sub_scene_count,
                'estimated_pages': script.estimated_pages,
            }
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Failed to save scene: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["POST"])
def api_create_scene(request, script_id):
    """Creates a new scene appended at the end of the script."""
    script = get_user_script(request.user, script_id)
    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        data = {}

    heading = data.get('heading', 'INT. LOCATION - DAY').strip()
    summary = data.get('summary', '').strip()

    new_scene = insert_scene_relative(script, reference_scene_id=None, position='after', heading=heading, summary=summary)

    return JsonResponse({
        'status': 'ok',
        'scene': {
            'id': new_scene.id,
            'parent_scene_id': new_scene.parent_scene_id,
            'is_sub_scene': new_scene.is_sub_scene,
            'is_intercut': new_scene.is_intercut,
            'scene_number': new_scene.scene_number,
            'scene_identifier': new_scene.scene_identifier,
            'display_number': new_scene.display_number,
            'display_number_formatted': new_scene.display_number_formatted,
            'full_display_heading': new_scene.full_display_heading,
            'clean_heading': new_scene.clean_heading,
            'heading': new_scene.heading,
            'transition': new_scene.transition or 'CUT TO',
            'order': new_scene.order,
        },
        'scenes_tree': serialize_scenes_hierarchy(script),
    })


@login_required
@require_http_methods(["POST"])
def api_insert_scene(request, script_id):
    """Inserts a scene before or after a specified reference scene."""
    script = get_user_script(request.user, script_id)
    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    reference_scene_id = data.get('reference_scene_id')
    position = data.get('position', 'after')
    heading = data.get('heading', 'INT. LOCATION - DAY').strip()
    summary = data.get('summary', '').strip()

    if reference_scene_id:
        get_object_or_404(Scene, id=reference_scene_id, script=script)

    new_scene = insert_scene_relative(
        script,
        reference_scene_id=reference_scene_id,
        position=position,
        heading=heading,
        summary=summary
    )

    return JsonResponse({
        'status': 'ok',
        'scene': {
            'id': new_scene.id,
            'parent_scene_id': new_scene.parent_scene_id,
            'is_sub_scene': new_scene.is_sub_scene,
            'is_intercut': new_scene.is_intercut,
            'scene_number': new_scene.scene_number,
            'scene_identifier': new_scene.scene_identifier,
            'display_number': new_scene.display_number,
            'display_number_formatted': new_scene.display_number_formatted,
            'full_display_heading': new_scene.full_display_heading,
            'clean_heading': new_scene.clean_heading,
            'heading': new_scene.heading,
            'transition': new_scene.transition or 'CUT TO',
            'order': new_scene.order,
        },
        'scenes_tree': serialize_scenes_hierarchy(script),
    })


@login_required
@require_http_methods(["POST"])
def api_create_sub_scene(request, script_id, parent_scene_id):
    """Creates a sub-scene (e.g. Scene 3A) under a parent scene."""
    script = get_user_script(request.user, script_id)
    parent_scene = get_object_or_404(Scene, id=parent_scene_id, script=script)

    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        data = {}

    heading = data.get('heading', f'{parent_scene.heading} - SUB SCENE').strip()
    summary = data.get('summary', '').strip()

    new_sub_scene = create_sub_scene(script, parent_scene_id=parent_scene.id, heading=heading, summary=summary)

    return JsonResponse({
        'status': 'ok',
        'scene': {
            'id': new_sub_scene.id,
            'parent_scene_id': new_sub_scene.parent_scene_id,
            'is_sub_scene': new_sub_scene.is_sub_scene,
            'is_intercut': new_sub_scene.is_intercut,
            'scene_number': new_sub_scene.scene_number,
            'scene_identifier': new_sub_scene.scene_identifier,
            'display_number': new_sub_scene.display_number,
            'display_number_formatted': new_sub_scene.display_number_formatted,
            'full_display_heading': new_sub_scene.full_display_heading,
            'clean_heading': new_sub_scene.clean_heading,
            'heading': new_sub_scene.heading,
            'transition': new_sub_scene.transition or 'CUT TO',
            'order': new_sub_scene.order,
        },
        'scenes_tree': serialize_scenes_hierarchy(script),
    })


@login_required
@require_http_methods(["POST"])
def api_create_sub_scene_2(request, script_id):
    """Creates a sub-scene associated with a previously selected scene (e.g. Scene 2.A), placed at the current position."""
    script = get_user_script(request.user, script_id)
    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    source_scene_id = data.get('source_scene_id')
    current_scene_id = data.get('current_scene_id')

    if not source_scene_id:
        return JsonResponse({'status': 'error', 'message': 'Source scene ID is required'}, status=400)

    get_object_or_404(Scene, id=source_scene_id, script=script)
    if current_scene_id:
        get_object_or_404(Scene, id=current_scene_id, script=script)

    new_sub = create_sub_scene_2(script, source_scene_id=source_scene_id, current_scene_id=current_scene_id)

    return JsonResponse({
        'status': 'ok',
        'scene': {
            'id': new_sub.id,
            'parent_scene_id': new_sub.parent_scene_id,
            'is_sub_scene': new_sub.is_sub_scene,
            'is_intercut': new_sub.is_intercut,
            'scene_number': new_sub.scene_number,
            'scene_identifier': new_sub.scene_identifier,
            'display_number': new_sub.display_number,
            'display_number_formatted': new_sub.display_number_formatted,
            'full_display_heading': new_sub.full_display_heading,
            'clean_heading': new_sub.clean_heading,
            'heading': new_sub.heading,
            'transition': new_sub.transition or 'CUT TO',
            'order': new_sub.order,
        },
        'scenes_tree': serialize_scenes_hierarchy(script),
    })


@login_required
@require_http_methods(["POST"])
def api_create_intercut(request, script_id):
    """Creates a new intercut scene instance copied from a source scene, placed at the current position."""
    script = get_user_script(request.user, script_id)
    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    source_scene_id = data.get('source_scene_id')
    current_scene_id = data.get('current_scene_id')

    if not source_scene_id:
        return JsonResponse({'status': 'error', 'message': 'Source scene ID is required'}, status=400)

    get_object_or_404(Scene, id=source_scene_id, script=script)
    if current_scene_id:
        get_object_or_404(Scene, id=current_scene_id, script=script)

    new_scene = create_intercut_scene(script, source_scene_id=source_scene_id, current_scene_id=current_scene_id)

    return JsonResponse({
        'status': 'ok',
        'scene': {
            'id': new_scene.id,
            'parent_scene_id': new_scene.parent_scene_id,
            'is_sub_scene': new_scene.is_sub_scene,
            'is_intercut': new_scene.is_intercut,
            'intercut_source_id': new_scene.intercut_source_id,
            'scene_number': new_scene.scene_number,
            'scene_identifier': new_scene.scene_identifier,
            'display_number': new_scene.display_number,
            'display_number_formatted': new_scene.display_number_formatted,
            'full_display_heading': new_scene.full_display_heading,
            'clean_heading': new_scene.clean_heading,
            'heading': new_scene.heading,
            'transition': new_scene.transition or 'CUT TO',
            'order': new_scene.order,
        },
        'scenes_tree': serialize_scenes_hierarchy(script),
    })


@login_required
@require_http_methods(["POST"])
def api_move_scene(request, script_id, scene_id):
    """Moves a scene or sub-scene up or down among its immediate siblings."""
    script = get_user_script(request.user, script_id)
    scene = get_object_or_404(Scene, id=scene_id, script=script)

    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    direction = data.get('direction', 'up')
    if direction not in ['up', 'down']:
        return JsonResponse({'status': 'error', 'message': 'Direction must be up or down'}, status=400)

    moved = move_scene(script, scene_id=scene.id, direction=direction)

    return JsonResponse({
        'status': 'ok' if moved else 'noop',
        'scenes_tree': serialize_scenes_hierarchy(script),
    })


@login_required
@require_http_methods(["POST"])
def api_duplicate_scene(request, script_id, scene_id):
    script = get_user_script(request.user, script_id)
    source_scene = get_object_or_404(Scene, id=scene_id, script=script)

    new_scene = duplicate_scene(script, source_scene)

    return JsonResponse({
        'status': 'ok',
        'scene': {
            'id': new_scene.id,
            'parent_scene_id': new_scene.parent_scene_id,
            'is_sub_scene': new_scene.is_sub_scene,
            'is_duplicate': new_scene.is_duplicate,
            'duplicate_number': new_scene.duplicate_number,
            'scene_number': new_scene.scene_number,
            'display_number': new_scene.display_number,
            'display_number_formatted': new_scene.display_number_formatted,
            'heading': new_scene.heading,
            'order': new_scene.order,
        },
        'scenes_tree': serialize_scenes_hierarchy(script),
    })


@login_required
@require_http_methods(["POST"])
def api_delete_scene(request, script_id, scene_id):
    script = get_user_script(request.user, script_id)
    scene = get_object_or_404(Scene, id=scene_id, script=script)

    # Don't delete if it's the last remaining main scene and there are no other scenes
    if script.scenes.count() <= 1:
        return JsonResponse({
            'status': 'error',
            'message': 'Cannot delete the only scene in the script. You can edit its contents instead.'
        }, status=400)

    # Determine a safe adjacent scene to switch to
    ordered_scenes = script.get_ordered_scenes()
    current_idx = -1
    for i, s in enumerate(ordered_scenes):
        if s.id == scene.id:
            current_idx = i
            break

    fallback_scene_id = None
    if current_idx > 0:
        fallback_scene_id = ordered_scenes[current_idx - 1].id
    elif current_idx + 1 < len(ordered_scenes):
        fallback_scene_id = ordered_scenes[current_idx + 1].id

    with transaction.atomic():
        scene.delete()
        resequence_script_scenes(script)
        script.updated_at = timezone.now()
        script.save(update_fields=['updated_at'])

    return JsonResponse({
        'status': 'ok',
        'fallback_scene_id': fallback_scene_id,
        'scenes_tree': serialize_scenes_hierarchy(script),
    })


@login_required
@require_http_methods(["POST"])
def api_reorder_scenes(request, script_id):
    script = get_user_script(request.user, script_id)
    try:
        data = json.loads(request.body)
        scene_ids = data.get('scene_ids', [])
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    with transaction.atomic():
        for order_idx, sc_id in enumerate(scene_ids):
            Scene.objects.filter(id=sc_id, script=script, parent_scene__isnull=True).update(
                order=order_idx
            )
        resequence_script_scenes(script)
        script.updated_at = timezone.now()
        script.save(update_fields=['updated_at'])

    return JsonResponse({
        'status': 'ok',
        'scenes_tree': serialize_scenes_hierarchy(script),
    })


@login_required
@require_http_methods(["GET"])
def api_get_scenes_tree(request, script_id):
    script = get_user_script(request.user, script_id)
    return JsonResponse({
        'status': 'ok',
        'scenes_tree': serialize_scenes_hierarchy(script),
        'script_stats': {
            'word_count': script.word_count,
            'char_count': script.char_count,
            'scene_count': script.scene_count,
            'primary_scene_count': script.primary_scene_count,
            'sub_scene_count': script.sub_scene_count,
            'estimated_pages': script.estimated_pages,
        }
    })


@login_required
@require_http_methods(["GET"])
def api_get_characters(request, script_id):
    script = get_user_script(request.user, script_id)
    names = list(script.characters.values_list('name', flat=True))
    return JsonResponse({'status': 'ok', 'characters': names})

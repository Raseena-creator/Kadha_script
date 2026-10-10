import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, Http404, JsonResponse, HttpResponseNotAllowed
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from .models import Script, Scene, ScriptElement, Character, ScriptNote, ScriptVersion, ScriptTitlePage
from .forms import ScriptForm, CharacterForm, ScriptNoteForm, ScriptVersionForm, SceneForm, ScriptTitlePageForm
from .services.pdf_export import generate_screenplay_pdf
from .services.docx_export import generate_screenplay_docx
from .services.txt_export import generate_screenplay_txt
from .services.version_service import create_version_snapshot, restore_version_snapshot


def get_user_script(user, script_id, allow_deleted=False):
    """
    Enforce strict user ownership and active status.
    By default, returns only active (non-deleted) screenplays owned by user.
    When allow_deleted=True, permits access to trashed screenplays still owned by user.
    """
    if allow_deleted:
        return get_object_or_404(Script, id=script_id, user=user)
    return get_object_or_404(Script, id=script_id, user=user, is_deleted=False)

@login_required
def script_list_view(request):
    scripts = Script.objects.filter(user=request.user, is_deleted=False).prefetch_related('scenes__elements', 'characters')
    
    # Filtering
    query = request.GET.get('q', '').strip()
    genre = request.GET.get('genre', '').strip()
    script_type = request.GET.get('type', '').strip()

    if query:
        scripts = scripts.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(author_name__icontains=query)
        )
    if genre:
        scripts = scripts.filter(genre=genre)
    if script_type:
        scripts = scripts.filter(script_type=script_type)

    return render(request, 'scripts/script_list.html', {
        'scripts': scripts.order_by('-updated_at'),
        'query': query,
        'genre': genre,
        'script_type': script_type,
        'genres': Script.GENRE_CHOICES,
        'script_types': Script.SCRIPT_TYPE_CHOICES,
        'total_count': Script.objects.filter(user=request.user, is_deleted=False).count(),
    })


@login_required
def script_trash_view(request):
    """
    Project Trash view.
    Retrieves and displays soft-deleted screenplays owned by the current authenticated user.
    Strictly read-only; active projects are never displayed.
    """
    trashed_scripts = Script.objects.filter(
        user=request.user,
        is_deleted=True
    ).order_by('-deleted_at')

    return render(request, 'scripts/script_trash.html', {
        'trashed_scripts': trashed_scripts,
        'total_trashed': trashed_scripts.count(),
    })


@login_required
def script_create_view(request):
    if request.method == 'POST':
        form = ScriptForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                script = form.save(commit=False)
                script.user = request.user
                if not script.author_name:
                    script.author_name = request.user.profile.pen_name or request.user.get_full_name() or request.user.username
                script.save()

                # Seed with Scene 1 automatically
                scene1 = Scene.objects.create(
                    script=script,
                    scene_number=1,
                    heading='INT. HOUSE - NIGHT',
                    summary='',
                    order=0
                )
                # Seed initial elements
                ScriptElement.objects.create(scene=scene1, element_type='scene_heading', content='INT. HOUSE - NIGHT', order=0)
                ScriptElement.objects.create(scene=scene1, element_type='action', content='മഴ ശക്തമായി പെയ്യുന്നു.', order=1)

                # Create initial version snapshot
                create_version_snapshot(script, title='Initial Draft')

            messages.success(request, f'Script "{script.title}" created successfully!')
            return redirect('script_editor', script_id=script.id)
    else:
        initial = {}
        if hasattr(request.user, 'profile') and request.user.profile.pen_name:
            initial['author_name'] = request.user.profile.pen_name
        form = ScriptForm(initial=initial)
    
    return render(request, 'scripts/script_create.html', {'form': form})


@login_required
def script_detail_view(request, script_id):
    """Compatibility redirect: Script Overview is removed from user flow; redirect directly to editor."""
    script = get_user_script(request.user, script_id)
    return redirect('script_editor', script_id=script.id)


@login_required
def script_edit_metadata_view(request, script_id):
    script = get_user_script(request.user, script_id)
    if request.method == 'POST':
        form = ScriptForm(request.POST, instance=script)
        if form.is_valid():
            form.save()
            messages.success(request, f'Script "{script.title}" details updated.')
            return redirect('script_editor', script_id=script.id)
    else:
        form = ScriptForm(instance=script)
    return render(request, 'scripts/script_edit_metadata.html', {'form': form, 'script': script})


@login_required
def script_title_page_view(request, script_id):
    """Manages dedicated title page configuration and production metadata for a script."""
    script = get_user_script(request.user, script_id)
    title_page, created = ScriptTitlePage.objects.get_or_create(
        script=script,
        defaults={
            'title': '',
            'author_name': script.author_name or (request.user.profile.pen_name if hasattr(request.user, 'profile') else (request.user.get_full_name() or request.user.username)),
        }
    )

    if request.method == 'POST':
        form = ScriptTitlePageForm(request.POST, instance=title_page)
        if form.is_valid():
            form.save()
            messages.success(request, 'Title Page & Production Metadata saved successfully!')
            return redirect('script_title_page', script_id=script.id)
        else:
            messages.error(request, 'Please correct the errors in the form below.')
    else:
        form = ScriptTitlePageForm(instance=title_page)

    return render(request, 'scripts/script_title_page.html', {
        'script': script,
        'title_page': title_page,
        'form': form,
    })


@login_required
def script_duplicate_view(request, script_id):
    """Creates a complete and independent copy of an entire screenplay."""
    original_script = get_user_script(request.user, script_id)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                duplicate_title = f"{original_script.title} (Copy)"
                dup_script = Script.objects.create(
                    user=request.user,
                    title=duplicate_title,
                    description=original_script.description,
                    genre=original_script.genre,
                    script_type=original_script.script_type,
                    author_name=original_script.author_name,
                    language=original_script.language,
                )

                # Duplicate Title Page metadata if present
                if hasattr(original_script, 'title_page') and original_script.title_page:
                    tp = original_script.title_page
                    ScriptTitlePage.objects.create(
                        script=dup_script,
                        title=f"{tp.title} (Copy)" if tp.title else "",
                        subtitle=tp.subtitle,
                        author_name=tp.author_name,
                        pen_name=tp.pen_name,
                        adaptation_credits=tp.adaptation_credits,
                        copyright_registration=tp.copyright_registration,
                        draft_revision=tp.draft_revision,
                        draft_date=tp.draft_date,
                        contact_name=tp.contact_name,
                        contact_email=tp.contact_email,
                        contact_phone=tp.contact_phone,
                    )

                # Duplicate Main Scenes and Script Elements
                scene_mapping = {}
                main_scenes = original_script.scenes.filter(parent_scene__isnull=True).order_by('order', 'id')
                for sc in main_scenes:
                    dup_scene = Scene.objects.create(
                        script=dup_script,
                        parent_scene=None,
                        scene_number=sc.scene_number,
                        is_duplicate=sc.is_duplicate,
                        duplicate_number=sc.duplicate_number,
                        heading=sc.heading,
                        summary=sc.summary,
                        order=sc.order,
                    )
                    scene_mapping[sc.id] = dup_scene

                    new_elements = [
                        ScriptElement(
                            scene=dup_scene,
                            element_type=elem.element_type,
                            content=elem.content,
                            order=elem.order,
                        )
                        for elem in sc.elements.all().order_by('order')
                    ]
                    if new_elements:
                        ScriptElement.objects.bulk_create(new_elements)

                    # Duplicate Sub-scenes
                    for sub in sc.sub_scenes.all().order_by('order', 'id'):
                        dup_sub = Scene.objects.create(
                            script=dup_script,
                            parent_scene=dup_scene,
                            scene_number=sub.scene_number,
                            is_duplicate=sub.is_duplicate,
                            duplicate_number=sub.duplicate_number,
                            heading=sub.heading,
                            summary=sub.summary,
                            order=sub.order,
                        )
                        sub_elements = [
                            ScriptElement(
                                scene=dup_sub,
                                element_type=elem.element_type,
                                content=elem.content,
                                order=elem.order,
                            )
                            for elem in sub.elements.all().order_by('order')
                        ]
                        if sub_elements:
                            ScriptElement.objects.bulk_create(sub_elements)

                # Duplicate Characters
                for char in original_script.characters.all():
                    Character.objects.create(
                        script=dup_script,
                        name=char.name,
                        age=char.age,
                        gender=char.gender,
                        description=char.description,
                        notes=char.notes,
                    )

                # Duplicate Notes
                for note in original_script.notes.all():
                    ScriptNote.objects.create(
                        script=dup_script,
                        title=note.title,
                        category=note.category,
                        content=note.content,
                    )

                # Initial version snapshot for the duplicate
                create_version_snapshot(dup_script, title='Initial Duplication Snapshot')

            messages.success(request, f'Script "{original_script.title}" duplicated successfully as "{dup_script.title}".')
            return redirect('script_editor', script_id=dup_script.id)
        except Exception as e:
            messages.error(request, f'Failed to duplicate script: {str(e)}')
            return redirect('script_editor', script_id=original_script.id)

    return redirect('script_editor', script_id=original_script.id)



@login_required
def script_delete_view(request, script_id):
    script = get_user_script(request.user, script_id)
    if request.method == 'POST':
        title = script.title
        with transaction.atomic():
            script.is_deleted = True
            script.deleted_at = timezone.now()
            script.save(update_fields=['is_deleted', 'deleted_at'])
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            total_scripts = Script.objects.filter(user=request.user, is_deleted=False).count()
            total_scenes = Scene.objects.filter(script__user=request.user, script__is_deleted=False, is_deleted=False, is_intercut=False).count()
            return JsonResponse({
                'status': 'ok',
                'message': f'Script "{title}" moved to Trash.',
                'total_scripts': total_scripts,
                'total_scenes': total_scenes
            })
        messages.success(request, f'Script "{title}" moved to Trash.')
        return redirect('script_list')
    return render(request, 'scripts/script_confirm_delete.html', {'script': script})


@login_required
def script_restore_view(request, script_id):
    """
    Safely restores a soft-deleted screenplay owned by the authenticated user from Trash.
    Accepts POST requests only.
    Sets is_deleted=False and clears deleted_at.
    Preserves all scenes, elements, characters, notes, title-page, versions, and backup logs.
    Preserves scene Trash states (does not reactivate independently trashed scenes).
    Checks for active screenplays with duplicate titles and displays an informative warning.
    """
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    # Enforce strict user ownership, allowing retrieval of trashed scripts
    script = get_user_script(request.user, script_id, allow_deleted=True)

    # Reject already active screenplay
    if not script.is_deleted:
        messages.info(request, f'Script "{script.title}" is already active.')
        return redirect('dashboard')

    with transaction.atomic():
        script.is_deleted = False
        script.deleted_at = None
        script.save(update_fields=['is_deleted', 'deleted_at'])

    # Check if another active screenplay owned by this user has the exact same title
    has_title_collision = Script.objects.filter(
        user=request.user,
        is_deleted=False,
        title=script.title
    ).exclude(id=script.id).exists()

    if has_title_collision:
        messages.warning(
            request,
            f'Screenplay "{script.title}" restored successfully. Note: You already have another active screenplay with the same title.'
        )
    else:
        messages.success(request, f'Screenplay "{script.title}" restored successfully.')

    return redirect('dashboard')


@login_required
def script_rename_view(request, script_id):
    """Update screenplay title directly from homepage/dashboard."""
    script = get_user_script(request.user, script_id)
    if request.method == 'POST':
        new_title = request.POST.get('title', '').strip()
        if not new_title and request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
                new_title = (data.get('title') or '').strip()
            except Exception:
                pass

        if not new_title:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
                return JsonResponse({'status': 'error', 'message': 'Screenplay title cannot be empty.'}, status=400)
            messages.error(request, 'Screenplay title cannot be empty.')
            return redirect('dashboard')

        script.title = new_title
        script.save(update_fields=['title', 'updated_at'])

        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({'status': 'ok', 'title': script.title, 'script_id': script.id})

        messages.success(request, f'Screenplay renamed to "{script.title}".')
        return redirect('dashboard')

    return redirect('dashboard')


@login_required
def script_editor_view(request, script_id):
    """The dedicated writing platform for screenwriters."""
    script = get_user_script(request.user, script_id)
    scenes = script.get_ordered_scenes()

    # If no scenes exist, create one
    if not scenes:
        sc = Scene.objects.create(script=script, scene_number=1, heading='INT. HOUSE - NIGHT', order=0)
        ScriptElement.objects.create(scene=sc, element_type='scene_heading', content='INT. HOUSE - NIGHT', order=0)
        ScriptElement.objects.create(scene=sc, element_type='action', content='', order=1)
        scenes = script.get_ordered_scenes()

    target_scene_id = request.GET.get('scene')
    current_scene = None
    if target_scene_id:
        try:
            target_id_int = int(target_scene_id)
            current_scene = next((s for s in scenes if s.id == target_id_int), None)
        except (ValueError, TypeError):
            current_scene = None
    if not current_scene:
        current_scene = scenes[0]

    characters = list(script.characters.values_list('name', flat=True))

    return render(request, 'scripts/editor.html', {
        'script': script,
        'scenes': scenes,
        'current_scene': current_scene,
        'characters': characters,
    })


@login_required
def scenes_management_view(request, script_id):
    """Compatibility redirect: Standalone Scene Management is removed from user flow; redirect directly to editor."""
    return redirect('script_editor', script_id=script_id)


@login_required
def character_management_view(request, script_id):
    """Obsolete standalone character management page - redirect to editor."""
    return redirect('script_editor', script_id=script_id)


@login_required
def notes_view(request, script_id):
    """Obsolete standalone notes page - redirect to editor."""
    return redirect('script_editor', script_id=script_id)


@login_required
def versions_view(request, script_id):
    """Obsolete standalone versions page - redirect to editor."""
    return redirect('script_editor', script_id=script_id)


@login_required
def export_pdf_view(request, script_id):
    script = get_user_script(request.user, script_id)
    include_notes = request.GET.get('notes') == '1'
    pdf_content = generate_screenplay_pdf(script, include_notes=include_notes)
    
    filename = f"{slugify(script.title) or 'script'}_screenplay.pdf"
    response = HttpResponse(pdf_content, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def export_docx_view(request, script_id):
    script = get_user_script(request.user, script_id)
    include_notes = request.GET.get('notes') == '1'
    docx_content = generate_screenplay_docx(script, include_notes=include_notes)
    
    filename = f"{slugify(script.title) or 'script'}_screenplay.docx"
    response = HttpResponse(docx_content, content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def export_txt_view(request, script_id):
    script = get_user_script(request.user, script_id)
    include_notes = request.GET.get('notes') == '1'
    txt_content = generate_screenplay_txt(script, include_notes=include_notes)
    
    filename = f"{slugify(script.title) or 'script'}_screenplay.txt"
    response = HttpResponse(txt_content, content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def print_preview_view(request, script_id):
    script = get_user_script(request.user, script_id)
    scenes = script.get_ordered_scenes()
    return render(request, 'scripts/print_preview.html', {
        'script': script,
        'scenes': scenes,
    })


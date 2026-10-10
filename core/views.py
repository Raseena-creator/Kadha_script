from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
from scripts.models import Script, Scene, ScriptElement, Character, ScriptNote

def landing_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'core/landing.html')

@login_required
def dashboard_view(request):
    user = request.user
    user_scripts = Script.objects.filter(user=user, is_deleted=False)
    
    total_scripts = user_scripts.count()
    total_scenes = Scene.objects.filter(script__user=user, script__is_deleted=False, is_deleted=False, is_intercut=False).count()
    total_primary_scenes = Scene.objects.filter(script__user=user, script__is_deleted=False, is_deleted=False, parent_scene__isnull=True, is_intercut=False).count()
    total_sub_scenes = Scene.objects.filter(script__user=user, script__is_deleted=False, is_deleted=False, parent_scene__isnull=False, is_intercut=False).count()
    
    scripts = user_scripts.annotate(
        num_scenes=Count('scenes', filter=Q(scenes__is_deleted=False, scenes__parent_scene__isnull=True, scenes__is_intercut=False))
    ).order_by('-updated_at')

    return render(request, 'core/dashboard.html', {
        'total_scripts': total_scripts,
        'total_scenes': total_scenes,
        'total_primary_scenes': total_primary_scenes,
        'total_sub_scenes': total_sub_scenes,
        'scripts': scripts,
    })


@login_required
def global_search_view(request):
    """Global script search across titles, scene content, characters, dialogue, notes with Malayalam Unicode."""
    query = request.GET.get('q', '').strip()
    user = request.user

    results = {
        'scripts': [],
        'scenes': [],
        'dialogues': [],
        'characters': [],
        'notes': [],
    }

    if query:
        # Script title / description (active scripts only)
        results['scripts'] = Script.objects.filter(
            Q(user=user, is_deleted=False) &
            (Q(title__icontains=query) | Q(description__icontains=query) | Q(author_name__icontains=query))
        )
        # Scenes heading / summary (active scenes in active scripts only)
        results['scenes'] = Scene.objects.filter(
            Q(script__user=user, script__is_deleted=False, is_deleted=False) &
            (Q(heading__icontains=query) | Q(summary__icontains=query))
        ).select_related('script')
        # Script Elements (dialogue, action, character) (active scenes in active scripts only)
        results['dialogues'] = ScriptElement.objects.filter(
            Q(scene__script__user=user, scene__script__is_deleted=False, scene__is_deleted=False) &
            Q(content__icontains=query)
        ).select_related('scene', 'scene__script')[:30]
        # Characters (active scripts only)
        results['characters'] = Character.objects.filter(
            Q(script__user=user, script__is_deleted=False) &
            (Q(name__icontains=query) | Q(description__icontains=query))
        ).select_related('script')
        # Notes (active scripts only)
        results['notes'] = ScriptNote.objects.filter(
            Q(script__user=user, script__is_deleted=False) &
            (Q(title__icontains=query) | Q(content__icontains=query))
        ).select_related('script')

    total_results_count = (
        len(results['scripts']) +
        len(results['scenes']) +
        len(results['dialogues']) +
        len(results['characters']) +
        len(results['notes'])
    )

    return render(request, 'core/search.html', {
        'query': query,
        'results': results,
        'total_results_count': total_results_count,
    })


@login_required
def settings_view(request):
    return render(request, 'core/settings.html')


def custom_404(request, exception=None):
    return render(request, 'errors/404.html', status=404)

def custom_403(request, exception=None):
    return render(request, 'errors/403.html', status=403)

def custom_500(request):
    return render(request, 'errors/500.html', status=500)


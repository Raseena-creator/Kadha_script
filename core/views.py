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
    user_scripts = Script.objects.filter(user=user)
    
    total_scripts = user_scripts.count()
    total_scenes = Scene.objects.filter(script__user=user).count()
    
    scripts = user_scripts.annotate(num_scenes=Count('scenes')).order_by('-updated_at')

    return render(request, 'core/dashboard.html', {
        'total_scripts': total_scripts,
        'total_scenes': total_scenes,
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
        # Script title / description
        results['scripts'] = Script.objects.filter(
            Q(user=user) &
            (Q(title__icontains=query) | Q(description__icontains=query) | Q(author_name__icontains=query))
        )
        # Scenes heading / summary
        results['scenes'] = Scene.objects.filter(
            Q(script__user=user) &
            (Q(heading__icontains=query) | Q(summary__icontains=query))
        ).select_related('script')
        # Script Elements (dialogue, action, character)
        results['dialogues'] = ScriptElement.objects.filter(
            Q(scene__script__user=user) &
            Q(content__icontains=query)
        ).select_related('scene', 'scene__script')[:30]
        # Characters
        results['characters'] = Character.objects.filter(
            Q(script__user=user) &
            (Q(name__icontains=query) | Q(description__icontains=query))
        ).select_related('script')
        # Notes
        results['notes'] = ScriptNote.objects.filter(
            Q(script__user=user) &
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


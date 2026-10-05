from django.urls import path
from . import views, api_views

urlpatterns = [
    path('', views.script_list_view, name='script_list'),
    path('new/', views.script_create_view, name='script_create'),
    path('<int:script_id>/', views.script_detail_view, name='script_detail'),
    path('<int:script_id>/edit-info/', views.script_edit_metadata_view, name='script_edit_metadata'),
    path('<int:script_id>/title-page/', views.script_title_page_view, name='script_title_page'),
    path('<int:script_id>/duplicate/', views.script_duplicate_view, name='script_duplicate'),
    path('<int:script_id>/delete/', views.script_delete_view, name='script_delete'),
    path('<int:script_id>/editor/', views.script_editor_view, name='script_editor'),
    path('<int:script_id>/scenes/', views.scenes_management_view, name='scenes_management'),
    path('<int:script_id>/characters/', views.character_management_view, name='character_management'),
    path('<int:script_id>/notes/', views.notes_view, name='notes'),
    path('<int:script_id>/versions/', views.versions_view, name='versions'),
    path('<int:script_id>/export/pdf/', views.export_pdf_view, name='export_pdf'),
    path('<int:script_id>/export/docx/', views.export_docx_view, name='export_docx'),
    path('<int:script_id>/export/txt/', views.export_txt_view, name='export_txt'),
    path('<int:script_id>/print/', views.print_preview_view, name='print_preview'),

    # API endpoints for dynamic editor
    path('api/<int:script_id>/scenes/tree/', api_views.api_get_scenes_tree, name='api_get_scenes_tree'),
    path('api/<int:script_id>/scenes/<int:scene_id>/', api_views.api_get_scene, name='api_get_scene'),
    path('api/<int:script_id>/scenes/<int:scene_id>/save/', api_views.api_save_scene, name='api_save_scene'),
    path('api/<int:script_id>/scenes/create/', api_views.api_create_scene, name='api_create_scene'),
    path('api/<int:script_id>/scenes/insert/', api_views.api_insert_scene, name='api_insert_scene'),
    path('api/<int:script_id>/scenes/<int:parent_scene_id>/subscene/', api_views.api_create_sub_scene, name='api_create_sub_scene'),
    path('api/<int:script_id>/scenes/subscene-2/', api_views.api_create_sub_scene_2, name='api_create_sub_scene_2'),
    path('api/<int:script_id>/scenes/intercut/', api_views.api_create_intercut, name='api_create_intercut'),
    path('api/<int:script_id>/scenes/<int:scene_id>/move/', api_views.api_move_scene, name='api_move_scene'),
    path('api/<int:script_id>/scenes/<int:scene_id>/delete/', api_views.api_delete_scene, name='api_delete_scene'),
    path('api/<int:script_id>/scenes/<int:scene_id>/duplicate/', api_views.api_duplicate_scene, name='api_duplicate_scene'),
    path('api/<int:script_id>/scenes/reorder/', api_views.api_reorder_scenes, name='api_reorder_scenes'),
    path('api/<int:script_id>/characters/', api_views.api_get_characters, name='api_get_characters'),
]

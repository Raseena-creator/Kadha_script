from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_view, name='landing'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('search/', views.global_search_view, name='global_search'),
    path('settings/', views.settings_view, name='settings'),
]

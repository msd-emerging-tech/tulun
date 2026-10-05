from django.conf import settings
from django.urls import path

from translations import api


urlpatterns = [
    path('api/v1/health', api.health, name='api-health'),
    path('api/v1/ready', api.ready, name='api-ready'),
    path('api/v1/translate', api.translate, name='api-translate'),
]

if settings.TULUN_ENABLE_LEGACY_UI:
    from django.contrib import admin
    from django.contrib.auth import views as auth_views
    from django.shortcuts import redirect
    from translations.views import create_corpus_entry, translate_view

    urlpatterns += [
        path('admin/', admin.site.urls),
        path('accounts/login/', auth_views.LoginView.as_view(template_name='translations/login.html'), name='login'),
        path('accounts/logout/', auth_views.LogoutView.as_view(template_name='translations/logout.html'), name='logout'),
        path('translate/', translate_view, name='translate'),
        path('', lambda request: redirect('translate'), name='home'),
        path('api/corpus-entry/', create_corpus_entry, name='create_corpus_entry'),
    ]

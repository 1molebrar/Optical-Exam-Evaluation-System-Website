"""
URL configuration for optical_exam_system project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from evaluation.admin import pink_admin_site

urlpatterns = [
    path('admin/', pink_admin_site.urls),
    path('', include('evaluation.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
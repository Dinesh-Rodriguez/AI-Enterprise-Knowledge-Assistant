from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static


def service_status(request):
    return JsonResponse({"service": "AI Enterprise Knowledge Assistant API", "status": "ok", "health": "/api/health/"})

urlpatterns = [
    path("", service_status),
    path("admin/", admin.site.urls),
    path("api/", include("assistant.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

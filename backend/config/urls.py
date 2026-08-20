"""Rutas principales de la API del sistema de control de asistencia."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/organizacion/", include("apps.organization.urls")),
    path("api/empleados/", include("apps.employees.urls")),
    path("api/dispositivos/", include("apps.devices.urls")),
    path("api/horarios/", include("apps.schedules.urls")),
    path("api/asistencia/", include("apps.attendance.urls")),
    path("api/reportes/", include("apps.reports.urls")),
    path("api/dashboard/", include("apps.dashboard.urls")),
    path("api/auditoria/", include("apps.audit.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

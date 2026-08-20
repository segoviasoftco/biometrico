from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.schedules.views import (
    AsignacionTurnoViewSet,
    ConfiguracionAsistenciaViewSet,
    FeriadoViewSet,
    HorarioViewSet,
    PermisoViewSet,
    TurnoViewSet,
)

router = DefaultRouter()
router.register("horarios", HorarioViewSet, basename="horario")
router.register("turnos", TurnoViewSet, basename="turno")
router.register("asignaciones", AsignacionTurnoViewSet, basename="asignacion-turno")
router.register("feriados", FeriadoViewSet, basename="feriado")
router.register("permisos", PermisoViewSet, basename="permiso")
router.register("configuracion", ConfiguracionAsistenciaViewSet, basename="configuracion-asistencia")

urlpatterns = [path("", include(router.urls))]

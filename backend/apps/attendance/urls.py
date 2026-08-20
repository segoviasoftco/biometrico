from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.attendance.views import MarcacionViewSet, RegistroAsistenciaViewSet

router = DefaultRouter()
router.register("marcaciones", MarcacionViewSet, basename="marcacion")
router.register("registros", RegistroAsistenciaViewSet, basename="registro-asistencia")

urlpatterns = [path("", include(router.urls))]

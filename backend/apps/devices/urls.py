from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.devices.views import DispositivoViewSet, RegistroSincronizacionViewSet

router = DefaultRouter()
router.register("sincronizaciones", RegistroSincronizacionViewSet, basename="sincronizacion")
router.register("", DispositivoViewSet, basename="dispositivo")

urlpatterns = [path("", include(router.urls))]

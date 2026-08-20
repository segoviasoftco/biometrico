from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.devices.views import (
    ComandoDispositivoViewSet,
    DispositivoViewSet,
    PeticionADMSViewSet,
    RegistroSincronizacionViewSet,
)

router = DefaultRouter()
router.register("sincronizaciones", RegistroSincronizacionViewSet, basename="sincronizacion")
router.register("comandos", ComandoDispositivoViewSet, basename="comando-dispositivo")
router.register("peticiones-adms", PeticionADMSViewSet, basename="peticion-adms")
router.register("", DispositivoViewSet, basename="dispositivo")

urlpatterns = [path("", include(router.urls))]

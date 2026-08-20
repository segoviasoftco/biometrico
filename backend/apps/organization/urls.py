from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.organization.views import AreaViewSet, CargoViewSet, DepartamentoViewSet, SedeViewSet

router = DefaultRouter()
router.register("sedes", SedeViewSet, basename="sede")
router.register("departamentos", DepartamentoViewSet, basename="departamento")
router.register("areas", AreaViewSet, basename="area")
router.register("cargos", CargoViewSet, basename="cargo")

urlpatterns = [path("", include(router.urls))]

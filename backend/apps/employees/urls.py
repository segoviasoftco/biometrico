from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.employees.views import EmpleadoViewSet

router = DefaultRouter()
router.register("", EmpleadoViewSet, basename="empleado")

urlpatterns = [path("", include(router.urls))]

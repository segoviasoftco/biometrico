from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.reports.views import ReporteViewSet

router = DefaultRouter()
router.register("", ReporteViewSet, basename="reporte")

urlpatterns = [path("", include(router.urls))]

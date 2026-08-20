from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.audit.views import RegistroAuditoriaViewSet

router = DefaultRouter()
router.register("", RegistroAuditoriaViewSet, basename="auditoria")

urlpatterns = [path("", include(router.urls))]

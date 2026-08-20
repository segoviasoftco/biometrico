from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from apps.accounts.views import LoginView, PerfilView, UsuarioViewSet

router = DefaultRouter()
router.register("usuarios", UsuarioViewSet, basename="usuario")
router.register("perfil", PerfilView, basename="perfil")

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("verify/", TokenVerifyView.as_view(), name="token-verify"),
    path("", include(router.urls)),
]

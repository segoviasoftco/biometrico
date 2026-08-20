"""Vistas de autenticacion y gestion de usuarios del sistema."""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.accounts.models import Usuario
from apps.accounts.permissions import EsAdministrador
from apps.accounts.serializers import (
    CambiarPasswordSerializer,
    LoginSerializer,
    UsuarioEscrituraSerializer,
    UsuarioSerializer,
)
from apps.audit.middleware import registrar_auditoria
from apps.audit.models import RegistroAuditoria


class LoginView(TokenObtainPairView):
    """Entrega el par de tokens JWT y deja constancia del ingreso."""

    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        respuesta = super().post(request, *args, **kwargs)
        if respuesta.status_code == status.HTTP_200_OK:
            email = request.data.get("email", "")
            usuario = Usuario.objects.filter(email=email).first()
            registrar_auditoria(
                accion=RegistroAuditoria.Accion.INICIAR_SESION,
                descripcion=f"Inicio de sesion de {email}",
                usuario=usuario,
            )
        return respuesta


class PerfilView(viewsets.ViewSet):
    """Datos y clave del usuario que tiene la sesion abierta."""

    permission_classes = [IsAuthenticated]

    def list(self, request):
        return Response(UsuarioSerializer(request.user).data)

    @action(detail=False, methods=["post"], url_path="cambiar-password")
    def cambiar_password(self, request):
        serializer = CambiarPasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        registrar_auditoria(
            accion=RegistroAuditoria.Accion.ACTUALIZAR,
            modelo="Usuario",
            objeto_id=request.user.id,
            descripcion="Cambio de clave propia",
        )
        return Response({"detalle": "La clave se actualizo correctamente."})


class UsuarioViewSet(viewsets.ModelViewSet):
    """Administracion de los usuarios que acceden al sistema."""

    queryset = Usuario.objects.select_related("sede").all()
    permission_classes = [EsAdministrador]
    filterset_fields = ["rol", "is_active", "sede"]
    search_fields = ["email", "nombres", "apellidos"]
    ordering_fields = ["apellidos", "email", "creado_en"]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return UsuarioEscrituraSerializer
        return UsuarioSerializer

    def perform_create(self, serializer):
        usuario = serializer.save()
        registrar_auditoria(
            accion=RegistroAuditoria.Accion.CREAR,
            modelo="Usuario",
            objeto_id=usuario.id,
            descripcion=f"Creacion del usuario {usuario.email}",
        )

    def perform_update(self, serializer):
        usuario = serializer.save()
        registrar_auditoria(
            accion=RegistroAuditoria.Accion.ACTUALIZAR,
            modelo="Usuario",
            objeto_id=usuario.id,
            descripcion=f"Actualizacion del usuario {usuario.email}",
        )

    def perform_destroy(self, instance):
        # Los usuarios se desactivan en lugar de borrarse: su rastro en la
        # auditoria y en los reportes generados debe seguir siendo legible.
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        registrar_auditoria(
            accion=RegistroAuditoria.Accion.ELIMINAR,
            modelo="Usuario",
            objeto_id=instance.id,
            descripcion=f"Desactivacion del usuario {instance.email}",
        )

    @action(detail=False, methods=["get"])
    def roles(self, request):
        """Catalogo de roles para poblar los selectores del frontend."""
        return Response(
            [{"valor": valor, "etiqueta": etiqueta} for valor, etiqueta in Usuario.Rol.choices]
        )

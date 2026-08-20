"""API de consulta de la bitacora de auditoria."""

from rest_framework import serializers, viewsets

from apps.accounts.permissions import EsAdministrador
from apps.audit.models import RegistroAuditoria


class RegistroAuditoriaSerializer(serializers.ModelSerializer):
    accion_display = serializers.CharField(source="get_accion_display", read_only=True)
    usuario_nombre = serializers.CharField(
        source="usuario.nombre_completo", read_only=True, default="Sistema"
    )

    class Meta:
        model = RegistroAuditoria
        fields = [
            "id",
            "usuario",
            "usuario_nombre",
            "usuario_email",
            "accion",
            "accion_display",
            "modelo",
            "objeto_id",
            "descripcion",
            "cambios",
            "ip",
            "ruta",
            "metodo",
            "fecha_hora",
        ]
        read_only_fields = fields


class RegistroAuditoriaViewSet(viewsets.ReadOnlyModelViewSet):
    """Bitacora de acciones. Es de solo lectura por definicion.

    Permitir editarla o borrarla anularia su proposito como evidencia.
    """

    queryset = RegistroAuditoria.objects.select_related("usuario").all()
    serializer_class = RegistroAuditoriaSerializer
    permission_classes = [EsAdministrador]
    filterset_fields = {
        "usuario": ["exact"],
        "accion": ["exact"],
        "modelo": ["exact"],
        "fecha_hora": ["gte", "lte", "date"],
    }
    search_fields = ["descripcion", "usuario_email", "objeto_id"]
    ordering_fields = ["fecha_hora"]

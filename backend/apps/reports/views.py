"""API de generacion y descarga de reportes."""

from django.core.files.base import ContentFile
from django.http import HttpResponse
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import LecturaTodosEscrituraRRHH
from apps.audit.middleware import registrar_auditoria
from apps.audit.models import RegistroAuditoria
from apps.reports.models import ReporteGenerado
from apps.reports.services.exportadores import exportar_excel, exportar_pdf
from apps.reports.services.generador import construir_datos

TIPOS_CONTENIDO = {
    ReporteGenerado.Formato.EXCEL: (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx",
    ),
    ReporteGenerado.Formato.PDF: ("application/pdf", "pdf"),
}


class ReporteGeneradoSerializer(serializers.ModelSerializer):
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)
    generado_por_nombre = serializers.CharField(
        source="generado_por.nombre_completo", read_only=True, default=None
    )

    class Meta:
        model = ReporteGenerado
        fields = [
            "id",
            "tipo",
            "tipo_display",
            "formato",
            "fecha_inicio",
            "fecha_fin",
            "filtros",
            "archivo",
            "total_registros",
            "generado_por",
            "generado_por_nombre",
            "generado_en",
        ]
        read_only_fields = fields


class SolicitudReporteSerializer(serializers.Serializer):
    """Parametros para generar un reporte."""

    tipo = serializers.ChoiceField(choices=ReporteGenerado.Tipo.choices)
    formato = serializers.ChoiceField(
        choices=ReporteGenerado.Formato.choices, default=ReporteGenerado.Formato.EXCEL
    )
    fecha_inicio = serializers.DateField()
    fecha_fin = serializers.DateField()
    sede = serializers.IntegerField(required=False, allow_null=True)
    departamento = serializers.IntegerField(required=False, allow_null=True)
    area = serializers.IntegerField(required=False, allow_null=True)
    empleados = serializers.ListField(child=serializers.IntegerField(), required=False)
    guardar = serializers.BooleanField(
        default=True, help_text="Conserva el archivo en el historial de reportes."
    )

    def validate(self, attrs):
        if attrs["fecha_fin"] < attrs["fecha_inicio"]:
            raise serializers.ValidationError(
                {"fecha_fin": "La fecha de fin no puede ser anterior a la de inicio."}
            )
        return attrs


class ReporteViewSet(viewsets.ReadOnlyModelViewSet):
    """Historial de reportes y generacion de nuevos."""

    queryset = ReporteGenerado.objects.select_related("generado_por").all()
    serializer_class = ReporteGeneradoSerializer
    permission_classes = [LecturaTodosEscrituraRRHH]
    filterset_fields = ["tipo", "formato"]
    ordering_fields = ["generado_en"]

    def get_permissions(self):
        # Generar y previsualizar son consultas: usan POST solo porque los
        # filtros viajan en el cuerpo. Un supervisor debe poder obtener los
        # reportes de su sede, que es a lo que `_filtros` los restringe.
        if self.action in ("generar", "previsualizar", "tipos"):
            return [IsAuthenticated()]
        return super().get_permissions()

    @action(detail=False, methods=["post"])
    def generar(self, request):
        """Genera un reporte y lo devuelve como archivo descargable."""
        serializer = SolicitudReporteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos_solicitud = serializer.validated_data

        filtros = self._filtros(datos_solicitud, request.user)
        datos = construir_datos(
            datos_solicitud["tipo"],
            datos_solicitud["fecha_inicio"],
            datos_solicitud["fecha_fin"],
            filtros,
        )

        formato = datos_solicitud["formato"]
        exportador = (
            exportar_excel if formato == ReporteGenerado.Formato.EXCEL else exportar_pdf
        )
        buffer = exportador(
            datos, datos_solicitud["fecha_inicio"], datos_solicitud["fecha_fin"]
        )
        contenido = buffer.getvalue()

        tipo_contenido, extension = TIPOS_CONTENIDO[formato]
        nombre = (
            f"{datos_solicitud['tipo']}_{datos_solicitud['fecha_inicio']}"
            f"_{datos_solicitud['fecha_fin']}.{extension}"
        )

        if datos_solicitud["guardar"]:
            reporte = ReporteGenerado(
                tipo=datos_solicitud["tipo"],
                formato=formato,
                fecha_inicio=datos_solicitud["fecha_inicio"],
                fecha_fin=datos_solicitud["fecha_fin"],
                filtros=filtros,
                total_registros=len(datos["filas"]),
                generado_por=request.user,
            )
            reporte.archivo.save(nombre, ContentFile(contenido), save=True)

        registrar_auditoria(
            accion=RegistroAuditoria.Accion.GENERAR_REPORTE,
            modelo="ReporteGenerado",
            descripcion=(
                f"Generacion del reporte de {datos_solicitud['tipo']} "
                f"del {datos_solicitud['fecha_inicio']} al {datos_solicitud['fecha_fin']}"
            ),
        )

        respuesta = HttpResponse(contenido, content_type=tipo_contenido)
        respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
        return respuesta

    @action(detail=False, methods=["post"], url_path="previsualizar")
    def previsualizar(self, request):
        """Devuelve los datos del reporte en JSON, sin generar el archivo.

        Permite revisar los resultados en pantalla antes de descargar.
        """
        serializer = SolicitudReporteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos_solicitud = serializer.validated_data

        datos = construir_datos(
            datos_solicitud["tipo"],
            datos_solicitud["fecha_inicio"],
            datos_solicitud["fecha_fin"],
            self._filtros(datos_solicitud, request.user),
        )
        return Response(
            {
                "titulo": datos["titulo"],
                "columnas": [
                    {"clave": clave, "etiqueta": etiqueta} for clave, etiqueta in datos["columnas"]
                ],
                "filas": datos["filas"],
                "totales": datos["totales"],
                "nota": datos.get("nota", ""),
                "total_registros": len(datos["filas"]),
            }
        )

    @action(detail=False, methods=["get"])
    def tipos(self, request):
        """Catalogo de reportes disponibles."""
        return Response(
            [
                {"valor": valor, "etiqueta": etiqueta}
                for valor, etiqueta in ReporteGenerado.Tipo.choices
            ]
        )

    @staticmethod
    def _filtros(datos, usuario):
        filtros = {
            clave: datos.get(clave)
            for clave in ("sede", "departamento", "area", "empleados")
            if datos.get(clave)
        }
        # Un supervisor no puede consultar mas alla de su sede, aunque envie
        # otro valor en el filtro.
        if usuario.es_supervisor and usuario.sede_id:
            filtros["sede"] = usuario.sede_id
        return filtros

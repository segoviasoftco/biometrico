"""API de marcaciones y registros de asistencia."""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import EsAdministradorORRHH, LecturaTodosEscrituraRRHH
from apps.attendance.models import Marcacion, RegistroAsistencia
from apps.attendance.serializers import (
    AjustarAsistenciaSerializer,
    MarcacionManualSerializer,
    MarcacionSerializer,
    ProcesarAsistenciaSerializer,
    RegistroAsistenciaSerializer,
)
from apps.attendance.services.processor import ProcesadorAsistencia
from apps.audit.middleware import registrar_auditoria
from apps.audit.models import RegistroAuditoria
from apps.employees.models import Empleado


class MarcacionViewSet(viewsets.ModelViewSet):
    """Marcaciones crudas. Solo se permite agregar registros manuales."""

    queryset = Marcacion.objects.select_related("empleado", "dispositivo").all()
    permission_classes = [LecturaTodosEscrituraRRHH]
    filterset_fields = {
        "empleado": ["exact"],
        "empleado__sede": ["exact"],
        "empleado__departamento": ["exact"],
        "dispositivo": ["exact"],
        "tipo_verificacion": ["exact"],
        "origen": ["exact"],
        "fecha_hora": ["gte", "lte", "date"],
    }
    search_fields = ["empleado__codigo_empleado", "empleado__apellido_paterno"]
    ordering_fields = ["fecha_hora"]

    def get_serializer_class(self):
        if self.action == "create":
            return MarcacionManualSerializer
        return MarcacionSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        usuario = self.request.user
        if usuario.es_supervisor and usuario.sede_id:
            queryset = queryset.filter(empleado__sede_id=usuario.sede_id)
        return queryset

    def get_permissions(self):
        if self.action in ("create", "destroy"):
            return [EsAdministradorORRHH()]
        return super().get_permissions()

    def perform_create(self, serializer):
        marcacion = serializer.save()
        registrar_auditoria(
            accion=RegistroAuditoria.Accion.AJUSTE_MANUAL,
            modelo="Marcacion",
            objeto_id=marcacion.id,
            descripcion=(
                f"Marcacion manual de {marcacion.empleado.codigo_empleado} "
                f"el {marcacion.fecha_hora:%Y-%m-%d %H:%M}: {marcacion.observacion}"
            ),
        )
        # El dia debe reflejar de inmediato la marcacion agregada.
        ProcesadorAsistencia().procesar_dia(
            marcacion.empleado, marcacion.fecha_hora.date(), forzar=True
        )

    def perform_destroy(self, instance):
        empleado, fecha = instance.empleado, instance.fecha_hora.date()
        registrar_auditoria(
            accion=RegistroAuditoria.Accion.ELIMINAR,
            modelo="Marcacion",
            objeto_id=instance.id,
            descripcion=(
                f"Eliminacion de la marcacion de {empleado.codigo_empleado} "
                f"del {instance.fecha_hora:%Y-%m-%d %H:%M}"
            ),
        )
        instance.delete()
        ProcesadorAsistencia().procesar_dia(empleado, fecha, forzar=True)


class RegistroAsistenciaViewSet(viewsets.ReadOnlyModelViewSet):
    """Resultado diario del procesamiento de asistencia."""

    queryset = RegistroAsistencia.objects.select_related(
        "empleado__sede", "empleado__departamento", "turno", "horario"
    ).all()
    serializer_class = RegistroAsistenciaSerializer
    permission_classes = [LecturaTodosEscrituraRRHH]
    filterset_fields = {
        "empleado": ["exact"],
        "empleado__sede": ["exact"],
        "empleado__departamento": ["exact"],
        "empleado__area": ["exact"],
        "estado": ["exact", "in"],
        "es_descontable": ["exact"],
        "fecha": ["exact", "gte", "lte"],
    }
    search_fields = ["empleado__codigo_empleado", "empleado__apellido_paterno"]
    ordering_fields = ["fecha", "minutos_tardanza"]

    def get_queryset(self):
        queryset = super().get_queryset()
        usuario = self.request.user
        if usuario.es_supervisor and usuario.sede_id:
            queryset = queryset.filter(empleado__sede_id=usuario.sede_id)
        return queryset

    @action(detail=False, methods=["post"], permission_classes=[EsAdministradorORRHH])
    def procesar(self, request):
        """Recalcula la asistencia de un rango de fechas."""
        serializer = ProcesarAsistenciaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        empleados = Empleado.objects.filter(estado=Empleado.Estado.ACTIVO)
        if datos.get("empleados"):
            empleados = empleados.filter(id__in=datos["empleados"])
        empleados = list(empleados)

        total = ProcesadorAsistencia().procesar_rango(
            empleados, datos["fecha_inicio"], datos["fecha_fin"], forzar=datos["forzar"]
        )

        registrar_auditoria(
            accion=RegistroAuditoria.Accion.ACTUALIZAR,
            modelo="RegistroAsistencia",
            descripcion=(
                f"Procesamiento de asistencia del {datos['fecha_inicio']} al "
                f"{datos['fecha_fin']} para {len(empleados)} empleados"
            ),
        )
        return Response(
            {
                "detalle": f"Se procesaron {total} registros.",
                "empleados": len(empleados),
                "registros": total,
            }
        )

    @action(detail=True, methods=["post"], permission_classes=[EsAdministradorORRHH])
    def ajustar(self, request, pk=None):
        """Corrige manualmente un dia procesado.

        El registro queda marcado como ajustado para que el recalculo automatico
        no vuelva a sobrescribirlo.
        """
        registro = self.get_object()
        serializer = AjustarAsistenciaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        anterior = {
            "estado": registro.estado,
            "minutos_tardanza": registro.minutos_tardanza,
            "es_descontable": registro.es_descontable,
        }

        registro.estado = datos["estado"]
        if "minutos_tardanza" in datos:
            registro.minutos_tardanza = datos["minutos_tardanza"]
        if "es_descontable" in datos:
            registro.es_descontable = datos["es_descontable"]
        registro.observacion = datos["observacion"]
        registro.ajustado_manualmente = True
        registro.ajustado_por = request.user
        registro.save()

        registrar_auditoria(
            accion=RegistroAuditoria.Accion.AJUSTE_MANUAL,
            modelo="RegistroAsistencia",
            objeto_id=registro.id,
            descripcion=(
                f"Ajuste de la asistencia de {registro.empleado.codigo_empleado} "
                f"del {registro.fecha}: {datos['observacion']}"
            ),
            cambios={
                "anterior": anterior,
                "nuevo": {
                    "estado": registro.estado,
                    "minutos_tardanza": registro.minutos_tardanza,
                    "es_descontable": registro.es_descontable,
                },
            },
        )
        return Response(
            {"detalle": "Registro ajustado.", "registro": RegistroAsistenciaSerializer(registro).data}
        )

    @action(detail=False, methods=["get"], url_path="resumen-empleado/(?P<empleado_id>[^/.]+)")
    def resumen_empleado(self, request, empleado_id=None):
        """Totales de un empleado en un rango, para su ficha."""
        from django.db.models import Count, Q, Sum

        queryset = self.get_queryset().filter(empleado_id=empleado_id)
        fecha_inicio = request.query_params.get("fecha_inicio")
        fecha_fin = request.query_params.get("fecha_fin")
        if fecha_inicio:
            queryset = queryset.filter(fecha__gte=fecha_inicio)
        if fecha_fin:
            queryset = queryset.filter(fecha__lte=fecha_fin)

        Estado = RegistroAsistencia.Estado
        resumen = queryset.aggregate(
            dias_puntuales=Count("id", filter=Q(estado=Estado.PUNTUAL)),
            dias_tardanza=Count("id", filter=Q(estado=Estado.TARDANZA)),
            dias_falta=Count("id", filter=Q(estado=Estado.FALTA)),
            dias_permiso=Count("id", filter=Q(estado__in=[Estado.PERMISO, Estado.VACACIONES])),
            minutos_tardanza=Sum("minutos_tardanza"),
            minutos_trabajados=Sum("minutos_trabajados"),
        )
        resumen = {clave: valor or 0 for clave, valor in resumen.items()}
        resumen["horas_trabajadas"] = round(resumen["minutos_trabajados"] / 60, 2)
        return Response(resumen)

"""API de horarios, turnos, feriados y permisos."""

from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import (
    EsAdministrador,
    EsAdministradorORRHH,
    LecturaTodosEscrituraRRHH,
)
from apps.audit.middleware import registrar_auditoria
from apps.audit.models import RegistroAuditoria
from apps.employees.models import Empleado
from apps.schedules.models import (
    AsignacionTurno,
    DiaLaborableConfig,
    Feriado,
    Horario,
    Permiso,
    Turno,
)
from apps.schedules.serializers import (
    AprobarPermisoSerializer,
    AsignacionMasivaSerializer,
    AsignacionTurnoSerializer,
    DiaLaborableConfigSerializer,
    FeriadoSerializer,
    HorarioSerializer,
    PermisoSerializer,
    TurnoSerializer,
)


class HorarioViewSet(viewsets.ModelViewSet):
    queryset = Horario.objects.all()
    serializer_class = HorarioSerializer
    permission_classes = [LecturaTodosEscrituraRRHH]
    filterset_fields = ["activo"]
    search_fields = ["nombre"]
    ordering_fields = ["nombre", "hora_entrada"]


class TurnoViewSet(viewsets.ModelViewSet):
    queryset = Turno.objects.prefetch_related("detalles__horario").all()
    serializer_class = TurnoSerializer
    permission_classes = [LecturaTodosEscrituraRRHH]
    filterset_fields = ["activo", "tipo"]
    search_fields = ["nombre"]

    @action(detail=False, methods=["post"], url_path="asignar-masivo",
            permission_classes=[EsAdministradorORRHH])
    @transaction.atomic
    def asignar_masivo(self, request):
        """Asigna un turno a varios empleados en una sola operacion."""
        serializer = AsignacionMasivaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        empleados = Empleado.objects.filter(id__in=datos["empleados"])
        if not empleados.exists():
            return Response(
                {"detalle": "No se encontraron los empleados indicados."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        fecha_inicio = datos["fecha_inicio"]
        creadas, omitidos = [], []

        for empleado in empleados:
            if datos["cerrar_asignacion_anterior"]:
                # El dia anterior al nuevo inicio, para que no haya un dia con
                # dos turnos vigentes ni un hueco sin turno.
                AsignacionTurno.objects.filter(empleado=empleado).filter(
                    Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha_inicio)
                ).filter(fecha_inicio__lt=fecha_inicio).update(
                    fecha_fin=fecha_inicio - timedelta(days=1)
                )

            solapada = AsignacionTurno.objects.filter(
                empleado=empleado, fecha_inicio__lte=fecha_inicio
            ).filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha_inicio))
            if solapada.exists():
                omitidos.append(
                    {
                        "empleado": empleado.codigo_empleado,
                        "motivo": "Ya tiene un turno vigente en esa fecha.",
                    }
                )
                continue

            creadas.append(
                AsignacionTurno(
                    empleado=empleado,
                    turno=datos["turno"],
                    fecha_inicio=fecha_inicio,
                    fecha_fin=datos.get("fecha_fin"),
                )
            )

        AsignacionTurno.objects.bulk_create(creadas)
        registrar_auditoria(
            accion=RegistroAuditoria.Accion.CREAR,
            modelo="AsignacionTurno",
            descripcion=f"Asignacion masiva del turno {datos['turno'].nombre} a {len(creadas)} empleados",
        )
        return Response(
            {
                "detalle": f"Se asignaron {len(creadas)} empleados al turno.",
                "asignados": len(creadas),
                "omitidos": omitidos,
            }
        )


class AsignacionTurnoViewSet(viewsets.ModelViewSet):
    queryset = AsignacionTurno.objects.select_related("empleado", "turno").all()
    serializer_class = AsignacionTurnoSerializer
    permission_classes = [LecturaTodosEscrituraRRHH]
    filterset_fields = ["empleado", "turno", "empleado__sede", "empleado__departamento"]
    ordering_fields = ["fecha_inicio"]

    def get_queryset(self):
        queryset = super().get_queryset()
        usuario = self.request.user
        if usuario.es_supervisor and usuario.sede_id:
            queryset = queryset.filter(empleado__sede_id=usuario.sede_id)

        if self.request.query_params.get("vigentes") == "true":
            hoy = timezone.localdate()
            queryset = queryset.filter(fecha_inicio__lte=hoy).filter(
                Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy)
            )
        return queryset


class FeriadoViewSet(viewsets.ModelViewSet):
    queryset = Feriado.objects.select_related("sede").all()
    serializer_class = FeriadoSerializer
    permission_classes = [LecturaTodosEscrituraRRHH]
    filterset_fields = ["sede", "es_recurrente"]
    ordering_fields = ["fecha"]

    def get_queryset(self):
        queryset = super().get_queryset()
        anio = self.request.query_params.get("anio")
        if anio:
            # Los recurrentes aplican a cualquier ano, por eso se incluyen
            # siempre en el calendario que se consulta.
            queryset = queryset.filter(Q(fecha__year=anio) | Q(es_recurrente=True))
        return queryset


class PermisoViewSet(viewsets.ModelViewSet):
    """Solicitudes de permiso y su aprobacion."""

    queryset = Permiso.objects.select_related("empleado", "aprobado_por").all()
    serializer_class = PermisoSerializer
    permission_classes = [LecturaTodosEscrituraRRHH]
    filterset_fields = ["empleado", "tipo", "estado", "con_goce", "empleado__sede"]
    search_fields = ["empleado__codigo_empleado", "empleado__apellido_paterno"]
    ordering_fields = ["fecha_inicio", "creado_en"]

    def get_queryset(self):
        queryset = super().get_queryset()
        usuario = self.request.user
        if usuario.es_supervisor and usuario.sede_id:
            queryset = queryset.filter(empleado__sede_id=usuario.sede_id)
        return queryset

    @action(detail=True, methods=["post"], permission_classes=[EsAdministradorORRHH])
    def aprobar(self, request, pk=None):
        """Aprueba o rechaza un permiso y recalcula los dias que abarca.

        El recalculo es necesario porque los dias ya procesados pudieron
        quedar marcados como falta antes de la aprobacion.
        """
        permiso = self.get_object()
        serializer = AprobarPermisoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        aprobar = serializer.validated_data["aprobar"]
        permiso.estado = (
            Permiso.EstadoAprobacion.APROBADO if aprobar else Permiso.EstadoAprobacion.RECHAZADO
        )
        permiso.aprobado_por = request.user
        permiso.fecha_aprobacion = timezone.now()
        permiso.observacion_aprobacion = serializer.validated_data.get("observacion", "")
        permiso.save()

        dias = self._recalcular_dias(permiso)

        registrar_auditoria(
            accion=RegistroAuditoria.Accion.APROBAR_PERMISO,
            modelo="Permiso",
            objeto_id=permiso.id,
            descripcion=(
                f"Permiso de {permiso.empleado.codigo_empleado} "
                f"{'aprobado' if aprobar else 'rechazado'}"
            ),
        )
        return Response(
            {
                "detalle": f"Permiso {'aprobado' if aprobar else 'rechazado'}.",
                "dias_recalculados": dias,
                "permiso": PermisoSerializer(permiso).data,
            }
        )

    @staticmethod
    def _recalcular_dias(permiso):
        from apps.attendance.services.processor import ProcesadorAsistencia

        procesador = ProcesadorAsistencia()
        fecha = permiso.fecha_inicio
        total = 0
        while fecha <= permiso.fecha_fin:
            procesador.procesar_dia(permiso.empleado, fecha)
            fecha += timedelta(days=1)
            total += 1
        return total

    @action(detail=False, methods=["get"])
    def pendientes(self, request):
        """Bandeja de permisos por aprobar."""
        queryset = self.get_queryset().filter(estado=Permiso.EstadoAprobacion.PENDIENTE)
        return Response(PermisoSerializer(queryset, many=True).data)


class ConfiguracionAsistenciaViewSet(viewsets.ViewSet):
    """Parametros globales que usa el motor de asistencia."""

    permission_classes = [EsAdministrador]

    def list(self, request):
        return Response(DiaLaborableConfigSerializer(DiaLaborableConfig.obtener()).data)

    def create(self, request):
        """Actualiza la configuracion unica del sistema."""
        config = DiaLaborableConfig.obtener()
        serializer = DiaLaborableConfigSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        registrar_auditoria(
            accion=RegistroAuditoria.Accion.ACTUALIZAR,
            modelo="DiaLaborableConfig",
            objeto_id=config.id,
            descripcion="Actualizacion de la configuracion de asistencia",
        )
        return Response(serializer.data)

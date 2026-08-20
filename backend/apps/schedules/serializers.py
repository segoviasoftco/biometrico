"""Serializers de horarios, turnos, feriados y permisos."""

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from apps.schedules.models import (
    AsignacionTurno,
    DiaLaborableConfig,
    Feriado,
    Horario,
    Permiso,
    Turno,
    TurnoDetalle,
)


class HorarioSerializer(serializers.ModelSerializer):
    horas_jornada = serializers.FloatField(read_only=True)
    minutos_jornada = serializers.IntegerField(read_only=True)
    cruza_medianoche = serializers.BooleanField(read_only=True)

    class Meta:
        model = Horario
        fields = [
            "id",
            "nombre",
            "hora_entrada",
            "hora_salida",
            "tolerancia_entrada",
            "tolerancia_salida",
            "tiene_refrigerio",
            "hora_inicio_refrigerio",
            "hora_fin_refrigerio",
            "minutos_falta",
            "horas_jornada",
            "minutos_jornada",
            "cruza_medianoche",
            "activo",
            "creado_en",
        ]
        read_only_fields = ["id", "creado_en"]

    def validate(self, attrs):
        instancia = Horario(**{**self._datos_actuales(), **attrs})
        instancia.clean()
        return attrs

    def _datos_actuales(self):
        if self.instance is None:
            return {}
        campos = [
            "hora_entrada",
            "hora_salida",
            "tiene_refrigerio",
            "hora_inicio_refrigerio",
            "hora_fin_refrigerio",
        ]
        return {campo: getattr(self.instance, campo) for campo in campos}


class TurnoDetalleSerializer(serializers.ModelSerializer):
    dia_display = serializers.CharField(source="get_dia_semana_display", read_only=True)
    horario_nombre = serializers.CharField(source="horario.nombre", read_only=True, default=None)
    es_descanso = serializers.BooleanField(read_only=True)

    class Meta:
        model = TurnoDetalle
        fields = ["id", "dia_semana", "dia_display", "horario", "horario_nombre", "es_descanso"]
        read_only_fields = ["id"]


class TurnoSerializer(serializers.ModelSerializer):
    """Turno con su patron semanal completo.

    Los detalles se escriben junto con el turno: separarlos obligaria al
    frontend a coordinar varias peticiones para guardar una sola pantalla.
    """

    detalles = TurnoDetalleSerializer(many=True)
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)
    total_empleados = serializers.SerializerMethodField()

    class Meta:
        model = Turno
        fields = [
            "id",
            "nombre",
            "tipo",
            "tipo_display",
            "descripcion",
            "detalles",
            "total_empleados",
            "activo",
            "creado_en",
        ]
        read_only_fields = ["id", "creado_en"]

    def get_total_empleados(self, obj):
        hoy = timezone.localdate()
        return obj.asignaciones.filter(
            Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy), fecha_inicio__lte=hoy
        ).count()

    def validate_detalles(self, value):
        dias = [d["dia_semana"] for d in value]
        if len(dias) != len(set(dias)):
            raise serializers.ValidationError("Hay dias repetidos en el turno.")
        return value

    def create(self, validated_data):
        detalles = validated_data.pop("detalles", [])
        turno = Turno.objects.create(**validated_data)
        self._guardar_detalles(turno, detalles)
        return turno

    def update(self, instance, validated_data):
        detalles = validated_data.pop("detalles", None)
        turno = super().update(instance, validated_data)
        if detalles is not None:
            # Se reemplaza el patron completo: es una sola pantalla de edicion y
            # el borrado parcial dejaria dias huerfanos del patron anterior.
            turno.detalles.all().delete()
            self._guardar_detalles(turno, detalles)
        return turno

    @staticmethod
    def _guardar_detalles(turno, detalles):
        TurnoDetalle.objects.bulk_create(
            [TurnoDetalle(turno=turno, **detalle) for detalle in detalles]
        )


class AsignacionTurnoSerializer(serializers.ModelSerializer):
    empleado_nombre = serializers.CharField(source="empleado.nombre_completo", read_only=True)
    empleado_codigo = serializers.CharField(source="empleado.codigo_empleado", read_only=True)
    turno_nombre = serializers.CharField(source="turno.nombre", read_only=True)
    vigente = serializers.SerializerMethodField()

    class Meta:
        model = AsignacionTurno
        fields = [
            "id",
            "empleado",
            "empleado_nombre",
            "empleado_codigo",
            "turno",
            "turno_nombre",
            "fecha_inicio",
            "fecha_fin",
            "vigente",
            "observacion",
            "creado_en",
        ]
        read_only_fields = ["id", "creado_en"]

    def get_vigente(self, obj):
        hoy = timezone.localdate()
        return obj.fecha_inicio <= hoy and (obj.fecha_fin is None or obj.fecha_fin >= hoy)

    def validate(self, attrs):
        empleado = attrs.get("empleado") or getattr(self.instance, "empleado", None)
        inicio = attrs.get("fecha_inicio") or getattr(self.instance, "fecha_inicio", None)
        fin = attrs.get("fecha_fin", getattr(self.instance, "fecha_fin", None))

        if fin and inicio and fin < inicio:
            raise serializers.ValidationError(
                {"fecha_fin": "La fecha de fin no puede ser anterior a la de inicio."}
            )

        # Dos turnos vigentes a la vez harian ambiguo que horario aplica en el
        # calculo de tardanzas.
        solapadas = AsignacionTurno.objects.filter(empleado=empleado).filter(
            Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=inicio)
        )
        if fin:
            solapadas = solapadas.filter(fecha_inicio__lte=fin)
        if self.instance:
            solapadas = solapadas.exclude(pk=self.instance.pk)

        if solapadas.exists():
            raise serializers.ValidationError(
                "El empleado ya tiene un turno asignado que se cruza con estas fechas. "
                "Cierre la asignacion anterior indicando su fecha de fin."
            )
        return attrs


class AsignacionMasivaSerializer(serializers.Serializer):
    """Asigna un mismo turno a varios empleados a la vez."""

    empleados = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    turno = serializers.PrimaryKeyRelatedField(queryset=Turno.objects.all())
    fecha_inicio = serializers.DateField()
    fecha_fin = serializers.DateField(required=False, allow_null=True)
    cerrar_asignacion_anterior = serializers.BooleanField(
        default=True,
        help_text=(
            "Cierra el turno vigente el dia previo al inicio, evitando el cruce "
            "de dos turnos activos."
        ),
    )


class FeriadoSerializer(serializers.ModelSerializer):
    sede_nombre = serializers.CharField(source="sede.nombre", read_only=True, default="Todas")

    class Meta:
        model = Feriado
        fields = ["id", "fecha", "descripcion", "es_recurrente", "sede", "sede_nombre", "creado_en"]
        read_only_fields = ["id", "creado_en"]


class PermisoSerializer(serializers.ModelSerializer):
    empleado_nombre = serializers.CharField(source="empleado.nombre_completo", read_only=True)
    empleado_codigo = serializers.CharField(source="empleado.codigo_empleado", read_only=True)
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    aprobado_por_nombre = serializers.CharField(
        source="aprobado_por.nombre_completo", read_only=True, default=None
    )
    dias_totales = serializers.IntegerField(read_only=True)

    class Meta:
        model = Permiso
        fields = [
            "id",
            "empleado",
            "empleado_nombre",
            "empleado_codigo",
            "tipo",
            "tipo_display",
            "fecha_inicio",
            "fecha_fin",
            "dias_totales",
            "con_goce",
            "motivo",
            "documento",
            "estado",
            "estado_display",
            "aprobado_por",
            "aprobado_por_nombre",
            "fecha_aprobacion",
            "observacion_aprobacion",
            "creado_en",
        ]
        read_only_fields = [
            "id",
            # La aprobacion pasa por su propia accion, que registra quien la hizo.
            "estado",
            "aprobado_por",
            "fecha_aprobacion",
            "observacion_aprobacion",
            "creado_en",
        ]

    def validate(self, attrs):
        inicio = attrs.get("fecha_inicio") or getattr(self.instance, "fecha_inicio", None)
        fin = attrs.get("fecha_fin") or getattr(self.instance, "fecha_fin", None)
        if inicio and fin and fin < inicio:
            raise serializers.ValidationError(
                {"fecha_fin": "La fecha de fin no puede ser anterior a la de inicio."}
            )
        return attrs


class AprobarPermisoSerializer(serializers.Serializer):
    aprobar = serializers.BooleanField()
    observacion = serializers.CharField(required=False, allow_blank=True, max_length=255)


class DiaLaborableConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiaLaborableConfig
        fields = [
            "id",
            "minutos_tolerancia_global",
            "considerar_marcacion_unica_como_falta",
            "valor_minuto_tardanza",
        ]
        read_only_fields = ["id"]

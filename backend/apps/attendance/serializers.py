"""Serializers de marcaciones y registros de asistencia."""

from rest_framework import serializers

from apps.attendance.models import Marcacion, RegistroAsistencia


class MarcacionSerializer(serializers.ModelSerializer):
    empleado_nombre = serializers.CharField(source="empleado.nombre_completo", read_only=True)
    empleado_codigo = serializers.CharField(source="empleado.codigo_empleado", read_only=True)
    tipo_verificacion_display = serializers.CharField(
        source="get_tipo_verificacion_display", read_only=True
    )
    tipo_marcacion_display = serializers.CharField(
        source="get_tipo_marcacion_display", read_only=True
    )
    dispositivo_nombre = serializers.CharField(
        source="dispositivo.nombre", read_only=True, default=None
    )

    class Meta:
        model = Marcacion
        fields = [
            "id",
            "empleado",
            "empleado_nombre",
            "empleado_codigo",
            "dispositivo",
            "dispositivo_nombre",
            "fecha_hora",
            "tipo_verificacion",
            "tipo_verificacion_display",
            "tipo_marcacion",
            "tipo_marcacion_display",
            "origen",
            "observacion",
            "descargado_en",
        ]
        read_only_fields = ["id", "descargado_en", "origen"]


class MarcacionManualSerializer(serializers.ModelSerializer):
    """Alta manual de una marcacion.

    Exige un sustento por escrito: es un dato que no proviene del equipo y que
    puede cambiar un descuento, asi que debe quedar justificado.
    """

    observacion = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=255,
        help_text="Motivo del registro manual. Queda en la auditoria.",
    )

    class Meta:
        model = Marcacion
        fields = ["id", "empleado", "fecha_hora", "tipo_marcacion", "observacion"]

    def create(self, validated_data):
        validated_data["origen"] = Marcacion.Origen.MANUAL
        validated_data["registrado_por"] = self.context["request"].user
        return super().create(validated_data)


class RegistroAsistenciaSerializer(serializers.ModelSerializer):
    empleado_nombre = serializers.CharField(source="empleado.nombre_completo", read_only=True)
    empleado_codigo = serializers.CharField(source="empleado.codigo_empleado", read_only=True)
    departamento_nombre = serializers.CharField(
        source="empleado.departamento.nombre", read_only=True
    )
    sede_nombre = serializers.CharField(source="empleado.sede.nombre", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    turno_nombre = serializers.CharField(source="turno.nombre", read_only=True, default=None)
    horario_nombre = serializers.CharField(source="horario.nombre", read_only=True, default=None)
    horas_trabajadas = serializers.FloatField(read_only=True)

    class Meta:
        model = RegistroAsistencia
        fields = [
            "id",
            "empleado",
            "empleado_nombre",
            "empleado_codigo",
            "sede_nombre",
            "departamento_nombre",
            "fecha",
            "turno",
            "turno_nombre",
            "horario",
            "horario_nombre",
            "hora_entrada_programada",
            "hora_salida_programada",
            "marcacion_entrada",
            "marcacion_salida",
            "total_marcaciones",
            "minutos_tardanza",
            "minutos_salida_anticipada",
            "minutos_trabajados",
            "minutos_programados",
            "horas_trabajadas",
            "estado",
            "estado_display",
            "permiso",
            "es_descontable",
            "observacion",
            "ajustado_manualmente",
            "ajustado_por",
            "procesado_en",
        ]
        read_only_fields = fields


class AjustarAsistenciaSerializer(serializers.Serializer):
    """Correccion manual de un dia ya procesado."""

    estado = serializers.ChoiceField(choices=RegistroAsistencia.Estado.choices)
    minutos_tardanza = serializers.IntegerField(min_value=0, required=False)
    es_descontable = serializers.BooleanField(required=False)
    observacion = serializers.CharField(
        max_length=255,
        help_text="Sustento del ajuste. Es obligatorio y queda en la auditoria.",
    )


class ProcesarAsistenciaSerializer(serializers.Serializer):
    """Solicitud de recalculo de asistencia."""

    fecha_inicio = serializers.DateField()
    fecha_fin = serializers.DateField()
    empleados = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="Si se omite, se procesan todos los empleados activos.",
    )
    forzar = serializers.BooleanField(
        default=False,
        help_text="Sobrescribe incluso los registros ajustados manualmente.",
    )

    def validate(self, attrs):
        if attrs["fecha_fin"] < attrs["fecha_inicio"]:
            raise serializers.ValidationError(
                {"fecha_fin": "La fecha de fin no puede ser anterior a la de inicio."}
            )
        return attrs

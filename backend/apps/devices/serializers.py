"""Serializers de dispositivos biometricos."""

from rest_framework import serializers

from apps.devices.models import Dispositivo, RegistroSincronizacion


class DispositivoSerializer(serializers.ModelSerializer):
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    sede_nombre = serializers.CharField(source="sede.nombre", read_only=True, default=None)

    class Meta:
        model = Dispositivo
        fields = [
            "id",
            "nombre",
            "ip",
            "puerto",
            "password_comunicacion",
            "timeout",
            "force_udp",
            "sede",
            "sede_nombre",
            "ubicacion",
            "modelo",
            "numero_serie",
            "version_firmware",
            "version_plataforma",
            "version_rostro",
            "version_huella",
            "mac",
            "admin_user_id",
            "estado",
            "estado_display",
            "ultima_conexion",
            "ultima_sincronizacion_marcaciones",
            "activo",
            "creado_en",
        ]
        read_only_fields = [
            "id",
            # Estos datos los reporta el propio equipo al probar la conexion.
            "modelo",
            "numero_serie",
            "version_firmware",
            "version_plataforma",
            "version_rostro",
            "version_huella",
            "mac",
            "estado",
            "ultima_conexion",
            "ultima_sincronizacion_marcaciones",
            "creado_en",
        ]
        extra_kwargs = {"password_comunicacion": {"write_only": True}}


class RegistroSincronizacionSerializer(serializers.ModelSerializer):
    operacion_display = serializers.CharField(source="get_operacion_display", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    dispositivo_nombre = serializers.CharField(source="dispositivo.nombre", read_only=True)
    ejecutado_por_nombre = serializers.CharField(
        source="ejecutado_por.nombre_completo", read_only=True, default="Tarea programada"
    )
    duracion_segundos = serializers.FloatField(read_only=True)

    class Meta:
        model = RegistroSincronizacion
        fields = [
            "id",
            "dispositivo",
            "dispositivo_nombre",
            "operacion",
            "operacion_display",
            "estado",
            "estado_display",
            "registros_procesados",
            "registros_nuevos",
            "registros_fallidos",
            "mensaje",
            "detalle",
            "ejecutado_por",
            "ejecutado_por_nombre",
            "inicio",
            "fin",
            "duracion_segundos",
        ]
        read_only_fields = fields


class DescargarMarcacionesSerializer(serializers.Serializer):
    """Parametros de una descarga manual de marcaciones."""

    desde = serializers.DateField(
        required=False,
        help_text=(
            "Si se omite, se descarga desde la ultima sincronizacion registrada. "
            "Repetir un rango ya descargado no genera duplicados."
        ),
    )
    procesar = serializers.BooleanField(
        default=True,
        help_text="Recalcular la asistencia de los dias afectados tras la descarga.",
    )

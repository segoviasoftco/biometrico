"""Serializers de dispositivos biometricos."""

from rest_framework import serializers

from apps.devices.models import (
    ComandoDispositivo,
    Dispositivo,
    PeticionADMS,
    RegistroSincronizacion,
)


class DispositivoSerializer(serializers.ModelSerializer):
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    sede_nombre = serializers.CharField(source="sede.nombre", read_only=True, default=None)
    modo_display = serializers.CharField(source="get_modo_display", read_only=True)
    comandos_pendientes = serializers.SerializerMethodField()

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
            "modo",
            "modo_display",
            "adms_habilitado",
            "adms_ip_permitida",
            "ultima_conexion_adms",
            "comandos_pendientes",
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
            "version_firmware",
            "version_plataforma",
            "version_rostro",
            "version_huella",
            "mac",
            "estado",
            "ultima_conexion",
            "ultima_conexion_adms",
            "ultima_sincronizacion_marcaciones",
            "creado_en",
        ]
        extra_kwargs = {
            "password_comunicacion": {"write_only": True},
            # En modo SDK lo descubre el propio equipo, pero en ADMS es el dato
            # con el que se autentica, y hay que poder escribirlo a mano.
            "numero_serie": {
                "required": False,
                "allow_blank": True,
                "help_text": (
                    "Obligatorio en modo ADMS: es la unica identificacion que "
                    "presenta el equipo al enviar datos."
                ),
            },
        }

    def get_comandos_pendientes(self, obj):
        return obj.comandos.filter(estado=ComandoDispositivo.Estado.PENDIENTE).count()

    def validate(self, attrs):
        modo = attrs.get("modo", getattr(self.instance, "modo", Dispositivo.Modo.SDK))
        adms = attrs.get(
            "adms_habilitado", getattr(self.instance, "adms_habilitado", False)
        )
        serie = attrs.get("numero_serie", getattr(self.instance, "numero_serie", ""))

        # Sin numero de serie el modo ADMS no puede distinguir un equipo legitimo
        # de cualquier otro cliente que envie datos al servidor.
        if (modo == Dispositivo.Modo.ADMS or adms) and not serie:
            raise serializers.ValidationError(
                {
                    "numero_serie": (
                        "El numero de serie es obligatorio para habilitar ADMS: es lo "
                        "unico que permite verificar que los datos vienen de este equipo."
                    )
                }
            )
        return attrs


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


class ComandoDispositivoSerializer(serializers.ModelSerializer):
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    dispositivo_nombre = serializers.CharField(source="dispositivo.nombre", read_only=True)
    empleado_codigo = serializers.CharField(
        source="empleado.codigo_empleado", read_only=True, default=None
    )
    empleado_nombre = serializers.CharField(
        source="empleado.nombre_completo", read_only=True, default=None
    )
    creado_por_nombre = serializers.CharField(
        source="creado_por.nombre_completo", read_only=True, default="Sistema"
    )

    class Meta:
        model = ComandoDispositivo
        fields = [
            "id",
            "dispositivo",
            "dispositivo_nombre",
            "tipo",
            "tipo_display",
            "estado",
            "estado_display",
            "empleado",
            "empleado_codigo",
            "empleado_nombre",
            "codigo_retorno",
            "respuesta",
            "creado_por_nombre",
            "creado_en",
            "enviado_en",
            "confirmado_en",
        ]
        read_only_fields = fields


class PeticionADMSSerializer(serializers.ModelSerializer):
    dispositivo_nombre = serializers.CharField(
        source="dispositivo.nombre", read_only=True, default=None
    )

    class Meta:
        model = PeticionADMS
        fields = [
            "id",
            "dispositivo",
            "dispositivo_nombre",
            "numero_serie",
            "ruta",
            "metodo",
            "parametros",
            "cuerpo",
            "respuesta",
            "ip_origen",
            "aceptada",
            "registros_procesados",
            "recibida_en",
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

"""Dispositivos biometricos ZKTeco y bitacora de sincronizaciones."""

from django.conf import settings
from django.db import models


class Dispositivo(models.Model):
    """Terminal biometrica ZKTeco accesible por red local.

    El sistema esta pensado para el MB560-VL en 192.168.18.202, pero la IP y el
    puerto son configurables para el paso a produccion, y el modelo admite mas
    de un equipo por si se agregan sedes.
    """

    class Estado(models.TextChoices):
        CONECTADO = "conectado", "Conectado"
        DESCONECTADO = "desconectado", "Desconectado"
        ERROR = "error", "Error de conexion"
        DESCONOCIDO = "desconocido", "Desconocido"

    nombre = models.CharField("nombre", max_length=100)
    ip = models.GenericIPAddressField("direccion IP", protocol="IPv4", default="192.168.18.202")
    puerto = models.PositiveIntegerField("puerto", default=4370)
    password_comunicacion = models.IntegerField(
        "clave de comunicacion",
        default=0,
        help_text="Clave de comunicacion configurada en el equipo (0 si no tiene).",
    )
    timeout = models.PositiveIntegerField("timeout en segundos", default=10)
    force_udp = models.BooleanField(
        "forzar UDP",
        default=False,
        help_text="Activar solo si el equipo no responde por TCP.",
    )

    sede = models.ForeignKey(
        "organization.Sede",
        verbose_name="sede",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dispositivos",
    )
    ubicacion = models.CharField("ubicacion fisica", max_length=255, blank=True)

    # --- Datos reportados por el propio equipo ---------------------------
    modelo = models.CharField("modelo", max_length=100, blank=True)
    numero_serie = models.CharField("numero de serie", max_length=100, blank=True)
    version_firmware = models.CharField("version de firmware", max_length=100, blank=True)
    version_plataforma = models.CharField("plataforma", max_length=100, blank=True)
    version_rostro = models.CharField("version del algoritmo facial", max_length=50, blank=True)
    version_huella = models.CharField("version del algoritmo de huella", max_length=50, blank=True)
    mac = models.CharField("direccion MAC", max_length=50, blank=True)

    admin_user_id = models.CharField(
        "ID del administrador del equipo",
        max_length=20,
        default="6999383",
        help_text="Este usuario nunca se elimina durante una sincronizacion.",
    )

    estado = models.CharField(
        "estado", max_length=20, choices=Estado.choices, default=Estado.DESCONOCIDO
    )
    ultima_conexion = models.DateTimeField("ultima conexion exitosa", null=True, blank=True)
    ultima_sincronizacion_marcaciones = models.DateTimeField(
        "ultima descarga de marcaciones",
        null=True,
        blank=True,
        help_text="Marca desde cuando se descargan las marcaciones nuevas.",
    )
    activo = models.BooleanField("activo", default=True)

    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        verbose_name = "dispositivo biometrico"
        verbose_name_plural = "dispositivos biometricos"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(fields=["ip", "puerto"], name="dispositivo_ip_puerto_unico")
        ]

    def __str__(self):
        return f"{self.nombre} ({self.ip}:{self.puerto})"


class RegistroSincronizacion(models.Model):
    """Bitacora de cada operacion realizada contra un dispositivo.

    Toda comunicacion con el equipo deja rastro aqui, para poder diagnosticar
    fallas de red o de firmware sin depender de los logs del servidor.
    """

    class Operacion(models.TextChoices):
        PROBAR_CONEXION = "probar_conexion", "Probar conexion"
        SUBIR_EMPLEADOS = "subir_empleados", "Subir empleados al equipo"
        DESCARGAR_EMPLEADOS = "descargar_empleados", "Descargar empleados del equipo"
        DESCARGAR_HUELLAS = "descargar_huellas", "Respaldar huellas"
        RESTAURAR_HUELLAS = "restaurar_huellas", "Restaurar huellas en el equipo"
        DESCARGAR_MARCACIONES = "descargar_marcaciones", "Descargar marcaciones"
        ELIMINAR_EMPLEADO = "eliminar_empleado", "Eliminar empleado del equipo"
        SINCRONIZAR_HORA = "sincronizar_hora", "Sincronizar hora del equipo"
        LIMPIAR_MARCACIONES = "limpiar_marcaciones", "Limpiar marcaciones del equipo"

    class Estado(models.TextChoices):
        EN_PROCESO = "en_proceso", "En proceso"
        EXITOSO = "exitoso", "Exitoso"
        FALLIDO = "fallido", "Fallido"
        PARCIAL = "parcial", "Parcial"

    dispositivo = models.ForeignKey(
        Dispositivo,
        verbose_name="dispositivo",
        on_delete=models.CASCADE,
        related_name="sincronizaciones",
    )
    operacion = models.CharField("operacion", max_length=30, choices=Operacion.choices)
    estado = models.CharField(
        "estado", max_length=20, choices=Estado.choices, default=Estado.EN_PROCESO
    )
    registros_procesados = models.IntegerField("registros procesados", default=0)
    registros_nuevos = models.IntegerField("registros nuevos", default=0)
    registros_fallidos = models.IntegerField("registros fallidos", default=0)
    mensaje = models.TextField("mensaje", blank=True)
    detalle = models.JSONField("detalle", null=True, blank=True)

    ejecutado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="ejecutado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sincronizaciones",
        help_text="Nulo cuando la ejecuta una tarea programada.",
    )
    inicio = models.DateTimeField("inicio", auto_now_add=True)
    fin = models.DateTimeField("fin", null=True, blank=True)

    class Meta:
        verbose_name = "registro de sincronizacion"
        verbose_name_plural = "registros de sincronizacion"
        ordering = ["-inicio"]
        indexes = [
            models.Index(fields=["-inicio"]),
            models.Index(fields=["dispositivo", "operacion"]),
        ]

    def __str__(self):
        return f"{self.get_operacion_display()} - {self.get_estado_display()} ({self.inicio:%Y-%m-%d %H:%M})"

    @property
    def duracion_segundos(self):
        if not self.fin:
            return None
        return (self.fin - self.inicio).total_seconds()

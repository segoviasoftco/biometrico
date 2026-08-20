"""Bitacora de acciones realizadas en el sistema."""

from django.conf import settings
from django.db import models


class RegistroAuditoria(models.Model):
    """Traza de quien hizo que y cuando.

    Cubre tanto los cambios sobre los datos (crear, editar, eliminar) como las
    operaciones sensibles contra el dispositivo biometrico.
    """

    class Accion(models.TextChoices):
        CREAR = "crear", "Crear"
        ACTUALIZAR = "actualizar", "Actualizar"
        ELIMINAR = "eliminar", "Eliminar"
        INICIAR_SESION = "iniciar_sesion", "Iniciar sesion"
        CERRAR_SESION = "cerrar_sesion", "Cerrar sesion"
        SINCRONIZAR = "sincronizar", "Sincronizar con dispositivo"
        GENERAR_REPORTE = "generar_reporte", "Generar reporte"
        AJUSTE_MANUAL = "ajuste_manual", "Ajuste manual de asistencia"
        APROBAR_PERMISO = "aprobar_permiso", "Aprobar o rechazar permiso"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acciones_auditoria",
    )
    usuario_email = models.EmailField(
        "email del usuario",
        blank=True,
        help_text="Se conserva aunque luego se elimine el usuario.",
    )
    accion = models.CharField("accion", max_length=30, choices=Accion.choices)
    modelo = models.CharField("modelo afectado", max_length=100, blank=True)
    objeto_id = models.CharField("ID del objeto", max_length=50, blank=True)
    descripcion = models.CharField("descripcion", max_length=500, blank=True)
    cambios = models.JSONField(
        "cambios",
        null=True,
        blank=True,
        help_text="Valores anteriores y nuevos de los campos modificados.",
    )

    ip = models.GenericIPAddressField("direccion IP", null=True, blank=True)
    user_agent = models.CharField("navegador", max_length=300, blank=True)
    ruta = models.CharField("ruta", max_length=255, blank=True)
    metodo = models.CharField("metodo HTTP", max_length=10, blank=True)

    fecha_hora = models.DateTimeField("fecha y hora", auto_now_add=True)

    class Meta:
        verbose_name = "registro de auditoria"
        verbose_name_plural = "registros de auditoria"
        ordering = ["-fecha_hora"]
        indexes = [
            models.Index(fields=["-fecha_hora"]),
            models.Index(fields=["usuario", "-fecha_hora"]),
            models.Index(fields=["modelo", "objeto_id"]),
        ]

    def __str__(self):
        actor = self.usuario_email or "sistema"
        return f"{actor} - {self.get_accion_display()} - {self.fecha_hora:%Y-%m-%d %H:%M}"

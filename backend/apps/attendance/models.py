"""Marcaciones descargadas del dispositivo y su procesamiento diario.

Se mantienen dos niveles:
  - `Marcacion`: el dato crudo tal como lo entrega el equipo. Nunca se modifica.
  - `RegistroAsistencia`: el resultado de evaluar esas marcaciones contra el
    horario del empleado. Es lo que alimenta el dashboard y los reportes.

Separarlos permite recalcular la asistencia (por un cambio de turno o la
aprobacion tardia de un permiso) sin volver a consultar el dispositivo.
"""

from django.db import models


class Marcacion(models.Model):
    """Registro crudo de una marcacion leida del dispositivo biometrico."""

    class TipoVerificacion(models.IntegerChoices):
        """Metodo con el que el empleado se identifico en el equipo."""

        PASSWORD = 0, "Clave"
        HUELLA = 1, "Huella digital"
        TARJETA = 2, "Tarjeta"
        ROSTRO = 15, "Rostro"
        OTRO = 99, "Otro"

    class TipoMarcacion(models.IntegerChoices):
        """Codigo de punch que reporta el equipo."""

        ENTRADA = 0, "Entrada"
        SALIDA = 1, "Salida"
        SALIDA_REFRIGERIO = 2, "Salida a refrigerio"
        RETORNO_REFRIGERIO = 3, "Retorno de refrigerio"
        SIN_DEFINIR = 255, "Sin definir"

    class Origen(models.TextChoices):
        DISPOSITIVO = "dispositivo", "Dispositivo biometrico"
        MANUAL = "manual", "Registro manual"

    empleado = models.ForeignKey(
        "employees.Empleado",
        verbose_name="empleado",
        on_delete=models.CASCADE,
        related_name="marcaciones",
    )
    dispositivo = models.ForeignKey(
        "devices.Dispositivo",
        verbose_name="dispositivo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marcaciones",
    )
    fecha_hora = models.DateTimeField("fecha y hora")
    tipo_verificacion = models.IntegerField(
        "tipo de verificacion",
        choices=TipoVerificacion.choices,
        default=TipoVerificacion.OTRO,
    )
    tipo_marcacion = models.IntegerField(
        "tipo de marcacion",
        choices=TipoMarcacion.choices,
        default=TipoMarcacion.SIN_DEFINIR,
    )
    uid_dispositivo = models.IntegerField(
        "UID en el dispositivo",
        null=True,
        blank=True,
        help_text="Identificador interno del registro en el equipo.",
    )
    origen = models.CharField(
        "origen", max_length=20, choices=Origen.choices, default=Origen.DISPOSITIVO
    )
    observacion = models.CharField(
        "observacion",
        max_length=255,
        blank=True,
        help_text="Sustento obligatorio cuando la marcacion se registra manualmente.",
    )
    registrado_por = models.ForeignKey(
        "accounts.Usuario",
        verbose_name="registrado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marcaciones_registradas",
    )
    descargado_en = models.DateTimeField("descargado en", auto_now_add=True)

    class Meta:
        verbose_name = "marcacion"
        verbose_name_plural = "marcaciones"
        ordering = ["-fecha_hora"]
        constraints = [
            # Hace idempotente la descarga: volver a bajar el mismo rango de
            # fechas no duplica registros.
            models.UniqueConstraint(
                fields=["empleado", "fecha_hora", "dispositivo"],
                name="marcacion_unica_por_empleado_fecha_dispositivo",
            )
        ]
        indexes = [
            models.Index(fields=["empleado", "fecha_hora"]),
            models.Index(fields=["-fecha_hora"]),
        ]

    def __str__(self):
        return f"{self.empleado.codigo_empleado} - {self.fecha_hora:%Y-%m-%d %H:%M:%S}"

    @property
    def fecha(self):
        return self.fecha_hora.date()


class RegistroAsistencia(models.Model):
    """Resultado del procesamiento de un dia para un empleado.

    Se recalcula de forma idempotente: procesar el mismo dia varias veces
    siempre produce el mismo resultado.
    """

    class Estado(models.TextChoices):
        PUNTUAL = "puntual", "Puntual"
        TARDANZA = "tardanza", "Tardanza"
        FALTA = "falta", "Falta injustificada"
        FALTA_JUSTIFICADA = "falta_justificada", "Falta justificada"
        PERMISO = "permiso", "Permiso"
        VACACIONES = "vacaciones", "Vacaciones"
        DESCANSO = "descanso", "Descanso"
        FERIADO = "feriado", "Feriado"
        INCOMPLETO = "incompleto", "Asistencia incompleta"
        SIN_TURNO = "sin_turno", "Sin turno asignado"

    empleado = models.ForeignKey(
        "employees.Empleado",
        verbose_name="empleado",
        on_delete=models.CASCADE,
        related_name="registros_asistencia",
    )
    fecha = models.DateField("fecha")

    turno = models.ForeignKey(
        "schedules.Turno",
        verbose_name="turno aplicado",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registros_asistencia",
    )
    horario = models.ForeignKey(
        "schedules.Horario",
        verbose_name="horario aplicado",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registros_asistencia",
    )

    hora_entrada_programada = models.TimeField("entrada programada", null=True, blank=True)
    hora_salida_programada = models.TimeField("salida programada", null=True, blank=True)
    marcacion_entrada = models.DateTimeField("marcacion de entrada", null=True, blank=True)
    marcacion_salida = models.DateTimeField("marcacion de salida", null=True, blank=True)
    total_marcaciones = models.PositiveSmallIntegerField("total de marcaciones", default=0)

    minutos_tardanza = models.PositiveIntegerField("minutos de tardanza", default=0)
    minutos_salida_anticipada = models.PositiveIntegerField(
        "minutos de salida anticipada", default=0
    )
    minutos_trabajados = models.PositiveIntegerField("minutos trabajados", default=0)
    minutos_programados = models.PositiveIntegerField("minutos programados", default=0)

    estado = models.CharField(
        "estado", max_length=20, choices=Estado.choices, default=Estado.SIN_TURNO
    )
    permiso = models.ForeignKey(
        "schedules.Permiso",
        verbose_name="permiso aplicado",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registros_asistencia",
    )
    es_descontable = models.BooleanField(
        "afecta el descuento",
        default=False,
        help_text="Marca los dias que se consideran en el reporte de descuentos.",
    )
    observacion = models.CharField("observacion", max_length=255, blank=True)

    ajustado_manualmente = models.BooleanField(
        "ajustado manualmente",
        default=False,
        help_text="Si esta activo, el recalculo automatico respeta este registro.",
    )
    ajustado_por = models.ForeignKey(
        "accounts.Usuario",
        verbose_name="ajustado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registros_ajustados",
    )

    procesado_en = models.DateTimeField("procesado en", auto_now=True)
    creado_en = models.DateTimeField("creado en", auto_now_add=True)

    class Meta:
        verbose_name = "registro de asistencia"
        verbose_name_plural = "registros de asistencia"
        ordering = ["-fecha", "empleado"]
        constraints = [
            models.UniqueConstraint(
                fields=["empleado", "fecha"], name="registro_asistencia_unico_por_dia"
            )
        ]
        indexes = [
            models.Index(fields=["fecha", "estado"]),
            models.Index(fields=["empleado", "-fecha"]),
            models.Index(fields=["estado", "es_descontable"]),
        ]

    def __str__(self):
        return f"{self.empleado.codigo_empleado} - {self.fecha} ({self.get_estado_display()})"

    @property
    def horas_trabajadas(self):
        return round(self.minutos_trabajados / 60, 2)

    @property
    def es_falta(self):
        return self.estado in (self.Estado.FALTA, self.Estado.FALTA_JUSTIFICADA)

    @property
    def tuvo_tardanza(self):
        return self.minutos_tardanza > 0

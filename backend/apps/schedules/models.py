"""Horarios, turnos, feriados y permisos.

Define la jornada esperada de cada empleado. El motor de asistencia compara las
marcaciones reales contra lo definido aqui para determinar tardanzas y faltas.
"""

from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class DiaSemana(models.IntegerChoices):
    """Dias de la semana con la misma numeracion de `date.weekday()`."""

    LUNES = 0, "Lunes"
    MARTES = 1, "Martes"
    MIERCOLES = 2, "Miercoles"
    JUEVES = 3, "Jueves"
    VIERNES = 4, "Viernes"
    SABADO = 5, "Sabado"
    DOMINGO = 6, "Domingo"


class Horario(models.Model):
    """Jornada de un dia: hora de entrada, de salida y tolerancias."""

    nombre = models.CharField("nombre", max_length=100, unique=True)
    hora_entrada = models.TimeField("hora de entrada")
    hora_salida = models.TimeField("hora de salida")

    tolerancia_entrada = models.PositiveSmallIntegerField(
        "tolerancia de entrada (minutos)",
        default=5,
        help_text="Minutos de gracia antes de considerar tardanza.",
    )
    tolerancia_salida = models.PositiveSmallIntegerField(
        "tolerancia de salida (minutos)",
        default=5,
        help_text="Minutos de gracia antes de considerar salida anticipada.",
    )

    tiene_refrigerio = models.BooleanField("tiene refrigerio", default=False)
    hora_inicio_refrigerio = models.TimeField("inicio de refrigerio", null=True, blank=True)
    hora_fin_refrigerio = models.TimeField("fin de refrigerio", null=True, blank=True)

    minutos_falta = models.PositiveSmallIntegerField(
        "minutos para considerar falta",
        default=120,
        help_text=(
            "Si la tardanza supera estos minutos, el dia se marca como falta "
            "en lugar de tardanza."
        ),
    )

    activo = models.BooleanField("activo", default=True)
    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        verbose_name = "horario"
        verbose_name_plural = "horarios"
        ordering = ["hora_entrada", "nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.hora_entrada:%H:%M} - {self.hora_salida:%H:%M})"

    def clean(self):
        if self.tiene_refrigerio:
            if not self.hora_inicio_refrigerio or not self.hora_fin_refrigerio:
                raise ValidationError(
                    "Si el horario tiene refrigerio debe indicar la hora de inicio y fin."
                )
            if self.hora_inicio_refrigerio >= self.hora_fin_refrigerio:
                raise ValidationError(
                    "La hora de inicio del refrigerio debe ser anterior a la de fin."
                )

    @property
    def cruza_medianoche(self):
        """Un turno nocturno termina al dia siguiente (ej. 22:00 a 06:00)."""
        return self.hora_salida <= self.hora_entrada

    @property
    def minutos_refrigerio(self):
        if not self.tiene_refrigerio:
            return 0
        inicio = datetime.combine(datetime.today(), self.hora_inicio_refrigerio)
        fin = datetime.combine(datetime.today(), self.hora_fin_refrigerio)
        return int((fin - inicio).total_seconds() // 60)

    @property
    def minutos_jornada(self):
        """Minutos de trabajo esperados, descontando el refrigerio."""
        base = datetime.today()
        entrada = datetime.combine(base, self.hora_entrada)
        salida = datetime.combine(base, self.hora_salida)
        if self.cruza_medianoche:
            salida += timedelta(days=1)
        return int((salida - entrada).total_seconds() // 60) - self.minutos_refrigerio

    @property
    def horas_jornada(self):
        return round(self.minutos_jornada / 60, 2)


class Turno(models.Model):
    """Patron semanal de horarios que se asigna a un empleado."""

    class Tipo(models.TextChoices):
        FIJO = "fijo", "Fijo"
        ROTATIVO = "rotativo", "Rotativo"
        FLEXIBLE = "flexible", "Flexible"

    nombre = models.CharField("nombre", max_length=100, unique=True)
    tipo = models.CharField("tipo", max_length=20, choices=Tipo.choices, default=Tipo.FIJO)
    descripcion = models.CharField("descripcion", max_length=255, blank=True)
    activo = models.BooleanField("activo", default=True)
    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        verbose_name = "turno"
        verbose_name_plural = "turnos"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    def horario_del_dia(self, dia_semana):
        """Devuelve el horario configurado para un dia, o None si es descanso."""
        detalle = self.detalles.filter(dia_semana=dia_semana).select_related("horario").first()
        return detalle.horario if detalle else None


class TurnoDetalle(models.Model):
    """Horario que corresponde a cada dia de la semana dentro de un turno.

    Un dia sin registro (o con horario nulo) se interpreta como descanso.
    """

    turno = models.ForeignKey(
        Turno, verbose_name="turno", on_delete=models.CASCADE, related_name="detalles"
    )
    dia_semana = models.IntegerField("dia de la semana", choices=DiaSemana.choices)
    horario = models.ForeignKey(
        Horario,
        verbose_name="horario",
        on_delete=models.PROTECT,
        related_name="detalles_turno",
        null=True,
        blank=True,
        help_text="Dejar vacio si el dia es de descanso.",
    )

    class Meta:
        verbose_name = "detalle de turno"
        verbose_name_plural = "detalles de turno"
        ordering = ["turno", "dia_semana"]
        constraints = [
            models.UniqueConstraint(
                fields=["turno", "dia_semana"], name="turno_detalle_unico_por_dia"
            )
        ]

    def __str__(self):
        horario = self.horario.nombre if self.horario else "Descanso"
        return f"{self.turno.nombre} - {self.get_dia_semana_display()}: {horario}"

    @property
    def es_descanso(self):
        return self.horario_id is None


class AsignacionTurno(models.Model):
    """Vigencia de un turno para un empleado.

    Se guarda el historico: al cambiar de turno se cierra la asignacion anterior
    con `fecha_fin` en vez de borrarla, para que el recalculo de meses pasados
    siga usando el turno que realmente estaba vigente.
    """

    empleado = models.ForeignKey(
        "employees.Empleado",
        verbose_name="empleado",
        on_delete=models.CASCADE,
        related_name="asignaciones_turno",
    )
    turno = models.ForeignKey(
        Turno, verbose_name="turno", on_delete=models.PROTECT, related_name="asignaciones"
    )
    fecha_inicio = models.DateField("fecha de inicio")
    fecha_fin = models.DateField(
        "fecha de fin", null=True, blank=True, help_text="Vacio significa vigente."
    )
    observacion = models.CharField("observacion", max_length=255, blank=True)
    creado_en = models.DateTimeField("creado en", auto_now_add=True)

    class Meta:
        verbose_name = "asignacion de turno"
        verbose_name_plural = "asignaciones de turno"
        ordering = ["-fecha_inicio"]
        indexes = [models.Index(fields=["empleado", "fecha_inicio", "fecha_fin"])]

    def __str__(self):
        fin = self.fecha_fin or "vigente"
        return f"{self.empleado.codigo_empleado} - {self.turno.nombre} ({self.fecha_inicio} a {fin})"

    def clean(self):
        if self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValidationError("La fecha de fin no puede ser anterior a la de inicio.")


class Feriado(models.Model):
    """Dia no laborable. No genera falta ni tardanza."""

    fecha = models.DateField("fecha")
    descripcion = models.CharField("descripcion", max_length=255)
    es_recurrente = models.BooleanField(
        "se repite cada ano",
        default=False,
        help_text="Para feriados de fecha fija como Fiestas Patrias o Navidad.",
    )
    sede = models.ForeignKey(
        "organization.Sede",
        verbose_name="sede",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="feriados",
        help_text="Vacio significa que aplica a todas las sedes.",
    )
    creado_en = models.DateTimeField("creado en", auto_now_add=True)

    class Meta:
        verbose_name = "feriado"
        verbose_name_plural = "feriados"
        ordering = ["-fecha"]
        constraints = [
            models.UniqueConstraint(fields=["fecha", "sede"], name="feriado_unico_por_fecha_sede")
        ]

    def __str__(self):
        return f"{self.fecha} - {self.descripcion}"


class Permiso(models.Model):
    """Ausencia justificada de un empleado.

    Evita que el motor marque falta a quien tiene vacaciones, descanso medico o
    un permiso aprobado, que es lo que impide aplicar descuentos indebidos.
    """

    class Tipo(models.TextChoices):
        VACACIONES = "vacaciones", "Vacaciones"
        DESCANSO_MEDICO = "descanso_medico", "Descanso medico"
        PERMISO_PERSONAL = "permiso_personal", "Permiso personal"
        LICENCIA = "licencia", "Licencia"
        CAPACITACION = "capacitacion", "Capacitacion"
        COMISION = "comision", "Comision de servicio"

    class EstadoAprobacion(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        APROBADO = "aprobado", "Aprobado"
        RECHAZADO = "rechazado", "Rechazado"

    empleado = models.ForeignKey(
        "employees.Empleado",
        verbose_name="empleado",
        on_delete=models.CASCADE,
        related_name="permisos",
    )
    tipo = models.CharField("tipo", max_length=20, choices=Tipo.choices)
    fecha_inicio = models.DateField("fecha de inicio")
    fecha_fin = models.DateField("fecha de fin")
    con_goce = models.BooleanField(
        "con goce de haber",
        default=True,
        help_text="Si es sin goce, los dias se consideran para descuento.",
    )
    motivo = models.TextField("motivo", blank=True)
    documento = models.FileField(
        "documento de sustento", upload_to="permisos/", null=True, blank=True
    )

    estado = models.CharField(
        "estado",
        max_length=20,
        choices=EstadoAprobacion.choices,
        default=EstadoAprobacion.PENDIENTE,
    )
    aprobado_por = models.ForeignKey(
        "accounts.Usuario",
        verbose_name="aprobado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="permisos_aprobados",
    )
    fecha_aprobacion = models.DateTimeField("fecha de aprobacion", null=True, blank=True)
    observacion_aprobacion = models.CharField("observacion", max_length=255, blank=True)

    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        verbose_name = "permiso"
        verbose_name_plural = "permisos"
        ordering = ["-fecha_inicio"]
        indexes = [models.Index(fields=["empleado", "fecha_inicio", "fecha_fin"])]

    def __str__(self):
        return f"{self.empleado.codigo_empleado} - {self.get_tipo_display()} ({self.fecha_inicio} a {self.fecha_fin})"

    def clean(self):
        if self.fecha_fin < self.fecha_inicio:
            raise ValidationError("La fecha de fin no puede ser anterior a la de inicio.")

    @property
    def dias_totales(self):
        return (self.fecha_fin - self.fecha_inicio).days + 1


class DiaLaborableConfig(models.Model):
    """Parametros globales que usa el motor de asistencia."""

    minutos_tolerancia_global = models.PositiveSmallIntegerField(
        "tolerancia global (minutos)",
        default=0,
        help_text="Se suma a la tolerancia propia de cada horario.",
    )
    considerar_marcacion_unica_como_falta = models.BooleanField(
        "una sola marcacion cuenta como falta",
        default=False,
        help_text=(
            "Si esta activo, un dia con una sola marcacion se considera falta. "
            "Si no, se registra como asistencia incompleta."
        ),
    )
    valor_minuto_tardanza = models.DecimalField(
        "costo del minuto de tardanza",
        max_digits=8,
        decimal_places=4,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Si es 0, el descuento se calcula a partir del sueldo del empleado.",
    )

    class Meta:
        verbose_name = "configuracion de asistencia"
        verbose_name_plural = "configuracion de asistencia"

    def __str__(self):
        return "Configuracion de asistencia"

    @classmethod
    def obtener(cls):
        """Devuelve la configuracion unica del sistema, creandola si no existe."""
        config, _ = cls.objects.get_or_create(pk=1)
        return config

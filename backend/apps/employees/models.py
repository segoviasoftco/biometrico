"""Maestro de empleados y sus datos biometricos.

El `codigo_empleado` es la clave de correlacion con el dispositivo ZKTeco: se
envia como `user_id` al equipo y es el valor con el que regresan las marcaciones.
"""

from django.core.validators import MinValueValidator, RegexValidator
from django.db import models


class Empleado(models.Model):
    """Persona que marca asistencia en el dispositivo biometrico."""

    class Sexo(models.TextChoices):
        MASCULINO = "M", "Masculino"
        FEMENINO = "F", "Femenino"

    class Estado(models.TextChoices):
        ACTIVO = "activo", "Activo"
        INACTIVO = "inactivo", "Inactivo"
        CESADO = "cesado", "Cesado"
        VACACIONES = "vacaciones", "De vacaciones"

    class TipoContrato(models.TextChoices):
        INDEFINIDO = "indefinido", "Plazo indeterminado"
        PLAZO_FIJO = "plazo_fijo", "Plazo fijo"
        PRACTICAS = "practicas", "Practicas"
        LOCACION = "locacion", "Locacion de servicios"

    class PrivilegioDispositivo(models.IntegerChoices):
        """Niveles de privilegio que acepta el firmware ZKTeco.

        Solo se ofrecen estos dos valores: el protocolo descarta silenciosamente
        cualquier otro y lo convierte en usuario comun, asi que exponerlos daria
        una falsa sensacion de haberlos aplicado.
        """

        USUARIO = 0, "Usuario"
        ADMINISTRADOR = 14, "Administrador del equipo"

    # --- Identidad -------------------------------------------------------
    codigo_empleado = models.CharField(
        "codigo de empleado",
        max_length=20,
        unique=True,
        validators=[RegexValidator(r"^\d+$", "El codigo debe ser numerico.")],
        help_text="Identificador numerico usado en el dispositivo biometrico (user_id).",
    )
    dni = models.CharField("DNI", max_length=15, unique=True)
    nombres = models.CharField("nombres", max_length=100)
    apellido_paterno = models.CharField("apellido paterno", max_length=60)
    apellido_materno = models.CharField("apellido materno", max_length=60, blank=True)
    fecha_nacimiento = models.DateField("fecha de nacimiento", null=True, blank=True)
    sexo = models.CharField("sexo", max_length=1, choices=Sexo.choices, blank=True)
    foto = models.ImageField("foto", upload_to="empleados/fotos/", null=True, blank=True)

    # --- Contacto --------------------------------------------------------
    email = models.EmailField("correo electronico", blank=True)
    telefono = models.CharField("telefono", max_length=20, blank=True)
    direccion = models.CharField("direccion", max_length=255, blank=True)

    # --- Datos laborales -------------------------------------------------
    sede = models.ForeignKey(
        "organization.Sede",
        verbose_name="sede",
        on_delete=models.PROTECT,
        related_name="empleados",
    )
    departamento = models.ForeignKey(
        "organization.Departamento",
        verbose_name="departamento",
        on_delete=models.PROTECT,
        related_name="empleados",
    )
    area = models.ForeignKey(
        "organization.Area",
        verbose_name="area",
        on_delete=models.PROTECT,
        related_name="empleados",
        null=True,
        blank=True,
    )
    cargo = models.ForeignKey(
        "organization.Cargo",
        verbose_name="cargo",
        on_delete=models.PROTECT,
        related_name="empleados",
    )
    fecha_ingreso = models.DateField("fecha de ingreso")
    fecha_cese = models.DateField("fecha de cese", null=True, blank=True)
    tipo_contrato = models.CharField(
        "tipo de contrato",
        max_length=20,
        choices=TipoContrato.choices,
        default=TipoContrato.INDEFINIDO,
    )
    estado = models.CharField(
        "estado", max_length=20, choices=Estado.choices, default=Estado.ACTIVO
    )
    sueldo_basico = models.DecimalField(
        "sueldo basico",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Se usa para calcular el monto de los descuentos por tardanza o falta.",
    )

    # --- Datos biometricos y del dispositivo -----------------------------
    # El enrolamiento de huella y rostro se hace en el equipo fisico; aqui solo
    # se refleja el estado que reporta el dispositivo al sincronizar.
    tiene_huella = models.BooleanField("tiene huella enrolada", default=False)
    cantidad_huellas = models.PositiveSmallIntegerField("cantidad de huellas", default=0)
    tiene_rostro = models.BooleanField("tiene rostro enrolado", default=False)
    tiene_tarjeta = models.BooleanField("tiene tarjeta", default=False)
    numero_tarjeta = models.CharField("numero de tarjeta", max_length=20, blank=True)
    privilegio_dispositivo = models.IntegerField(
        "privilegio en el dispositivo",
        choices=PrivilegioDispositivo.choices,
        default=PrivilegioDispositivo.USUARIO,
    )
    password_dispositivo = models.CharField(
        "clave del dispositivo",
        max_length=20,
        blank=True,
        help_text="Clave numerica para marcar por teclado en el equipo.",
    )
    uid_dispositivo = models.PositiveIntegerField(
        "UID en el dispositivo",
        null=True,
        blank=True,
        help_text=(
            "Indice interno que asigna el equipo (1 a 65535). Es distinto del "
            "codigo de empleado y se conserva para no duplicar al re-sincronizar."
        ),
    )
    sincronizado_dispositivo = models.BooleanField("sincronizado", default=False)
    fecha_ultima_sincronizacion = models.DateTimeField(
        "ultima sincronizacion", null=True, blank=True
    )

    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        verbose_name = "empleado"
        verbose_name_plural = "empleados"
        ordering = ["apellido_paterno", "apellido_materno", "nombres"]
        indexes = [
            models.Index(fields=["codigo_empleado"]),
            models.Index(fields=["estado"]),
            models.Index(fields=["sede", "departamento"]),
        ]

    def __str__(self):
        return f"{self.codigo_empleado} - {self.nombre_completo}"

    @property
    def nombre_completo(self):
        return f"{self.apellido_paterno} {self.apellido_materno}, {self.nombres}".strip()

    @property
    def esta_activo(self):
        return self.estado == self.Estado.ACTIVO

    @property
    def tiene_biometria(self):
        """Indica si el empleado puede marcar sin recurrir a clave o tarjeta."""
        return self.tiene_huella or self.tiene_rostro


class HuellaEmpleado(models.Model):
    """Respaldo de las plantillas de huella descargadas del dispositivo.

    Permite restaurar el enrolamiento en un equipo nuevo o luego de un reseteo,
    sin obligar al empleado a volver a registrar sus dedos.

    El rostro no aparece aqui: el algoritmo facial de ZKTeco es propietario y su
    plantilla no puede extraerse por el protocolo estandar del equipo.
    """

    empleado = models.ForeignKey(
        Empleado, verbose_name="empleado", on_delete=models.CASCADE, related_name="huellas"
    )
    finger_id = models.PositiveSmallIntegerField(
        "dedo", help_text="Indice del dedo segun el dispositivo (0 a 9)."
    )
    template = models.TextField(
        "plantilla", help_text="Plantilla biometrica codificada en base64."
    )
    size = models.PositiveIntegerField("tamano en bytes", default=0)
    valid = models.PositiveSmallIntegerField("validez", default=1)
    dispositivo_origen = models.ForeignKey(
        "devices.Dispositivo",
        verbose_name="dispositivo de origen",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="huellas_respaldadas",
    )
    capturado_en = models.DateTimeField("capturado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        verbose_name = "huella de empleado"
        verbose_name_plural = "huellas de empleados"
        ordering = ["empleado", "finger_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["empleado", "finger_id"], name="huella_unica_por_dedo"
            )
        ]

    def __str__(self):
        return f"{self.empleado.codigo_empleado} - dedo {self.finger_id}"

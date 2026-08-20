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

    class Modo(models.TextChoices):
        """Forma en que el sistema se comunica con el equipo.

        SDK: el servidor abre una conexion al equipo por el puerto 4370.
        ADMS: el equipo se conecta al servidor por HTTP y le envia los datos.
        """

        SDK = "sdk", "SDK (el servidor consulta al equipo por el puerto 4370)"
        ADMS = "adms", "ADMS / Push (el equipo envia los datos al servidor)"

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

    # --- Comunicacion ADMS ------------------------------------------------
    modo = models.CharField(
        "modo de comunicacion", max_length=10, choices=Modo.choices, default=Modo.SDK
    )
    adms_habilitado = models.BooleanField(
        "aceptar conexiones ADMS",
        default=False,
        help_text=(
            "Permite que este equipo envie datos a los endpoints /iclock/. "
            "Los datos solo se aceptan si el numero de serie coincide."
        ),
    )
    adms_ip_permitida = models.GenericIPAddressField(
        "IP autorizada para ADMS",
        protocol="IPv4",
        null=True,
        blank=True,
        help_text=(
            "Si se indica, solo se aceptan peticiones ADMS que provengan de esta IP. "
            "Es la principal defensa contra marcaciones falsas desde la red."
        ),
    )
    ultima_conexion_adms = models.DateTimeField(
        "ultima conexion ADMS", null=True, blank=True
    )
    adms_stamp = models.CharField(
        "marca de tiempo de marcaciones",
        max_length=32,
        default="0",
        help_text="Contador que el equipo usa para saber desde donde reenviar las marcaciones.",
    )
    adms_op_stamp = models.CharField(
        "marca de tiempo de operaciones", max_length=32, default="0"
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


class ComandoDispositivo(models.Model):
    """Comando en cola para enviar al equipo cuando trabaja en modo ADMS.

    En ADMS el servidor no puede iniciar la comunicacion: es el equipo el que
    consulta periodicamente si hay algo pendiente. Por eso las ordenes (dar de
    alta un empleado, borrarlo, pedir un reenvio de datos) se encolan aqui y se
    entregan cuando el equipo pregunta.
    """

    class Tipo(models.TextChoices):
        ACTUALIZAR_USUARIO = "actualizar_usuario", "Actualizar usuario"
        ELIMINAR_USUARIO = "eliminar_usuario", "Eliminar usuario"
        ACTUALIZAR_HUELLA = "actualizar_huella", "Restaurar huella"
        SOLICITAR_DATOS = "solicitar_datos", "Solicitar reenvio de datos"
        SOLICITAR_INFO = "solicitar_info", "Solicitar informacion del equipo"
        LIMPIAR_MARCACIONES = "limpiar_marcaciones", "Limpiar marcaciones del equipo"
        REINICIAR = "reiniciar", "Reiniciar el equipo"

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente de entrega"
        ENVIADO = "enviado", "Entregado al equipo"
        CONFIRMADO = "confirmado", "Ejecutado correctamente"
        FALLIDO = "fallido", "El equipo reporto un error"

    dispositivo = models.ForeignKey(
        Dispositivo,
        verbose_name="dispositivo",
        on_delete=models.CASCADE,
        related_name="comandos",
    )
    tipo = models.CharField("tipo", max_length=30, choices=Tipo.choices)
    comando = models.TextField(
        "comando",
        help_text="Instruccion en el formato que espera el equipo, sin el prefijo C:<id>:",
    )
    estado = models.CharField(
        "estado", max_length=20, choices=Estado.choices, default=Estado.PENDIENTE
    )
    empleado = models.ForeignKey(
        "employees.Empleado",
        verbose_name="empleado relacionado",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comandos_dispositivo",
    )
    codigo_retorno = models.IntegerField(
        "codigo de retorno",
        null=True,
        blank=True,
        help_text="Lo reporta el equipo al ejecutar el comando. 0 significa exito.",
    )
    respuesta = models.CharField("respuesta del equipo", max_length=255, blank=True)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="creado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comandos_creados",
    )
    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    enviado_en = models.DateTimeField("entregado en", null=True, blank=True)
    confirmado_en = models.DateTimeField("confirmado en", null=True, blank=True)

    class Meta:
        verbose_name = "comando de dispositivo"
        verbose_name_plural = "comandos de dispositivo"
        ordering = ["creado_en"]
        indexes = [
            models.Index(fields=["dispositivo", "estado"]),
            models.Index(fields=["-creado_en"]),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} ({self.get_estado_display()})"


class PeticionADMS(models.Model):
    """Registro crudo de cada peticion que el equipo hace al servidor.

    El protocolo ADMS es propietario y su formato cambia entre firmwares. Tener
    la peticion tal cual llego es lo que permite diagnosticar por que un equipo
    concreto no envia lo que se espera, sin depender de suposiciones.

    Se conserva una ventana corta de peticiones: son muchas y solo interesan
    para diagnostico reciente.
    """

    dispositivo = models.ForeignKey(
        Dispositivo,
        verbose_name="dispositivo",
        on_delete=models.CASCADE,
        related_name="peticiones_adms",
        null=True,
        blank=True,
        help_text="Nulo si el numero de serie no corresponde a ningun equipo registrado.",
    )
    numero_serie = models.CharField("numero de serie recibido", max_length=100, blank=True)
    ruta = models.CharField("ruta", max_length=255)
    metodo = models.CharField("metodo HTTP", max_length=10)
    parametros = models.JSONField("parametros de la URL", null=True, blank=True)
    cuerpo = models.TextField("cuerpo de la peticion", blank=True)
    respuesta = models.TextField("respuesta enviada", blank=True)
    ip_origen = models.GenericIPAddressField("IP de origen", null=True, blank=True)
    aceptada = models.BooleanField(
        "aceptada",
        default=True,
        help_text="Falso si se rechazo por numero de serie o IP no autorizados.",
    )
    registros_procesados = models.IntegerField("registros procesados", default=0)
    recibida_en = models.DateTimeField("recibida en", auto_now_add=True)

    class Meta:
        verbose_name = "peticion ADMS"
        verbose_name_plural = "peticiones ADMS"
        ordering = ["-recibida_en"]
        indexes = [
            models.Index(fields=["-recibida_en"]),
            models.Index(fields=["dispositivo", "-recibida_en"]),
        ]

    def __str__(self):
        return f"{self.metodo} {self.ruta} ({self.recibida_en:%Y-%m-%d %H:%M:%S})"

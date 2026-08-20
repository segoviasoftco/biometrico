"""Comunicacion con el dispositivo biometrico ZKTeco.

Envuelve la libreria `pyzk`, que habla el protocolo nativo de ZKTeco sobre el
puerto 4370, y traduce sus estructuras a los modelos del sistema.

Sobre el enrolamiento biometrico
--------------------------------
El registro de huella y rostro se hace en el equipo fisico. La huella si puede
descargarse y respaldarse aqui (y restaurarse luego con `save_user_template`),
pero la plantilla de rostro no: el algoritmo facial de ZKTeco es propietario y
no se expone por el protocolo estandar. Para el rostro solo se refleja un
indicador de si el empleado ya esta enrolado en el equipo.
"""

import base64
import logging
from contextlib import contextmanager
from datetime import datetime

from django.utils import timezone
from zk import ZK
from zk.exception import ZKError

logger = logging.getLogger("apps.devices")

# El equipo indexa a sus usuarios con un entero de 16 bits.
MAX_UID_DISPOSITIVO = 65535


class ErrorDispositivo(Exception):
    """Falla al comunicarse u operar con el dispositivo biometrico."""


# Mapeo entre los codigos de verificacion del firmware ZKTeco y los del sistema.
# El firmware usa 15 para rostro en los equipos de la linea visible light.
MAPA_VERIFICACION = {
    0: 0,   # clave
    1: 1,   # huella
    2: 2,   # tarjeta
    15: 15,  # rostro
}


class ServicioZK:
    """Operaciones sobre un dispositivo biometrico ZKTeco.

    Cada metodo publico abre y cierra su propia conexion. El equipo admite una
    sola sesion a la vez, asi que mantenerla abierta bloquearia al resto del
    sistema y a las tareas programadas.
    """

    def __init__(self, dispositivo):
        self.dispositivo = dispositivo

    # ------------------------------------------------------------------
    # Conexion
    # ------------------------------------------------------------------
    @contextmanager
    def _conexion(self, deshabilitar_equipo=True):
        """Abre una conexion y garantiza que el equipo quede utilizable.

        Durante una sincronizacion se deshabilita el equipo para que nadie marque
        mientras se escriben datos, y se vuelve a habilitar pase lo que pase.
        """
        zk = ZK(
            self.dispositivo.ip,
            port=self.dispositivo.puerto,
            timeout=self.dispositivo.timeout,
            password=self.dispositivo.password_comunicacion,
            force_udp=self.dispositivo.force_udp,
            ommit_ping=True,
        )
        conexion = None
        try:
            conexion = zk.connect()
        except (ZKError, OSError) as exc:
            self._marcar_estado(self.dispositivo.Estado.ERROR)
            raise ErrorDispositivo(
                f"No se pudo conectar con el dispositivo {self.dispositivo.ip}:"
                f"{self.dispositivo.puerto}. Detalle: {exc}"
            ) from exc

        try:
            if deshabilitar_equipo:
                conexion.disable_device()
            yield conexion
        finally:
            try:
                if deshabilitar_equipo:
                    conexion.enable_device()
            except Exception:  # noqa: BLE001 - el cierre no debe ocultar el error real
                logger.warning("No se pudo rehabilitar el dispositivo %s", self.dispositivo.ip)
            try:
                conexion.disconnect()
            except Exception:  # noqa: BLE001
                logger.warning("No se pudo cerrar la conexion con %s", self.dispositivo.ip)

    def _marcar_estado(self, estado, con_conexion_exitosa=False):
        campos = ["estado"]
        self.dispositivo.estado = estado
        if con_conexion_exitosa:
            self.dispositivo.ultima_conexion = timezone.now()
            campos.append("ultima_conexion")
        self.dispositivo.save(update_fields=campos)

    # ------------------------------------------------------------------
    # Informacion del equipo
    # ------------------------------------------------------------------
    def probar_conexion(self):
        """Verifica la conexion y actualiza los datos que reporta el equipo."""
        with self._conexion(deshabilitar_equipo=False) as conexion:
            info = {
                "numero_serie": self._leer(conexion.get_serialnumber),
                "modelo": self._leer(conexion.get_device_name),
                "version_firmware": self._leer(conexion.get_firmware_version),
                "version_plataforma": self._leer(conexion.get_platform),
                "version_rostro": self._leer(conexion.get_face_version),
                "version_huella": self._leer(conexion.get_fp_version),
                "mac": self._leer(conexion.get_mac),
            }
            hora_equipo = self._leer(conexion.get_time)

        for campo, valor in info.items():
            if valor:
                setattr(self.dispositivo, campo, str(valor)[:100])
        self.dispositivo.estado = self.dispositivo.Estado.CONECTADO
        self.dispositivo.ultima_conexion = timezone.now()
        self.dispositivo.save()

        info["hora_dispositivo"] = hora_equipo
        return info

    @staticmethod
    def _leer(metodo):
        """Ejecuta un getter del equipo tolerando que el firmware no lo soporte.

        No todos los modelos responden a todos los comandos; que falte el dato de
        la version facial no debe abortar una prueba de conexion.
        """
        try:
            return metodo()
        except Exception as exc:  # noqa: BLE001
            logger.debug("El dispositivo no respondio a %s: %s", metodo.__name__, exc)
            return None

    def sincronizar_hora(self):
        """Ajusta el reloj del equipo a la hora del servidor.

        Un reloj desfasado produce tardanzas y faltas falsas, por eso conviene
        sincronizarlo periodicamente.
        """
        ahora = timezone.localtime().replace(tzinfo=None)
        with self._conexion(deshabilitar_equipo=False) as conexion:
            conexion.set_time(ahora)
        return ahora

    # ------------------------------------------------------------------
    # Empleados
    # ------------------------------------------------------------------
    def subir_empleados(self, empleados):
        """Envia los datos maestros de los empleados al equipo.

        Solo sube identidad y privilegios: la huella y el rostro se enrolan en el
        propio dispositivo.

        El `uid` es el indice interno del equipo y viaja en 16 bits, por lo que
        no puede ser el codigo del empleado (que suele excederlo). Se reutiliza
        el uid que ya tenga el usuario en el equipo y, si es nuevo, se le asigna
        el primero libre; asi una segunda sincronizacion actualiza al empleado en
        lugar de duplicarlo.
        """
        empleados = list(empleados)
        resultado = {"procesados": 0, "fallidos": 0, "errores": []}

        with self._conexion() as conexion:
            uid_por_codigo, siguiente_uid = self._mapear_uids(conexion)

            for empleado in empleados:
                codigo = str(empleado.codigo_empleado)
                uid = uid_por_codigo.get(codigo) or empleado.uid_dispositivo
                if not uid:
                    uid = siguiente_uid
                    siguiente_uid += 1

                if uid > MAX_UID_DISPOSITIVO:
                    resultado["fallidos"] += 1
                    resultado["errores"].append(
                        {
                            "empleado": codigo,
                            "error": "El dispositivo alcanzo su capacidad maxima de usuarios.",
                        }
                    )
                    continue

                try:
                    conexion.set_user(
                        uid=uid,
                        name=self._nombre_para_equipo(empleado),
                        privilege=empleado.privilegio_dispositivo,
                        password=empleado.password_dispositivo or "",
                        group_id="",
                        user_id=codigo,
                        card=int(empleado.numero_tarjeta) if empleado.numero_tarjeta else 0,
                    )
                    empleado.uid_dispositivo = uid
                    resultado["procesados"] += 1
                except Exception as exc:  # noqa: BLE001 - un empleado no debe abortar el lote
                    resultado["fallidos"] += 1
                    resultado["errores"].append({"empleado": codigo, "error": str(exc)})
                    logger.warning("Error al subir el empleado %s: %s", codigo, exc)

        codigos_fallidos = {err["empleado"] for err in resultado["errores"]}
        self._marcar_sincronizados(
            [e for e in empleados if str(e.codigo_empleado) not in codigos_fallidos]
        )
        return resultado

    @staticmethod
    def _mapear_uids(conexion):
        """Devuelve el mapa codigo -> uid del equipo y el primer uid libre."""
        try:
            usuarios = conexion.get_users() or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudieron leer los usuarios del equipo: %s", exc)
            return {}, 1

        uid_por_codigo = {str(u.user_id): u.uid for u in usuarios}
        siguiente_uid = max((u.uid for u in usuarios), default=0) + 1
        return uid_por_codigo, siguiente_uid

    @staticmethod
    def _nombre_para_equipo(empleado):
        """La pantalla del equipo trunca los nombres largos, asi que se acortan."""
        nombre = f"{empleado.nombres.split()[0]} {empleado.apellido_paterno}"
        return nombre[:24]

    @staticmethod
    def _marcar_sincronizados(empleados):
        from apps.employees.models import Empleado

        if not empleados:
            return

        ahora = timezone.now()
        for empleado in empleados:
            empleado.sincronizado_dispositivo = True
            empleado.fecha_ultima_sincronizacion = ahora

        Empleado.objects.bulk_update(
            empleados,
            ["sincronizado_dispositivo", "fecha_ultima_sincronizacion", "uid_dispositivo"],
        )

    def descargar_empleados(self):
        """Lee los usuarios del equipo y los concilia con la base de datos.

        No crea ni borra empleados por su cuenta: reporta las diferencias para
        que un responsable decida, porque un alta o baja automatica a partir del
        equipo podria borrar datos laborales.
        """
        from apps.employees.models import Empleado

        with self._conexion() as conexion:
            usuarios = conexion.get_users()

        codigos_equipo = {str(u.user_id) for u in usuarios}
        codigos_sistema = set(
            Empleado.objects.values_list("codigo_empleado", flat=True)
        )

        return {
            "total_en_equipo": len(usuarios),
            "usuarios": [
                {
                    "uid": u.uid,
                    "user_id": str(u.user_id),
                    "nombre": u.name,
                    "privilegio": u.privilege,
                    "tarjeta": u.card,
                    "registrado_en_sistema": str(u.user_id) in codigos_sistema,
                }
                for u in usuarios
            ],
            "solo_en_equipo": sorted(codigos_equipo - codigos_sistema),
            "solo_en_sistema": sorted(codigos_sistema - codigos_equipo),
        }

    def eliminar_empleado(self, codigo_empleado):
        """Borra un usuario del equipo, protegiendo al administrador.

        El administrador del equipo (6999383 por defecto) queda excluido: sin el
        no se puede entrar al menu del dispositivo para reconfigurarlo.
        """
        codigo = str(codigo_empleado)
        if codigo == str(self.dispositivo.admin_user_id):
            raise ErrorDispositivo(
                f"El usuario {codigo} es el administrador del dispositivo y no puede eliminarse."
            )

        with self._conexion() as conexion:
            conexion.delete_user(user_id=codigo)
        return True

    # ------------------------------------------------------------------
    # Huellas
    # ------------------------------------------------------------------
    def respaldar_huellas(self):
        """Descarga las plantillas de huella y actualiza los indicadores biometricos.

        El rostro no se descarga (no lo permite el protocolo); su indicador se
        deduce de la informacion del usuario en el equipo.
        """
        from apps.employees.models import Empleado, HuellaEmpleado

        with self._conexion() as conexion:
            usuarios = conexion.get_users()
            plantillas = conexion.get_templates()

        # El equipo identifica las plantillas por `uid` interno, no por el
        # codigo de empleado, asi que hace falta el puente entre ambos.
        uid_a_codigo = {u.uid: str(u.user_id) for u in usuarios}

        empleados = {
            e.codigo_empleado: e
            for e in Empleado.objects.filter(codigo_empleado__in=uid_a_codigo.values())
        }

        guardadas = 0
        huellas_por_empleado = {}

        for plantilla in plantillas:
            codigo = uid_a_codigo.get(plantilla.uid)
            empleado = empleados.get(codigo) if codigo else None
            if empleado is None:
                continue

            HuellaEmpleado.objects.update_or_create(
                empleado=empleado,
                finger_id=plantilla.fid,
                defaults={
                    "template": base64.b64encode(plantilla.template).decode("ascii"),
                    "size": len(plantilla.template),
                    "valid": plantilla.valid,
                    "dispositivo_origen": self.dispositivo,
                },
            )
            huellas_por_empleado[empleado.id] = huellas_por_empleado.get(empleado.id, 0) + 1
            guardadas += 1

        self._actualizar_indicadores_biometricos(empleados, huellas_por_empleado)

        return {
            "plantillas_descargadas": guardadas,
            "empleados_con_huella": len(huellas_por_empleado),
            "usuarios_en_equipo": len(usuarios),
        }

    @staticmethod
    def _actualizar_indicadores_biometricos(empleados, huellas_por_empleado):
        from apps.employees.models import Empleado

        para_actualizar = []
        for empleado in empleados.values():
            cantidad = huellas_por_empleado.get(empleado.id, 0)
            empleado.cantidad_huellas = cantidad
            empleado.tiene_huella = cantidad > 0
            para_actualizar.append(empleado)

        if para_actualizar:
            Empleado.objects.bulk_update(
                para_actualizar, ["cantidad_huellas", "tiene_huella"]
            )

    def restaurar_huellas(self, empleado):
        """Re-escribe en el equipo las huellas respaldadas de un empleado.

        Sirve cuando se reemplaza o resetea el dispositivo y no se quiere obligar
        al empleado a enrolarse de nuevo.
        """
        from zk.user import User
        from zk.finger import Finger

        huellas = list(empleado.huellas.all())
        if not huellas:
            raise ErrorDispositivo(
                f"El empleado {empleado.codigo_empleado} no tiene huellas respaldadas."
            )

        with self._conexion() as conexion:
            uid_por_codigo, siguiente_uid = self._mapear_uids(conexion)
            codigo = str(empleado.codigo_empleado)
            uid = uid_por_codigo.get(codigo) or empleado.uid_dispositivo or siguiente_uid

            usuario = User(
                uid=uid,
                name=self._nombre_para_equipo(empleado),
                privilege=empleado.privilegio_dispositivo,
                password=empleado.password_dispositivo or "",
                group_id="",
                user_id=codigo,
                card=int(empleado.numero_tarjeta) if empleado.numero_tarjeta else 0,
            )
            dedos = [
                Finger(
                    uid=uid,
                    fid=h.finger_id,
                    valid=h.valid,
                    template=base64.b64decode(h.template),
                )
                for h in huellas
            ]
            conexion.save_user_template(usuario, dedos)

        if empleado.uid_dispositivo != uid:
            empleado.uid_dispositivo = uid
            empleado.save(update_fields=["uid_dispositivo"])

        return {"empleado": codigo, "huellas_restauradas": len(dedos)}

    # ------------------------------------------------------------------
    # Marcaciones
    # ------------------------------------------------------------------
    def descargar_marcaciones(self, desde=None):
        """Descarga las marcaciones del equipo y las guarda sin duplicar.

        La restriccion unica de `Marcacion` hace la operacion idempotente: se
        puede repetir la descarga del mismo rango sin generar registros dobles.
        No se borra nada del equipo tras la descarga.
        """
        from apps.attendance.models import Marcacion
        from apps.employees.models import Empleado

        with self._conexion() as conexion:
            registros = conexion.get_attendance() or []

        if desde is not None:
            registros = [r for r in registros if self._a_datetime(r.timestamp) >= desde]

        if not registros:
            return {"leidas": 0, "nuevas": 0, "sin_empleado": [], "fechas_afectadas": []}

        codigos = {str(r.user_id) for r in registros}
        empleados = {
            e.codigo_empleado: e
            for e in Empleado.objects.filter(codigo_empleado__in=codigos)
        }
        sin_empleado = sorted(codigos - set(empleados))

        marcaciones = []
        fechas_afectadas = set()
        for registro in registros:
            empleado = empleados.get(str(registro.user_id))
            if empleado is None:
                # Usuario presente en el equipo pero no dado de alta en el
                # sistema (por ejemplo el administrador del dispositivo).
                continue

            fecha_hora = self._a_datetime(registro.timestamp)
            marcaciones.append(
                Marcacion(
                    empleado=empleado,
                    dispositivo=self.dispositivo,
                    fecha_hora=fecha_hora,
                    tipo_verificacion=MAPA_VERIFICACION.get(registro.status, 99),
                    tipo_marcacion=registro.punch if registro.punch is not None else 255,
                    uid_dispositivo=getattr(registro, "uid", None),
                )
            )
            fechas_afectadas.add((empleado.id, timezone.localtime(fecha_hora).date()))

        # Con `ignore_conflicts` la base de datos descarta los duplicados, pero no
        # devuelve las claves de los objetos insertados, por lo que las nuevas se
        # cuentan por diferencia.
        total_previo = Marcacion.objects.count()
        Marcacion.objects.bulk_create(marcaciones, ignore_conflicts=True)
        nuevas = Marcacion.objects.count() - total_previo

        self.dispositivo.ultima_sincronizacion_marcaciones = timezone.now()
        self.dispositivo.save(update_fields=["ultima_sincronizacion_marcaciones"])

        return {
            "leidas": len(registros),
            "nuevas": nuevas,
            "sin_empleado": sin_empleado,
            "fechas_afectadas": [
                {"empleado_id": eid, "fecha": fecha.isoformat()}
                for eid, fecha in sorted(fechas_afectadas)
            ],
        }

    @staticmethod
    def _a_datetime(valor):
        """Convierte la hora del equipo (sin zona) a un datetime con zona horaria.

        El dispositivo reporta la hora local configurada en el, por eso se
        interpreta en la zona horaria del proyecto.
        """
        if isinstance(valor, str):
            valor = datetime.strptime(valor, "%Y-%m-%d %H:%M:%S")
        if timezone.is_naive(valor):
            return timezone.make_aware(valor, timezone.get_current_timezone())
        return valor

    def limpiar_marcaciones(self):
        """Borra las marcaciones almacenadas en el equipo.

        Operacion irreversible: solo debe ejecutarse tras confirmar que las
        marcaciones ya fueron descargadas al sistema.
        """
        with self._conexion() as conexion:
            conexion.clear_attendance()
        return True

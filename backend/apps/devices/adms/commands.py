"""Construccion y encolado de comandos para los equipos en modo ADMS.

En ADMS el servidor no puede iniciar la comunicacion. Las ordenes se dejan en
cola y el equipo las recoge la proxima vez que consulta `/iclock/getrequest`,
que segun su configuracion ocurre cada pocos segundos.
"""

import base64
import binascii
import logging

from apps.devices.models import ComandoDispositivo

logger = logging.getLogger("apps.devices")

# Zona horaria vacia: el equipo aplica la suya. Se envia por compatibilidad,
# porque algunos firmwares rechazan el comando si falta el campo.
TZ_POR_DEFECTO = "0" * 16


def _nombre_para_equipo(empleado):
    """La pantalla del equipo trunca los nombres largos."""
    primer_nombre = empleado.nombres.split()[0] if empleado.nombres else ""
    return f"{primer_nombre} {empleado.apellido_paterno}".strip()[:24]


def comando_actualizar_usuario(empleado):
    """Alta o actualizacion de un empleado en el equipo.

    A diferencia del SDK, aqui no hace falta gestionar el `uid` de 16 bits: el
    protocolo identifica al usuario por su PIN, que es el codigo de empleado.
    """
    campos = [
        f"PIN={empleado.codigo_empleado}",
        f"Name={_nombre_para_equipo(empleado)}",
        f"Pri={empleado.privilegio_dispositivo}",
        f"Passwd={empleado.password_dispositivo or ''}",
        f"Card={empleado.numero_tarjeta or ''}",
        "Grp=1",
        f"TZ={TZ_POR_DEFECTO}",
    ]
    return "DATA UPDATE USERINFO " + "\t".join(campos)


def comando_eliminar_usuario(codigo_empleado):
    return f"DATA DELETE USERINFO PIN={codigo_empleado}"


def comando_actualizar_huella(empleado, huella):
    """Restaura en el equipo una plantilla de huella respaldada.

    La plantilla se guarda en base64 en la base de datos, que es el mismo
    formato que espera el protocolo, por lo que viaja tal cual.
    """
    plantilla = huella.template.strip()
    campos = [
        f"PIN={empleado.codigo_empleado}",
        f"FID={huella.finger_id}",
        f"Size={huella.size or len(plantilla)}",
        f"Valid={huella.valid}",
        f"TMP={plantilla}",
    ]
    return "DATA UPDATE FINGERTMP " + "\t".join(campos)


# Comandos sin parametros que entiende el equipo.
COMANDOS_SIMPLES = {
    ComandoDispositivo.Tipo.SOLICITAR_DATOS: "CHECK",
    ComandoDispositivo.Tipo.SOLICITAR_INFO: "INFO",
    ComandoDispositivo.Tipo.LIMPIAR_MARCACIONES: "CLEAR LOG",
    ComandoDispositivo.Tipo.REINICIAR: "REBOOT",
}


def encolar(dispositivo, tipo, comando, empleado=None, usuario=None):
    """Deja un comando en la cola del equipo."""
    return ComandoDispositivo.objects.create(
        dispositivo=dispositivo,
        tipo=tipo,
        comando=comando,
        empleado=empleado,
        creado_por=usuario,
    )


def encolar_empleados(dispositivo, empleados, usuario=None):
    """Encola el alta o actualizacion de varios empleados.

    Reemplaza los comandos pendientes del mismo empleado: si aun no se
    entregaron, el equipo solo necesita la version mas reciente.
    """
    empleados = list(empleados)
    if not empleados:
        return []

    ComandoDispositivo.objects.filter(
        dispositivo=dispositivo,
        empleado__in=empleados,
        tipo=ComandoDispositivo.Tipo.ACTUALIZAR_USUARIO,
        estado=ComandoDispositivo.Estado.PENDIENTE,
    ).delete()

    comandos = [
        ComandoDispositivo(
            dispositivo=dispositivo,
            tipo=ComandoDispositivo.Tipo.ACTUALIZAR_USUARIO,
            comando=comando_actualizar_usuario(empleado),
            empleado=empleado,
            creado_por=usuario,
        )
        for empleado in empleados
    ]
    return ComandoDispositivo.objects.bulk_create(comandos)


def encolar_huellas(dispositivo, empleado, usuario=None):
    """Encola la restauracion de todas las huellas respaldadas de un empleado."""
    comandos = []
    for huella in empleado.huellas.all():
        if not _es_base64_valido(huella.template):
            logger.warning(
                "Se omitio la huella %s del empleado %s: la plantilla no es base64 valido.",
                huella.finger_id,
                empleado.codigo_empleado,
            )
            continue
        comandos.append(
            ComandoDispositivo(
                dispositivo=dispositivo,
                tipo=ComandoDispositivo.Tipo.ACTUALIZAR_HUELLA,
                comando=comando_actualizar_huella(empleado, huella),
                empleado=empleado,
                creado_por=usuario,
            )
        )
    return ComandoDispositivo.objects.bulk_create(comandos)


def _es_base64_valido(texto):
    """Evita enviar al equipo una plantilla corrupta, que podria bloquearlo."""
    try:
        base64.b64decode(texto, validate=True)
        return True
    except (binascii.Error, ValueError):
        return False


def obtener_pendientes(dispositivo, limite=10):
    """Comandos pendientes de entrega, en orden de creacion.

    Se entregan de a pocos: un lote grande puede desbordar el buffer del equipo
    y hacer que descarte todo.
    """
    return list(
        ComandoDispositivo.objects.filter(
            dispositivo=dispositivo, estado=ComandoDispositivo.Estado.PENDIENTE
        ).order_by("creado_en")[:limite]
    )


def formatear_para_equipo(comandos):
    """Arma el cuerpo de la respuesta a /iclock/getrequest.

    Cada linea tiene la forma `C:<id>:<comando>`; el equipo devuelve ese id al
    confirmar la ejecucion.
    """
    return "\n".join(f"C:{c.id}:{c.comando}" for c in comandos)

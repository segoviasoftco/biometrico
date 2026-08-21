"""Tareas programadas de sincronizacion con los dispositivos."""

import logging

from celery import shared_task

from apps.devices.models import Dispositivo
from apps.devices.services.sincronizacion import descargar_y_procesar

logger = logging.getLogger("apps.devices")


@shared_task(name="apps.devices.tasks.sincronizar_marcaciones_task")
def sincronizar_marcaciones_task(dispositivo_id=None):
    """Descarga las marcaciones de los dispositivos activos y procesa los dias.

    La ejecuta Celery Beat cada 15 minutos. Un equipo caido no debe impedir que
    se sincronicen los demas, por eso los errores se registran y se continua.

    Solo aplica a equipos en modo SDK: en ADMS las marcaciones llegan solas por
    push (`/iclock/cdata`), asi que intentar aqui una conexion por el puerto
    4370 -- que en ADMS esta cerrado a proposito -- solo generaria un fallo
    cada 15 minutos sin ningun beneficio.
    """
    dispositivos = Dispositivo.objects.filter(activo=True, modo=Dispositivo.Modo.SDK)
    if dispositivo_id:
        dispositivos = dispositivos.filter(id=dispositivo_id)

    resumen = []
    for dispositivo in dispositivos:
        registro, resultado = descargar_y_procesar(
            dispositivo, desde=dispositivo.ultima_sincronizacion_marcaciones, procesar=True
        )
        resumen.append(
            {
                "dispositivo": dispositivo.nombre,
                "estado": registro.estado,
                "nuevas": (resultado or {}).get("nuevas", 0),
                "mensaje": registro.mensaje,
            }
        )
        if resultado is None:
            logger.warning(
                "No se pudo sincronizar el dispositivo %s: %s", dispositivo.ip, registro.mensaje
            )

    return resumen


@shared_task(name="apps.devices.tasks.sincronizar_hora_task")
def sincronizar_hora_task():
    """Ajusta el reloj de los equipos al del servidor.

    Se ejecuta bajo demanda; conviene programarla si el equipo tiende a
    desfasarse, porque un reloj corrido genera tardanzas inexistentes.

    Solo aplica a equipos en modo SDK. En ADMS el equipo no expone el puerto
    4370 y ademas ya recibe su zona horaria en cada handshake
    (`TimeZone=` en `devices/adms/views.py`), asi que no hace falta sincronizar
    la hora por este camino.
    """
    from apps.devices.models import RegistroSincronizacion
    from apps.devices.services.sincronizacion import ejecutar_operacion

    resultados = []
    for dispositivo in Dispositivo.objects.filter(activo=True, modo=Dispositivo.Modo.SDK):
        registro, _ = ejecutar_operacion(
            dispositivo,
            RegistroSincronizacion.Operacion.SINCRONIZAR_HORA,
            lambda servicio: servicio.sincronizar_hora(),
        )
        resultados.append({"dispositivo": dispositivo.nombre, "estado": registro.estado})
    return resultados

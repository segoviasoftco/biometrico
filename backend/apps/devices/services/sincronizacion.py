"""Orquestacion de las sincronizaciones con el dispositivo.

Concentra aqui el patron comun a toda operacion contra el equipo: abrir un
registro en la bitacora, ejecutar, y cerrarlo con el resultado o el error. De
ese modo las vistas y las tareas de Celery comparten el mismo comportamiento.
"""

import logging

from django.utils import timezone

from apps.devices.models import RegistroSincronizacion
from apps.devices.services.zk_service import ErrorDispositivo, ServicioZK

logger = logging.getLogger("apps.devices")


def ejecutar_operacion(dispositivo, operacion, funcion, usuario=None):
    """Ejecuta una operacion contra el equipo dejando constancia en la bitacora.

    Devuelve la tupla (registro, resultado). Si falla, `resultado` es None y el
    registro queda en estado fallido con el mensaje del error.
    """
    registro = RegistroSincronizacion.objects.create(
        dispositivo=dispositivo, operacion=operacion, ejecutado_por=usuario
    )
    servicio = ServicioZK(dispositivo)

    try:
        resultado = funcion(servicio)
    except ErrorDispositivo as exc:
        registro.estado = RegistroSincronizacion.Estado.FALLIDO
        registro.mensaje = str(exc)
        registro.fin = timezone.now()
        registro.save()
        logger.warning("Fallo la operacion %s en %s: %s", operacion, dispositivo.ip, exc)
        return registro, None
    except Exception as exc:  # noqa: BLE001 - cualquier fallo debe quedar registrado
        registro.estado = RegistroSincronizacion.Estado.FALLIDO
        registro.mensaje = f"Error inesperado: {exc}"
        registro.fin = timezone.now()
        registro.save()
        logger.exception("Error inesperado en la operacion %s", operacion)
        return registro, None

    registro.estado = RegistroSincronizacion.Estado.EXITOSO
    registro.detalle = _serializable(resultado)
    registro.fin = timezone.now()
    _completar_contadores(registro, resultado)
    registro.save()
    return registro, resultado


def _completar_contadores(registro, resultado):
    """Traslada al registro los contadores que reporte la operacion."""
    if not isinstance(resultado, dict):
        return

    equivalencias = {
        "registros_procesados": ("procesados", "leidas", "plantillas_descargadas", "total_en_equipo"),
        "registros_nuevos": ("nuevas", "huellas_restauradas"),
        "registros_fallidos": ("fallidos",),
    }
    for campo, claves in equivalencias.items():
        for clave in claves:
            if clave in resultado:
                setattr(registro, campo, resultado[clave] or 0)
                break

    if registro.registros_fallidos and registro.registros_procesados:
        registro.estado = RegistroSincronizacion.Estado.PARCIAL


def _serializable(valor):
    """Convierte el resultado a algo que quepa en un JSONField."""
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    if isinstance(valor, dict):
        return {k: _serializable(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, set)):
        return [_serializable(v) for v in valor]
    return str(valor)


def descargar_y_procesar(dispositivo, desde=None, usuario=None, procesar=True):
    """Descarga las marcaciones y recalcula la asistencia de los dias afectados.

    Solo se reprocesan los dias que realmente recibieron marcaciones nuevas, en
    lugar de recalcular todo el periodo.
    """
    registro, resultado = ejecutar_operacion(
        dispositivo,
        RegistroSincronizacion.Operacion.DESCARGAR_MARCACIONES,
        lambda servicio: servicio.descargar_marcaciones(desde=desde),
        usuario=usuario,
    )

    if resultado is None or not procesar:
        return registro, resultado

    procesados = _procesar_fechas_afectadas(resultado.get("fechas_afectadas", []))
    resultado["dias_procesados"] = procesados
    registro.detalle = _serializable(resultado)
    registro.save(update_fields=["detalle"])
    return registro, resultado


def _procesar_fechas_afectadas(fechas_afectadas):
    from datetime import date

    from apps.attendance.services.processor import ProcesadorAsistencia
    from apps.employees.models import Empleado

    if not fechas_afectadas:
        return 0

    procesador = ProcesadorAsistencia()
    empleados = {
        e.id: e
        for e in Empleado.objects.filter(
            id__in={item["empleado_id"] for item in fechas_afectadas}
        )
    }

    procesados = 0
    for item in fechas_afectadas:
        empleado = empleados.get(item["empleado_id"])
        if empleado is None:
            continue
        procesador.procesar_dia(empleado, date.fromisoformat(item["fecha"]))
        procesados += 1
    return procesados

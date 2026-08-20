"""Tareas programadas de procesamiento de asistencia."""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.attendance.services.processor import ProcesadorAsistencia
from apps.employees.models import Empleado

logger = logging.getLogger("apps.attendance")


@shared_task(name="apps.attendance.tasks.procesar_asistencia_dia_anterior_task")
def procesar_asistencia_dia_anterior_task():
    """Recalcula la asistencia del dia anterior de madrugada.

    A esa hora ya llegaron todas las marcaciones del dia, incluidas las salidas
    de los turnos nocturnos que ocurren pasada la medianoche.
    """
    ayer = timezone.localdate() - timedelta(days=1)
    empleados = list(Empleado.objects.filter(estado=Empleado.Estado.ACTIVO))

    total = ProcesadorAsistencia().procesar_rango(empleados, ayer, ayer)
    logger.info("Asistencia del %s procesada: %s registros", ayer, total)
    return {"fecha": ayer.isoformat(), "registros": total}


@shared_task(name="apps.attendance.tasks.procesar_rango_task")
def procesar_rango_task(fecha_inicio, fecha_fin, empleados_ids=None, forzar=False):
    """Recalcula un rango de fechas en segundo plano.

    Se usa desde la API cuando el rango es amplio y procesarlo en linea dejaria
    la peticion colgada.
    """
    from datetime import date

    empleados = Empleado.objects.filter(estado=Empleado.Estado.ACTIVO)
    if empleados_ids:
        empleados = empleados.filter(id__in=empleados_ids)

    total = ProcesadorAsistencia().procesar_rango(
        list(empleados),
        date.fromisoformat(fecha_inicio),
        date.fromisoformat(fecha_fin),
        forzar=forzar,
    )
    return {"registros": total}

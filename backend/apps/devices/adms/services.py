"""Procesamiento de los datos que llegan por ADMS.

Convierte lo que envia el equipo en marcaciones y estado biometrico, y dispara
el recalculo de la asistencia de los dias afectados. Reutiliza el mismo motor
que la via SDK: el origen de los datos cambia, las reglas de negocio no.
"""

import base64
import binascii
import logging

from django.utils import timezone

from apps.attendance.models import Marcacion
from apps.employees.models import Empleado, HuellaEmpleado

logger = logging.getLogger("apps.devices")

# Correspondencia entre los codigos de verificacion del equipo y los del sistema.
MAPA_VERIFICACION = {0: 0, 1: 1, 2: 2, 15: 15}


def registrar_marcaciones(dispositivo, registros):
    """Guarda las marcaciones recibidas y recalcula los dias afectados.

    Es idempotente: si el equipo reenvia un lote que ya se proceso (algo
    habitual cuando no recibe confirmacion), la restriccion unica de
    `Marcacion` descarta los duplicados.
    """
    if not registros:
        return {"recibidas": 0, "nuevas": 0, "sin_empleado": [], "dias_procesados": 0}

    codigos = {r["codigo_empleado"] for r in registros}
    empleados = {
        e.codigo_empleado: e for e in Empleado.objects.filter(codigo_empleado__in=codigos)
    }
    sin_empleado = sorted(codigos - set(empleados))

    marcaciones = []
    dias_afectados = set()
    for registro in registros:
        empleado = empleados.get(registro["codigo_empleado"])
        if empleado is None:
            # Puede ser el administrador del equipo u otro usuario que no
            # corresponde a un empleado del sistema.
            continue

        marcaciones.append(
            Marcacion(
                empleado=empleado,
                dispositivo=dispositivo,
                fecha_hora=registro["fecha_hora"],
                tipo_verificacion=MAPA_VERIFICACION.get(registro["tipo_verificacion"], 99),
                tipo_marcacion=registro["tipo_marcacion"],
            )
        )
        dias_afectados.add(
            (empleado.id, timezone.localtime(registro["fecha_hora"]).date())
        )

    if not marcaciones:
        return {
            "recibidas": len(registros),
            "nuevas": 0,
            "sin_empleado": sin_empleado,
            "dias_procesados": 0,
        }

    total_previo = Marcacion.objects.count()
    Marcacion.objects.bulk_create(marcaciones, ignore_conflicts=True)
    nuevas = Marcacion.objects.count() - total_previo

    procesados = _procesar_dias(dias_afectados) if nuevas else 0

    return {
        "recibidas": len(registros),
        "nuevas": nuevas,
        "sin_empleado": sin_empleado,
        "dias_procesados": procesados,
    }


def _procesar_dias(dias_afectados):
    """Recalcula la asistencia unicamente de los dias que recibieron datos."""
    from apps.attendance.services.processor import ProcesadorAsistencia

    if not dias_afectados:
        return 0

    procesador = ProcesadorAsistencia()
    empleados = {
        e.id: e for e in Empleado.objects.filter(id__in={eid for eid, _ in dias_afectados})
    }

    procesados = 0
    for empleado_id, fecha in dias_afectados:
        empleado = empleados.get(empleado_id)
        if empleado is None:
            continue
        try:
            procesador.procesar_dia(empleado, fecha)
            procesados += 1
        except Exception:  # noqa: BLE001 - un dia con problema no debe frenar el resto
            logger.exception(
                "Error al procesar la asistencia de %s el %s", empleado.codigo_empleado, fecha
            )
    return procesados


def registrar_operaciones(dispositivo, datos):
    """Actualiza el estado biometrico a partir del bloque OPERLOG."""
    resumen = {"huellas": 0, "rostros": 0, "usuarios": 0}

    resumen["huellas"] = _guardar_huellas(dispositivo, datos.get("huellas", []))
    resumen["rostros"] = _marcar_rostros(datos.get("rostros", []))
    resumen["usuarios"] = len(datos.get("usuarios", []))

    return resumen


def _guardar_huellas(dispositivo, huellas):
    """Respalda las plantillas de huella que envia el equipo."""
    if not huellas:
        return 0

    codigos = {h["codigo_empleado"] for h in huellas}
    empleados = {
        e.codigo_empleado: e for e in Empleado.objects.filter(codigo_empleado__in=codigos)
    }

    guardadas = 0
    afectados = set()
    for huella in huellas:
        empleado = empleados.get(huella["codigo_empleado"])
        if empleado is None or not huella["template"]:
            continue

        # Una plantilla corrupta guardada aqui haria fallar una futura
        # restauracion, asi que se valida antes de aceptarla.
        try:
            base64.b64decode(huella["template"], validate=True)
        except (binascii.Error, ValueError):
            logger.warning(
                "Plantilla de huella invalida para el empleado %s (dedo %s)",
                huella["codigo_empleado"],
                huella["finger_id"],
            )
            continue

        HuellaEmpleado.objects.update_or_create(
            empleado=empleado,
            finger_id=huella["finger_id"],
            defaults={
                "template": huella["template"],
                "size": huella["size"] or len(huella["template"]),
                "valid": huella["valid"],
                "dispositivo_origen": dispositivo,
            },
        )
        guardadas += 1
        afectados.add(empleado.id)

    _actualizar_contadores_huella(afectados)
    return guardadas


def _actualizar_contadores_huella(empleados_ids):
    from django.db.models import Count

    for empleado in Empleado.objects.filter(id__in=empleados_ids).annotate(
        total=Count("huellas")
    ):
        Empleado.objects.filter(id=empleado.id).update(
            cantidad_huellas=empleado.total, tiene_huella=empleado.total > 0
        )


def _marcar_rostros(rostros):
    """Marca como enrolados a los empleados cuyo rostro reporta el equipo.

    La plantilla facial no se conserva: es propietaria y no tiene uso fuera del
    dispositivo. Solo interesa saber que el empleado ya puede marcar con rostro.
    """
    codigos = {r["codigo_empleado"] for r in rostros if r.get("valid", 1)}
    if not codigos:
        return 0
    return Empleado.objects.filter(codigo_empleado__in=codigos).update(tiene_rostro=True)

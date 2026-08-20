"""Generacion de los reportes de asistencia.

Los datos se calculan una sola vez en `construir_datos` y de ahi se exportan a
Excel o PDF, para que ambos formatos muestren siempre lo mismo.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count, Q, Sum

from apps.attendance.models import RegistroAsistencia
from apps.schedules.models import DiaLaborableConfig

Estado = RegistroAsistencia.Estado

# Jornada de referencia para convertir el sueldo mensual a un valor por minuto.
DIAS_MES = 30
MINUTOS_JORNADA = 480


def _base_queryset(fecha_inicio, fecha_fin, filtros=None):
    """Registros del periodo, aplicando los filtros de la solicitud."""
    queryset = RegistroAsistencia.objects.select_related(
        "empleado__sede", "empleado__departamento", "empleado__cargo"
    ).filter(fecha__gte=fecha_inicio, fecha__lte=fecha_fin)

    filtros = filtros or {}
    if filtros.get("sede"):
        queryset = queryset.filter(empleado__sede_id=filtros["sede"])
    if filtros.get("departamento"):
        queryset = queryset.filter(empleado__departamento_id=filtros["departamento"])
    if filtros.get("area"):
        queryset = queryset.filter(empleado__area_id=filtros["area"])
    if filtros.get("empleados"):
        queryset = queryset.filter(empleado_id__in=filtros["empleados"])
    return queryset


def _agrupar_por_empleado(queryset):
    """Totales de asistencia por empleado."""
    return (
        queryset.values(
            "empleado_id",
            "empleado__codigo_empleado",
            "empleado__dni",
            "empleado__nombres",
            "empleado__apellido_paterno",
            "empleado__apellido_materno",
            "empleado__sede__nombre",
            "empleado__departamento__nombre",
            "empleado__cargo__nombre",
            "empleado__sueldo_basico",
        )
        .annotate(
            dias_puntuales=Count("id", filter=Q(estado=Estado.PUNTUAL)),
            dias_tardanza=Count("id", filter=Q(estado=Estado.TARDANZA)),
            dias_falta=Count("id", filter=Q(estado=Estado.FALTA)),
            dias_justificados=Count("id", filter=Q(estado=Estado.FALTA_JUSTIFICADA)),
            dias_permiso=Count("id", filter=Q(estado__in=[Estado.PERMISO, Estado.VACACIONES])),
            dias_incompletos=Count("id", filter=Q(estado=Estado.INCOMPLETO)),
            minutos_tardanza=Sum("minutos_tardanza"),
            minutos_salida_anticipada=Sum("minutos_salida_anticipada"),
            minutos_trabajados=Sum("minutos_trabajados"),
        )
        .order_by("empleado__apellido_paterno", "empleado__nombres")
    )


def _nombre(fila):
    return (
        f"{fila['empleado__apellido_paterno']} "
        f"{fila['empleado__apellido_materno']}, {fila['empleado__nombres']}"
    ).strip()


def _identificacion(fila):
    return {
        "empleado_id": fila["empleado_id"],
        "codigo": fila["empleado__codigo_empleado"],
        "dni": fila["empleado__dni"],
        "nombre": _nombre(fila),
        "sede": fila["empleado__sede__nombre"],
        "departamento": fila["empleado__departamento__nombre"],
        "cargo": fila["empleado__cargo__nombre"],
    }


# ----------------------------------------------------------------------
# Reportes
# ----------------------------------------------------------------------
def reporte_tardanzas(fecha_inicio, fecha_fin, filtros=None):
    """Tardanzas acumuladas por empleado en el periodo."""
    queryset = _base_queryset(fecha_inicio, fecha_fin, filtros).filter(
        estado=Estado.TARDANZA
    )
    filas = []
    for fila in _agrupar_por_empleado(queryset):
        minutos = fila["minutos_tardanza"] or 0
        filas.append(
            {
                **_identificacion(fila),
                "dias_tardanza": fila["dias_tardanza"],
                "minutos_tardanza": minutos,
                "horas_tardanza": round(minutos / 60, 2),
                "promedio_minutos": (
                    round(minutos / fila["dias_tardanza"], 1) if fila["dias_tardanza"] else 0
                ),
            }
        )
    return {
        "titulo": "Reporte de Tardanzas",
        "columnas": [
            ("codigo", "Codigo"),
            ("dni", "DNI"),
            ("nombre", "Empleado"),
            ("departamento", "Departamento"),
            ("cargo", "Cargo"),
            ("dias_tardanza", "Dias con tardanza"),
            ("minutos_tardanza", "Minutos totales"),
            ("horas_tardanza", "Horas"),
            ("promedio_minutos", "Promedio min/dia"),
        ],
        "filas": filas,
        "totales": {
            "dias_tardanza": sum(f["dias_tardanza"] for f in filas),
            "minutos_tardanza": sum(f["minutos_tardanza"] for f in filas),
        },
    }


def reporte_faltas(fecha_inicio, fecha_fin, filtros=None):
    """Faltas del periodo, separando las justificadas de las que se descuentan."""
    queryset = _base_queryset(fecha_inicio, fecha_fin, filtros).filter(
        estado__in=[Estado.FALTA, Estado.FALTA_JUSTIFICADA]
    )
    filas = []
    for fila in _agrupar_por_empleado(queryset):
        filas.append(
            {
                **_identificacion(fila),
                "faltas_injustificadas": fila["dias_falta"],
                "faltas_justificadas": fila["dias_justificados"],
                "total_faltas": fila["dias_falta"] + fila["dias_justificados"],
            }
        )
    return {
        "titulo": "Reporte de Faltas",
        "columnas": [
            ("codigo", "Codigo"),
            ("dni", "DNI"),
            ("nombre", "Empleado"),
            ("departamento", "Departamento"),
            ("faltas_injustificadas", "Faltas injustificadas"),
            ("faltas_justificadas", "Faltas justificadas"),
            ("total_faltas", "Total"),
        ],
        "filas": filas,
        "totales": {
            "faltas_injustificadas": sum(f["faltas_injustificadas"] for f in filas),
            "faltas_justificadas": sum(f["faltas_justificadas"] for f in filas),
        },
    }


def reporte_descuentos(fecha_inicio, fecha_fin, filtros=None):
    """Consolidado de descuentos por tardanza y falta injustificada.

    Es el reporte que se entrega a planilla, por eso incluye el detalle del
    calculo: quien lo revise debe poder reconstruir cada monto.

    El valor del minuto sale de la configuracion del sistema; si esta en cero,
    se deriva del sueldo basico del empleado (sueldo / 30 dias / 480 minutos).
    """
    config = DiaLaborableConfig.obtener()
    queryset = _base_queryset(fecha_inicio, fecha_fin, filtros).filter(es_descontable=True)

    filas = []
    for fila in _agrupar_por_empleado(queryset):
        sueldo = fila["empleado__sueldo_basico"]
        minutos_tardanza = fila["minutos_tardanza"] or 0
        minutos_anticipada = fila["minutos_salida_anticipada"] or 0
        dias_falta = fila["dias_falta"]

        valor_minuto, valor_dia = _valores_de_descuento(config, sueldo)

        descuento_tardanza = _redondear(Decimal(minutos_tardanza) * valor_minuto)
        descuento_anticipada = _redondear(Decimal(minutos_anticipada) * valor_minuto)
        descuento_faltas = _redondear(Decimal(dias_falta) * valor_dia)

        filas.append(
            {
                **_identificacion(fila),
                "sueldo_basico": sueldo,
                "dias_tardanza": fila["dias_tardanza"],
                "minutos_tardanza": minutos_tardanza,
                "minutos_salida_anticipada": minutos_anticipada,
                "dias_falta": dias_falta,
                "valor_minuto": valor_minuto,
                "descuento_tardanza": descuento_tardanza,
                "descuento_salida_anticipada": descuento_anticipada,
                "descuento_faltas": descuento_faltas,
                "descuento_total": descuento_tardanza + descuento_anticipada + descuento_faltas,
            }
        )

    return {
        "titulo": "Reporte de Descuentos",
        "columnas": [
            ("codigo", "Codigo"),
            ("dni", "DNI"),
            ("nombre", "Empleado"),
            ("departamento", "Departamento"),
            ("sueldo_basico", "Sueldo basico"),
            ("dias_tardanza", "Dias tardanza"),
            ("minutos_tardanza", "Min. tardanza"),
            ("minutos_salida_anticipada", "Min. salida anticipada"),
            ("dias_falta", "Dias falta"),
            ("descuento_tardanza", "Desc. tardanza"),
            ("descuento_salida_anticipada", "Desc. salida"),
            ("descuento_faltas", "Desc. faltas"),
            ("descuento_total", "Descuento total"),
        ],
        "filas": filas,
        "totales": {
            "minutos_tardanza": sum(f["minutos_tardanza"] for f in filas),
            "dias_falta": sum(f["dias_falta"] for f in filas),
            "descuento_total": sum(f["descuento_total"] for f in filas),
        },
        "nota": (
            "El descuento por tardanza considera el retraso completo desde la hora "
            "programada. Los dias con permiso con goce de haber no se descuentan."
        ),
    }


def _valores_de_descuento(config, sueldo):
    """Devuelve el valor del minuto y el del dia para un empleado."""
    if config.valor_minuto_tardanza and config.valor_minuto_tardanza > 0:
        valor_minuto = Decimal(config.valor_minuto_tardanza)
        return valor_minuto, valor_minuto * MINUTOS_JORNADA

    if not sueldo:
        # Sin sueldo registrado no se puede valorizar; se reportan los minutos y
        # los dias, y planilla aplica su propia tarifa.
        return Decimal(0), Decimal(0)

    valor_dia = Decimal(sueldo) / DIAS_MES
    return valor_dia / MINUTOS_JORNADA, valor_dia


def _redondear(valor):
    return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def reporte_horas_trabajadas(fecha_inicio, fecha_fin, filtros=None):
    """Horas efectivamente trabajadas por empleado."""
    queryset = _base_queryset(fecha_inicio, fecha_fin, filtros)
    filas = []
    for fila in _agrupar_por_empleado(queryset):
        minutos = fila["minutos_trabajados"] or 0
        dias = fila["dias_puntuales"] + fila["dias_tardanza"] + fila["dias_incompletos"]
        filas.append(
            {
                **_identificacion(fila),
                "dias_asistidos": dias,
                "minutos_trabajados": minutos,
                "horas_trabajadas": round(minutos / 60, 2),
                "promedio_horas_dia": round(minutos / 60 / dias, 2) if dias else 0,
            }
        )
    return {
        "titulo": "Reporte de Horas Trabajadas",
        "columnas": [
            ("codigo", "Codigo"),
            ("nombre", "Empleado"),
            ("departamento", "Departamento"),
            ("dias_asistidos", "Dias asistidos"),
            ("horas_trabajadas", "Horas trabajadas"),
            ("promedio_horas_dia", "Promedio h/dia"),
        ],
        "filas": filas,
        "totales": {"horas_trabajadas": round(sum(f["horas_trabajadas"] for f in filas), 2)},
    }


def reporte_asistencia_general(fecha_inicio, fecha_fin, filtros=None):
    """Resumen completo de asistencia por empleado."""
    queryset = _base_queryset(fecha_inicio, fecha_fin, filtros)
    filas = []
    for fila in _agrupar_por_empleado(queryset):
        filas.append(
            {
                **_identificacion(fila),
                "dias_puntuales": fila["dias_puntuales"],
                "dias_tardanza": fila["dias_tardanza"],
                "dias_falta": fila["dias_falta"],
                "dias_permiso": fila["dias_permiso"],
                "minutos_tardanza": fila["minutos_tardanza"] or 0,
                "horas_trabajadas": round((fila["minutos_trabajados"] or 0) / 60, 2),
            }
        )
    return {
        "titulo": "Reporte General de Asistencia",
        "columnas": [
            ("codigo", "Codigo"),
            ("nombre", "Empleado"),
            ("departamento", "Departamento"),
            ("dias_puntuales", "Puntuales"),
            ("dias_tardanza", "Tardanzas"),
            ("dias_falta", "Faltas"),
            ("dias_permiso", "Permisos"),
            ("minutos_tardanza", "Min. tardanza"),
            ("horas_trabajadas", "Horas trabajadas"),
        ],
        "filas": filas,
        "totales": {},
    }


def reporte_marcaciones(fecha_inicio, fecha_fin, filtros=None):
    """Detalle dia por dia de las marcaciones y su evaluacion."""
    queryset = _base_queryset(fecha_inicio, fecha_fin, filtros).order_by(
        "empleado__apellido_paterno", "fecha"
    )
    filas = [
        {
            "codigo": r.empleado.codigo_empleado,
            "nombre": r.empleado.nombre_completo,
            "departamento": r.empleado.departamento.nombre,
            "fecha": r.fecha,
            "entrada_programada": r.hora_entrada_programada,
            "salida_programada": r.hora_salida_programada,
            "entrada_real": r.marcacion_entrada,
            "salida_real": r.marcacion_salida,
            "minutos_tardanza": r.minutos_tardanza,
            "estado": r.get_estado_display(),
            "observacion": r.observacion,
        }
        for r in queryset
    ]
    return {
        "titulo": "Reporte de Marcaciones",
        "columnas": [
            ("codigo", "Codigo"),
            ("nombre", "Empleado"),
            ("departamento", "Departamento"),
            ("fecha", "Fecha"),
            ("entrada_programada", "Entrada prog."),
            ("entrada_real", "Entrada real"),
            ("salida_programada", "Salida prog."),
            ("salida_real", "Salida real"),
            ("minutos_tardanza", "Min. tardanza"),
            ("estado", "Estado"),
            ("observacion", "Observacion"),
        ],
        "filas": filas,
        "totales": {},
    }


GENERADORES = {
    "tardanzas": reporte_tardanzas,
    "faltas": reporte_faltas,
    "descuentos": reporte_descuentos,
    "horas_trabajadas": reporte_horas_trabajadas,
    "asistencia_general": reporte_asistencia_general,
    "marcaciones": reporte_marcaciones,
}


def construir_datos(tipo, fecha_inicio, fecha_fin, filtros=None):
    """Punto de entrada unico para generar cualquier reporte."""
    generador = GENERADORES.get(tipo)
    if generador is None:
        raise ValueError(f"Tipo de reporte no reconocido: {tipo}")
    return generador(fecha_inicio, fecha_fin, filtros)

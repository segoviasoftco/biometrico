"""Pruebas del motor de asistencia.

Cubren los casos que determinan un descuento en planilla, que es donde un error
tiene consecuencias directas sobre el sueldo de una persona.
"""

from datetime import date, datetime, time, timedelta

import pytest
from django.utils import timezone

from apps.attendance.models import Marcacion, RegistroAsistencia
from apps.attendance.services.processor import ProcesadorAsistencia
from apps.employees.models import Empleado
from apps.organization.models import Area, Cargo, Departamento, Sede
from apps.schedules.models import (
    AsignacionTurno,
    DiaLaborableConfig,
    Feriado,
    Horario,
    Permiso,
    Turno,
    TurnoDetalle,
)

pytestmark = pytest.mark.django_db

# 2025-06-02 es lunes: sirve como fecha base para los turnos de lunes a viernes.
LUNES = date(2025, 6, 2)
SABADO = date(2025, 6, 7)


def aware(fecha, hora):
    """Construye un datetime con la zona horaria del proyecto."""
    return timezone.make_aware(
        datetime.combine(fecha, hora), timezone.get_current_timezone()
    )


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
@pytest.fixture
def organizacion():
    sede = Sede.objects.create(nombre="Sede Central", codigo="SC")
    departamento = Departamento.objects.create(nombre="Operaciones", codigo="OP", sede=sede)
    area = Area.objects.create(nombre="Almacen", codigo="ALM", departamento=departamento)
    cargo = Cargo.objects.create(nombre="Operario")
    return {"sede": sede, "departamento": departamento, "area": area, "cargo": cargo}


@pytest.fixture
def empleado(organizacion):
    return Empleado.objects.create(
        codigo_empleado="1001",
        dni="70000001",
        nombres="Juan",
        apellido_paterno="Perez",
        apellido_materno="Gomez",
        sede=organizacion["sede"],
        departamento=organizacion["departamento"],
        area=organizacion["area"],
        cargo=organizacion["cargo"],
        fecha_ingreso=date(2024, 1, 1),
    )


@pytest.fixture
def horario_diurno():
    """Jornada de 08:00 a 17:00 con 5 minutos de tolerancia y una hora de refrigerio."""
    return Horario.objects.create(
        nombre="Administrativo",
        hora_entrada=time(8, 0),
        hora_salida=time(17, 0),
        tolerancia_entrada=5,
        tolerancia_salida=5,
        tiene_refrigerio=True,
        hora_inicio_refrigerio=time(13, 0),
        hora_fin_refrigerio=time(14, 0),
        minutos_falta=120,
    )


@pytest.fixture
def horario_nocturno():
    """Turno que cruza medianoche: 22:00 a 06:00."""
    return Horario.objects.create(
        nombre="Nocturno",
        hora_entrada=time(22, 0),
        hora_salida=time(6, 0),
        tolerancia_entrada=5,
        tolerancia_salida=5,
        minutos_falta=120,
    )


@pytest.fixture
def turno_lunes_viernes(horario_diurno):
    """Turno con horario de lunes a viernes y descanso el fin de semana."""
    turno = Turno.objects.create(nombre="Lunes a Viernes")
    for dia in range(5):
        TurnoDetalle.objects.create(turno=turno, dia_semana=dia, horario=horario_diurno)
    for dia in (5, 6):
        TurnoDetalle.objects.create(turno=turno, dia_semana=dia, horario=None)
    return turno


@pytest.fixture
def empleado_con_turno(empleado, turno_lunes_viernes):
    AsignacionTurno.objects.create(
        empleado=empleado, turno=turno_lunes_viernes, fecha_inicio=date(2024, 1, 1)
    )
    return empleado


@pytest.fixture
def procesador():
    DiaLaborableConfig.objects.create(pk=1)
    return ProcesadorAsistencia()


def marcar(empleado, fecha, hora):
    return Marcacion.objects.create(empleado=empleado, fecha_hora=aware(fecha, hora))


# ----------------------------------------------------------------------
# Casos de jornada normal
# ----------------------------------------------------------------------
def test_llegada_a_tiempo_es_puntual(procesador, empleado_con_turno):
    marcar(empleado_con_turno, LUNES, time(7, 55))
    marcar(empleado_con_turno, LUNES, time(17, 5))

    registro = procesador.procesar_dia(empleado_con_turno, LUNES)

    assert registro.estado == RegistroAsistencia.Estado.PUNTUAL
    assert registro.minutos_tardanza == 0
    assert registro.es_descontable is False
    # 07:55 a 17:05 son 550 minutos, menos 60 de refrigerio.
    assert registro.minutos_trabajados == 490


def test_llegada_dentro_de_la_tolerancia_no_es_tardanza(procesador, empleado_con_turno):
    marcar(empleado_con_turno, LUNES, time(8, 5))
    marcar(empleado_con_turno, LUNES, time(17, 0))

    registro = procesador.procesar_dia(empleado_con_turno, LUNES)

    assert registro.estado == RegistroAsistencia.Estado.PUNTUAL
    assert registro.minutos_tardanza == 0


def test_llegada_fuera_de_tolerancia_cuenta_desde_la_hora_programada(
    procesador, empleado_con_turno
):
    """Superada la tolerancia, se descuenta el retraso completo, no el excedente."""
    marcar(empleado_con_turno, LUNES, time(8, 20))
    marcar(empleado_con_turno, LUNES, time(17, 0))

    registro = procesador.procesar_dia(empleado_con_turno, LUNES)

    assert registro.estado == RegistroAsistencia.Estado.TARDANZA
    assert registro.minutos_tardanza == 20
    assert registro.es_descontable is True


def test_tardanza_excesiva_se_convierte_en_falta(procesador, empleado_con_turno):
    marcar(empleado_con_turno, LUNES, time(11, 0))
    marcar(empleado_con_turno, LUNES, time(17, 0))

    registro = procesador.procesar_dia(empleado_con_turno, LUNES)

    assert registro.estado == RegistroAsistencia.Estado.FALTA
    assert registro.minutos_tardanza == 180
    assert registro.es_descontable is True


def test_salida_anticipada_se_registra(procesador, empleado_con_turno):
    marcar(empleado_con_turno, LUNES, time(8, 0))
    marcar(empleado_con_turno, LUNES, time(16, 0))

    registro = procesador.procesar_dia(empleado_con_turno, LUNES)

    assert registro.minutos_salida_anticipada == 60
    assert registro.es_descontable is True


def test_sin_marcaciones_en_dia_laborable_es_falta(procesador, empleado_con_turno):
    registro = procesador.procesar_dia(empleado_con_turno, LUNES)

    assert registro.estado == RegistroAsistencia.Estado.FALTA
    assert registro.es_descontable is True
    assert registro.total_marcaciones == 0


# ----------------------------------------------------------------------
# Dias sin obligacion de trabajar
# ----------------------------------------------------------------------
def test_dia_de_descanso_no_genera_falta(procesador, empleado_con_turno):
    registro = procesador.procesar_dia(empleado_con_turno, SABADO)

    assert registro.estado == RegistroAsistencia.Estado.DESCANSO
    assert registro.es_descontable is False


def test_feriado_no_genera_falta(procesador, empleado_con_turno):
    Feriado.objects.create(fecha=LUNES, descripcion="Feriado de prueba")

    registro = procesador.procesar_dia(empleado_con_turno, LUNES)

    assert registro.estado == RegistroAsistencia.Estado.FERIADO
    assert registro.es_descontable is False


def test_feriado_recurrente_aplica_en_otro_ano(procesador, empleado_con_turno):
    Feriado.objects.create(
        fecha=date(2020, 6, 2), descripcion="Aniversario", es_recurrente=True
    )

    registro = procesador.procesar_dia(empleado_con_turno, LUNES)

    assert registro.estado == RegistroAsistencia.Estado.FERIADO


def test_permiso_aprobado_evita_la_falta(procesador, empleado_con_turno):
    Permiso.objects.create(
        empleado=empleado_con_turno,
        tipo=Permiso.Tipo.VACACIONES,
        fecha_inicio=LUNES,
        fecha_fin=LUNES + timedelta(days=4),
        estado=Permiso.EstadoAprobacion.APROBADO,
    )

    registro = procesador.procesar_dia(empleado_con_turno, LUNES)

    assert registro.estado == RegistroAsistencia.Estado.VACACIONES
    assert registro.es_descontable is False


def test_permiso_pendiente_no_evita_la_falta(procesador, empleado_con_turno):
    """Solo un permiso aprobado justifica la ausencia."""
    Permiso.objects.create(
        empleado=empleado_con_turno,
        tipo=Permiso.Tipo.PERMISO_PERSONAL,
        fecha_inicio=LUNES,
        fecha_fin=LUNES,
        estado=Permiso.EstadoAprobacion.PENDIENTE,
    )

    registro = procesador.procesar_dia(empleado_con_turno, LUNES)

    assert registro.estado == RegistroAsistencia.Estado.FALTA
    assert registro.es_descontable is True


def test_permiso_sin_goce_si_es_descontable(procesador, empleado_con_turno):
    Permiso.objects.create(
        empleado=empleado_con_turno,
        tipo=Permiso.Tipo.PERMISO_PERSONAL,
        fecha_inicio=LUNES,
        fecha_fin=LUNES,
        estado=Permiso.EstadoAprobacion.APROBADO,
        con_goce=False,
    )

    registro = procesador.procesar_dia(empleado_con_turno, LUNES)

    assert registro.estado == RegistroAsistencia.Estado.PERMISO
    assert registro.es_descontable is True


# ----------------------------------------------------------------------
# Casos borde
# ----------------------------------------------------------------------
def test_turno_nocturno_toma_la_salida_del_dia_siguiente(
    procesador, empleado, horario_nocturno
):
    turno = Turno.objects.create(nombre="Nocturno", tipo=Turno.Tipo.ROTATIVO)
    for dia in range(7):
        TurnoDetalle.objects.create(turno=turno, dia_semana=dia, horario=horario_nocturno)
    AsignacionTurno.objects.create(empleado=empleado, turno=turno, fecha_inicio=date(2024, 1, 1))

    marcar(empleado, LUNES, time(21, 55))
    marcar(empleado, LUNES + timedelta(days=1), time(6, 5))

    registro = procesador.procesar_dia(empleado, LUNES)

    assert registro.estado == RegistroAsistencia.Estado.PUNTUAL
    assert registro.minutos_trabajados == 490  # 8 h 10 min
    assert registro.marcacion_salida is not None


def test_turno_diurno_ignora_las_marcaciones_de_la_vispera(
    procesador, empleado_con_turno
):
    """La ventana se ancla al horario, no al dia calendario."""
    marcar(empleado_con_turno, LUNES - timedelta(days=1), time(20, 0))
    marcar(empleado_con_turno, LUNES, time(8, 0))
    marcar(empleado_con_turno, LUNES, time(17, 0))

    registro = procesador.procesar_dia(empleado_con_turno, LUNES)

    assert registro.total_marcaciones == 2
    assert registro.estado == RegistroAsistencia.Estado.PUNTUAL


def test_marcacion_unica_es_asistencia_incompleta(procesador, empleado_con_turno):
    marcar(empleado_con_turno, LUNES, time(8, 0))

    registro = procesador.procesar_dia(empleado_con_turno, LUNES)

    assert registro.estado == RegistroAsistencia.Estado.INCOMPLETO
    assert registro.marcacion_salida is None


def test_marcacion_unica_puede_configurarse_como_falta(procesador, empleado_con_turno):
    config = DiaLaborableConfig.obtener()
    config.considerar_marcacion_unica_como_falta = True
    config.save()

    marcar(empleado_con_turno, LUNES, time(8, 0))

    registro = ProcesadorAsistencia().procesar_dia(empleado_con_turno, LUNES)

    assert registro.estado == RegistroAsistencia.Estado.FALTA
    assert registro.es_descontable is True


def test_sin_turno_asignado_no_genera_falta(procesador, empleado):
    """Sin turno no se puede saber que se esperaba del empleado ese dia."""
    registro = procesador.procesar_dia(empleado, LUNES)

    assert registro.estado == RegistroAsistencia.Estado.SIN_TURNO
    assert registro.es_descontable is False


def test_fecha_anterior_al_ingreso_no_genera_falta(procesador, empleado_con_turno):
    registro = procesador.procesar_dia(empleado_con_turno, date(2023, 6, 5))

    assert registro.estado == RegistroAsistencia.Estado.SIN_TURNO
    assert registro.es_descontable is False


def test_fecha_posterior_al_cese_no_genera_falta(procesador, empleado_con_turno):
    empleado_con_turno.fecha_cese = date(2025, 5, 30)
    empleado_con_turno.save()

    registro = procesador.procesar_dia(empleado_con_turno, LUNES)

    assert registro.estado == RegistroAsistencia.Estado.SIN_TURNO
    assert registro.es_descontable is False


def test_el_turno_vigente_es_el_de_la_fecha_no_el_actual(
    procesador, empleado, turno_lunes_viernes, horario_nocturno
):
    """Al recalcular un periodo pasado debe usarse el turno que regia entonces."""
    AsignacionTurno.objects.create(
        empleado=empleado,
        turno=turno_lunes_viernes,
        fecha_inicio=date(2024, 1, 1),
        fecha_fin=LUNES,
    )
    turno_nuevo = Turno.objects.create(nombre="Nuevo")
    for dia in range(7):
        TurnoDetalle.objects.create(turno=turno_nuevo, dia_semana=dia, horario=horario_nocturno)
    AsignacionTurno.objects.create(
        empleado=empleado, turno=turno_nuevo, fecha_inicio=LUNES + timedelta(days=1)
    )

    marcar(empleado, LUNES, time(8, 0))
    marcar(empleado, LUNES, time(17, 0))

    registro = procesador.procesar_dia(empleado, LUNES)

    assert registro.turno == turno_lunes_viernes
    assert registro.estado == RegistroAsistencia.Estado.PUNTUAL


# ----------------------------------------------------------------------
# Idempotencia y ajustes manuales
# ----------------------------------------------------------------------
def test_procesar_dos_veces_da_el_mismo_resultado(procesador, empleado_con_turno):
    marcar(empleado_con_turno, LUNES, time(8, 20))
    marcar(empleado_con_turno, LUNES, time(17, 0))

    primero = procesador.procesar_dia(empleado_con_turno, LUNES)
    minutos = primero.minutos_tardanza
    segundo = procesador.procesar_dia(empleado_con_turno, LUNES)

    assert RegistroAsistencia.objects.filter(empleado=empleado_con_turno, fecha=LUNES).count() == 1
    assert segundo.minutos_tardanza == minutos
    assert segundo.pk == primero.pk


def test_el_recalculo_respeta_el_ajuste_manual(procesador, empleado_con_turno):
    marcar(empleado_con_turno, LUNES, time(9, 0))
    marcar(empleado_con_turno, LUNES, time(17, 0))

    registro = procesador.procesar_dia(empleado_con_turno, LUNES)
    registro.estado = RegistroAsistencia.Estado.PUNTUAL
    registro.minutos_tardanza = 0
    registro.es_descontable = False
    registro.ajustado_manualmente = True
    registro.save()

    resultado = procesador.procesar_dia(empleado_con_turno, LUNES)

    assert resultado.estado == RegistroAsistencia.Estado.PUNTUAL
    assert resultado.minutos_tardanza == 0


def test_forzar_sobrescribe_el_ajuste_manual(procesador, empleado_con_turno):
    marcar(empleado_con_turno, LUNES, time(9, 0))
    marcar(empleado_con_turno, LUNES, time(17, 0))

    registro = procesador.procesar_dia(empleado_con_turno, LUNES)
    registro.ajustado_manualmente = True
    registro.estado = RegistroAsistencia.Estado.PUNTUAL
    registro.save()

    resultado = procesador.procesar_dia(empleado_con_turno, LUNES, forzar=True)

    assert resultado.estado == RegistroAsistencia.Estado.TARDANZA
    assert resultado.minutos_tardanza == 60

"""Pruebas de los endpoints de agregacion del dashboard.

Las agregaciones son propensas a romperse en tiempo de ejecucion (alias que
chocan con nombres de campo, divisiones por cero), y esos fallos no aparecen
hasta que alguien abre la pantalla. Por eso se ejercitan todos los endpoints
con datos reales.
"""

from datetime import date

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Usuario
from apps.attendance.models import RegistroAsistencia
from apps.employees.models import Empleado
from apps.organization.models import Cargo, Departamento, Sede

pytestmark = pytest.mark.django_db

FECHA = date(2025, 6, 2)

RUTAS = [
    "/api/dashboard/resumen-dia/",
    "/api/dashboard/tendencia-semanal/",
    "/api/dashboard/tendencia-mensual/",
    "/api/dashboard/ranking/",
    "/api/dashboard/comparativo-departamento/",
    "/api/dashboard/estado-sistema/",
]


@pytest.fixture
def cliente():
    usuario = Usuario.objects.create_user(
        email="admin@test.local",
        password="ClaveSegura2025!",
        nombres="Admin",
        apellidos="Test",
        rol=Usuario.Rol.ADMINISTRADOR,
    )
    api = APIClient()
    api.force_authenticate(user=usuario)
    return api


@pytest.fixture
def datos():
    sede = Sede.objects.create(nombre="Central", codigo="C1")
    departamento = Departamento.objects.create(nombre="Operaciones", codigo="OP", sede=sede)
    cargo = Cargo.objects.create(nombre="Operario")

    empleados = []
    for indice in range(3):
        empleados.append(
            Empleado.objects.create(
                codigo_empleado=f"100{indice}",
                dni=f"7000000{indice}",
                nombres=f"Empleado{indice}",
                apellido_paterno="Prueba",
                sede=sede,
                departamento=departamento,
                cargo=cargo,
                fecha_ingreso=date(2024, 1, 1),
            )
        )

    Estado = RegistroAsistencia.Estado
    RegistroAsistencia.objects.create(
        empleado=empleados[0], fecha=FECHA, estado=Estado.PUNTUAL, minutos_trabajados=480
    )
    RegistroAsistencia.objects.create(
        empleado=empleados[1],
        fecha=FECHA,
        estado=Estado.TARDANZA,
        minutos_tardanza=20,
        es_descontable=True,
        minutos_trabajados=460,
    )
    RegistroAsistencia.objects.create(
        empleado=empleados[2], fecha=FECHA, estado=Estado.FALTA, es_descontable=True
    )
    return {"sede": sede, "departamento": departamento, "empleados": empleados}


@pytest.mark.parametrize("ruta", RUTAS)
def test_todos_los_endpoints_responden(cliente, datos, ruta):
    """Ninguna agregacion debe romperse al ejecutarse contra datos reales."""
    respuesta = cliente.get(ruta, {"fecha_inicio": "2025-06-01", "fecha_fin": "2025-06-30"})
    assert respuesta.status_code == 200, respuesta.data


@pytest.mark.parametrize("ruta", RUTAS)
def test_los_endpoints_toleran_la_ausencia_de_datos(cliente, ruta):
    """Sin registros los indicadores deben salir en cero, no fallar."""
    respuesta = cliente.get(ruta)
    assert respuesta.status_code == 200, respuesta.data


def test_resumen_del_dia(cliente, datos):
    respuesta = cliente.get("/api/dashboard/resumen-dia/", {"fecha": FECHA.isoformat()})

    assert respuesta.data["puntuales"] == 1
    assert respuesta.data["tardanzas"] == 1
    assert respuesta.data["faltas"] == 1
    assert respuesta.data["esperados"] == 3
    # Dos de los tres esperados asistieron.
    assert respuesta.data["porcentaje_asistencia"] == 66.7


def test_el_porcentaje_ignora_descansos_y_feriados(cliente, datos):
    """Un dia de descanso no debe bajar el porcentaje de asistencia."""
    RegistroAsistencia.objects.create(
        empleado=datos["empleados"][0],
        fecha=date(2025, 6, 8),
        estado=RegistroAsistencia.Estado.DESCANSO,
    )
    respuesta = cliente.get("/api/dashboard/resumen-dia/", {"fecha": "2025-06-08"})

    assert respuesta.data["descansos"] == 1
    assert respuesta.data["esperados"] == 0
    assert respuesta.data["porcentaje_asistencia"] == 0.0


def test_comparativo_calcula_el_promedio_de_tardanza(cliente, datos):
    """El promedio se toma sobre los dias con tardanza, no sobre todos."""
    respuesta = cliente.get(
        "/api/dashboard/comparativo-departamento/",
        {"fecha_inicio": "2025-06-01", "fecha_fin": "2025-06-30"},
    )

    fila = respuesta.data[0]
    assert fila["departamento"] == "Operaciones"
    assert fila["tardanzas"] == 1
    assert fila["faltas"] == 1
    assert fila["minutos_tardanza"] == 20
    assert fila["promedio_minutos_tardanza"] == 20.0


def test_ranking_ordena_por_minutos(cliente, datos):
    respuesta = cliente.get(
        "/api/dashboard/ranking/", {"fecha_inicio": "2025-06-01", "fecha_fin": "2025-06-30"}
    )

    assert len(respuesta.data["tardanzas"]) == 1
    assert respuesta.data["tardanzas"][0]["minutos"] == 20
    assert len(respuesta.data["faltas"]) == 1


def test_estado_del_sistema_cuenta_los_pendientes(cliente, datos):
    respuesta = cliente.get("/api/dashboard/estado-sistema/")

    assert respuesta.data["empleados_activos"] == 3
    # Ninguno tiene biometria ni turno todavia.
    assert respuesta.data["sin_biometria"] == 3
    assert respuesta.data["sin_turno"] == 3

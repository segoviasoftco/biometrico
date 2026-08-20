"""Pruebas de control de acceso de la API.

Verifican que cada rol vea y modifique solo lo que le corresponde. Un supervisor
que alcance los datos de otra sede, o que pueda editar asistencia, seria una
fuga real de informacion laboral.
"""

from datetime import date

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Usuario
from apps.attendance.models import RegistroAsistencia
from apps.employees.models import Empleado
from apps.organization.models import Cargo, Departamento, Sede

pytestmark = pytest.mark.django_db


@pytest.fixture
def sedes():
    norte = Sede.objects.create(nombre="Sede Norte", codigo="N1")
    sur = Sede.objects.create(nombre="Sede Sur", codigo="S1")
    return {"norte": norte, "sur": sur}


@pytest.fixture
def empleados(sedes):
    cargo = Cargo.objects.create(nombre="Operario")
    creados = {}
    for clave, sede in sedes.items():
        departamento = Departamento.objects.create(
            nombre=f"Operaciones {clave}", codigo=f"OP{clave[:1].upper()}", sede=sede
        )
        creados[clave] = Empleado.objects.create(
            codigo_empleado="1001" if clave == "norte" else "2001",
            dni="70000001" if clave == "norte" else "70000002",
            nombres="Empleado",
            apellido_paterno=clave.capitalize(),
            sede=sede,
            departamento=departamento,
            cargo=cargo,
            fecha_ingreso=date(2024, 1, 1),
        )
    return creados


def crear_usuario(rol, email, sede=None):
    return Usuario.objects.create_user(
        email=email, password="ClaveSegura2025!", nombres="Test", apellidos=rol, rol=rol, sede=sede
    )


def cliente_de(usuario):
    cliente = APIClient()
    cliente.force_authenticate(user=usuario)
    return cliente


@pytest.fixture
def administrador():
    return crear_usuario(Usuario.Rol.ADMINISTRADOR, "admin@test.local")


@pytest.fixture
def rrhh():
    return crear_usuario(Usuario.Rol.RRHH, "rrhh@test.local")


@pytest.fixture
def supervisor_norte(sedes):
    return crear_usuario(Usuario.Rol.SUPERVISOR, "supervisor@test.local", sede=sedes["norte"])


# ----------------------------------------------------------------------
# Autenticacion
# ----------------------------------------------------------------------
def test_la_api_exige_autenticacion():
    respuesta = APIClient().get("/api/empleados/")
    assert respuesta.status_code == 401


def test_el_login_devuelve_los_datos_del_usuario(administrador):
    respuesta = APIClient().post(
        "/api/auth/login/",
        {"email": "admin@test.local", "password": "ClaveSegura2025!"},
        format="json",
    )
    assert respuesta.status_code == 200
    assert "access" in respuesta.data
    assert respuesta.data["usuario"]["rol"] == Usuario.Rol.ADMINISTRADOR


# ----------------------------------------------------------------------
# Alcance del supervisor
# ----------------------------------------------------------------------
def test_el_supervisor_solo_ve_los_empleados_de_su_sede(supervisor_norte, empleados):
    respuesta = cliente_de(supervisor_norte).get("/api/empleados/")

    assert respuesta.status_code == 200
    codigos = {fila["codigo_empleado"] for fila in respuesta.data["results"]}
    assert codigos == {"1001"}


def test_el_supervisor_no_accede_a_un_empleado_de_otra_sede(supervisor_norte, empleados):
    respuesta = cliente_de(supervisor_norte).get(f"/api/empleados/{empleados['sur'].id}/")
    assert respuesta.status_code == 404


def test_rrhh_ve_los_empleados_de_todas_las_sedes(rrhh, empleados):
    respuesta = cliente_de(rrhh).get("/api/empleados/")

    assert respuesta.status_code == 200
    assert respuesta.data["count"] == 2


def test_el_supervisor_solo_ve_la_asistencia_de_su_sede(supervisor_norte, empleados):
    for empleado in empleados.values():
        RegistroAsistencia.objects.create(
            empleado=empleado,
            fecha=date(2025, 6, 2),
            estado=RegistroAsistencia.Estado.PUNTUAL,
        )

    respuesta = cliente_de(supervisor_norte).get("/api/asistencia/registros/")

    assert respuesta.status_code == 200
    assert respuesta.data["count"] == 1
    assert respuesta.data["results"][0]["empleado_codigo"] == "1001"


def test_el_reporte_del_supervisor_se_limita_a_su_sede(supervisor_norte, empleados):
    """Aunque pida otra sede en el filtro, el reporte debe ceñirse a la suya."""
    for empleado in empleados.values():
        RegistroAsistencia.objects.create(
            empleado=empleado,
            fecha=date(2025, 6, 2),
            estado=RegistroAsistencia.Estado.TARDANZA,
            minutos_tardanza=15,
            es_descontable=True,
        )

    respuesta = cliente_de(supervisor_norte).post(
        "/api/reportes/previsualizar/",
        {
            "tipo": "tardanzas",
            "fecha_inicio": "2025-06-01",
            "fecha_fin": "2025-06-30",
            "sede": empleados["sur"].sede_id,
        },
        format="json",
    )

    assert respuesta.status_code == 200
    codigos = {fila["codigo"] for fila in respuesta.data["filas"]}
    assert codigos == {"1001"}


# ----------------------------------------------------------------------
# Restricciones de escritura
# ----------------------------------------------------------------------
def test_el_supervisor_no_puede_crear_empleados(supervisor_norte, sedes):
    departamento = Departamento.objects.create(
        nombre="Nuevo", codigo="NV", sede=sedes["norte"]
    )
    cargo = Cargo.objects.create(nombre="Asistente")

    respuesta = cliente_de(supervisor_norte).post(
        "/api/empleados/",
        {
            "codigo_empleado": "3001",
            "dni": "70000003",
            "nombres": "Nuevo",
            "apellido_paterno": "Empleado",
            "sede": sedes["norte"].id,
            "departamento": departamento.id,
            "cargo": cargo.id,
            "fecha_ingreso": "2025-01-01",
        },
        format="json",
    )
    assert respuesta.status_code == 403


def test_rrhh_si_puede_crear_empleados(rrhh, sedes):
    departamento = Departamento.objects.create(nombre="Nuevo", codigo="NV", sede=sedes["norte"])
    cargo = Cargo.objects.create(nombre="Asistente")

    respuesta = cliente_de(rrhh).post(
        "/api/empleados/",
        {
            "codigo_empleado": "3001",
            "dni": "70000003",
            "nombres": "Nuevo",
            "apellido_paterno": "Empleado",
            "sede": sedes["norte"].id,
            "departamento": departamento.id,
            "cargo": cargo.id,
            "fecha_ingreso": "2025-01-01",
        },
        format="json",
    )
    assert respuesta.status_code == 201


def test_solo_el_administrador_gestiona_usuarios(rrhh, administrador):
    assert cliente_de(rrhh).get("/api/auth/usuarios/").status_code == 403
    assert cliente_de(administrador).get("/api/auth/usuarios/").status_code == 200


def test_solo_el_administrador_consulta_la_auditoria(rrhh, supervisor_norte, administrador):
    assert cliente_de(rrhh).get("/api/auditoria/").status_code == 403
    assert cliente_de(supervisor_norte).get("/api/auditoria/").status_code == 403
    assert cliente_de(administrador).get("/api/auditoria/").status_code == 200


def test_rrhh_no_puede_cambiar_la_configuracion_del_dispositivo(rrhh):
    respuesta = cliente_de(rrhh).post(
        "/api/dispositivos/",
        {"nombre": "Otro equipo", "ip": "192.168.1.50", "puerto": 4370},
        format="json",
    )
    assert respuesta.status_code == 403


# ----------------------------------------------------------------------
# Validaciones de negocio
# ----------------------------------------------------------------------
def test_un_supervisor_debe_tener_sede_asignada(administrador):
    respuesta = cliente_de(administrador).post(
        "/api/auth/usuarios/",
        {
            "email": "nuevo@test.local",
            "nombres": "Nuevo",
            "apellidos": "Supervisor",
            "rol": Usuario.Rol.SUPERVISOR,
            "password": "ClaveSegura2025!",
        },
        format="json",
    )
    assert respuesta.status_code == 400
    assert "sede" in respuesta.data


def test_el_empleado_se_cesa_en_lugar_de_borrarse(rrhh, empleados):
    empleado = empleados["norte"]
    respuesta = cliente_de(rrhh).delete(f"/api/empleados/{empleado.id}/")

    assert respuesta.status_code == 204
    empleado.refresh_from_db()
    assert empleado.estado == Empleado.Estado.CESADO
    assert empleado.fecha_cese is not None

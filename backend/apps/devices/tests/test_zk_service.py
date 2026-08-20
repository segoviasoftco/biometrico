"""Pruebas del servicio de comunicacion con el dispositivo ZKTeco.

La libreria `pyzk` se sustituye por un doble de prueba: las pruebas deben poder
correr sin el equipo fisico y sin acceso a la red.
"""

from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.attendance.models import Marcacion
from apps.devices.models import Dispositivo
from apps.devices.services.zk_service import ErrorDispositivo, ServicioZK
from apps.employees.models import Empleado, HuellaEmpleado
from apps.organization.models import Cargo, Departamento, Sede

pytestmark = pytest.mark.django_db


# ----------------------------------------------------------------------
# Dobles de prueba
# ----------------------------------------------------------------------
class UsuarioFalso:
    def __init__(self, uid, user_id, name="", privilege=0, card=0):
        self.uid = uid
        self.user_id = user_id
        self.name = name
        self.privilege = privilege
        self.card = card


class HuellaFalsa:
    def __init__(self, uid, fid, template=b"\x01\x02\x03", valid=1):
        self.uid = uid
        self.fid = fid
        self.template = template
        self.valid = valid


class MarcacionFalsa:
    def __init__(self, user_id, timestamp, status=1, punch=0, uid=1):
        self.user_id = user_id
        self.timestamp = timestamp
        self.status = status
        self.punch = punch
        self.uid = uid


class ConexionFalsa:
    """Simula la conexion que devuelve `ZK.connect()`."""

    def __init__(self, usuarios=None, huellas=None, marcaciones=None):
        self.usuarios = usuarios or []
        self.huellas = huellas or []
        self.marcaciones = marcaciones or []
        self.usuarios_creados = []
        self.usuarios_borrados = []
        self.plantillas_guardadas = []
        self.marcaciones_borradas = False
        self.deshabilitado = False
        self.desconectado = False

    def disable_device(self):
        self.deshabilitado = True

    def enable_device(self):
        self.deshabilitado = False

    def disconnect(self):
        self.desconectado = True

    def get_users(self):
        return self.usuarios

    def get_templates(self):
        return self.huellas

    def get_attendance(self):
        return self.marcaciones

    def set_user(self, **kwargs):
        self.usuarios_creados.append(kwargs)

    def delete_user(self, user_id=None, uid=0):
        self.usuarios_borrados.append(user_id)

    def save_user_template(self, user, fingers):
        self.plantillas_guardadas.append((user, fingers))

    def clear_attendance(self):
        self.marcaciones_borradas = True

    def get_serialnumber(self):
        return "MB560VL123"

    def get_device_name(self):
        return "MB560-VL"

    def get_firmware_version(self):
        return "Ver 6.60"

    def get_platform(self):
        return "ZMM220"

    def get_face_version(self):
        return "7"

    def get_fp_version(self):
        return "10"

    def get_mac(self):
        return "00:17:61:01:02:03"

    def get_time(self):
        return datetime(2025, 6, 2, 8, 0, 0)

    def set_time(self, valor):
        self.hora_establecida = valor


@pytest.fixture
def dispositivo():
    return Dispositivo.objects.create(
        nombre="MB560-VL de prueba", ip="192.168.18.202", puerto=4370, admin_user_id="6999383"
    )


@pytest.fixture
def empleado():
    sede = Sede.objects.create(nombre="Central", codigo="C1")
    departamento = Departamento.objects.create(nombre="Operaciones", codigo="OP", sede=sede)
    cargo = Cargo.objects.create(nombre="Operario")
    return Empleado.objects.create(
        codigo_empleado="1001",
        dni="70000001",
        nombres="Juan Carlos",
        apellido_paterno="Perez",
        apellido_materno="Gomez",
        sede=sede,
        departamento=departamento,
        cargo=cargo,
        fecha_ingreso=date(2024, 1, 1),
    )


def conectar_con(conexion):
    """Sustituye `ZK.connect` para que devuelva la conexion simulada."""
    return patch("apps.devices.services.zk_service.ZK.connect", return_value=conexion)


# ----------------------------------------------------------------------
# Conexion e informacion
# ----------------------------------------------------------------------
def test_probar_conexion_guarda_los_datos_del_equipo(dispositivo):
    conexion = ConexionFalsa()
    with conectar_con(conexion):
        info = ServicioZK(dispositivo).probar_conexion()

    dispositivo.refresh_from_db()
    assert dispositivo.numero_serie == "MB560VL123"
    assert dispositivo.modelo == "MB560-VL"
    assert dispositivo.version_rostro == "7"
    assert dispositivo.estado == Dispositivo.Estado.CONECTADO
    assert dispositivo.ultima_conexion is not None
    assert info["hora_dispositivo"] is not None


def test_un_fallo_de_red_marca_el_dispositivo_en_error(dispositivo):
    with patch(
        "apps.devices.services.zk_service.ZK.connect", side_effect=OSError("host inalcanzable")
    ):
        with pytest.raises(ErrorDispositivo):
            ServicioZK(dispositivo).probar_conexion()

    dispositivo.refresh_from_db()
    assert dispositivo.estado == Dispositivo.Estado.ERROR


def test_la_conexion_rehabilita_el_equipo_al_terminar(dispositivo, empleado):
    """El equipo se deshabilita durante la escritura y debe volver a quedar usable."""
    conexion = ConexionFalsa()
    with conectar_con(conexion):
        ServicioZK(dispositivo).subir_empleados([empleado])

    assert conexion.deshabilitado is False
    assert conexion.desconectado is True


# ----------------------------------------------------------------------
# Empleados
# ----------------------------------------------------------------------
def test_subir_empleado_nuevo_asigna_un_uid_dentro_del_rango(dispositivo, empleado):
    """El uid viaja en 16 bits, por lo que no puede ser el codigo del empleado."""
    conexion = ConexionFalsa()
    with conectar_con(conexion):
        resultado = ServicioZK(dispositivo).subir_empleados([empleado])

    assert resultado["procesados"] == 1
    enviado = conexion.usuarios_creados[0]
    assert enviado["user_id"] == "1001"
    assert 0 < enviado["uid"] <= 65535

    empleado.refresh_from_db()
    assert empleado.sincronizado_dispositivo is True
    assert empleado.uid_dispositivo == enviado["uid"]


def test_resincronizar_reutiliza_el_uid_del_equipo(dispositivo, empleado):
    """Sin reutilizar el uid, cada sincronizacion crearia un usuario duplicado."""
    conexion = ConexionFalsa(usuarios=[UsuarioFalso(uid=37, user_id="1001", name="Juan Perez")])
    with conectar_con(conexion):
        ServicioZK(dispositivo).subir_empleados([empleado])

    assert conexion.usuarios_creados[0]["uid"] == 37


def test_el_codigo_de_empleado_grande_no_desborda_el_uid(dispositivo, empleado):
    empleado.codigo_empleado = "6999383"
    empleado.save()

    conexion = ConexionFalsa()
    with conectar_con(conexion):
        ServicioZK(dispositivo).subir_empleados([empleado])

    enviado = conexion.usuarios_creados[0]
    assert enviado["uid"] <= 65535
    assert enviado["user_id"] == "6999383"


def test_un_empleado_fallido_no_aborta_el_lote(dispositivo, empleado):
    otro = Empleado.objects.create(
        codigo_empleado="1002",
        dni="70000002",
        nombres="Maria",
        apellido_paterno="Lopez",
        sede=empleado.sede,
        departamento=empleado.departamento,
        cargo=empleado.cargo,
        fecha_ingreso=date(2024, 1, 1),
    )

    conexion = ConexionFalsa()
    llamadas = {"n": 0}

    def set_user_fallando(**kwargs):
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            raise RuntimeError("el equipo rechazo el registro")
        conexion.usuarios_creados.append(kwargs)

    conexion.set_user = set_user_fallando

    with conectar_con(conexion):
        resultado = ServicioZK(dispositivo).subir_empleados([empleado, otro])

    assert resultado["procesados"] == 1
    assert resultado["fallidos"] == 1
    assert len(resultado["errores"]) == 1


def test_el_administrador_del_equipo_no_puede_eliminarse(dispositivo):
    """Sin el administrador no se podria entrar al menu del dispositivo."""
    conexion = ConexionFalsa()
    with conectar_con(conexion):
        with pytest.raises(ErrorDispositivo, match="administrador"):
            ServicioZK(dispositivo).eliminar_empleado("6999383")

    assert conexion.usuarios_borrados == []


def test_eliminar_un_empleado_normal_si_procede(dispositivo):
    conexion = ConexionFalsa()
    with conectar_con(conexion):
        ServicioZK(dispositivo).eliminar_empleado("1001")

    assert conexion.usuarios_borrados == ["1001"]


def test_descargar_empleados_reporta_las_diferencias(dispositivo, empleado):
    conexion = ConexionFalsa(
        usuarios=[
            UsuarioFalso(uid=1, user_id="1001"),
            UsuarioFalso(uid=2, user_id="9999"),  # esta en el equipo pero no en el sistema
        ]
    )
    with conectar_con(conexion):
        resultado = ServicioZK(dispositivo).descargar_empleados()

    assert resultado["total_en_equipo"] == 2
    assert resultado["solo_en_equipo"] == ["9999"]
    assert resultado["solo_en_sistema"] == []


# ----------------------------------------------------------------------
# Huellas
# ----------------------------------------------------------------------
def test_respaldar_huellas_guarda_las_plantillas_y_actualiza_los_indicadores(
    dispositivo, empleado
):
    conexion = ConexionFalsa(
        usuarios=[UsuarioFalso(uid=5, user_id="1001")],
        huellas=[HuellaFalsa(uid=5, fid=0), HuellaFalsa(uid=5, fid=1)],
    )
    with conectar_con(conexion):
        resultado = ServicioZK(dispositivo).respaldar_huellas()

    empleado.refresh_from_db()
    assert resultado["plantillas_descargadas"] == 2
    assert empleado.cantidad_huellas == 2
    assert empleado.tiene_huella is True
    assert HuellaEmpleado.objects.filter(empleado=empleado).count() == 2


def test_respaldar_huellas_dos_veces_no_duplica(dispositivo, empleado):
    conexion = ConexionFalsa(
        usuarios=[UsuarioFalso(uid=5, user_id="1001")],
        huellas=[HuellaFalsa(uid=5, fid=0)],
    )
    with conectar_con(conexion):
        ServicioZK(dispositivo).respaldar_huellas()
    with conectar_con(conexion):
        ServicioZK(dispositivo).respaldar_huellas()

    assert HuellaEmpleado.objects.filter(empleado=empleado).count() == 1


def test_restaurar_huellas_sin_respaldo_avisa(dispositivo, empleado):
    conexion = ConexionFalsa()
    with conectar_con(conexion):
        with pytest.raises(ErrorDispositivo, match="no tiene huellas respaldadas"):
            ServicioZK(dispositivo).restaurar_huellas(empleado)


def test_restaurar_huellas_envia_las_plantillas_al_equipo(dispositivo, empleado):
    import base64

    HuellaEmpleado.objects.create(
        empleado=empleado,
        finger_id=0,
        template=base64.b64encode(b"\x01\x02\x03").decode("ascii"),
        size=3,
    )

    conexion = ConexionFalsa()
    with conectar_con(conexion):
        resultado = ServicioZK(dispositivo).restaurar_huellas(empleado)

    assert resultado["huellas_restauradas"] == 1
    usuario, dedos = conexion.plantillas_guardadas[0]
    assert usuario.user_id == "1001"
    assert dedos[0].template == b"\x01\x02\x03"


# ----------------------------------------------------------------------
# Marcaciones
# ----------------------------------------------------------------------
def test_descargar_marcaciones_las_guarda(dispositivo, empleado):
    conexion = ConexionFalsa(
        marcaciones=[
            MarcacionFalsa("1001", datetime(2025, 6, 2, 8, 0, 0), status=1),
            MarcacionFalsa("1001", datetime(2025, 6, 2, 17, 0, 0), status=15, punch=1),
        ]
    )
    with conectar_con(conexion):
        resultado = ServicioZK(dispositivo).descargar_marcaciones()

    assert resultado["leidas"] == 2
    assert resultado["nuevas"] == 2
    assert Marcacion.objects.count() == 2

    rostro = Marcacion.objects.get(tipo_verificacion=Marcacion.TipoVerificacion.ROSTRO)
    assert rostro.tipo_marcacion == Marcacion.TipoMarcacion.SALIDA


def test_descargar_el_mismo_rango_dos_veces_no_duplica(dispositivo, empleado):
    """La descarga debe poder repetirse sin ensuciar los datos."""
    conexion = ConexionFalsa(
        marcaciones=[MarcacionFalsa("1001", datetime(2025, 6, 2, 8, 0, 0))]
    )
    with conectar_con(conexion):
        primera = ServicioZK(dispositivo).descargar_marcaciones()
    with conectar_con(conexion):
        segunda = ServicioZK(dispositivo).descargar_marcaciones()

    assert primera["nuevas"] == 1
    assert segunda["nuevas"] == 0
    assert Marcacion.objects.count() == 1


def test_las_marcaciones_de_usuarios_desconocidos_se_reportan(dispositivo, empleado):
    """El administrador del equipo marca, pero no es un empleado del sistema."""
    conexion = ConexionFalsa(
        marcaciones=[
            MarcacionFalsa("1001", datetime(2025, 6, 2, 8, 0, 0)),
            MarcacionFalsa("6999383", datetime(2025, 6, 2, 8, 5, 0)),
        ]
    )
    with conectar_con(conexion):
        resultado = ServicioZK(dispositivo).descargar_marcaciones()

    assert resultado["sin_empleado"] == ["6999383"]
    assert Marcacion.objects.count() == 1


def test_el_filtro_desde_descarta_las_marcaciones_antiguas(dispositivo, empleado):
    conexion = ConexionFalsa(
        marcaciones=[
            MarcacionFalsa("1001", datetime(2025, 6, 1, 8, 0, 0)),
            MarcacionFalsa("1001", datetime(2025, 6, 3, 8, 0, 0)),
        ]
    )
    desde = timezone.make_aware(
        datetime(2025, 6, 2, 0, 0, 0), timezone.get_current_timezone()
    )
    with conectar_con(conexion):
        resultado = ServicioZK(dispositivo).descargar_marcaciones(desde=desde)

    assert resultado["leidas"] == 1
    assert Marcacion.objects.count() == 1


def test_la_descarga_registra_las_fechas_afectadas(dispositivo, empleado):
    """El motor solo recalcula los dias que recibieron marcaciones nuevas."""
    conexion = ConexionFalsa(
        marcaciones=[
            MarcacionFalsa("1001", datetime(2025, 6, 2, 8, 0, 0)),
            MarcacionFalsa("1001", datetime(2025, 6, 2, 17, 0, 0)),
            MarcacionFalsa("1001", datetime(2025, 6, 3, 8, 0, 0)),
        ]
    )
    with conectar_con(conexion):
        resultado = ServicioZK(dispositivo).descargar_marcaciones()

    fechas = {item["fecha"] for item in resultado["fechas_afectadas"]}
    assert fechas == {"2025-06-02", "2025-06-03"}


def test_la_descarga_actualiza_la_marca_de_sincronizacion(dispositivo, empleado):
    conexion = ConexionFalsa(
        marcaciones=[MarcacionFalsa("1001", datetime(2025, 6, 2, 8, 0, 0))]
    )
    with conectar_con(conexion):
        ServicioZK(dispositivo).descargar_marcaciones()

    dispositivo.refresh_from_db()
    assert dispositivo.ultima_sincronizacion_marcaciones is not None


def test_la_hora_del_equipo_se_interpreta_en_la_zona_horaria_local(dispositivo, empleado):
    """El equipo reporta hora local sin zona; guardarla como UTC correria las marcaciones."""
    conexion = ConexionFalsa(
        marcaciones=[MarcacionFalsa("1001", datetime(2025, 6, 2, 8, 0, 0))]
    )
    with conectar_con(conexion):
        ServicioZK(dispositivo).descargar_marcaciones()

    marcacion = Marcacion.objects.first()
    local = timezone.localtime(marcacion.fecha_hora)
    assert (local.hour, local.minute) == (8, 0)

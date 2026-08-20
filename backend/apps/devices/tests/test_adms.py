"""Pruebas del protocolo ADMS.

Simulan las peticiones que hace el equipo. Cubren tanto el camino feliz como los
controles de seguridad: los endpoints son publicos por diseno del protocolo, y
una marcacion falsa se traduce en dinero en la planilla.
"""

import base64
from datetime import date, time

import pytest
from django.utils import timezone

from apps.attendance.models import Marcacion, RegistroAsistencia
from apps.devices.models import ComandoDispositivo, Dispositivo, PeticionADMS
from apps.employees.models import Empleado, HuellaEmpleado
from apps.organization.models import Cargo, Departamento, Sede
from apps.schedules.models import AsignacionTurno, DiaLaborableConfig, Horario, Turno, TurnoDetalle

pytestmark = pytest.mark.django_db

SERIE = "MB560VL0001"
IP_EQUIPO = "192.168.18.202"
LUNES = date(2025, 6, 2)


@pytest.fixture
def dispositivo():
    return Dispositivo.objects.create(
        nombre="MB560-VL",
        ip=IP_EQUIPO,
        numero_serie=SERIE,
        modo=Dispositivo.Modo.ADMS,
        adms_habilitado=True,
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
        sede=sede,
        departamento=departamento,
        cargo=cargo,
        fecha_ingreso=date(2024, 1, 1),
    )


@pytest.fixture
def empleado_con_turno(empleado):
    horario = Horario.objects.create(
        nombre="Administrativo",
        hora_entrada=time(8, 0),
        hora_salida=time(17, 0),
        tolerancia_entrada=5,
        minutos_falta=120,
    )
    turno = Turno.objects.create(nombre="Lunes a Viernes")
    for dia in range(5):
        TurnoDetalle.objects.create(turno=turno, dia_semana=dia, horario=horario)
    for dia in (5, 6):
        TurnoDetalle.objects.create(turno=turno, dia_semana=dia, horario=None)
    AsignacionTurno.objects.create(empleado=empleado, turno=turno, fecha_inicio=date(2024, 1, 1))
    DiaLaborableConfig.objects.get_or_create(pk=1)
    return empleado


def enviar_attlog(cliente, cuerpo, serie=SERIE, ip=IP_EQUIPO):
    return cliente.post(
        f"/iclock/cdata?SN={serie}&table=ATTLOG&Stamp=9999",
        data=cuerpo,
        content_type="text/plain",
        REMOTE_ADDR=ip,
    )


# ----------------------------------------------------------------------
# Seguridad
# ----------------------------------------------------------------------
def test_se_rechaza_una_peticion_sin_numero_de_serie(client, dispositivo):
    respuesta = client.get("/iclock/cdata")

    assert respuesta.status_code == 400
    assert Marcacion.objects.count() == 0


def test_se_rechaza_un_numero_de_serie_desconocido(client, dispositivo, empleado):
    """Nadie mas en la red debe poder inyectar marcaciones."""
    respuesta = enviar_attlog(client, "1001\t2025-06-02 08:00:00\t0\t1\t0", serie="FALSO123")

    assert respuesta.status_code == 403
    assert Marcacion.objects.count() == 0


def test_se_rechaza_un_equipo_con_adms_deshabilitado(client, dispositivo, empleado):
    dispositivo.adms_habilitado = False
    dispositivo.save()

    respuesta = enviar_attlog(client, "1001\t2025-06-02 08:00:00\t0\t1\t0")

    assert respuesta.status_code == 403
    assert Marcacion.objects.count() == 0


def test_se_rechaza_una_ip_no_autorizada(client, dispositivo, empleado):
    dispositivo.adms_ip_permitida = IP_EQUIPO
    dispositivo.save()

    respuesta = enviar_attlog(client, "1001\t2025-06-02 08:00:00\t0\t1\t0", ip="192.168.18.99")

    assert respuesta.status_code == 403
    assert Marcacion.objects.count() == 0


def test_se_acepta_la_ip_autorizada(client, dispositivo, empleado):
    dispositivo.adms_ip_permitida = IP_EQUIPO
    dispositivo.save()

    respuesta = enviar_attlog(client, "1001\t2025-06-02 08:00:00\t0\t1\t0", ip=IP_EQUIPO)

    assert respuesta.status_code == 200
    assert Marcacion.objects.count() == 1


def test_los_rechazos_quedan_registrados(client, dispositivo):
    enviar_attlog(client, "1001\t2025-06-02 08:00:00\t0\t1\t0", serie="INTRUSO")

    peticion = PeticionADMS.objects.first()
    assert peticion.aceptada is False
    assert peticion.numero_serie == "INTRUSO"


def test_se_rechaza_un_cuerpo_excesivamente_grande(client, dispositivo, empleado):
    from django.conf import settings

    respuesta = enviar_attlog(client, "x" * (settings.ADMS_TAMANO_MAXIMO_CUERPO + 10))

    assert respuesta.status_code == 413


def test_un_volcado_completo_de_huellas_no_excede_el_limite(client, dispositivo, empleado):
    """Un volcado real de plantillas supera el limite por defecto de Django.

    Con 2.5 MB (el valor de fabrica) esta sincronizacion fallaria con un 400 sin
    explicacion, dejando a los empleados sin respaldo de sus huellas.
    """
    from django.conf import settings

    plantilla = base64.b64encode(b"\x00" * 1500).decode()
    lineas = [
        f"FP PIN=1001\tFID={i % 10}\tSize=1500\tValid=1\tTMP={plantilla}" for i in range(1400)
    ]
    cuerpo = "\n".join(lineas)

    # Debe superar el limite de fabrica de Django (2.5 MB) para que la prueba
    # demuestre que sin el ajuste esta sincronizacion fallaria.
    assert len(cuerpo) > 2.5 * 1024 * 1024, "El lote de prueba deberia superar los 2.5 MB"
    assert len(cuerpo) < settings.ADMS_TAMANO_MAXIMO_CUERPO

    respuesta = client.post(
        f"/iclock/cdata?SN={SERIE}&table=OPERLOG",
        data=cuerpo,
        content_type="text/plain",
    )

    assert respuesta.status_code == 200
    assert HuellaEmpleado.objects.filter(empleado=empleado).count() == 10


# ----------------------------------------------------------------------
# Handshake
# ----------------------------------------------------------------------
def test_el_handshake_devuelve_las_opciones(client, dispositivo):
    respuesta = client.get(f"/iclock/cdata?SN={SERIE}&options=all&pushver=2.4.1")

    assert respuesta.status_code == 200
    contenido = respuesta.content.decode()
    assert f"GET OPTION FROM: {SERIE}" in contenido
    assert "TransFlag=" in contenido
    assert "Realtime=1" in contenido
    assert respuesta["Content-Type"].startswith("text/plain")


def test_el_handshake_marca_el_equipo_como_conectado(client, dispositivo):
    client.get(f"/iclock/cdata?SN={SERIE}&options=all")

    dispositivo.refresh_from_db()
    assert dispositivo.estado == Dispositivo.Estado.CONECTADO
    assert dispositivo.ultima_conexion_adms is not None


# ----------------------------------------------------------------------
# Marcaciones
# ----------------------------------------------------------------------
def test_se_registran_las_marcaciones_recibidas(client, dispositivo, empleado):
    cuerpo = "1001\t2025-06-02 08:00:00\t0\t1\t0\n1001\t2025-06-02 17:00:00\t1\t15\t0"

    respuesta = enviar_attlog(client, cuerpo)

    assert respuesta.status_code == 200
    assert respuesta.content.decode().startswith("OK")
    assert Marcacion.objects.count() == 2

    entrada = Marcacion.objects.order_by("fecha_hora").first()
    assert entrada.tipo_verificacion == Marcacion.TipoVerificacion.HUELLA
    salida = Marcacion.objects.order_by("fecha_hora").last()
    assert salida.tipo_verificacion == Marcacion.TipoVerificacion.ROSTRO


def test_la_hora_se_interpreta_en_la_zona_local(client, dispositivo, empleado):
    """El equipo envia su hora local sin zona; tomarla como UTC la correria."""
    enviar_attlog(client, "1001\t2025-06-02 08:25:00\t0\t1\t0")

    marcacion = Marcacion.objects.first()
    local = timezone.localtime(marcacion.fecha_hora)
    assert (local.hour, local.minute) == (8, 25)


def test_reenviar_el_mismo_lote_no_duplica(client, dispositivo, empleado):
    """El equipo reenvia si no recibe confirmacion; no debe duplicar nada."""
    cuerpo = "1001\t2025-06-02 08:00:00\t0\t1\t0"

    enviar_attlog(client, cuerpo)
    respuesta = enviar_attlog(client, cuerpo)

    assert respuesta.content.decode() == "OK: 0"
    assert Marcacion.objects.count() == 1


def test_las_marcaciones_de_usuarios_desconocidos_se_ignoran(client, dispositivo, empleado):
    """El administrador del equipo marca, pero no es un empleado del sistema."""
    cuerpo = "1001\t2025-06-02 08:00:00\t0\t1\t0\n6999383\t2025-06-02 08:05:00\t0\t1\t0"

    respuesta = enviar_attlog(client, cuerpo)

    assert respuesta.status_code == 200
    assert Marcacion.objects.count() == 1


def test_las_lineas_ilegibles_no_abortan_el_lote(client, dispositivo, empleado):
    cuerpo = "linea corrupta sin sentido\n1001\t2025-06-02 08:00:00\t0\t1\t0"

    respuesta = enviar_attlog(client, cuerpo)

    assert respuesta.status_code == 200
    assert Marcacion.objects.count() == 1


def test_la_recepcion_dispara_el_procesamiento_de_asistencia(
    client, dispositivo, empleado_con_turno
):
    """Una marcacion tardia debe reflejarse de inmediato como tardanza."""
    cuerpo = "1001\t2025-06-02 08:25:00\t0\t1\t0\n1001\t2025-06-02 17:00:00\t1\t1\t0"

    enviar_attlog(client, cuerpo)

    registro = RegistroAsistencia.objects.get(empleado=empleado_con_turno, fecha=LUNES)
    assert registro.estado == RegistroAsistencia.Estado.TARDANZA
    assert registro.minutos_tardanza == 25
    assert registro.es_descontable is True


def test_se_acepta_una_fecha_con_formato_alternativo(client, dispositivo, empleado):
    respuesta = enviar_attlog(client, "1001\t2025/06/02 08:00:00\t0\t1\t0")

    assert respuesta.status_code == 200
    assert Marcacion.objects.count() == 1


# ----------------------------------------------------------------------
# OPERLOG: huellas y rostros
# ----------------------------------------------------------------------
def test_se_respaldan_las_huellas_recibidas(client, dispositivo, empleado):
    plantilla = base64.b64encode(b"\x01\x02\x03\x04").decode()
    cuerpo = f"FP PIN=1001\tFID=0\tSize=4\tValid=1\tTMP={plantilla}"

    respuesta = client.post(
        f"/iclock/cdata?SN={SERIE}&table=OPERLOG",
        data=cuerpo,
        content_type="text/plain",
    )

    assert respuesta.status_code == 200
    huella = HuellaEmpleado.objects.get(empleado=empleado, finger_id=0)
    assert huella.template == plantilla

    empleado.refresh_from_db()
    assert empleado.tiene_huella is True
    assert empleado.cantidad_huellas == 1


def test_una_plantilla_corrupta_se_descarta(client, dispositivo, empleado):
    """Guardar base64 invalido haria fallar una futura restauracion."""
    cuerpo = "FP PIN=1001\tFID=0\tSize=4\tValid=1\tTMP=esto-no-es-base64!!!"

    respuesta = client.post(
        f"/iclock/cdata?SN={SERIE}&table=OPERLOG",
        data=cuerpo,
        content_type="text/plain",
    )

    assert respuesta.status_code == 200
    assert HuellaEmpleado.objects.count() == 0


def test_el_rostro_solo_marca_el_indicador(client, dispositivo, empleado):
    """La plantilla facial es propietaria: solo interesa saber que existe."""
    cuerpo = "FACE PIN=1001\tFID=12\tSIZE=1000\tVALID=1\tTMP=abc123"

    client.post(
        f"/iclock/cdata?SN={SERIE}&table=OPERLOG",
        data=cuerpo,
        content_type="text/plain",
    )

    empleado.refresh_from_db()
    assert empleado.tiene_rostro is True


# ----------------------------------------------------------------------
# Comandos
# ----------------------------------------------------------------------
def test_sin_comandos_pendientes_responde_ok(client, dispositivo):
    respuesta = client.get(f"/iclock/getrequest?SN={SERIE}")

    assert respuesta.status_code == 200
    assert respuesta.content.decode() == "OK"


def test_se_entregan_los_comandos_pendientes(client, dispositivo, empleado):
    from apps.devices.adms import commands

    commands.encolar_empleados(dispositivo, [empleado])

    respuesta = client.get(f"/iclock/getrequest?SN={SERIE}")

    contenido = respuesta.content.decode()
    assert contenido.startswith("C:")
    assert "DATA UPDATE USERINFO" in contenido
    assert "PIN=1001" in contenido

    comando = ComandoDispositivo.objects.first()
    assert comando.estado == ComandoDispositivo.Estado.ENVIADO
    assert comando.enviado_en is not None


def test_un_comando_entregado_no_se_vuelve_a_entregar(client, dispositivo, empleado):
    from apps.devices.adms import commands

    commands.encolar_empleados(dispositivo, [empleado])

    client.get(f"/iclock/getrequest?SN={SERIE}")
    segunda = client.get(f"/iclock/getrequest?SN={SERIE}")

    assert segunda.content.decode() == "OK"


def test_el_equipo_confirma_la_ejecucion(client, dispositivo, empleado):
    from apps.devices.adms import commands

    commands.encolar_empleados(dispositivo, [empleado])
    client.get(f"/iclock/getrequest?SN={SERIE}")
    comando = ComandoDispositivo.objects.first()

    respuesta = client.post(
        f"/iclock/devicecmd?SN={SERIE}",
        data=f"ID={comando.id}&Return=0&CMD=DATA",
        content_type="text/plain",
    )

    assert respuesta.status_code == 200
    comando.refresh_from_db()
    assert comando.estado == ComandoDispositivo.Estado.CONFIRMADO
    assert comando.codigo_retorno == 0


def test_un_retorno_distinto_de_cero_marca_el_comando_como_fallido(
    client, dispositivo, empleado
):
    from apps.devices.adms import commands

    commands.encolar_empleados(dispositivo, [empleado])
    client.get(f"/iclock/getrequest?SN={SERIE}")
    comando = ComandoDispositivo.objects.first()

    client.post(
        f"/iclock/devicecmd?SN={SERIE}",
        data=f"ID={comando.id}&Return=-1&CMD=DATA",
        content_type="text/plain",
    )

    comando.refresh_from_db()
    assert comando.estado == ComandoDispositivo.Estado.FALLIDO
    assert comando.codigo_retorno == -1


def test_un_equipo_no_puede_confirmar_comandos_de_otro(client, dispositivo, empleado):
    """Aislamiento entre equipos: cada uno solo confirma lo suyo."""
    from apps.devices.adms import commands

    otro = Dispositivo.objects.create(
        nombre="Otro equipo",
        ip="192.168.18.203",
        numero_serie="OTRO999",
        modo=Dispositivo.Modo.ADMS,
        adms_habilitado=True,
    )
    commands.encolar_empleados(dispositivo, [empleado])
    comando = ComandoDispositivo.objects.first()

    client.post(
        f"/iclock/devicecmd?SN={otro.numero_serie}",
        data=f"ID={comando.id}&Return=0&CMD=DATA",
        content_type="text/plain",
    )

    comando.refresh_from_db()
    assert comando.estado == ComandoDispositivo.Estado.PENDIENTE


def test_encolar_empleados_reemplaza_los_pendientes(dispositivo, empleado):
    """Solo importa la ultima version de los datos del empleado."""
    from apps.devices.adms import commands

    commands.encolar_empleados(dispositivo, [empleado])
    commands.encolar_empleados(dispositivo, [empleado])

    assert ComandoDispositivo.objects.filter(
        estado=ComandoDispositivo.Estado.PENDIENTE
    ).count() == 1


def test_no_se_encolan_huellas_con_plantilla_invalida(dispositivo, empleado):
    from apps.devices.adms import commands

    HuellaEmpleado.objects.create(
        empleado=empleado, finger_id=0, template="no-es-base64!!!", size=10
    )
    HuellaEmpleado.objects.create(
        empleado=empleado,
        finger_id=1,
        template=base64.b64encode(b"\x01\x02").decode(),
        size=2,
    )

    comandos = commands.encolar_huellas(dispositivo, empleado)

    assert len(comandos) == 1


# ----------------------------------------------------------------------
# Diagnostico
# ----------------------------------------------------------------------
def test_toda_peticion_queda_registrada(client, dispositivo, empleado):
    enviar_attlog(client, "1001\t2025-06-02 08:00:00\t0\t1\t0")

    peticion = PeticionADMS.objects.first()
    assert peticion.dispositivo == dispositivo
    assert peticion.metodo == "POST"
    assert "1001" in peticion.cuerpo
    assert peticion.parametros["table"] == "ATTLOG"
    assert peticion.aceptada is True


def test_una_ruta_no_implementada_responde_ok(client, dispositivo):
    """Responder OK evita que el equipo reintente en bucle."""
    respuesta = client.get(f"/iclock/rtdata?SN={SERIE}")

    assert respuesta.status_code == 200
    assert PeticionADMS.objects.filter(ruta__contains="rtdata").exists()


def test_una_tabla_desconocida_se_confirma_sin_procesar(client, dispositivo, empleado):
    respuesta = client.post(
        f"/iclock/cdata?SN={SERIE}&table=ATTPHOTO",
        data="datos binarios",
        content_type="text/plain",
    )

    assert respuesta.status_code == 200
    assert Marcacion.objects.count() == 0

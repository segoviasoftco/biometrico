"""Endpoints que consume el dispositivo biometrico en modo ADMS.

El equipo actua como cliente: se conecta al servidor por HTTP y le envia las
marcaciones. Estas vistas hablan el protocolo propietario de ZKTeco, que es
texto plano, no JSON.

Sobre la autenticacion
----------------------
El equipo no puede presentar credenciales: no maneja JWT ni cookies. La unica
identificacion que ofrece es su numero de serie en el parametro `SN`. Como ese
dato viaja en claro y es facil de suplantar, y como una marcacion falsa se
traduce en dinero en la planilla, se aplican tres controles:

  1. Solo se aceptan numeros de serie de equipos registrados y con ADMS
     habilitado de forma explicita.
  2. Si el equipo tiene una IP autorizada configurada, se rechaza cualquier
     peticion que venga de otra direccion.
  3. Toda peticion queda registrada en `PeticionADMS`, aceptada o no.

Estos endpoints deben quedar accesibles solo desde la red local. No los exponga
a Internet sin una VPN o un cortafuegos delante.
"""

import logging

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.devices.adms import commands, parsers, services
from apps.devices.models import ComandoDispositivo, Dispositivo, PeticionADMS

logger = logging.getLogger("apps.devices")

# Tope del cuerpo de una peticion. Debe quedar por debajo de
# DATA_UPLOAD_MAX_MEMORY_SIZE para que sea esta vista la que rechace el exceso,
# con un mensaje claro y dejando constancia, en vez del error generico de Django.
TAMANO_MAXIMO_CUERPO = getattr(
    settings, "ADMS_TAMANO_MAXIMO_CUERPO", 10 * 1024 * 1024
)

# Peticiones que se conservan para diagnostico. El equipo consulta cada pocos
# segundos, asi que sin un limite la tabla creceria sin control.
PETICIONES_A_CONSERVAR = 500


def _ip_origen(request):
    reenviada = request.META.get("HTTP_X_FORWARDED_FOR")
    if reenviada:
        return reenviada.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _texto(contenido, estado=200):
    """El equipo espera texto plano; un JSON haria que descarte la respuesta."""
    return HttpResponse(contenido, content_type="text/plain; charset=utf-8", status=estado)


def _registrar(request, dispositivo, numero_serie, respuesta, aceptada=True, procesados=0):
    """Deja constancia de la peticion y poda el historial antiguo."""
    try:
        cuerpo = request.body.decode("utf-8", errors="replace")[:20000]
    except Exception:  # noqa: BLE001
        cuerpo = "(no se pudo leer el cuerpo)"

    PeticionADMS.objects.create(
        dispositivo=dispositivo,
        numero_serie=numero_serie or "",
        ruta=request.path[:255],
        metodo=request.method,
        parametros=dict(request.GET.items()) or None,
        cuerpo=cuerpo,
        respuesta=str(respuesta)[:5000],
        ip_origen=_ip_origen(request),
        aceptada=aceptada,
        registros_procesados=procesados,
    )
    _podar_historial()


def _podar_historial():
    """Conserva solo las peticiones mas recientes."""
    total = PeticionADMS.objects.count()
    if total <= PETICIONES_A_CONSERVAR * 2:
        return
    limite = PeticionADMS.objects.order_by("-recibida_en").values_list(
        "id", flat=True
    )[PETICIONES_A_CONSERVAR : PETICIONES_A_CONSERVAR + 1]
    if limite:
        PeticionADMS.objects.filter(id__lte=list(limite)[0]).delete()


def _autorizar(request):
    """Identifica el equipo que hace la peticion y valida que pueda hacerla.

    Devuelve (dispositivo, numero_serie, error). Si `error` no es None, es la
    respuesta que debe devolverse.
    """
    numero_serie = (request.GET.get("SN") or request.GET.get("sn") or "").strip()

    if not numero_serie:
        _registrar(request, None, "", "sin numero de serie", aceptada=False)
        logger.warning("Peticion ADMS sin numero de serie desde %s", _ip_origen(request))
        return None, "", _texto("ERROR: falta el numero de serie", estado=400)

    dispositivo = Dispositivo.objects.filter(
        numero_serie=numero_serie, adms_habilitado=True, activo=True
    ).first()

    if dispositivo is None:
        _registrar(request, None, numero_serie, "equipo no autorizado", aceptada=False)
        logger.warning(
            "Peticion ADMS de un equipo no registrado. Serie=%s IP=%s",
            numero_serie,
            _ip_origen(request),
        )
        return None, numero_serie, _texto("ERROR: equipo no autorizado", estado=403)

    ip = _ip_origen(request)
    if dispositivo.adms_ip_permitida and ip != dispositivo.adms_ip_permitida:
        _registrar(request, dispositivo, numero_serie, "IP no autorizada", aceptada=False)
        logger.warning(
            "Peticion ADMS del equipo %s desde una IP no autorizada: %s (esperada %s)",
            numero_serie,
            ip,
            dispositivo.adms_ip_permitida,
        )
        return None, numero_serie, _texto("ERROR: origen no autorizado", estado=403)

    return dispositivo, numero_serie, None


def _marcar_visto(dispositivo):
    Dispositivo.objects.filter(id=dispositivo.id).update(
        ultima_conexion_adms=timezone.now(),
        ultima_conexion=timezone.now(),
        estado=Dispositivo.Estado.CONECTADO,
    )


def _desfase_horario():
    """Desfase de la zona horaria del proyecto, en horas, como espera el equipo."""
    desplazamiento = timezone.localtime().utcoffset()
    return int(desplazamiento.total_seconds() // 3600) if desplazamiento else 0


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------
@csrf_exempt
@require_http_methods(["GET", "POST"])
def cdata(request):
    """Handshake inicial (GET) y recepcion de datos (POST)."""
    dispositivo, numero_serie, error = _autorizar(request)
    if error is not None:
        return error

    _marcar_visto(dispositivo)

    if request.method == "GET":
        return _handshake(request, dispositivo, numero_serie)
    return _recibir_datos(request, dispositivo, numero_serie)


def _handshake(request, dispositivo, numero_serie):
    """Responde la configuracion con la que el equipo debe operar.

    `TransFlag` le indica que tipos de datos enviar y `Delay` cada cuantos
    segundos consultar por comandos nuevos.
    """
    opciones = "\n".join(
        [
            f"GET OPTION FROM: {numero_serie}",
            f"Stamp={dispositivo.adms_stamp or '0'}",
            f"OpStamp={dispositivo.adms_op_stamp or '0'}",
            "ErrorDelay=30",
            "Delay=10",
            "TransTimes=00:00;12:00",
            "TransInterval=1",
            (
                "TransFlag=TransData AttLog OpLog AttPhoto EnrollUser "
                "ChgUser EnrollFP ChgFP FPImag FACE UserPic"
            ),
            f"TimeZone={_desfase_horario()}",
            "Realtime=1",
            "Encrypt=0",
        ]
    )
    _registrar(request, dispositivo, numero_serie, opciones)
    logger.info("Handshake ADMS del equipo %s desde %s", numero_serie, _ip_origen(request))
    return _texto(opciones)


def _recibir_datos(request, dispositivo, numero_serie):
    """Procesa un lote de marcaciones u operaciones."""
    if len(request.body) > TAMANO_MAXIMO_CUERPO:
        _registrar(request, dispositivo, numero_serie, "cuerpo demasiado grande", aceptada=False)
        logger.warning("El equipo %s envio un lote excesivamente grande.", numero_serie)
        return _texto("ERROR: cuerpo demasiado grande", estado=413)

    tabla = (request.GET.get("table") or request.GET.get("TABLE") or "").upper()
    cuerpo = request.body.decode("utf-8", errors="replace")

    if tabla == "ATTLOG":
        registros, descartadas = parsers.parsear_attlog(cuerpo)
        resultado = services.registrar_marcaciones(dispositivo, registros)

        if descartadas:
            logger.warning(
                "El equipo %s envio %s linea(s) de marcacion no interpretables.",
                numero_serie,
                len(descartadas),
            )
        if resultado["sin_empleado"]:
            logger.info(
                "Marcaciones de usuarios sin empleado en el sistema: %s",
                resultado["sin_empleado"],
            )

        respuesta = f"OK: {resultado['nuevas']}"
        _registrar(
            request, dispositivo, numero_serie, respuesta, procesados=resultado["nuevas"]
        )
        _guardar_stamp(dispositivo, request, campo="adms_stamp")
        return _texto(respuesta)

    if tabla == "OPERLOG":
        datos = parsers.parsear_operlog(cuerpo)
        resumen = services.registrar_operaciones(dispositivo, datos)
        respuesta = f"OK: {resumen['huellas'] + resumen['rostros']}"
        _registrar(
            request,
            dispositivo,
            numero_serie,
            respuesta,
            procesados=resumen["huellas"] + resumen["rostros"],
        )
        _guardar_stamp(dispositivo, request, campo="adms_op_stamp")
        return _texto(respuesta)

    # Fotos de marcacion y otras tablas: se confirman para que el equipo no
    # reintente, pero no se procesan.
    logger.info("El equipo %s envio la tabla '%s', que no se procesa.", numero_serie, tabla)
    _registrar(request, dispositivo, numero_serie, "OK")
    return _texto("OK")


def _guardar_stamp(dispositivo, request, campo):
    """Guarda el contador que el equipo usa para no reenviar lo ya entregado."""
    valor = request.GET.get("Stamp") or request.GET.get("stamp")
    if valor:
        Dispositivo.objects.filter(id=dispositivo.id).update(**{campo: str(valor)[:32]})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def getrequest(request):
    """Entrega al equipo los comandos que tiene pendientes."""
    dispositivo, numero_serie, error = _autorizar(request)
    if error is not None:
        return error

    _marcar_visto(dispositivo)

    pendientes = commands.obtener_pendientes(dispositivo)
    if not pendientes:
        _registrar(request, dispositivo, numero_serie, "OK")
        return _texto("OK")

    cuerpo = commands.formatear_para_equipo(pendientes)

    ahora = timezone.now()
    ComandoDispositivo.objects.filter(id__in=[c.id for c in pendientes]).update(
        estado=ComandoDispositivo.Estado.ENVIADO, enviado_en=ahora
    )

    _registrar(request, dispositivo, numero_serie, cuerpo, procesados=len(pendientes))
    logger.info("Se entregaron %s comando(s) al equipo %s", len(pendientes), numero_serie)
    return _texto(cuerpo)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def devicecmd(request):
    """Recibe el resultado de los comandos que ejecuto el equipo.

    Llega como `ID=1&Return=0&CMD=DATA`, y puede traer varias confirmaciones
    separadas por saltos de linea.
    """
    dispositivo, numero_serie, error = _autorizar(request)
    if error is not None:
        return error

    _marcar_visto(dispositivo)

    cuerpo = request.body.decode("utf-8", errors="replace")
    confirmados = 0

    for linea in cuerpo.splitlines():
        linea = linea.strip()
        if not linea:
            continue

        datos = {}
        for parte in linea.split("&"):
            clave, _, valor = parte.partition("=")
            datos[clave.strip().upper()] = valor.strip()

        comando_id = datos.get("ID")
        if not comando_id or not comando_id.isdigit():
            continue

        comando = ComandoDispositivo.objects.filter(
            id=int(comando_id), dispositivo=dispositivo
        ).first()
        if comando is None:
            continue

        retorno = datos.get("RETURN", "")
        codigo = int(retorno) if retorno.lstrip("-").isdigit() else None

        # El protocolo usa 0 para exito; cualquier otro valor es un error.
        exitoso = codigo == 0
        comando.estado = (
            ComandoDispositivo.Estado.CONFIRMADO
            if exitoso
            else ComandoDispositivo.Estado.FALLIDO
        )
        comando.codigo_retorno = codigo
        comando.respuesta = linea[:255]
        comando.confirmado_en = timezone.now()
        comando.save()
        confirmados += 1

        if not exitoso:
            logger.warning(
                "El equipo %s rechazo el comando %s (retorno=%s): %s",
                numero_serie,
                comando.id,
                codigo,
                comando.get_tipo_display(),
            )

    _registrar(request, dispositivo, numero_serie, "OK", procesados=confirmados)
    return _texto("OK")


@csrf_exempt
@require_http_methods(["GET", "POST"])
def ping(request):
    """Comprobacion de conectividad que hacen algunos firmwares."""
    dispositivo, numero_serie, error = _autorizar(request)
    if error is not None:
        return error

    _marcar_visto(dispositivo)
    _registrar(request, dispositivo, numero_serie, "OK")
    return _texto("OK")


@csrf_exempt
@require_http_methods(["GET", "POST"])
def fdata(request):
    """Recepcion de plantillas biometricas en firmwares que usan esta ruta."""
    dispositivo, numero_serie, error = _autorizar(request)
    if error is not None:
        return error

    _marcar_visto(dispositivo)

    cuerpo = request.body.decode("utf-8", errors="replace")
    datos = parsers.parsear_operlog(cuerpo)
    resumen = services.registrar_operaciones(dispositivo, datos)

    _registrar(
        request,
        dispositivo,
        numero_serie,
        "OK",
        procesados=resumen["huellas"] + resumen["rostros"],
    )
    return _texto("OK")


@csrf_exempt
def desconocido(request, ruta=""):
    """Recoge cualquier otra ruta /iclock/ que use el firmware.

    Responder OK evita que el equipo reintente en bucle, y la peticion queda
    registrada para poder implementarla si resulta necesaria.
    """
    numero_serie = (request.GET.get("SN") or "").strip()
    dispositivo = Dispositivo.objects.filter(
        numero_serie=numero_serie, adms_habilitado=True
    ).first()

    _registrar(request, dispositivo, numero_serie, "OK (ruta no implementada)")
    logger.info(
        "El equipo %s uso la ruta ADMS no implementada '%s'", numero_serie or "?", request.path
    )
    return _texto("OK")

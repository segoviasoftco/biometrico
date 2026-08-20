"""Interpretacion de los datos que el equipo envia por ADMS.

El equipo manda texto plano: una linea por registro y los campos separados por
tabuladores. Hay dos tablas principales:

  ATTLOG   marcaciones de asistencia
  OPERLOG  altas y bajas de usuarios, huellas, rostros y operaciones del menu

El formato no esta publicado oficialmente y varia entre firmwares, por lo que
estas funciones son deliberadamente tolerantes: si una linea no se entiende, se
descarta y se informa, en lugar de abortar el lote completo. La peticion cruda
queda guardada en `PeticionADMS` para poder revisarla.
"""

import logging
import re
from datetime import datetime

from django.utils import timezone

logger = logging.getLogger("apps.devices")

# Formatos de fecha que se han visto en distintos firmwares.
FORMATOS_FECHA = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)


def parsear_fecha(texto):
    """Convierte la fecha del equipo a un datetime con zona horaria.

    El equipo informa su hora local sin zona, por lo que se interpreta en la
    zona del proyecto. Tomarla como UTC correria todas las marcaciones.
    """
    texto = (texto or "").strip()
    if not texto:
        return None

    for formato in FORMATOS_FECHA:
        try:
            ingenuo = datetime.strptime(texto, formato)
            return timezone.make_aware(ingenuo, timezone.get_current_timezone())
        except ValueError:
            continue

    # Algunos firmwares envian la fecha como marca de tiempo Unix.
    if texto.isdigit() and len(texto) >= 9:
        try:
            return timezone.make_aware(
                datetime.fromtimestamp(int(texto)), timezone.get_current_timezone()
            )
        except (ValueError, OSError):
            pass

    logger.warning("No se pudo interpretar la fecha enviada por el equipo: %r", texto)
    return None


def _entero(valor, por_defecto=0):
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return por_defecto


def parsear_attlog(cuerpo):
    """Interpreta el bloque de marcaciones.

    Formato habitual, separado por tabuladores:

        PIN  FechaHora  Estado  Verificacion  CodigoTrabajo  Reserva1  Reserva2

    donde `Estado` es el tipo de marcacion (entrada, salida, refrigerio) y
    `Verificacion` el metodo con el que se identifico (huella, rostro, tarjeta).

    Devuelve (registros, lineas_descartadas).
    """
    registros = []
    descartadas = []

    for numero, linea in enumerate(cuerpo.splitlines(), start=1):
        linea = linea.strip()
        if not linea:
            continue

        campos = linea.split("\t")
        # Algunos firmwares separan por espacios multiples en vez de tabuladores.
        if len(campos) < 3:
            campos = re.split(r"\s{2,}", linea)
        if len(campos) < 2:
            descartadas.append({"linea": numero, "contenido": linea[:200]})
            continue

        codigo = campos[0].strip()
        fecha_hora = parsear_fecha(campos[1])
        if not codigo or fecha_hora is None:
            descartadas.append({"linea": numero, "contenido": linea[:200]})
            continue

        registros.append(
            {
                "codigo_empleado": codigo,
                "fecha_hora": fecha_hora,
                "tipo_marcacion": _entero(campos[2], 255) if len(campos) > 2 else 255,
                "tipo_verificacion": _entero(campos[3], 99) if len(campos) > 3 else 99,
                "codigo_trabajo": _entero(campos[4]) if len(campos) > 4 else 0,
            }
        )

    return registros, descartadas


def _parsear_pares(texto):
    """Convierte 'PIN=1\tName=Juan\tPri=0' en un diccionario."""
    datos = {}
    for parte in texto.split("\t"):
        if "=" in parte:
            clave, _, valor = parte.partition("=")
            datos[clave.strip().upper()] = valor.strip()
    return datos


def parsear_operlog(cuerpo):
    """Interpreta el bloque de operaciones.

    Cada linea empieza con el tipo de registro:

        USER PIN=1  Name=Juan  Pri=0  Passwd=  Card=0  Grp=1
        FP   PIN=1  FID=0  Size=...  Valid=1  TMP=<base64>
        FACE PIN=1  FID=12  SIZE=...  VALID=1  TMP=<base64>
        OPLOG ...
    """
    resultado = {"usuarios": [], "huellas": [], "rostros": [], "operaciones": [], "otros": []}

    for linea in cuerpo.splitlines():
        linea = linea.strip()
        if not linea:
            continue

        etiqueta, _, resto = linea.partition(" ")
        etiqueta = etiqueta.strip().upper()
        datos = _parsear_pares(resto)

        if etiqueta == "USER":
            resultado["usuarios"].append(
                {
                    "codigo_empleado": datos.get("PIN", ""),
                    "nombre": datos.get("NAME", ""),
                    "privilegio": _entero(datos.get("PRI"), 0),
                    "tarjeta": datos.get("CARD", ""),
                    "grupo": datos.get("GRP", ""),
                }
            )
        elif etiqueta == "FP":
            resultado["huellas"].append(
                {
                    "codigo_empleado": datos.get("PIN", ""),
                    "finger_id": _entero(datos.get("FID"), 0),
                    "size": _entero(datos.get("SIZE"), 0),
                    "valid": _entero(datos.get("VALID"), 1),
                    "template": datos.get("TMP", ""),
                }
            )
        elif etiqueta in ("FACE", "BIODATA"):
            # La plantilla facial llega en base64 pero es propietaria: solo se
            # usa para saber que el empleado ya esta enrolado.
            resultado["rostros"].append(
                {
                    "codigo_empleado": datos.get("PIN", ""),
                    "valid": _entero(datos.get("VALID"), 1),
                    "tipo": datos.get("TYPE", ""),
                }
            )
        elif etiqueta == "OPLOG":
            resultado["operaciones"].append({"contenido": linea[:500]})
        else:
            resultado["otros"].append({"contenido": linea[:500]})

    return resultado

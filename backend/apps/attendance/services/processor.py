"""Motor de procesamiento de asistencia.

Convierte las marcaciones crudas del dispositivo en un resultado diario por
empleado (puntual, tardanza, falta, permiso, descanso...), que es la base del
dashboard y de los reportes de descuento.

El procesamiento es idempotente: volver a procesar un dia produce siempre el
mismo resultado, de modo que se puede recalcular con seguridad cuando cambia un
turno o se aprueba un permiso con fecha retroactiva.
"""

import logging
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.attendance.models import Marcacion, RegistroAsistencia
from apps.schedules.models import AsignacionTurno, DiaLaborableConfig, Feriado, Permiso

logger = logging.getLogger("apps.attendance")

# Margen para capturar marcaciones que caen fuera del dia calendario: una entrada
# adelantada de la noche anterior o la salida de un turno que cruza medianoche.
MARGEN_ANTES = timedelta(hours=4)
MARGEN_DESPUES = timedelta(hours=6)


class ProcesadorAsistencia:
    """Evalua las marcaciones de un empleado contra su horario programado."""

    def __init__(self, config=None):
        # La configuracion se carga una sola vez para no consultarla por cada dia
        # al procesar rangos largos.
        self.config = config or DiaLaborableConfig.obtener()

    # ------------------------------------------------------------------
    # API principal
    # ------------------------------------------------------------------
    @transaction.atomic
    def procesar_dia(self, empleado, fecha, forzar=False):
        """Procesa un dia concreto y devuelve el `RegistroAsistencia` resultante.

        Si el registro fue ajustado manualmente no se toca, salvo que se pida
        forzar: de lo contrario el recalculo automatico borraria la correccion
        que hizo un responsable de RRHH.
        """
        registro = RegistroAsistencia.objects.filter(empleado=empleado, fecha=fecha).first()
        if registro and registro.ajustado_manualmente and not forzar:
            return registro

        datos = self._evaluar(empleado, fecha)

        registro, _ = RegistroAsistencia.objects.update_or_create(
            empleado=empleado, fecha=fecha, defaults=datos
        )
        return registro

    def procesar_rango(self, empleados, fecha_inicio, fecha_fin, forzar=False):
        """Procesa varios empleados a lo largo de un rango de fechas."""
        total = 0
        fecha = fecha_inicio
        while fecha <= fecha_fin:
            for empleado in empleados:
                self.procesar_dia(empleado, fecha, forzar=forzar)
                total += 1
            fecha += timedelta(days=1)
        return total

    # ------------------------------------------------------------------
    # Evaluacion de un dia
    # ------------------------------------------------------------------
    def _evaluar(self, empleado, fecha):
        """Determina el estado del dia y arma los campos del registro."""
        base = {
            "turno": None,
            "horario": None,
            "hora_entrada_programada": None,
            "hora_salida_programada": None,
            "marcacion_entrada": None,
            "marcacion_salida": None,
            "total_marcaciones": 0,
            "minutos_tardanza": 0,
            "minutos_salida_anticipada": 0,
            "minutos_trabajados": 0,
            "minutos_programados": 0,
            "estado": RegistroAsistencia.Estado.SIN_TURNO,
            "permiso": None,
            "es_descontable": False,
            "observacion": "",
        }

        # Fuera del periodo laboral del empleado no se evalua nada: antes de su
        # ingreso o despues de su cese no corresponde falta.
        if fecha < empleado.fecha_ingreso:
            base["observacion"] = "Anterior a la fecha de ingreso."
            return base
        if empleado.fecha_cese and fecha > empleado.fecha_cese:
            base["observacion"] = "Posterior a la fecha de cese."
            return base

        asignacion = self._turno_vigente(empleado, fecha)
        if asignacion is None:
            base["observacion"] = "El empleado no tiene un turno asignado para esta fecha."
            return base

        turno = asignacion.turno
        horario = turno.horario_del_dia(fecha.weekday())
        base["turno"] = turno

        marcaciones = self._marcaciones_del_dia(empleado, fecha, horario)
        base["total_marcaciones"] = len(marcaciones)

        # --- Dias en los que no se espera trabajo -------------------------
        feriado = self._feriado(empleado, fecha)
        if feriado:
            base["estado"] = RegistroAsistencia.Estado.FERIADO
            base["observacion"] = feriado.descripcion[:255]
            self._registrar_marcaciones(base, marcaciones)
            return base

        if horario is None:
            base["estado"] = RegistroAsistencia.Estado.DESCANSO
            base["observacion"] = "Dia de descanso segun el turno."
            self._registrar_marcaciones(base, marcaciones)
            return base

        base["horario"] = horario
        base["hora_entrada_programada"] = horario.hora_entrada
        base["hora_salida_programada"] = horario.hora_salida
        base["minutos_programados"] = horario.minutos_jornada

        permiso = self._permiso(empleado, fecha)
        if permiso:
            base["permiso"] = permiso
            base["estado"] = self._estado_por_permiso(permiso)
            # Un permiso sin goce de haber si genera descuento.
            base["es_descontable"] = not permiso.con_goce
            base["observacion"] = permiso.get_tipo_display()
            self._registrar_marcaciones(base, marcaciones)
            return base

        # --- Dia laborable -----------------------------------------------
        if not marcaciones:
            base["estado"] = RegistroAsistencia.Estado.FALTA
            base["es_descontable"] = True
            base["observacion"] = "Sin marcaciones registradas."
            return base

        self._registrar_marcaciones(base, marcaciones)

        if len(marcaciones) == 1:
            return self._evaluar_marcacion_unica(base, empleado, fecha, horario, marcaciones[0])

        return self._evaluar_jornada_completa(base, fecha, horario, marcaciones)

    # ------------------------------------------------------------------
    # Casos de evaluacion
    # ------------------------------------------------------------------
    def _evaluar_marcacion_unica(self, base, empleado, fecha, horario, marcacion):
        """Un solo registro en el dia: el empleado entro pero no marco salida.

        Segun la configuracion se trata como falta o como asistencia incompleta.
        Se calcula igual la tardanza, porque la hora de entrada si es conocida.
        """
        entrada_programada = self._combinar(fecha, horario.hora_entrada)
        tardanza = self._minutos_tardanza(marcacion.fecha_hora, entrada_programada, horario)
        base["minutos_tardanza"] = tardanza

        if self.config.considerar_marcacion_unica_como_falta:
            base["estado"] = RegistroAsistencia.Estado.FALTA
            base["es_descontable"] = True
            base["observacion"] = "Solo se registro una marcacion en el dia."
            return base

        base["estado"] = RegistroAsistencia.Estado.INCOMPLETO
        base["es_descontable"] = tardanza > 0
        base["observacion"] = "Falta la marcacion de salida."
        return base

    def _evaluar_jornada_completa(self, base, fecha, horario, marcaciones):
        """Jornada con entrada y salida: calcula tardanza, salida anticipada y horas."""
        entrada = marcaciones[0].fecha_hora
        salida = marcaciones[-1].fecha_hora

        entrada_programada = self._combinar(fecha, horario.hora_entrada)
        salida_programada = self._combinar(fecha, horario.hora_salida)
        if horario.cruza_medianoche:
            salida_programada += timedelta(days=1)

        tardanza = self._minutos_tardanza(entrada, entrada_programada, horario)
        anticipada = self._minutos_salida_anticipada(salida, salida_programada, horario)

        minutos_trabajados = int((salida - entrada).total_seconds() // 60)
        minutos_trabajados = max(0, minutos_trabajados - horario.minutos_refrigerio)

        base["minutos_tardanza"] = tardanza
        base["minutos_salida_anticipada"] = anticipada
        base["minutos_trabajados"] = minutos_trabajados

        # Una tardanza excesiva se considera falta: el empleado no cumplio la
        # jornada aunque haya llegado.
        if tardanza > horario.minutos_falta:
            base["estado"] = RegistroAsistencia.Estado.FALTA
            base["es_descontable"] = True
            base["observacion"] = f"Tardanza de {tardanza} minutos, supera el limite permitido."
            return base

        if tardanza > 0:
            base["estado"] = RegistroAsistencia.Estado.TARDANZA
            base["es_descontable"] = True
            base["observacion"] = f"Tardanza de {tardanza} minutos."
            return base

        base["estado"] = RegistroAsistencia.Estado.PUNTUAL
        if anticipada > 0:
            base["es_descontable"] = True
            base["observacion"] = f"Salida anticipada de {anticipada} minutos."
        return base

    # ------------------------------------------------------------------
    # Calculos auxiliares
    # ------------------------------------------------------------------
    def _minutos_tardanza(self, marcacion, programada, horario):
        """Minutos de retraso ya descontadas las tolerancias.

        Se cuenta el retraso completo desde la hora programada, no desde el fin
        de la tolerancia: la tolerancia decide si hay tardanza, no cuanto se
        descuenta.
        """
        tolerancia = horario.tolerancia_entrada + self.config.minutos_tolerancia_global
        limite = programada + timedelta(minutes=tolerancia)
        if marcacion <= limite:
            return 0
        return int((marcacion - programada).total_seconds() // 60)

    @staticmethod
    def _minutos_salida_anticipada(marcacion, programada, horario):
        limite = programada - timedelta(minutes=horario.tolerancia_salida)
        if marcacion >= limite:
            return 0
        return int((programada - marcacion).total_seconds() // 60)

    @staticmethod
    def _combinar(fecha, hora):
        """Une fecha y hora en un datetime con la zona horaria del proyecto."""
        ingenuo = datetime.combine(fecha, hora)
        return timezone.make_aware(ingenuo, timezone.get_current_timezone())

    @staticmethod
    def _registrar_marcaciones(base, marcaciones):
        if not marcaciones:
            return
        base["marcacion_entrada"] = marcaciones[0].fecha_hora
        if len(marcaciones) > 1:
            base["marcacion_salida"] = marcaciones[-1].fecha_hora

    # ------------------------------------------------------------------
    # Consultas de contexto
    # ------------------------------------------------------------------
    @staticmethod
    def _turno_vigente(empleado, fecha):
        """Asignacion de turno vigente en la fecha indicada.

        Se consulta por fecha (y no el turno actual del empleado) para que el
        recalculo de periodos pasados use el turno que realmente regia entonces.
        """
        return (
            AsignacionTurno.objects.filter(empleado=empleado, fecha_inicio__lte=fecha)
            .filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha))
            .select_related("turno")
            .order_by("-fecha_inicio")
            .first()
        )

    @staticmethod
    def _feriado(empleado, fecha):
        """Feriado aplicable a la sede del empleado, o general."""
        return (
            Feriado.objects.filter(Q(sede__isnull=True) | Q(sede=empleado.sede))
            .filter(
                Q(fecha=fecha)
                | Q(es_recurrente=True, fecha__month=fecha.month, fecha__day=fecha.day)
            )
            .first()
        )

    @staticmethod
    def _permiso(empleado, fecha):
        return Permiso.objects.filter(
            empleado=empleado,
            estado=Permiso.EstadoAprobacion.APROBADO,
            fecha_inicio__lte=fecha,
            fecha_fin__gte=fecha,
        ).first()

    @staticmethod
    def _estado_por_permiso(permiso):
        if permiso.tipo == Permiso.Tipo.VACACIONES:
            return RegistroAsistencia.Estado.VACACIONES
        if permiso.tipo == Permiso.Tipo.DESCANSO_MEDICO:
            return RegistroAsistencia.Estado.FALTA_JUSTIFICADA
        return RegistroAsistencia.Estado.PERMISO

    @staticmethod
    def _marcaciones_del_dia(empleado, fecha, horario):
        """Marcaciones que corresponden a la jornada de esa fecha.

        La ventana se ancla al horario programado y no al dia calendario. De otro
        modo un turno nocturno perderia su marcacion de salida (que ocurre al dia
        siguiente), y un turno diurno se quedaria con la salida de la vispera.

        En los dias sin horario (descanso o feriado) se usa el dia calendario,
        que es lo unico que se puede delimitar.
        """
        if horario is None:
            inicio = ProcesadorAsistencia._combinar(fecha, datetime.min.time())
            fin = inicio + timedelta(days=1)
        else:
            entrada = ProcesadorAsistencia._combinar(fecha, horario.hora_entrada)
            salida = ProcesadorAsistencia._combinar(fecha, horario.hora_salida)
            if horario.cruza_medianoche:
                salida += timedelta(days=1)
            inicio = entrada - MARGEN_ANTES
            fin = salida + MARGEN_DESPUES

        return list(
            Marcacion.objects.filter(
                empleado=empleado, fecha_hora__gte=inicio, fecha_hora__lt=fin
            ).order_by("fecha_hora")
        )


# ----------------------------------------------------------------------
# Funciones de conveniencia
# ----------------------------------------------------------------------
def procesar_dia(empleado, fecha, forzar=False):
    return ProcesadorAsistencia().procesar_dia(empleado, fecha, forzar=forzar)


def procesar_rango(empleados, fecha_inicio, fecha_fin, forzar=False):
    return ProcesadorAsistencia().procesar_rango(
        empleados, fecha_inicio, fecha_fin, forzar=forzar
    )

"""API de dispositivos biometricos."""

import csv
from datetime import datetime, time

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import (
    EsAdministrador,
    EsAdministradorORRHH,
    LecturaTodosEscrituraRRHH,
)
from apps.audit.middleware import registrar_auditoria
from apps.audit.models import RegistroAuditoria
from apps.devices.adms import commands as adms_commands
from apps.devices.models import (
    ComandoDispositivo,
    Dispositivo,
    PeticionADMS,
    RegistroSincronizacion,
)
from apps.devices.serializers import (
    ComandoDispositivoSerializer,
    DescargarMarcacionesSerializer,
    DispositivoSerializer,
    PeticionADMSSerializer,
    RegistroSincronizacionSerializer,
)
from apps.devices.services.sincronizacion import descargar_y_procesar, ejecutar_operacion
from apps.employees.models import Empleado


def _conciliar_empleados_equipo(dispositivo):
    """Arma el mismo reporte de conciliacion que la via SDK, a partir de lo
    ultimo que el equipo reporto por ADMS (tabla `UsuarioDispositivo`).

    No consulta al equipo en vivo -- en ADMS el servidor no puede hacerlo --
    asi que el resultado es tan reciente como el ultimo `OPERLOG` recibido.
    """
    reportados = list(dispositivo.usuarios_reportados.all())
    codigos_sistema = set(Empleado.objects.values_list("codigo_empleado", flat=True))
    codigos_equipo = {u.codigo_empleado for u in reportados}

    return {
        "total_en_equipo": len(reportados),
        "usuarios": [
            {
                "uid": None,
                "user_id": u.codigo_empleado,
                "nombre": u.nombre,
                "privilegio": u.privilegio,
                "tarjeta": u.tarjeta,
                "registrado_en_sistema": u.codigo_empleado in codigos_sistema,
                "actualizado_en": u.actualizado_en,
            }
            for u in reportados
        ],
        "solo_en_equipo": sorted(codigos_equipo - codigos_sistema),
        "solo_en_sistema": sorted(codigos_sistema - codigos_equipo),
    }


class DispositivoViewSet(viewsets.ModelViewSet):
    """Configuracion del equipo y operaciones de sincronizacion."""

    queryset = Dispositivo.objects.select_related("sede").all()
    serializer_class = DispositivoSerializer
    permission_classes = [LecturaTodosEscrituraRRHH]
    filterset_fields = ["activo", "estado", "sede"]
    search_fields = ["nombre", "ip", "numero_serie"]

    def get_permissions(self):
        # Cambiar la IP o borrar el equipo afecta a todo el sistema.
        if self.action in ("create", "update", "partial_update", "destroy", "limpiar_marcaciones"):
            return [EsAdministrador()]
        return super().get_permissions()

    # ------------------------------------------------------------------
    # Diagnostico
    # ------------------------------------------------------------------
    @action(detail=True, methods=["post"], url_path="probar-conexion")
    def probar_conexion(self, request, pk=None):
        """Verifica que el equipo responda y refresca sus datos de fabrica."""
        dispositivo = self.get_object()
        registro, resultado = ejecutar_operacion(
            dispositivo,
            RegistroSincronizacion.Operacion.PROBAR_CONEXION,
            lambda servicio: servicio.probar_conexion(),
            usuario=request.user,
        )
        if resultado is None:
            return Response({"detalle": registro.mensaje}, status=status.HTTP_502_BAD_GATEWAY)

        dispositivo.refresh_from_db()
        return Response(
            {
                "detalle": "Conexion establecida con el dispositivo.",
                "informacion": registro.detalle,
                "dispositivo": DispositivoSerializer(dispositivo).data,
            }
        )

    @action(detail=True, methods=["post"], url_path="sincronizar-hora")
    def sincronizar_hora(self, request, pk=None):
        """Ajusta el reloj del equipo al del servidor.

        Un reloj desfasado genera tardanzas y faltas que no ocurrieron.
        """
        dispositivo = self.get_object()
        registro, resultado = ejecutar_operacion(
            dispositivo,
            RegistroSincronizacion.Operacion.SINCRONIZAR_HORA,
            lambda servicio: servicio.sincronizar_hora(),
            usuario=request.user,
        )
        if resultado is None:
            return Response({"detalle": registro.mensaje}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"detalle": "Hora sincronizada.", "hora": resultado})

    # ------------------------------------------------------------------
    # Empleados
    # ------------------------------------------------------------------
    @action(detail=True, methods=["post"], url_path="subir-empleados")
    def subir_empleados(self, request, pk=None):
        """Sube al equipo los empleados activos.

        Por defecto solo los pendientes, para no reescribir todo el padron en
        cada sincronizacion.
        """
        dispositivo = self.get_object()
        solo_pendientes = request.data.get("solo_pendientes", True)

        empleados = Empleado.objects.filter(estado=Empleado.Estado.ACTIVO)
        if solo_pendientes:
            empleados = empleados.filter(sincronizado_dispositivo=False)
        empleados = list(empleados)

        if not empleados:
            return Response({"detalle": "No hay empleados pendientes de sincronizar.", "resultado": {}})

        # En modo ADMS el servidor no puede iniciar la comunicacion: los
        # empleados se dejan en cola y el equipo los recoge al consultar.
        if dispositivo.modo == Dispositivo.Modo.ADMS:
            return self._encolar_empleados(request, dispositivo, empleados)

        registro, resultado = ejecutar_operacion(
            dispositivo,
            RegistroSincronizacion.Operacion.SUBIR_EMPLEADOS,
            lambda servicio: servicio.subir_empleados(empleados),
            usuario=request.user,
        )
        if resultado is None:
            return Response({"detalle": registro.mensaje}, status=status.HTTP_502_BAD_GATEWAY)

        registrar_auditoria(
            accion=RegistroAuditoria.Accion.SINCRONIZAR,
            modelo="Dispositivo",
            objeto_id=dispositivo.id,
            descripcion=f"Subida de {resultado['procesados']} empleados al dispositivo",
        )
        return Response({"detalle": "Empleados sincronizados.", "resultado": resultado})

    def _encolar_empleados(self, request, dispositivo, empleados):
        """Deja los empleados en la cola de comandos del equipo (modo ADMS)."""
        comandos = adms_commands.encolar_empleados(
            dispositivo, empleados, usuario=request.user
        )

        # En ADMS la entrega no es inmediata: se marcan como sincronizados solo
        # cuando el equipo confirma la ejecucion del comando.
        registrar_auditoria(
            accion=RegistroAuditoria.Accion.SINCRONIZAR,
            modelo="Dispositivo",
            objeto_id=dispositivo.id,
            descripcion=f"Se encolaron {len(comandos)} empleados para el equipo (modo ADMS)",
        )
        return Response(
            {
                "detalle": (
                    f"Se encolaron {len(comandos)} empleado(s). El equipo los recibira "
                    "la proxima vez que consulte al servidor."
                ),
                "resultado": {"encolados": len(comandos), "procesados": 0, "fallidos": 0},
            }
        )

    @action(detail=True, methods=["get"], url_path="empleados-en-equipo")
    def empleados_en_equipo(self, request, pk=None):
        """Concilia los usuarios del equipo contra el maestro de empleados.

        No crea ni borra empleados: solo reporta las diferencias para que un
        responsable decida, porque un alta o baja automatica a partir del
        equipo podria borrar datos laborales.
        """
        dispositivo = self.get_object()

        if dispositivo.modo == Dispositivo.Modo.ADMS:
            resultado = _conciliar_empleados_equipo(dispositivo)
            resultado["fuente"] = "adms"
            return Response(resultado)

        registro, resultado = ejecutar_operacion(
            dispositivo,
            RegistroSincronizacion.Operacion.DESCARGAR_EMPLEADOS,
            lambda servicio: servicio.descargar_empleados(),
            usuario=request.user,
        )
        if resultado is None:
            return Response({"detalle": registro.mensaje}, status=status.HTTP_502_BAD_GATEWAY)
        resultado["fuente"] = "sdk"
        return Response(resultado)

    @action(detail=True, methods=["post"], url_path="solicitar-empleados")
    def solicitar_empleados(self, request, pk=None):
        """En ADMS, pide al equipo que reenvie su padron de usuarios.

        El servidor no puede leer los usuarios del equipo bajo demanda como en
        SDK: encola el mismo comando de reenvio que usan las huellas y las
        marcaciones, y el resultado llega despues por `/iclock/cdata` (bloque
        OPERLOG), que ahora se guarda en `UsuarioDispositivo`.
        """
        dispositivo = self.get_object()
        if dispositivo.modo != Dispositivo.Modo.ADMS:
            return Response(
                {"detalle": "Este equipo no esta en modo ADMS; use 'empleados-en-equipo'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        adms_commands.encolar(
            dispositivo,
            ComandoDispositivo.Tipo.SOLICITAR_DATOS,
            adms_commands.COMANDOS_SIMPLES[ComandoDispositivo.Tipo.SOLICITAR_DATOS],
            usuario=request.user,
        )
        return Response(
            {
                "detalle": (
                    "Se solicito al equipo el reenvio de su padron de usuarios. La lista se "
                    "actualizara cuando el equipo responda."
                ),
                "resultado": {"encolado": True},
            }
        )

    @action(detail=True, methods=["get"], url_path="empleados-en-equipo-csv")
    def empleados_en_equipo_csv(self, request, pk=None):
        """Exporta a CSV la conciliacion de empleados del equipo.

        Pensado para poder revisar o cargar los datos fuera del sistema (por
        ejemplo, para preparar un alta masiva en la base de datos) sin crear
        empleados automaticamente.
        """
        dispositivo = self.get_object()

        if dispositivo.modo == Dispositivo.Modo.ADMS:
            resultado = _conciliar_empleados_equipo(dispositivo)
        else:
            registro, resultado = ejecutar_operacion(
                dispositivo,
                RegistroSincronizacion.Operacion.DESCARGAR_EMPLEADOS,
                lambda servicio: servicio.descargar_empleados(),
                usuario=request.user,
            )
            if resultado is None:
                return Response({"detalle": registro.mensaje}, status=status.HTTP_502_BAD_GATEWAY)

        respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
        marca = timezone.localtime().strftime("%Y%m%d_%H%M")
        respuesta["Content-Disposition"] = (
            f'attachment; filename="empleados_equipo_{dispositivo.id}_{marca}.csv"'
        )
        # BOM para que Excel detecte UTF-8 en vez de interpretar tildes mal.
        respuesta.write("﻿")
        escritor = csv.writer(respuesta, delimiter=";")
        escritor.writerow(
            ["codigo_empleado", "nombre_en_equipo", "privilegio", "tarjeta", "registrado_en_sistema"]
        )
        for usuario in resultado["usuarios"]:
            escritor.writerow(
                [
                    usuario["user_id"],
                    usuario["nombre"],
                    usuario["privilegio"],
                    usuario["tarjeta"],
                    "si" if usuario["registrado_en_sistema"] else "no",
                ]
            )

        registrar_auditoria(
            accion=RegistroAuditoria.Accion.SINCRONIZAR,
            modelo="Dispositivo",
            objeto_id=dispositivo.id,
            descripcion=f"Exportacion CSV de empleados del equipo ({len(resultado['usuarios'])} usuarios)",
        )
        return respuesta

    # ------------------------------------------------------------------
    # Biometria
    # ------------------------------------------------------------------
    @action(detail=True, methods=["post"], url_path="respaldar-huellas")
    def respaldar_huellas(self, request, pk=None):
        """Descarga las huellas del equipo y actualiza los indicadores biometricos.

        El rostro no se descarga: su plantilla no es accesible por el protocolo.
        """
        dispositivo = self.get_object()

        # En ADMS no se puede pedir la informacion y esperarla: se solicita al
        # equipo que reenvie sus datos y estos llegan por /iclock/cdata.
        if dispositivo.modo == Dispositivo.Modo.ADMS:
            adms_commands.encolar(
                dispositivo,
                ComandoDispositivo.Tipo.SOLICITAR_DATOS,
                adms_commands.COMANDOS_SIMPLES[ComandoDispositivo.Tipo.SOLICITAR_DATOS],
                usuario=request.user,
            )
            return Response(
                {
                    "detalle": (
                        "Se solicito al equipo el reenvio de sus datos. Las huellas y el "
                        "estado de enrolamiento se actualizaran cuando el equipo responda."
                    ),
                    "resultado": {"encolado": True},
                }
            )

        registro, resultado = ejecutar_operacion(
            dispositivo,
            RegistroSincronizacion.Operacion.DESCARGAR_HUELLAS,
            lambda servicio: servicio.respaldar_huellas(),
            usuario=request.user,
        )
        if resultado is None:
            return Response({"detalle": registro.mensaje}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"detalle": "Huellas respaldadas.", "resultado": resultado})

    # ------------------------------------------------------------------
    # Marcaciones
    # ------------------------------------------------------------------
    @action(detail=True, methods=["post"], url_path="descargar-marcaciones")
    def descargar_marcaciones(self, request, pk=None):
        """Descarga las marcaciones y recalcula los dias afectados."""
        dispositivo = self.get_object()

        # En ADMS las marcaciones llegan solas. Lo unico que se puede hacer es
        # pedirle al equipo que reenvie lo que tenga almacenado.
        if dispositivo.modo == Dispositivo.Modo.ADMS:
            adms_commands.encolar(
                dispositivo,
                ComandoDispositivo.Tipo.SOLICITAR_DATOS,
                adms_commands.COMANDOS_SIMPLES[ComandoDispositivo.Tipo.SOLICITAR_DATOS],
                usuario=request.user,
            )
            return Response(
                {
                    "detalle": (
                        "En modo ADMS el equipo envia las marcaciones automaticamente. "
                        "Se le solicito reenviar los datos que tenga pendientes."
                    ),
                    "resultado": {"encolado": True, "nuevas": 0},
                }
            )

        serializer = DescargarMarcacionesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        desde = serializer.validated_data.get("desde")
        if desde:
            desde = timezone.make_aware(
                datetime.combine(desde, time.min), timezone.get_current_timezone()
            )
        else:
            desde = dispositivo.ultima_sincronizacion_marcaciones

        registro, resultado = descargar_y_procesar(
            dispositivo,
            desde=desde,
            usuario=request.user,
            procesar=serializer.validated_data["procesar"],
        )
        if resultado is None:
            return Response({"detalle": registro.mensaje}, status=status.HTTP_502_BAD_GATEWAY)

        registrar_auditoria(
            accion=RegistroAuditoria.Accion.SINCRONIZAR,
            modelo="Dispositivo",
            objeto_id=dispositivo.id,
            descripcion=f"Descarga de marcaciones: {resultado['nuevas']} nuevas",
        )
        return Response(
            {
                "detalle": f"Se descargaron {resultado['nuevas']} marcaciones nuevas.",
                "resultado": resultado,
            }
        )

    @action(detail=True, methods=["post"], url_path="limpiar-marcaciones")
    def limpiar_marcaciones(self, request, pk=None):
        """Borra las marcaciones almacenadas en el equipo.

        Operacion irreversible. Exige una confirmacion explicita en el cuerpo de
        la peticion para que no pueda dispararse por accidente.
        """
        dispositivo = self.get_object()
        if request.data.get("confirmacion") != "CONFIRMO":
            return Response(
                {
                    "detalle": (
                        "Esta operacion borra de forma irreversible las marcaciones del "
                        "equipo. Envie confirmacion='CONFIRMO' para continuar."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        registro, resultado = ejecutar_operacion(
            dispositivo,
            RegistroSincronizacion.Operacion.LIMPIAR_MARCACIONES,
            lambda servicio: servicio.limpiar_marcaciones(),
            usuario=request.user,
        )
        if resultado is None:
            return Response({"detalle": registro.mensaje}, status=status.HTTP_502_BAD_GATEWAY)

        registrar_auditoria(
            accion=RegistroAuditoria.Accion.SINCRONIZAR,
            modelo="Dispositivo",
            objeto_id=dispositivo.id,
            descripcion="Limpieza de las marcaciones almacenadas en el equipo",
        )
        return Response({"detalle": "Se borraron las marcaciones del equipo."})


class RegistroSincronizacionViewSet(viewsets.ReadOnlyModelViewSet):
    """Historial de operaciones contra los dispositivos."""

    queryset = RegistroSincronizacion.objects.select_related(
        "dispositivo", "ejecutado_por"
    ).all()
    serializer_class = RegistroSincronizacionSerializer
    filterset_fields = ["dispositivo", "operacion", "estado"]
    ordering_fields = ["inicio"]


class ComandoDispositivoViewSet(viewsets.ReadOnlyModelViewSet):
    """Cola de comandos hacia los equipos en modo ADMS."""

    queryset = ComandoDispositivo.objects.select_related(
        "dispositivo", "empleado", "creado_por"
    ).all()
    serializer_class = ComandoDispositivoSerializer
    permission_classes = [LecturaTodosEscrituraRRHH]
    filterset_fields = ["dispositivo", "tipo", "estado", "empleado"]
    ordering_fields = ["creado_en"]

    @action(detail=True, methods=["post"], permission_classes=[EsAdministrador])
    def cancelar(self, request, pk=None):
        """Elimina un comando que aun no se entrego al equipo."""
        comando = self.get_object()
        if comando.estado != ComandoDispositivo.Estado.PENDIENTE:
            return Response(
                {"detalle": "Solo se pueden cancelar los comandos que aun estan pendientes."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        comando.delete()
        return Response({"detalle": "Comando cancelado."})

    @action(detail=False, methods=["post"], url_path="reintentar-fallidos",
            permission_classes=[EsAdministradorORRHH])
    def reintentar_fallidos(self, request):
        """Vuelve a poner en cola los comandos que el equipo rechazo."""
        queryset = ComandoDispositivo.objects.filter(
            estado=ComandoDispositivo.Estado.FALLIDO
        )
        if request.data.get("dispositivo"):
            queryset = queryset.filter(dispositivo_id=request.data["dispositivo"])

        total = queryset.update(
            estado=ComandoDispositivo.Estado.PENDIENTE,
            codigo_retorno=None,
            respuesta="",
            enviado_en=None,
            confirmado_en=None,
        )
        return Response({"detalle": f"Se reencolaron {total} comando(s).", "total": total})


class PeticionADMSViewSet(viewsets.ReadOnlyModelViewSet):
    """Bitacora de las peticiones crudas que envia el equipo.

    Es la herramienta de diagnostico del protocolo: el formato ADMS varia entre
    firmwares y aqui se ve exactamente que envia este equipo en concreto.
    """

    queryset = PeticionADMS.objects.select_related("dispositivo").all()
    serializer_class = PeticionADMSSerializer
    permission_classes = [EsAdministrador]
    filterset_fields = ["dispositivo", "aceptada", "metodo"]
    search_fields = ["ruta", "numero_serie", "cuerpo"]
    ordering_fields = ["recibida_en"]

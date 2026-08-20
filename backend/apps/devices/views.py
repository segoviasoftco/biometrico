"""API de dispositivos biometricos."""

from datetime import datetime, time

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import EsAdministrador, LecturaTodosEscrituraRRHH
from apps.audit.middleware import registrar_auditoria
from apps.audit.models import RegistroAuditoria
from apps.devices.models import Dispositivo, RegistroSincronizacion
from apps.devices.serializers import (
    DescargarMarcacionesSerializer,
    DispositivoSerializer,
    RegistroSincronizacionSerializer,
)
from apps.devices.services.sincronizacion import descargar_y_procesar, ejecutar_operacion
from apps.employees.models import Empleado


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

    @action(detail=True, methods=["get"], url_path="empleados-en-equipo")
    def empleados_en_equipo(self, request, pk=None):
        """Concilia los usuarios del equipo contra el maestro de empleados."""
        dispositivo = self.get_object()
        registro, resultado = ejecutar_operacion(
            dispositivo,
            RegistroSincronizacion.Operacion.DESCARGAR_EMPLEADOS,
            lambda servicio: servicio.descargar_empleados(),
            usuario=request.user,
        )
        if resultado is None:
            return Response({"detalle": registro.mensaje}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(resultado)

    # ------------------------------------------------------------------
    # Biometria
    # ------------------------------------------------------------------
    @action(detail=True, methods=["post"], url_path="respaldar-huellas")
    def respaldar_huellas(self, request, pk=None):
        """Descarga las huellas del equipo y actualiza los indicadores biometricos.

        El rostro no se descarga: su plantilla no es accesible por el protocolo.
        """
        dispositivo = self.get_object()
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

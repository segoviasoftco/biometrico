"""API del maestro de empleados."""

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import FiltradoPorSedeMixin, LecturaTodosEscrituraRRHH
from apps.audit.middleware import registrar_auditoria
from apps.audit.models import RegistroAuditoria
from apps.devices.models import Dispositivo, RegistroSincronizacion
from apps.devices.services.zk_service import ErrorDispositivo, ServicioZK
from apps.employees.models import Empleado
from apps.employees.serializers import EmpleadoListaSerializer, EmpleadoSerializer


class EmpleadoViewSet(FiltradoPorSedeMixin, viewsets.ModelViewSet):
    """Gestion de empleados y de su sincronizacion con el dispositivo."""

    queryset = Empleado.objects.select_related(
        "sede", "departamento", "area", "cargo"
    ).prefetch_related("huellas")
    permission_classes = [LecturaTodosEscrituraRRHH]
    campo_sede = "sede_id"
    filterset_fields = [
        "sede",
        "departamento",
        "area",
        "cargo",
        "estado",
        "tipo_contrato",
        "tiene_huella",
        "tiene_rostro",
        "sincronizado_dispositivo",
    ]
    search_fields = ["codigo_empleado", "dni", "nombres", "apellido_paterno", "apellido_materno"]
    ordering_fields = ["apellido_paterno", "codigo_empleado", "fecha_ingreso"]

    def get_serializer_class(self):
        if self.action == "list":
            return EmpleadoListaSerializer
        return EmpleadoSerializer

    def perform_create(self, serializer):
        empleado = serializer.save()
        registrar_auditoria(
            accion=RegistroAuditoria.Accion.CREAR,
            modelo="Empleado",
            objeto_id=empleado.id,
            descripcion=f"Alta del empleado {empleado.codigo_empleado} - {empleado.nombre_completo}",
        )

    def perform_update(self, serializer):
        empleado = serializer.save()
        # Los datos maestros cambiaron: el equipo queda desactualizado hasta que
        # se vuelva a sincronizar.
        Empleado.objects.filter(pk=empleado.pk).update(sincronizado_dispositivo=False)
        registrar_auditoria(
            accion=RegistroAuditoria.Accion.ACTUALIZAR,
            modelo="Empleado",
            objeto_id=empleado.id,
            descripcion=f"Actualizacion del empleado {empleado.codigo_empleado}",
        )

    def perform_destroy(self, instance):
        # Nunca se borra un empleado: sus marcaciones y registros de asistencia
        # son el respaldo de los descuentos ya aplicados en planilla.
        instance.estado = Empleado.Estado.CESADO
        if not instance.fecha_cese:
            instance.fecha_cese = timezone.localdate()
        instance.save(update_fields=["estado", "fecha_cese"])
        registrar_auditoria(
            accion=RegistroAuditoria.Accion.ELIMINAR,
            modelo="Empleado",
            objeto_id=instance.id,
            descripcion=f"Cese del empleado {instance.codigo_empleado}",
        )

    # ------------------------------------------------------------------
    # Acciones sobre el dispositivo
    # ------------------------------------------------------------------
    @action(detail=True, methods=["post"], url_path="sincronizar")
    def sincronizar(self, request, pk=None):
        """Sube este empleado al dispositivo biometrico."""
        empleado = self.get_object()
        dispositivo = self._dispositivo_activo()
        if dispositivo is None:
            return Response(
                {"detalle": "No hay un dispositivo biometrico activo configurado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        registro = RegistroSincronizacion.objects.create(
            dispositivo=dispositivo,
            operacion=RegistroSincronizacion.Operacion.SUBIR_EMPLEADOS,
            ejecutado_por=request.user,
        )
        try:
            resultado = ServicioZK(dispositivo).subir_empleados([empleado])
        except ErrorDispositivo as exc:
            registro.estado = RegistroSincronizacion.Estado.FALLIDO
            registro.mensaje = str(exc)
            registro.fin = timezone.now()
            registro.save()
            return Response({"detalle": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        exitoso = resultado["fallidos"] == 0
        registro.estado = (
            RegistroSincronizacion.Estado.EXITOSO
            if exitoso
            else RegistroSincronizacion.Estado.FALLIDO
        )
        registro.registros_procesados = resultado["procesados"]
        registro.registros_fallidos = resultado["fallidos"]
        registro.detalle = resultado
        registro.fin = timezone.now()
        registro.save()

        registrar_auditoria(
            accion=RegistroAuditoria.Accion.SINCRONIZAR,
            modelo="Empleado",
            objeto_id=empleado.id,
            descripcion=f"Sincronizacion del empleado {empleado.codigo_empleado} con el dispositivo",
        )

        empleado.refresh_from_db()
        return Response(
            {
                "detalle": "Empleado sincronizado." if exitoso else "La sincronizacion fallo.",
                "resultado": resultado,
                "empleado": EmpleadoSerializer(empleado, context={"request": request}).data,
            },
            status=status.HTTP_200_OK if exitoso else status.HTTP_502_BAD_GATEWAY,
        )

    @action(detail=True, methods=["post"], url_path="restaurar-huellas")
    def restaurar_huellas(self, request, pk=None):
        """Re-escribe en el equipo las huellas respaldadas de este empleado."""
        empleado = self.get_object()
        dispositivo = self._dispositivo_activo()
        if dispositivo is None:
            return Response(
                {"detalle": "No hay un dispositivo biometrico activo configurado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            resultado = ServicioZK(dispositivo).restaurar_huellas(empleado)
        except ErrorDispositivo as exc:
            return Response({"detalle": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        registrar_auditoria(
            accion=RegistroAuditoria.Accion.SINCRONIZAR,
            modelo="Empleado",
            objeto_id=empleado.id,
            descripcion=f"Restauracion de huellas de {empleado.codigo_empleado}",
        )
        return Response({"detalle": "Huellas restauradas en el dispositivo.", **resultado})

    @action(detail=False, methods=["get"], url_path="pendientes-sincronizar")
    def pendientes_sincronizar(self, request):
        """Empleados activos que aun no estan en el equipo o cambiaron de datos."""
        queryset = self.get_queryset().filter(
            estado=Empleado.Estado.ACTIVO, sincronizado_dispositivo=False
        )
        return Response(EmpleadoListaSerializer(queryset, many=True).data)

    @action(detail=False, methods=["get"], url_path="sin-biometria")
    def sin_biometria(self, request):
        """Empleados activos que aun no tienen huella ni rostro enrolados.

        Es la lista de quienes deben pasar por el equipo a registrarse.
        """
        queryset = self.get_queryset().filter(
            estado=Empleado.Estado.ACTIVO, tiene_huella=False, tiene_rostro=False
        )
        return Response(EmpleadoListaSerializer(queryset, many=True).data)

    @staticmethod
    def _dispositivo_activo():
        return Dispositivo.objects.filter(activo=True).first()

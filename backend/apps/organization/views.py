"""API de la estructura organizacional."""

from django.db.models import Count, Q
from rest_framework import viewsets

from apps.accounts.permissions import LecturaTodosEscrituraRRHH
from apps.employees.models import Empleado
from apps.organization.models import Area, Cargo, Departamento, Sede
from apps.organization.serializers import (
    AreaSerializer,
    CargoSerializer,
    DepartamentoSerializer,
    SedeSerializer,
)

# Solo los empleados vigentes cuentan para los totales que se muestran en los
# catalogos; incluir a los cesados daria una idea equivocada del tamano del area.
EMPLEADOS_ACTIVOS = Count("empleados", filter=Q(empleados__estado=Empleado.Estado.ACTIVO))


class SedeViewSet(viewsets.ModelViewSet):
    serializer_class = SedeSerializer
    permission_classes = [LecturaTodosEscrituraRRHH]
    filterset_fields = ["activo"]
    search_fields = ["nombre", "codigo"]
    ordering_fields = ["nombre", "codigo"]

    def get_queryset(self):
        queryset = Sede.objects.annotate(total_empleados=EMPLEADOS_ACTIVOS)
        usuario = self.request.user
        if usuario.es_supervisor and usuario.sede_id:
            return queryset.filter(id=usuario.sede_id)
        return queryset


class DepartamentoViewSet(viewsets.ModelViewSet):
    serializer_class = DepartamentoSerializer
    permission_classes = [LecturaTodosEscrituraRRHH]
    filterset_fields = ["sede", "activo"]
    search_fields = ["nombre", "codigo"]
    ordering_fields = ["nombre"]

    def get_queryset(self):
        queryset = Departamento.objects.select_related("sede").annotate(
            total_empleados=EMPLEADOS_ACTIVOS
        )
        usuario = self.request.user
        if usuario.es_supervisor and usuario.sede_id:
            return queryset.filter(sede_id=usuario.sede_id)
        return queryset


class AreaViewSet(viewsets.ModelViewSet):
    serializer_class = AreaSerializer
    permission_classes = [LecturaTodosEscrituraRRHH]
    filterset_fields = ["departamento", "departamento__sede", "activo"]
    search_fields = ["nombre", "codigo"]
    ordering_fields = ["nombre"]

    def get_queryset(self):
        queryset = Area.objects.select_related("departamento__sede")
        usuario = self.request.user
        if usuario.es_supervisor and usuario.sede_id:
            return queryset.filter(departamento__sede_id=usuario.sede_id)
        return queryset


class CargoViewSet(viewsets.ModelViewSet):
    """Los cargos son transversales, por lo que no se filtran por sede."""

    queryset = Cargo.objects.all()
    serializer_class = CargoSerializer
    permission_classes = [LecturaTodosEscrituraRRHH]
    filterset_fields = ["activo"]
    search_fields = ["nombre"]
    ordering_fields = ["nombre"]

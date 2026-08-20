"""Endpoints de agregacion para el dashboard.

Todas las vistas parten de `RegistroAsistencia`, que ya tiene el dia evaluado,
en lugar de recalcular sobre las marcaciones crudas.
"""

from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth, TruncWeek
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.attendance.models import RegistroAsistencia
from apps.devices.models import Dispositivo
from apps.employees.models import Empleado

Estado = RegistroAsistencia.Estado

# Estados que representan una ausencia que se descuenta.
ESTADOS_FALTA = [Estado.FALTA]
# Estados en los que se espera que el empleado trabaje ese dia.
ESTADOS_LABORABLES = [Estado.PUNTUAL, Estado.TARDANZA, Estado.FALTA, Estado.INCOMPLETO]


class BaseDashboardView(APIView):
    """Comparte el filtrado por sede, departamento y rango de fechas."""

    permission_classes = [IsAuthenticated]

    def filtrar(self, queryset):
        usuario = self.request.user
        params = self.request.query_params

        # Un supervisor solo ve su sede, sin importar lo que pida por parametro.
        if usuario.es_supervisor and usuario.sede_id:
            queryset = queryset.filter(empleado__sede_id=usuario.sede_id)
        elif params.get("sede"):
            queryset = queryset.filter(empleado__sede_id=params["sede"])

        if params.get("departamento"):
            queryset = queryset.filter(empleado__departamento_id=params["departamento"])
        if params.get("fecha_inicio"):
            queryset = queryset.filter(fecha__gte=params["fecha_inicio"])
        if params.get("fecha_fin"):
            queryset = queryset.filter(fecha__lte=params["fecha_fin"])
        return queryset

    def rango(self, dias_por_defecto=30):
        """Rango de fechas solicitado, o los ultimos N dias."""
        params = self.request.query_params
        hoy = timezone.localdate()
        fin = params.get("fecha_fin") or hoy
        inicio = params.get("fecha_inicio") or (hoy - timedelta(days=dias_por_defecto))
        return inicio, fin


class ResumenDiaView(BaseDashboardView):
    """Situacion del dia: presentes, faltas, tardanzas y permisos."""

    def get(self, request):
        fecha = request.query_params.get("fecha") or timezone.localdate()
        queryset = self.filtrar(RegistroAsistencia.objects.filter(fecha=fecha))

        datos = queryset.aggregate(
            puntuales=Count("id", filter=Q(estado=Estado.PUNTUAL)),
            tardanzas=Count("id", filter=Q(estado=Estado.TARDANZA)),
            faltas=Count("id", filter=Q(estado=Estado.FALTA)),
            incompletos=Count("id", filter=Q(estado=Estado.INCOMPLETO)),
            permisos=Count("id", filter=Q(estado__in=[Estado.PERMISO, Estado.VACACIONES])),
            justificadas=Count("id", filter=Q(estado=Estado.FALTA_JUSTIFICADA)),
            descansos=Count("id", filter=Q(estado__in=[Estado.DESCANSO, Estado.FERIADO])),
            minutos_tardanza=Sum("minutos_tardanza"),
        )
        datos = {clave: valor or 0 for clave, valor in datos.items()}

        # El porcentaje se calcula solo sobre quienes debian trabajar ese dia:
        # incluir descansos y feriados lo distorsionaria.
        esperados = datos["puntuales"] + datos["tardanzas"] + datos["faltas"] + datos["incompletos"]
        asistieron = datos["puntuales"] + datos["tardanzas"] + datos["incompletos"]

        datos["fecha"] = str(fecha)
        datos["esperados"] = esperados
        datos["asistieron"] = asistieron
        datos["porcentaje_asistencia"] = (
            round(asistieron / esperados * 100, 1) if esperados else 0.0
        )
        datos["total_empleados_activos"] = self._empleados_activos()
        return Response(datos)

    def _empleados_activos(self):
        queryset = Empleado.objects.filter(estado=Empleado.Estado.ACTIVO)
        usuario = self.request.user
        if usuario.es_supervisor and usuario.sede_id:
            queryset = queryset.filter(sede_id=usuario.sede_id)
        elif self.request.query_params.get("sede"):
            queryset = queryset.filter(sede_id=self.request.query_params["sede"])
        return queryset.count()


class TendenciaSemanalView(BaseDashboardView):
    """Faltas y tardanzas agrupadas por semana, para el grafico de tendencia."""

    def get(self, request):
        inicio, fin = self.rango(dias_por_defecto=84)  # 12 semanas
        queryset = self.filtrar(
            RegistroAsistencia.objects.filter(fecha__gte=inicio, fecha__lte=fin)
        )

        datos = (
            queryset.annotate(periodo=TruncWeek("fecha"))
            .values("periodo")
            .annotate(
                faltas=Count("id", filter=Q(estado__in=ESTADOS_FALTA)),
                tardanzas=Count("id", filter=Q(estado=Estado.TARDANZA)),
                minutos_tardanza=Sum("minutos_tardanza"),
                puntuales=Count("id", filter=Q(estado=Estado.PUNTUAL)),
            )
            .order_by("periodo")
        )
        return Response(
            [
                {
                    "periodo": d["periodo"].isoformat() if d["periodo"] else None,
                    "faltas": d["faltas"],
                    "tardanzas": d["tardanzas"],
                    "minutos_tardanza": d["minutos_tardanza"] or 0,
                    "puntuales": d["puntuales"],
                }
                for d in datos
            ]
        )


class TendenciaMensualView(BaseDashboardView):
    """Faltas y tardanzas agrupadas por mes."""

    def get(self, request):
        inicio, fin = self.rango(dias_por_defecto=365)
        queryset = self.filtrar(
            RegistroAsistencia.objects.filter(fecha__gte=inicio, fecha__lte=fin)
        )

        datos = (
            queryset.annotate(periodo=TruncMonth("fecha"))
            .values("periodo")
            .annotate(
                faltas=Count("id", filter=Q(estado__in=ESTADOS_FALTA)),
                tardanzas=Count("id", filter=Q(estado=Estado.TARDANZA)),
                minutos_tardanza=Sum("minutos_tardanza"),
                puntuales=Count("id", filter=Q(estado=Estado.PUNTUAL)),
            )
            .order_by("periodo")
        )
        return Response(
            [
                {
                    "periodo": d["periodo"].isoformat() if d["periodo"] else None,
                    "faltas": d["faltas"],
                    "tardanzas": d["tardanzas"],
                    "minutos_tardanza": d["minutos_tardanza"] or 0,
                    "puntuales": d["puntuales"],
                }
                for d in datos
            ]
        )


class RankingView(BaseDashboardView):
    """Empleados con mas tardanzas y con mas faltas en el periodo."""

    def get(self, request):
        inicio, fin = self.rango()
        limite = int(request.query_params.get("limite", 10))
        queryset = self.filtrar(
            RegistroAsistencia.objects.filter(fecha__gte=inicio, fecha__lte=fin)
        )

        base = queryset.values(
            "empleado_id",
            "empleado__codigo_empleado",
            "empleado__nombres",
            "empleado__apellido_paterno",
            "empleado__apellido_materno",
            "empleado__departamento__nombre",
        )

        tardanzas = (
            base.annotate(
                dias=Count("id", filter=Q(estado=Estado.TARDANZA)),
                minutos=Sum("minutos_tardanza"),
            )
            .filter(dias__gt=0)
            .order_by("-minutos", "-dias")[:limite]
        )
        faltas = (
            base.annotate(dias=Count("id", filter=Q(estado__in=ESTADOS_FALTA)))
            .filter(dias__gt=0)
            .order_by("-dias")[:limite]
        )

        return Response(
            {
                "tardanzas": [self._fila(d, con_minutos=True) for d in tardanzas],
                "faltas": [self._fila(d) for d in faltas],
            }
        )

    @staticmethod
    def _fila(dato, con_minutos=False):
        fila = {
            "empleado_id": dato["empleado_id"],
            "codigo": dato["empleado__codigo_empleado"],
            "nombre": (
                f"{dato['empleado__apellido_paterno']} "
                f"{dato['empleado__apellido_materno']}, {dato['empleado__nombres']}"
            ).strip(),
            "departamento": dato["empleado__departamento__nombre"],
            "dias": dato["dias"],
        }
        if con_minutos:
            fila["minutos"] = dato["minutos"] or 0
        return fila


class ComparativoDepartamentoView(BaseDashboardView):
    """Indicadores de asistencia agrupados por departamento."""

    def get(self, request):
        inicio, fin = self.rango()
        queryset = self.filtrar(
            RegistroAsistencia.objects.filter(fecha__gte=inicio, fecha__lte=fin)
        )

        # El alias del total no puede llamarse igual que el campo: Django
        # resolveria el promedio contra la propia suma en lugar del campo.
        datos = (
            queryset.values("empleado__departamento__id", "empleado__departamento__nombre",
                            "empleado__sede__nombre")
            .annotate(
                puntuales=Count("id", filter=Q(estado=Estado.PUNTUAL)),
                tardanzas=Count("id", filter=Q(estado=Estado.TARDANZA)),
                faltas=Count("id", filter=Q(estado__in=ESTADOS_FALTA)),
                total_minutos_tardanza=Sum("minutos_tardanza"),
                dias_laborables=Count("id", filter=Q(estado__in=ESTADOS_LABORABLES)),
            )
            .order_by("-faltas", "-tardanzas")
        )

        resultado = []
        for d in datos:
            laborables = d["dias_laborables"] or 0
            asistidos = d["puntuales"] + d["tardanzas"]
            minutos = d["total_minutos_tardanza"] or 0
            resultado.append(
                {
                    "departamento_id": d["empleado__departamento__id"],
                    "departamento": d["empleado__departamento__nombre"],
                    "sede": d["empleado__sede__nombre"],
                    "puntuales": d["puntuales"],
                    "tardanzas": d["tardanzas"],
                    "faltas": d["faltas"],
                    "minutos_tardanza": minutos,
                    # Promedio sobre los dias que efectivamente tuvieron tardanza.
                    "promedio_minutos_tardanza": (
                        round(minutos / d["tardanzas"], 1) if d["tardanzas"] else 0.0
                    ),
                    "porcentaje_asistencia": (
                        round(asistidos / laborables * 100, 1) if laborables else 0.0
                    ),
                }
            )
        return Response(resultado)


class EstadoSistemaView(BaseDashboardView):
    """Estado del dispositivo y del maestro de empleados.

    Sirve para detectar a tiempo los dos problemas que dejan el sistema sin
    datos: que el equipo no responda, o que haya empleados sin biometria.
    """

    def get(self, request):
        dispositivos = [
            {
                "id": d.id,
                "nombre": d.nombre,
                "ip": d.ip,
                "estado": d.estado,
                "estado_display": d.get_estado_display(),
                "ultima_conexion": d.ultima_conexion,
                "ultima_sincronizacion_marcaciones": d.ultima_sincronizacion_marcaciones,
            }
            for d in Dispositivo.objects.filter(activo=True)
        ]

        empleados = Empleado.objects.filter(estado=Empleado.Estado.ACTIVO)
        usuario = request.user
        if usuario.es_supervisor and usuario.sede_id:
            empleados = empleados.filter(sede_id=usuario.sede_id)

        return Response(
            {
                "dispositivos": dispositivos,
                "empleados_activos": empleados.count(),
                "sin_biometria": empleados.filter(
                    tiene_huella=False, tiene_rostro=False
                ).count(),
                "pendientes_sincronizar": empleados.filter(
                    sincronizado_dispositivo=False
                ).count(),
                "sin_turno": empleados.filter(asignaciones_turno__isnull=True).count(),
            }
        )

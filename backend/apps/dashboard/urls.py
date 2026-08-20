from django.urls import path

from apps.dashboard.views import (
    ComparativoDepartamentoView,
    EstadoSistemaView,
    RankingView,
    ResumenDiaView,
    TendenciaMensualView,
    TendenciaSemanalView,
)

urlpatterns = [
    path("resumen-dia/", ResumenDiaView.as_view(), name="dashboard-resumen-dia"),
    path("tendencia-semanal/", TendenciaSemanalView.as_view(), name="dashboard-semanal"),
    path("tendencia-mensual/", TendenciaMensualView.as_view(), name="dashboard-mensual"),
    path("ranking/", RankingView.as_view(), name="dashboard-ranking"),
    path("comparativo-departamento/", ComparativoDepartamentoView.as_view(),
         name="dashboard-comparativo"),
    path("estado-sistema/", EstadoSistemaView.as_view(), name="dashboard-estado-sistema"),
]

"""Rutas del protocolo ADMS.

Las rutas y sus nombres los impone el firmware del equipo: no se pueden
renombrar ni agrupar bajo /api/. Van sin autenticacion por diseno del
protocolo; la validacion se hace por numero de serie e IP en las vistas.
"""

from django.urls import path, re_path

from apps.devices.adms import views

urlpatterns = [
    path("cdata", views.cdata, name="adms-cdata"),
    path("getrequest", views.getrequest, name="adms-getrequest"),
    path("devicecmd", views.devicecmd, name="adms-devicecmd"),
    path("fdata", views.fdata, name="adms-fdata"),
    path("ping", views.ping, name="adms-ping"),
    # Algunos firmwares agregan la barra final.
    path("cdata/", views.cdata),
    path("getrequest/", views.getrequest),
    path("devicecmd/", views.devicecmd),
    path("fdata/", views.fdata),
    path("ping/", views.ping),
    # Cualquier otra ruta queda registrada para poder implementarla despues.
    re_path(r"^(?P<ruta>.*)$", views.desconocido),
]

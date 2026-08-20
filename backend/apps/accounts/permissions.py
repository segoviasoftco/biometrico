"""Permisos por rol reutilizados en toda la API.

Los tres roles del sistema:
  - Administrador: acceso total, incluida la configuracion y el dispositivo.
  - RRHH: gestiona empleados, horarios, asistencia y reportes.
  - Supervisor: solo consulta, y unicamente sobre su sede.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission


class EsAdministrador(BasePermission):
    """Solo el administrador del sistema."""

    message = "Esta accion requiere permisos de administrador."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.es_administrador)


class EsAdministradorORRHH(BasePermission):
    """Administrador o personal de Recursos Humanos."""

    message = "Esta accion requiere permisos de administrador o de Recursos Humanos."

    def has_permission(self, request, view):
        usuario = request.user
        return bool(
            usuario
            and usuario.is_authenticated
            and (usuario.es_administrador or usuario.es_rrhh)
        )


class LecturaTodosEscrituraRRHH(BasePermission):
    """Cualquier usuario autenticado consulta; solo administrador y RRHH modifican.

    Es el permiso por defecto de los modulos operativos: un supervisor necesita
    ver la asistencia de su gente, pero no cambiarla.
    """

    message = "Solo el administrador o Recursos Humanos pueden modificar esta informacion."

    def has_permission(self, request, view):
        usuario = request.user
        if not (usuario and usuario.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return usuario.es_administrador or usuario.es_rrhh


class FiltradoPorSedeMixin:
    """Restringe el queryset de un supervisor a su sede.

    La ruta hacia la sede cambia segun el modelo, por eso cada vista declara
    `campo_sede` (por ejemplo "sede" o "empleado__sede").
    """

    campo_sede = "sede"

    def filtrar_por_sede(self, queryset):
        usuario = self.request.user
        if usuario.es_supervisor and usuario.sede_id:
            return queryset.filter(**{self.campo_sede: usuario.sede_id})
        return queryset

    def get_queryset(self):
        return self.filtrar_por_sede(super().get_queryset())

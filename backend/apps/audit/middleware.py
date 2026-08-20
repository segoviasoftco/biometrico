"""Middleware y utilidades de auditoria.

El middleware guarda el request en un contexto por hilo para que los servicios y
las vistas puedan registrar quien ejecuto una accion sin tener que pasar el
request por toda la cadena de llamadas.
"""

import threading

_contexto_local = threading.local()


def obtener_request_actual():
    """Devuelve el request en curso, o None si se ejecuta fuera de una peticion.

    Es None, por ejemplo, cuando la accion la dispara una tarea de Celery.
    """
    return getattr(_contexto_local, "request", None)


def obtener_usuario_actual():
    """Devuelve el usuario autenticado del request en curso, o None."""
    request = obtener_request_actual()
    if request is None:
        return None
    usuario = getattr(request, "user", None)
    if usuario is not None and usuario.is_authenticated:
        return usuario
    return None


def obtener_ip(request):
    """Extrae la IP del cliente considerando un posible proxy inverso."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class AuditMiddleware:
    """Expone el request actual al resto de la aplicacion."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _contexto_local.request = request
        try:
            return self.get_response(request)
        finally:
            # Limpiar siempre: los hilos se reutilizan entre peticiones y un
            # request colgado filtraria el usuario a la siguiente.
            _contexto_local.request = None


def registrar_auditoria(
    accion,
    modelo="",
    objeto_id="",
    descripcion="",
    cambios=None,
    usuario=None,
):
    """Crea una entrada de auditoria.

    Se importa el modelo dentro de la funcion para evitar problemas de carga de
    aplicaciones cuando el middleware se inicializa.
    """
    from apps.audit.models import RegistroAuditoria

    request = obtener_request_actual()
    usuario = usuario or obtener_usuario_actual()

    datos = {
        "usuario": usuario,
        "usuario_email": getattr(usuario, "email", "") or "",
        "accion": accion,
        "modelo": modelo,
        "objeto_id": str(objeto_id) if objeto_id else "",
        "descripcion": descripcion[:500],
        "cambios": cambios,
    }

    if request is not None:
        datos.update(
            {
                "ip": obtener_ip(request),
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:300],
                "ruta": request.path[:255],
                "metodo": request.method,
            }
        )

    return RegistroAuditoria.objects.create(**datos)

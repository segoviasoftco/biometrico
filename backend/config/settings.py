"""
Configuracion de Django para el Sistema de Control de Asistencia Biometrico.

La configuracion se lee de variables de entorno (archivo .env) para permitir
que el mismo codigo corra en desarrollo y en produccion on-premise.
"""

from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------
# Seguridad
# --------------------------------------------------------------------------
SECRET_KEY = config("SECRET_KEY", default="django-inseguro-solo-para-desarrollo")
DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

# --------------------------------------------------------------------------
# Aplicaciones
# --------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_filters",
    "django_celery_beat",
    "django_celery_results",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.organization",
    "apps.employees",
    "apps.devices",
    "apps.schedules",
    "apps.attendance",
    "apps.reports",
    "apps.dashboard",
    "apps.audit",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.audit.middleware.AuditMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --------------------------------------------------------------------------
# Base de datos
#
# En produccion on-premise se usa PostgreSQL. En desarrollo se permite SQLite
# para poder trabajar sin instalar el motor, cambiando DB_ENGINE en el .env.
# --------------------------------------------------------------------------
if config("DB_ENGINE", default="sqlite") == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("DB_NAME", default="biometrico"),
            "USER": config("DB_USER", default="postgres"),
            "PASSWORD": config("DB_PASSWORD", default=""),
            "HOST": config("DB_HOST", default="localhost"),
            "PORT": config("DB_PORT", default="5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# --------------------------------------------------------------------------
# Autenticacion
# --------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.Usuario"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------
# Internacionalizacion
# --------------------------------------------------------------------------
LANGUAGE_CODE = "es-pe"
TIME_ZONE = config("TIME_ZONE", default="America/Lima")
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------
# Archivos estaticos y media
# --------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------
# Django REST Framework
# --------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DATETIME_FORMAT": "%Y-%m-%d %H:%M:%S",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=config("JWT_ACCESS_HOURS", default=8, cast=int)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# --------------------------------------------------------------------------
# CORS (el frontend React corre en otro puerto durante el desarrollo)
# --------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:5173,http://127.0.0.1:5173",
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True

# --------------------------------------------------------------------------
# Celery
# --------------------------------------------------------------------------
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = "django-db"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
# Cuando no hay Redis disponible (desarrollo), las tareas se ejecutan en linea.
CELERY_TASK_ALWAYS_EAGER = config("CELERY_TASK_ALWAYS_EAGER", default=False, cast=bool)

# --------------------------------------------------------------------------
# Dispositivo biometrico ZKTeco
# --------------------------------------------------------------------------
ZK_DEVICE_IP = config("ZK_DEVICE_IP", default="192.168.18.202")
ZK_DEVICE_PORT = config("ZK_DEVICE_PORT", default=4370, cast=int)
ZK_DEVICE_TIMEOUT = config("ZK_DEVICE_TIMEOUT", default=10, cast=int)
ZK_DEVICE_PASSWORD = config("ZK_DEVICE_PASSWORD", default=0, cast=int)
ZK_FORCE_UDP = config("ZK_FORCE_UDP", default=False, cast=bool)
# Usuario administrador del equipo: nunca debe ser borrado por una sincronizacion.
ZK_ADMIN_USER_ID = config("ZK_ADMIN_USER_ID", default="6999383")

# --------------------------------------------------------------------------
# Endurecimiento para produccion
#
# Se activa solo con DEBUG=False para no entorpecer el desarrollo local, donde
# no hay certificado y forzar HTTPS impediria trabajar.
#
# El despliegue es on-premise: si la instalacion corre en HTTP dentro de la LAN
# (sin certificado), ponga USAR_HTTPS=False en el .env; de lo contrario las
# cookies seguras y la redireccion dejarian el sistema inaccesible.
# --------------------------------------------------------------------------
if not DEBUG:
    USAR_HTTPS = config("USAR_HTTPS", default=True, cast=bool)

    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_REFERRER_POLICY = "same-origin"

    if USAR_HTTPS:
        SECURE_SSL_REDIRECT = True
        SESSION_COOKIE_SECURE = True
        CSRF_COOKIE_SECURE = True
        SECURE_HSTS_SECONDS = 31536000  # un ano
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True
        SECURE_HSTS_PRELOAD = True
        # Necesario cuando Nginx termina el TLS y pasa la peticion por HTTP.
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "biometrico.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "loggers": {
        "apps": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
    },
}

# Directorios que deben existir para que el logging y los media funcionen.
for _directory in (BASE_DIR / "logs", BASE_DIR / "media"):
    _directory.mkdir(parents=True, exist_ok=True)

"""Configuracion de Celery para tareas asincronas y programadas."""

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("biometrico")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    # Descarga las marcaciones nuevas del dispositivo de forma periodica.
    "sincronizar-marcaciones": {
        "task": "apps.devices.tasks.sincronizar_marcaciones_task",
        "schedule": crontab(minute="*/15"),
    },
    # Recalcula la asistencia del dia anterior de madrugada, cuando ya
    # estan todas las marcaciones (incluidas las de turnos nocturnos).
    "procesar-asistencia-diaria": {
        "task": "apps.attendance.tasks.procesar_asistencia_dia_anterior_task",
        "schedule": crontab(hour=3, minute=0),
    },
}

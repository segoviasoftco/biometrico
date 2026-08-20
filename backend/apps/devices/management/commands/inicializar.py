"""Carga los datos minimos para que el sistema quede operativo.

Es idempotente: se puede volver a ejecutar sin duplicar nada, lo que permite
usarlo tanto en una instalacion nueva como para reparar datos base faltantes.
"""

from datetime import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Usuario
from apps.devices.models import Dispositivo
from apps.organization.models import Cargo, Departamento, Sede
from apps.schedules.models import DiaLaborableConfig, DiaSemana, Horario, Turno, TurnoDetalle


class Command(BaseCommand):
    help = "Crea el dispositivo, el administrador y los catalogos iniciales."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email", default="admin@biometrico.local", help="Email del administrador."
        )
        parser.add_argument(
            "--password", default="Admin2025!", help="Clave inicial del administrador."
        )
        parser.add_argument("--ip", default=settings.ZK_DEVICE_IP, help="IP del dispositivo.")

    @transaction.atomic
    def handle(self, *args, **opciones):
        self._crear_administrador(opciones["email"], opciones["password"])
        self._crear_dispositivo(opciones["ip"])
        self._crear_organizacion()
        self._crear_horarios_y_turnos()
        DiaLaborableConfig.obtener()

        self.stdout.write(self.style.SUCCESS("\nInicializacion completada."))
        self.stdout.write(
            f"  Ingrese con: {opciones['email']} / {opciones['password']}\n"
            "  Cambie esta clave despues del primer ingreso."
        )

    # ------------------------------------------------------------------
    def _crear_administrador(self, email, password):
        if Usuario.objects.filter(email=email).exists():
            self.stdout.write(f"  El administrador {email} ya existe.")
            return

        Usuario.objects.create_superuser(
            email=email,
            password=password,
            nombres="Administrador",
            apellidos="del Sistema",
            rol=Usuario.Rol.ADMINISTRADOR,
        )
        self.stdout.write(self.style.SUCCESS(f"  Administrador creado: {email}"))

    def _crear_dispositivo(self, ip):
        dispositivo, creado = Dispositivo.objects.get_or_create(
            ip=ip,
            puerto=settings.ZK_DEVICE_PORT,
            defaults={
                "nombre": "ZKTeco MB560-VL",
                "modelo": "MB560-VL",
                "timeout": settings.ZK_DEVICE_TIMEOUT,
                "password_comunicacion": settings.ZK_DEVICE_PASSWORD,
                "force_udp": settings.ZK_FORCE_UDP,
                "admin_user_id": settings.ZK_ADMIN_USER_ID,
                "ubicacion": "Ingreso principal",
            },
        )
        estado = "creado" if creado else "ya existia"
        self.stdout.write(
            self.style.SUCCESS(f"  Dispositivo {estado}: {dispositivo.ip}:{dispositivo.puerto}")
        )
        self.stdout.write(f"  Administrador del equipo protegido: {dispositivo.admin_user_id}")

    def _crear_organizacion(self):
        sede, _ = Sede.objects.get_or_create(
            codigo="PRIN", defaults={"nombre": "Sede Principal"}
        )
        Departamento.objects.get_or_create(
            sede=sede, codigo="ADM", defaults={"nombre": "Administracion"}
        )
        Departamento.objects.get_or_create(
            sede=sede, codigo="OPE", defaults={"nombre": "Operaciones"}
        )
        for nombre in ("Administrador", "Asistente", "Operario", "Supervisor"):
            Cargo.objects.get_or_create(nombre=nombre)
        self.stdout.write(self.style.SUCCESS("  Estructura organizacional base creada."))

    def _crear_horarios_y_turnos(self):
        horario, _ = Horario.objects.get_or_create(
            nombre="Administrativo (08:00 - 17:00)",
            defaults={
                "hora_entrada": time(8, 0),
                "hora_salida": time(17, 0),
                "tolerancia_entrada": 5,
                "tolerancia_salida": 5,
                "tiene_refrigerio": True,
                "hora_inicio_refrigerio": time(13, 0),
                "hora_fin_refrigerio": time(14, 0),
                "minutos_falta": 120,
            },
        )

        turno, creado = Turno.objects.get_or_create(
            nombre="Lunes a Viernes", defaults={"tipo": Turno.Tipo.FIJO}
        )
        if creado:
            for dia in (
                DiaSemana.LUNES,
                DiaSemana.MARTES,
                DiaSemana.MIERCOLES,
                DiaSemana.JUEVES,
                DiaSemana.VIERNES,
            ):
                TurnoDetalle.objects.create(turno=turno, dia_semana=dia, horario=horario)
            # Sabado y domingo quedan como descanso.
            for dia in (DiaSemana.SABADO, DiaSemana.DOMINGO):
                TurnoDetalle.objects.create(turno=turno, dia_semana=dia, horario=None)

        self.stdout.write(self.style.SUCCESS("  Horario y turno base creados."))

"""Usuarios del sistema web y sus roles.

Nota: estos son los usuarios que inician sesion en la aplicacion (administrador,
RRHH, supervisor). No confundir con los empleados que marcan asistencia en el
dispositivo biometrico, que viven en la app `employees`.
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UsuarioManager(BaseUserManager):
    """Manager que usa el email como identificador en lugar del username."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("El email es obligatorio")
        email = self.normalize_email(email)
        usuario = self.model(email=email, **extra_fields)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("rol", Usuario.Rol.ADMINISTRADOR)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("El superusuario debe tener is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("El superusuario debe tener is_superuser=True")

        return self._create_user(email, password, **extra_fields)


class Usuario(AbstractUser):
    """Usuario del sistema web, identificado por email."""

    class Rol(models.TextChoices):
        ADMINISTRADOR = "administrador", "Administrador"
        RRHH = "rrhh", "Recursos Humanos"
        SUPERVISOR = "supervisor", "Supervisor"

    username = None
    email = models.EmailField("correo electronico", unique=True)
    nombres = models.CharField("nombres", max_length=100)
    apellidos = models.CharField("apellidos", max_length=100)
    rol = models.CharField("rol", max_length=20, choices=Rol.choices, default=Rol.SUPERVISOR)
    telefono = models.CharField("telefono", max_length=20, blank=True)

    # El supervisor solo ve la informacion de su sede; queda nulo para los
    # roles que tienen alcance sobre toda la organizacion.
    sede = models.ForeignKey(
        "organization.Sede",
        verbose_name="sede asignada",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usuarios",
        help_text="Limita el alcance de los datos que puede ver un supervisor.",
    )

    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nombres", "apellidos"]

    objects = UsuarioManager()

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["apellidos", "nombres"]

    def __str__(self):
        return f"{self.nombre_completo} ({self.email})"

    @property
    def nombre_completo(self):
        return f"{self.nombres} {self.apellidos}".strip()

    @property
    def es_administrador(self):
        return self.rol == self.Rol.ADMINISTRADOR or self.is_superuser

    @property
    def es_rrhh(self):
        return self.rol == self.Rol.RRHH

    @property
    def es_supervisor(self):
        return self.rol == self.Rol.SUPERVISOR

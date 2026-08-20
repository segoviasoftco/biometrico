"""Estructura organizacional: sedes, departamentos, areas y cargos.

Sirve para agrupar empleados y para segmentar los reportes y el dashboard.
"""

from django.db import models


class ModeloBase(models.Model):
    """Campos comunes de auditoria ligera para los catalogos."""

    activo = models.BooleanField("activo", default=True)
    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        abstract = True


class Sede(ModeloBase):
    """Local o establecimiento donde trabajan los empleados."""

    nombre = models.CharField("nombre", max_length=100, unique=True)
    codigo = models.CharField("codigo", max_length=20, unique=True)
    direccion = models.CharField("direccion", max_length=255, blank=True)
    telefono = models.CharField("telefono", max_length=20, blank=True)

    class Meta:
        verbose_name = "sede"
        verbose_name_plural = "sedes"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Departamento(ModeloBase):
    """Departamento perteneciente a una sede."""

    nombre = models.CharField("nombre", max_length=100)
    codigo = models.CharField("codigo", max_length=20)
    sede = models.ForeignKey(
        Sede, verbose_name="sede", on_delete=models.PROTECT, related_name="departamentos"
    )
    descripcion = models.CharField("descripcion", max_length=255, blank=True)

    class Meta:
        verbose_name = "departamento"
        verbose_name_plural = "departamentos"
        ordering = ["sede__nombre", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["sede", "codigo"], name="departamento_codigo_unico_por_sede"
            )
        ]

    def __str__(self):
        return f"{self.nombre} - {self.sede.nombre}"


class Area(ModeloBase):
    """Area dentro de un departamento."""

    nombre = models.CharField("nombre", max_length=100)
    codigo = models.CharField("codigo", max_length=20)
    departamento = models.ForeignKey(
        Departamento,
        verbose_name="departamento",
        on_delete=models.PROTECT,
        related_name="areas",
    )

    class Meta:
        verbose_name = "area"
        verbose_name_plural = "areas"
        ordering = ["departamento__nombre", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["departamento", "codigo"], name="area_codigo_unico_por_departamento"
            )
        ]

    def __str__(self):
        return f"{self.nombre} - {self.departamento.nombre}"


class Cargo(ModeloBase):
    """Puesto que ocupa un empleado."""

    nombre = models.CharField("nombre", max_length=100, unique=True)
    descripcion = models.CharField("descripcion", max_length=255, blank=True)

    class Meta:
        verbose_name = "cargo"
        verbose_name_plural = "cargos"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

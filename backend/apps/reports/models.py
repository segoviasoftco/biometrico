"""Historial de reportes generados."""

from django.conf import settings
from django.db import models


class ReporteGenerado(models.Model):
    """Archivo de reporte producido por el sistema.

    Se conserva el historial para poder volver a descargar el mismo archivo que
    se entrego a planilla, sin regenerarlo (los datos podrian haber cambiado por
    un ajuste posterior).
    """

    class Tipo(models.TextChoices):
        TARDANZAS = "tardanzas", "Reporte de tardanzas"
        FALTAS = "faltas", "Reporte de faltas"
        DESCUENTOS = "descuentos", "Reporte de descuentos"
        MARCACIONES = "marcaciones", "Reporte de marcaciones"
        HORAS_TRABAJADAS = "horas_trabajadas", "Reporte de horas trabajadas"
        ASISTENCIA_GENERAL = "asistencia_general", "Reporte general de asistencia"

    class Formato(models.TextChoices):
        EXCEL = "excel", "Excel"
        PDF = "pdf", "PDF"

    tipo = models.CharField("tipo", max_length=30, choices=Tipo.choices)
    formato = models.CharField(
        "formato", max_length=10, choices=Formato.choices, default=Formato.EXCEL
    )
    fecha_inicio = models.DateField("desde")
    fecha_fin = models.DateField("hasta")
    filtros = models.JSONField(
        "filtros aplicados",
        null=True,
        blank=True,
        help_text="Sede, departamento, empleados y demas criterios usados.",
    )
    archivo = models.FileField("archivo", upload_to="reportes/%Y/%m/")
    total_registros = models.IntegerField("total de registros", default=0)

    generado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="generado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reportes_generados",
    )
    generado_en = models.DateTimeField("generado en", auto_now_add=True)

    class Meta:
        verbose_name = "reporte generado"
        verbose_name_plural = "reportes generados"
        ordering = ["-generado_en"]
        indexes = [models.Index(fields=["-generado_en"]), models.Index(fields=["tipo"])]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.fecha_inicio} a {self.fecha_fin}"

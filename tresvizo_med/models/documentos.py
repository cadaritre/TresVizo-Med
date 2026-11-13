from django.db import models

from .base import Auditado
from .clinico import BorradorAlta, Consulta, Paciente


class Documento(Auditado):
    paciente = models.ForeignKey(Paciente, on_delete=models.PROTECT, null=True, blank=True, related_name="documentos")
    consulta = models.ForeignKey(Consulta, on_delete=models.PROTECT, null=True, blank=True, related_name="documentos")
    borrador = models.ForeignKey(BorradorAlta, on_delete=models.PROTECT, null=True, blank=True, related_name="documentos")
    doctor_id = models.BigIntegerField()
    categoria = models.CharField(max_length=60)
    mime = models.CharField(max_length=120)
    tamano = models.BigIntegerField()
    sha256 = models.CharField(max_length=64)
    version_de = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="versiones")
    archivado = models.BooleanField(default=False)
    titulo = models.CharField(max_length=300)
    descripcion = models.TextField(blank=True)
    fecha_documento = models.DateField(null=True, blank=True)
    origen = models.CharField(max_length=60, default="Archivo local")
    nombre_original = models.CharField(max_length=300)
    ruta = models.CharField(max_length=300)  # relativa a TV_MED_ARCHIVOS
    historial = models.JSONField(default=list, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(paciente__isnull=False, borrador__isnull=True)
                           | models.Q(paciente__isnull=True, borrador__isnull=False)),
                name="med_documento_un_destino"),
        ]
        indexes = [models.Index(fields=["paciente", "-created_at"], name="med_documento_paciente"),
                   models.Index(fields=["sha256"], name="med_documento_sha")]


class ColaDocumentos(models.Model):
    """Archivos elegidos y aún no incorporados, por profesional y destino (reemplaza ``attachment_queues``)."""

    profesional_id = models.BigIntegerField()
    destino = models.CharField(max_length=130)  # «paciente:uuid|consulta:uuid|borrador:uuid»
    filas = models.JSONField(default=list)
    ediciones = models.JSONField(default=dict, blank=True)  # metadatos pendientes (document_edits)
    actualizado = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["profesional_id", "destino"], name="med_cola_unica")]

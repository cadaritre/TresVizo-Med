import uuid

from django.db import models

from .clinico import Paciente


class LoteImportacion(models.Model):
    class Tipo(models.TextChoices):
        CSV = "csv"
        ESCRITORIO = "escritorio"

    class Estado(models.TextChoices):
        ENSAYO = "ensayo"
        CONFIRMADO = "confirmado"
        FALLIDO = "fallido"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    sha256 = models.CharField(max_length=64, blank=True)  # del ZIP; vacío en los lotes de CSV
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.ENSAYO)
    actor_id = models.BigIntegerField()
    momento = models.DateTimeField()
    conteos = models.JSONField(default=dict, blank=True)
    recibo = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tipo", "sha256"], condition=~models.Q(sha256=""),
                                               name="med_lote_zip_unico")]


class HistoricoCita(models.Model):
    """Agenda del escritorio 1.0.0, importada como histórico de solo lectura (no se reactiva)."""

    id = models.UUIDField(primary_key=True)
    paciente = models.ForeignKey(Paciente, on_delete=models.PROTECT, related_name="citas_anteriores")
    consulta_id = models.UUIDField(null=True, blank=True)
    datos = models.JSONField()
    lote = models.ForeignKey(LoteImportacion, on_delete=models.PROTECT, null=True)


class HistoricoSeguimiento(models.Model):
    id = models.UUIDField(primary_key=True)
    paciente = models.ForeignKey(Paciente, on_delete=models.PROTECT, related_name="seguimientos_anteriores")
    consulta_id = models.UUIDField(null=True, blank=True)
    datos = models.JSONField()
    lote = models.ForeignKey(LoteImportacion, on_delete=models.PROTECT, null=True)

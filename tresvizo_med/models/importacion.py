import uuid

from django.db import models


class LoteImportacion(models.Model):
    """Lote de importación de pacientes desde CSV: la vista previa, el recibo y la idempotencia de la confirmación."""

    class Tipo(models.TextChoices):
        CSV = "csv"

    class Estado(models.TextChoices):
        ENSAYO = "ensayo"
        CONFIRMADO = "confirmado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.ENSAYO)
    actor_id = models.BigIntegerField()
    momento = models.DateTimeField()
    conteos = models.JSONField(default=dict, blank=True)
    recibo = models.JSONField(default=dict, blank=True)

import uuid

from django.db import models


class Auditado(models.Model):
    """Convenciones de med-web.md §4: UUID, revisión optimista, autoría por ``cuenta_id`` (sin clave foránea)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField()
    created_by = models.BigIntegerField(null=True)
    updated_at = models.DateTimeField()
    updated_by = models.BigIntegerField(null=True)

    class Meta:
        abstract = True

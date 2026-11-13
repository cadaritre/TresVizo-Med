import uuid

from django.db import models
from django.db.models.functions import Lower


class CatalogoMedicamento(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    producto = models.CharField(max_length=300)
    principio_activo = models.CharField(max_length=300, blank=True)
    presentacion = models.CharField(max_length=300, blank=True)
    concentracion = models.CharField(max_length=300, blank=True)

    class Meta:
        indexes = [models.Index(fields=["producto"], name="med_catalogo_producto")]


class Favorito(models.Model):
    medicamento = models.ForeignKey(CatalogoMedicamento, on_delete=models.CASCADE, related_name="favoritos")
    cuenta_id = models.BigIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["medicamento", "cuenta_id"], name="med_favorito_unico")]


class Tema(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dueno_id = models.BigIntegerField()
    nombre = models.CharField(max_length=80)
    tokens = models.JSONField()  # los 19 tokens del escritorio

    class Meta:
        constraints = [models.UniqueConstraint(Lower("nombre"), name="med_tema_nombre_unico")]

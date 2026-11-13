from django.contrib.postgres.indexes import GinIndex
from django.db import models

from .base import Auditado


class Paciente(Auditado):
    folio = models.CharField(max_length=20, unique=True)  # RC-000001
    nombre = models.CharField(max_length=300)
    nombre_norm = models.CharField(max_length=300)  # para ordenar
    busqueda = models.TextField()  # nombre, nombre preferido, folio y teléfono normalizados
    nacimiento = models.DateField(null=True, blank=True)
    edad_aproximada = models.JSONField(default=dict, blank=True)
    sexo = models.CharField(max_length=40, blank=True)
    telefono = models.CharField(max_length=60, blank=True)
    datos = models.JSONField(default=dict, blank=True)  # contactos, responsables, alergias, problemas, legacy…
    foto_documento = models.UUIDField(null=True, blank=True)
    archivado = models.BooleanField(default=False)
    lifecycle = models.JSONField(default=list, blank=True)

    class Meta:
        indexes = [
            GinIndex(fields=["busqueda"], name="med_paciente_busqueda_trgm", opclasses=["gin_trgm_ops"]),
            models.Index(fields=["nombre_norm", "folio"], name="med_paciente_orden"),
        ]


class Consulta(Auditado):
    class Estado(models.TextChoices):
        BORRADOR = "Borrador"
        FINALIZADA = "Finalizada"
        ANULADA = "Anulada"

    paciente = models.ForeignKey(Paciente, on_delete=models.PROTECT, related_name="consultas")
    doctor_id = models.BigIntegerField()
    captured_by = models.BigIntegerField()
    estado = models.CharField(max_length=12, choices=Estado.choices)
    archivada = models.BooleanField(default=False)
    atendida_iso = models.CharField(max_length=40)  # texto original con su desplazamiento
    atendida_en = models.DateTimeField()
    tipo = models.CharField(max_length=80, blank=True)
    motivo = models.TextField(blank=True)
    diagnostico = models.TextField(blank=True)
    plan = models.TextField(blank=True)
    contenido = models.JSONField(default=dict, blank=True)  # subjetivo, objetivo, signos, recetas, estudios, legacy…
    editor_state = models.JSONField(default=dict, blank=True)
    lifecycle = models.JSONField(default=list, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["paciente", "atendida_en"], name="med_consulta_paciente"),
            models.Index(fields=["doctor_id", "estado"], name="med_consulta_doctor"),
            models.Index(fields=["atendida_en"], name="med_consulta_fecha"),
        ]


class SoloInsercion(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionError("Las adendas solo se agregan.")

    def delete(self):
        raise PermissionError("Las adendas solo se agregan.")


class Adenda(models.Model):
    """Solo se inserta: no hay edición ni borrado, ni desde el ORM ni desde la base (disparador en la migración)."""

    class Tipo(models.TextChoices):
        ADENDA = "adenda"
        ANULACION = "anulacion"
        RESTAURACION = "restauracion"

    id = models.UUIDField(primary_key=True)
    consulta = models.ForeignKey(Consulta, on_delete=models.PROTECT, related_name="adendas")
    autor_id = models.BigIntegerField()
    momento = models.DateTimeField()
    tipo = models.CharField(max_length=14, choices=Tipo.choices, default=Tipo.ADENDA)
    motivo = models.TextField()
    contenido = models.TextField()
    documento_id = models.UUIDField(null=True, blank=True)

    objects = SoloInsercion.as_manager()

    class Meta:
        ordering = ["momento", "id"]
        indexes = [models.Index(fields=["consulta", "momento"], name="med_adenda_consulta")]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("Las adendas solo se agregan.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Las adendas solo se agregan.")


class BorradorAlta(Auditado):
    class Estado(models.TextChoices):
        BORRADOR = "Borrador"
        REGISTRADO = "Registrado"
        DESCARTADO = "Descartado"

    profesional_id = models.BigIntegerField()
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.BORRADOR)
    paciente = models.UUIDField(null=True, blank=True)  # paciente existente que se edita
    objetivo = models.UUIDField(null=True, blank=True)  # identificador del paciente que se creará (idempotencia)
    revision_origen = models.PositiveIntegerField(null=True, blank=True)
    contenido = models.JSONField(default=dict)

    class Meta:
        indexes = [models.Index(fields=["profesional_id", "estado"], name="med_borradoralta_dueno")]

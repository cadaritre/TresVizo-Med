from django.db import models

from ..dominio.themes import DEFAULT_IDENTITY
from .base import Auditado


class Clinica(Auditado):
    """Una sola fila (``id`` fijo): identidad de la clínica, preferencias de documentos y tema general."""

    ID = "00000000-0000-0000-0000-000000000001"

    identidad = models.JSONField(default=dict)  # mismo esquema que config/identity.json del escritorio
    logo_ruta = models.CharField(max_length=300, blank=True)  # relativa a TV_MED_ARCHIVOS
    icono_ruta = models.CharField(max_length=300, blank=True)
    tema_clinica = models.CharField(max_length=64, default="Clínico")  # nombre de fábrica o uuid de Tema
    configurada = models.BooleanField(default=False)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id="00000000-0000-0000-0000-000000000001"),
                                              name="med_clinica_una_fila")]

    @classmethod
    def obtener(cls):
        from django.utils import timezone
        ahora = timezone.now()
        fila, _ = cls.objects.get_or_create(
            id=cls.ID, defaults={"identidad": dict(DEFAULT_IDENTITY), "created_at": ahora, "updated_at": ahora})
        return fila

    def valores(self):
        return {**DEFAULT_IDENTITY, **self.identidad}


class Profesional(models.Model):
    cuenta_id = models.BigIntegerField(unique=True)
    nombre_visible = models.CharField(max_length=120, blank=True)
    cedula = models.CharField(max_length=60, blank=True)
    especialidad = models.CharField(max_length=120, blank=True)
    avatar = models.CharField(max_length=60, blank=True)  # nombre de avatar de fábrica o vacío (iniciales)
    foto_ruta = models.CharField(max_length=300, blank=True)
    tema = models.CharField(max_length=64, blank=True)  # tema propio; vacío = el de la clínica
    hereda_tema = models.BooleanField(default=True)
    reducir_movimiento = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    extra = models.JSONField(default=dict, blank=True)  # perfil del escritorio sin columna propia

    @classmethod
    def para(cls, cuenta_id):
        fila, _ = cls.objects.get_or_create(cuenta_id=int(cuenta_id))
        return fila

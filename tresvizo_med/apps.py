from django.apps import AppConfig


class MedConfig(AppConfig):
    name = "tresvizo_med"
    label = "med"
    verbose_name = "TresVizo Med"
    default_auto_field = "django.db.models.BigAutoField"
    tv_modulo = "tresvizo_med.modulo.MODULO"

    def ready(self):
        from . import subidas  # noqa: F401  (registra el destino «med.documento»)

"""Declaración del módulo y de los roles de Med (contrato tvplataforma §3.2)."""
from tvplataforma.modulos import Modulo, Rol

MODULO = Modulo(
    clave="med",
    nombre="TresVizo Med",
    host="med.tresvizo.com",      # el módulo vive en la raíz de su host
    urlconf="tresvizo_med.urls",  # sus URLs, activas solo para ese host
    icono="med/icono.svg",
    orden=10,
    roles=[
        Rol("admin", "Administrador de la clínica"),
        Rol("medico", "Médico"),
    ],
)

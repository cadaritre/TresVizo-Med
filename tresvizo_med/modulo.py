"""Declaración del módulo y de los roles de Med (contrato tvplataforma §3.2)."""
from tvplataforma.modulos import Modulo, Rol

MODULO = Modulo(
    clave="med",
    nombre="TresVizo Med",
    url="/med/",
    icono="med/icono.svg",
    orden=10,
    roles=[
        Rol("admin", "Administrador de la clínica"),
        Rol("medico", "Médico"),
    ],
)

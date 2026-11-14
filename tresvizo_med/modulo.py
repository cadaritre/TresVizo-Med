"""Declaración del módulo y de los roles de Med (contrato tvplataforma §3.2)."""
from tvplataforma.modulos import Modulo, Rol

MODULO = Modulo(
    clave="med",
    nombre="TresVizo Med",
    host="med.tresvizo.com",      # el módulo vive en la raíz de su host
    urlconf="tresvizo_med.urls",  # sus URLs, activas solo para ese host
    icono="med/img/modulo.png",
    orden=10,
    limpiezas=("tresvizo_med.limpieza.subidas_huerfanas", "tresvizo_med.limpieza.temporales"),
    roles=[
        Rol("admin", "Administrador de la clínica"),
        Rol("medico", "Médico"),
    ],
)

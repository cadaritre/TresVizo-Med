"""Servicios de Med: las reglas del escritorio (``Clinic``, ``Care``, ``Attachments``, ``Appearance``) sobre PostgreSQL.

Las vistas no escriben modelos directamente: llaman a estos módulos con un :class:`Actor`.
"""
from .actor import Actor  # noqa: F401
from .errores import ErrorServicio, NoEncontrado, PermisoDenegado, VersionConflict  # noqa: F401

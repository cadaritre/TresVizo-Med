"""Errores de los servicios. Las vistas los traducen: ``PermisoDenegado`` → 403, ``NoEncontrado`` → 404."""
from ..dominio.editing_state import VersionConflict  # noqa: F401
from ..dominio.errores import DataError


class ErrorServicio(DataError):
    pass


class PermisoDenegado(ErrorServicio):
    """La persona tiene Med pero no el rol que pide la acción (403)."""


class NoEncontrado(ErrorServicio):
    """El registro no existe o no es visible para la persona, p. ej. un borrador ajeno (404)."""

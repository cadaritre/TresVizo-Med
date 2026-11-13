"""Quién actúa: la cuenta del portal y sus roles de Med (``tvplataforma.permisos``)."""
from dataclasses import dataclass

from tvplataforma.permisos import tiene_rol

from .errores import NoEncontrado, PermisoDenegado


@dataclass(frozen=True)
class Actor:
    cuenta_id: int
    es_admin: bool
    es_medico: bool

    @classmethod
    def de(cls, usuario):
        """Sin sesión activa o sin ningún rol de Med: 404, igual que el armazón (la existencia no se revela)."""
        if usuario is None or not getattr(usuario, "is_authenticated", False) or not usuario.is_active:
            raise NoEncontrado("No disponible.")
        actor = cls(int(usuario.pk), tiene_rol(usuario, "med", "admin"), tiene_rol(usuario, "med", "medico"))
        if not (actor.es_admin or actor.es_medico):
            raise NoEncontrado("No disponible.")
        return actor

    def exigir_medico(self):
        if not self.es_medico:
            raise PermisoDenegado("Esta acción es para médicos.")
        return self

    def exigir_admin(self):
        if not self.es_admin:
            raise PermisoDenegado("Esta acción es del administrador de la clínica.")
        return self

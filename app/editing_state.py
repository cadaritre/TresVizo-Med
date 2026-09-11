"""Conflictos explícitos entre base guardada, captura local y versión durable."""
from copy import deepcopy
from app.storage import DataError


class VersionConflict(DataError):
    def __init__(self, current):
        super().__init__('El registro cambió en otra edición. Tu captura se conserva; revisa las diferencias antes de guardar.')
        self.current = deepcopy(current)


SYSTEM_FIELDS = {'revision', 'updated_at', 'updated_by', 'created_at', 'created_by', 'id', 'doctor_id', 'captured_by', 'schema_version'}


def merge_draft(base, local, remote):
    """Devuelve cambios no conflictivos y campos que requieren decisión humana."""
    merged, conflicts = deepcopy(remote), {}
    missing = object()
    for key in (base.keys() | local.keys() | remote.keys()) - SYSTEM_FIELDS:
        before, mine, theirs = base.get(key, missing), local.get(key, missing), remote.get(key, missing)
        if mine == before:
            continue
        if theirs != before and mine != theirs:
            conflicts[key] = {'local': deepcopy(local.get(key)), 'remote': deepcopy(remote.get(key))}
        elif mine is missing:
            merged.pop(key, None)
        else:
            merged[key] = deepcopy(mine)
    return merged, conflicts

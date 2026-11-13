#!/bin/sh
# Corre las pruebas de punta a punta o la de carga con el turno de la Mac (Playwright y cargas pesadas no corren a la vez
# con otros agentes) y un PostgreSQL desechable. Uso: e2e/ejecutar.sh e2e [argumentos de pytest]
set -eu
RAIZ=$(cd "$(dirname "$0")/.." && pwd)
LOCKS="${TV_LOCK_DIR:-/private/tmp/claude-501/-Users-cadaritre-Documents-TresVizo-RTK/8a244be0-6ace-482d-b2eb-4262d0c25e44/scratchpad/locks}"
PG_SCRIPT="${TV_PG_SCRIPT:-$RAIZ/../TresVizo-Portal/plataforma/tvplataforma/scripts/pg_pruebas.sh}"
TRABAJO=$(mktemp -d "${TMPDIR:-/tmp}/med-e2e.XXXXXX")
mkdir -p "$LOCKS"
while [ -n "$(ls -A "$LOCKS" 2>/dev/null)" ]; do sleep 5; done
mkdir "$LOCKS/native"
limpiar() { sh "$PG_SCRIPT" detener "$TRABAJO/pg" >/dev/null 2>&1 || true; rmdir "$LOCKS/native" 2>/dev/null || true; rm -rf "$TRABAJO"; }
trap limpiar EXIT INT TERM
sh "$PG_SCRIPT" iniciar "$TRABAJO/pg" > "$TRABAJO/env.sh" </dev/null
. "$TRABAJO/env.sh"
cd "$RAIZ"
"$RAIZ/.venv/bin/python" -m pytest "$@"

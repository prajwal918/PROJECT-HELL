#!/usr/bin/env sh
set -eu

PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
  exec "$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/jogiapp.py" --open
fi

exec python3 "$PROJECT_ROOT/jogiapp.py" --open

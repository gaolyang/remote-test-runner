#!/usr/bin/env sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$PROJECT_DIR"
exec python -m uvicorn backend.main:app --host "${RTR_HOST:-127.0.0.1}" --port "${RTR_PORT:-8000}"

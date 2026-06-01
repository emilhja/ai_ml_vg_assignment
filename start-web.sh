#!/usr/bin/env bash
# Start VG Agent trace dashboard: API (repo root) + Vite dev server.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

SKIP_INSTALL=0
API_PORT="${VG_DASHBOARD_PORT:-8787}"

usage() {
  echo "Usage: ./start-web.sh [--no-install] [--api-port PORT]" >&2
  echo "  Starts uvicorn from repo root and Vite in dashboard/web." >&2
  echo "  Open http://127.0.0.1:5173 (API on port ${API_PORT})." >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-install)
      SKIP_INSTALL=1
      shift
      ;;
    --api-port)
      if [[ $# -lt 2 ]]; then
        echo "error: --api-port requires a value" >&2
        exit 1
      fi
      API_PORT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

export VG_WORKSPACE_ROOT="${VG_WORKSPACE_ROOT:-workspace}"
export VG_DASHBOARD_PORT="$API_PORT"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "error: '$1' is required but not on PATH" >&2
    exit 1
  fi
}

require_cmd uv
require_cmd npm

if [[ "$SKIP_INSTALL" -eq 0 ]] && [[ ! -d "$ROOT_DIR/dashboard/web/node_modules" ]]; then
  echo "Installing dashboard/web npm dependencies..."
  (cd "$ROOT_DIR/dashboard/web" && npm install)
fi

API_PID=""
API_PGID=""

cleanup() {
  local pid="${API_PID:-}"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    if [[ -n "${API_PGID:-}" ]]; then
      kill -TERM -- "-${API_PGID}" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    else
      kill -TERM "$pid" 2>/dev/null || true
    fi
    wait "$pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "VG Agent dashboard"
echo "  repo root: $ROOT_DIR"
echo "  workspace: $VG_WORKSPACE_ROOT"
echo "  API:       http://127.0.0.1:${API_PORT}/api/v1/health"
echo "  UI:        http://127.0.0.1:5173"
echo ""
echo "Starting API (background)..."

if command -v setsid >/dev/null 2>&1; then
  setsid uv run uvicorn dashboard.api.main:app \
    --host 127.0.0.1 \
    --port "$API_PORT" \
    --reload \
    >/tmp/vg-agent-dashboard-api.log 2>&1 &
  API_PID=$!
  API_PGID=$API_PID
else
  uv run uvicorn dashboard.api.main:app \
    --host 127.0.0.1 \
    --port "$API_PORT" \
    --reload \
    >/tmp/vg-agent-dashboard-api.log 2>&1 &
  API_PID=$!
fi

health_url="http://127.0.0.1:${API_PORT}/api/v1/health"
ready=0
if command -v curl >/dev/null 2>&1; then
  for _ in $(seq 1 30); do
    if curl -sf "$health_url" >/dev/null 2>&1; then
      ready=1
      break
    fi
    if ! kill -0 "$API_PID" 2>/dev/null; then
      echo "error: API process exited; log:" >&2
      tail -n 20 /tmp/vg-agent-dashboard-api.log >&2 || true
      exit 1
    fi
    sleep 0.5
  done
else
  echo "warning: curl not found; waiting 3s for API startup..." >&2
  sleep 3
  ready=1
fi

if [[ "$ready" -eq 1 ]] && command -v curl >/dev/null 2>&1; then
  health_json="$(curl -sf "$health_url" || true)"
  if [[ "$health_json" == *'"traces_dirs":[]'* ]] || [[ "$health_json" == *'"traces_dirs": []'* ]]; then
    echo "warning: API reports no trace directories (History will be empty)." >&2
    echo "  Ensure uvicorn runs from repo root (this script does that)." >&2
    echo "  Log: /tmp/vg-agent-dashboard-api.log" >&2
  fi
fi

echo "API ready (pid $API_PID). Starting Vite (foreground; Ctrl+C stops both)..."
echo ""

cd "$ROOT_DIR/dashboard/web"
exec npm run dev

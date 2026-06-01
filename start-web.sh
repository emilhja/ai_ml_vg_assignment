#!/usr/bin/env bash
# Start VG Agent trace dashboard: API (repo root) + Vite dev server.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

SKIP_INSTALL=0
API_PORT="${VG_DASHBOARD_PORT:-8787}"
VITE_PORT="${VG_DASHBOARD_VITE_PORT:-5173}"

is_windows() {
  case "$(uname -s 2>/dev/null)" in
    MINGW* | MSYS* | CYGWIN*) return 0 ;;
    *) return 1 ;;
  esac
}

api_log_file() {
  if [[ -n "${TMPDIR:-}" ]]; then
    printf '%s/vg-agent-dashboard-api.log' "${TMPDIR%/}"
  elif [[ -n "${TEMP:-}" ]]; then
    printf '%s/vg-agent-dashboard-api.log' "${TEMP%/}"
  else
    echo "/tmp/vg-agent-dashboard-api.log"
  fi
}

# Free a TCP port before start / after stop (orphaned uvicorn --reload is common on Git Bash).
free_port() {
  local port="$1"
  local label="${2:-port ${port}}"
  local killed=0

  if is_windows; then
    local line pid
    while IFS= read -r line; do
      [[ "$line" == *LISTENING* ]] || continue
      pid="${line##* }"
      [[ "$pid" =~ ^[0-9]+$ ]] || continue
      [[ "$pid" -eq 0 ]] && continue
      if taskkill //F //PID "$pid" >/dev/null 2>&1; then
        killed=1
      fi
    done < <(netstat -ano 2>/dev/null | grep -E "[:\.]${port}[[:space:]]" || true)
  elif command -v fuser >/dev/null 2>&1; then
    if fuser -k "${port}/tcp" >/dev/null 2>&1; then
      killed=1
    fi
  elif command -v lsof >/dev/null 2>&1; then
    local pid
    while IFS= read -r pid; do
      [[ "$pid" =~ ^[0-9]+$ ]] || continue
      kill -TERM "$pid" 2>/dev/null || true
      killed=1
    done < <(lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null || true)
  fi

  if [[ "$killed" -eq 1 ]]; then
    echo "Stopped previous listener(s) on ${label}."
    sleep 0.5
  fi
}

kill_api_process() {
  local pid="${1:-}"
  [[ -z "$pid" ]] && return 0
  if is_windows; then
    taskkill //F //T //PID "$pid" >/dev/null 2>&1 || taskkill //F //PID "$pid" >/dev/null 2>&1 || true
  elif [[ -n "${API_PGID:-}" ]]; then
    kill -TERM -- "-${API_PGID}" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  else
    kill -TERM "$pid" 2>/dev/null || true
  fi
  wait "$pid" 2>/dev/null || true
}

usage() {
  echo "Usage: ./start-web.sh [--no-install] [--api-port PORT]" >&2
  echo "  Starts uvicorn from repo root and Vite in dashboard/web." >&2
  echo "  Open http://127.0.0.1:${VITE_PORT:-5173} (API on port ${API_PORT})." >&2
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
API_LOG="$(api_log_file)"

cleanup() {
  kill_api_process "${API_PID:-}"
  free_port "$API_PORT" "API port ${API_PORT}"
  free_port "$VITE_PORT" "Vite port ${VITE_PORT}"
}
trap cleanup EXIT INT TERM

echo "VG Agent dashboard"
echo "  repo root: $ROOT_DIR"
echo "  workspace: $VG_WORKSPACE_ROOT"
echo "  API:       http://127.0.0.1:${API_PORT}/api/v1/health"
echo "  UI:        http://127.0.0.1:${VITE_PORT}"
echo "  API log:   $API_LOG"
echo ""

free_port "$API_PORT" "API port ${API_PORT}"
free_port "$VITE_PORT" "Vite port ${VITE_PORT}"

echo "Starting API (background)..."

if command -v setsid >/dev/null 2>&1 && ! is_windows; then
  setsid uv run uvicorn dashboard.api.main:app \
    --host 127.0.0.1 \
    --port "$API_PORT" \
    --reload \
    >"$API_LOG" 2>&1 &
  API_PID=$!
  API_PGID=$API_PID
else
  uv run uvicorn dashboard.api.main:app \
    --host 127.0.0.1 \
    --port "$API_PORT" \
    --reload \
    >"$API_LOG" 2>&1 &
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
      tail -n 20 "$API_LOG" >&2 || true
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
    echo "  Log: $API_LOG" >&2
  fi
fi

echo "API ready (pid $API_PID). Starting Vite (foreground; Ctrl+C stops both)..."
echo ""

cd "$ROOT_DIR/dashboard/web"
exec npm run dev

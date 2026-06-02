#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

SKIP_BUILD=0

usage() {
  echo "Usage: ./start-dashboard.sh [--no-build]" >&2
  echo "  Starts the trace dashboard in Docker (persistent across agent rebuilds)." >&2
  echo "  Open http://127.0.0.1:8787" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-build)
      SKIP_BUILD=1
      shift
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

if ! command -v docker >/dev/null 2>&1; then
  echo "error: docker is required but was not found on PATH" >&2
  exit 1
fi

mkdir -p "$ROOT_DIR/workspace" "$ROOT_DIR/traces"

if [[ "$SKIP_BUILD" -eq 0 ]]; then
  echo "building vg-dashboard image..."
  docker compose build vg-dashboard
fi

echo "starting vg-dashboard (detached)..."
docker compose up -d vg-dashboard

echo ""
echo "VG Agent dashboard: http://127.0.0.1:8787"
echo "  logs:  docker compose logs -f vg-dashboard"
echo "  stop:  docker compose stop vg-dashboard"
echo ""

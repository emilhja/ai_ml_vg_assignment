#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

ENV_FILE="$ROOT_DIR/.env"

if ! command -v docker >/dev/null 2>&1; then
  echo "error: docker is required but was not found on PATH" >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ROOT_DIR/.env.example" "$ENV_FILE"
  echo "created .env from .env.example" >&2
fi

if ! grep -Eq '^OPENROUTER_API_KEY=[^[:space:]]+' "$ENV_FILE"; then
  echo "error: set OPENROUTER_API_KEY in .env before starting live chat" >&2
  exit 1
fi

mkdir -p "$ROOT_DIR/workspace" "$ROOT_DIR/traces"

echo "building Docker live chat image..."
docker compose build vg-agent-live

echo "seeding chat workspace..."
docker compose run --rm vg-agent --seed-fixture

echo "opening VG Agent live chat in Docker..."
exec docker compose run --rm -it vg-agent-live \
  --chat \
  --live-model \
  --trace \
  --show-context 3 \
  --require-approval writes

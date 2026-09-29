#!/usr/bin/env bash
set -euo pipefail

size=full
reset=false
prepare_only=false
for argument in "$@"; do
  case "$argument" in
    small|full) size="$argument" ;;
    --reset) reset=true ;;
    --prepare-only) prepare_only=true ;;
    *) echo "Usage: bash scripts/demo.sh [small|full] [--reset] [--prepare-only]" >&2; exit 2 ;;
  esac
done

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
api="$root/apps/api"
web="$root/apps/web"
python="$api/.venv/bin/python"

export APP_MODE=DEMO
export DATABASE_URL=sqlite:///./data/supportpilot.db
export UPLOAD_ROOT=./data/uploads
export COOKIE_SECURE=false
export COMMERCE_ADAPTER=local
export SUPPORT_ADAPTER=local
export SECRET_KEY=local-demo-only-change-before-deployment
export REFERENCE_DATE=2026-09-27
export UV_CACHE_DIR="${UV_CACHE_DIR:-$root/.uv-cache}"

command -v uv >/dev/null || { echo 'uv is required' >&2; exit 1; }
command -v pnpm >/dev/null || { echo 'pnpm is required' >&2; exit 1; }
command -v node >/dev/null || { echo 'Node.js is required' >&2; exit 1; }

(cd "$api" && uv sync --locked --extra dev)
if [[ ! -f "$root/fixtures/demo_$size.json" ]]; then
  "$python" "$root/scripts/generate_demo.py"
fi
if [[ ! -f "$root/evals/cases.jsonl" ]]; then
  "$python" "$root/scripts/generate_evals.py"
fi
(cd "$web" && pnpm install --frozen-lockfile)

if [[ "$reset" == true || ! -f "$api/data/supportpilot.db" ]]; then
  seed_args=(--size "$size")
  if [[ "$reset" == true ]]; then seed_args+=(--reset); fi
  (cd "$api" && "$python" -m supportpilot.seed "${seed_args[@]}")
else
  echo "Existing DEMO database kept at $api/data/supportpilot.db. Use --reset to replace only synthetic workspaces."
fi

if [[ "$prepare_only" == true ]]; then
  echo 'DEMO dependencies and data are ready.'
  exit 0
fi

"$python" -c 'import socket
for port in (8000, 5173):
    with socket.socket() as connection:
        if connection.connect_ex(("127.0.0.1", port)) == 0:
            raise SystemExit(f"Port {port} is already in use")'

(cd "$api" && "$python" -m uvicorn supportpilot.api:app --host 127.0.0.1 --port 8000) &
api_pid=$!
(cd "$web" && node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort) &
web_pid=$!
cleanup() {
  kill "$api_pid" "$web_pid" 2>/dev/null || true
  wait "$api_pid" "$web_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

"$python" -c 'import sys,time,urllib.request; urls=sys.argv[1:]; ready=False
for _ in range(60):
    try:
        for url in urls: urllib.request.urlopen(url, timeout=2).close()
        ready=True; break
    except Exception: time.sleep(1)
if not ready: raise SystemExit("DEMO services did not become healthy within 60 seconds")' \
  'http://127.0.0.1:8000/api/health' 'http://127.0.0.1:5173/'
echo 'SupportPilot DEMO is ready: http://127.0.0.1:5173'
echo 'API health: http://127.0.0.1:8000/api/health. Press Ctrl+C to stop both services.'
while kill -0 "$api_pid" 2>/dev/null && kill -0 "$web_pid" 2>/dev/null; do
  sleep 1
done
echo 'A DEMO service stopped' >&2
exit 1

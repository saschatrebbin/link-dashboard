#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

compose() {
  docker compose -f "$ROOT_DIR/docker-compose.yml" "$@"
}

usage() {
  cat <<'EOF'
Usage: ./scripts/manage.sh <command>

Commands:
  build      Build the Docker image
  up         Start the stack in detached mode
  down       Stop the stack
  restart    Restart the stack
  logs       Show compose logs
  ps         Show compose status
  health     Query /api/health on localhost:8080
  check      Run lightweight project checks
  config     Render docker compose config
EOF
}

run_check() {
  python3 -m compileall "$ROOT_DIR/backend"
  compose config >/dev/null
}

case "${1:-}" in
  build)
    compose build
    ;;
  up)
    compose up -d --build
    ;;
  down)
    compose down
    ;;
  restart)
    compose down
    compose up -d --build
    ;;
  logs)
    compose logs -f
    ;;
  ps)
    compose ps
    ;;
  health)
    curl -fsS http://127.0.0.1:8080/api/health
    ;;
  check)
    run_check
    ;;
  config)
    compose config
    ;;
  *)
    usage
    exit 1
    ;;
esac

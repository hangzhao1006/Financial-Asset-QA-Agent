#!/usr/bin/env bash
# docker-shell.sh — Load environment variables and run Docker Compose
# Usage:
#   ./docker-shell.sh              # Start all services
#   ./docker-shell.sh down         # Stop all services
#   ./docker-shell.sh build        # Rebuild images
#   ./docker-shell.sh logs         # View logs
#   ./docker-shell.sh backend      # Shell into backend container

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Load .env ──────────────────────────────────────────────
if [ ! -f .env ]; then
  echo "⚠  .env not found. Creating from .env.example..."
  cp .env.example .env
  echo "✏  Please edit .env and fill in your API keys, then re-run."
  exit 1
fi

set -a
source .env
set +a

echo "✓  Environment loaded from .env"

# ── Commands ───────────────────────────────────────────────
CMD="${1:-up}"

case "$CMD" in
  up)
    echo "🚀 Starting services..."
    docker compose up --build -d
    echo ""
    echo "✓  Backend:  http://localhost:8000/api/health"
    echo "✓  Frontend: http://localhost:3001"
    ;;
  down)
    echo "🛑 Stopping services..."
    docker compose down
    ;;
  build)
    echo "🔨 Rebuilding images..."
    docker compose build --no-cache
    ;;
  logs)
    docker compose logs -f "${2:-}"
    ;;
  backend)
    echo "🐚 Opening shell in backend container..."
    docker compose exec backend bash
    ;;
  frontend)
    echo "🐚 Opening shell in frontend container..."
    docker compose exec frontend sh
    ;;
  restart)
    docker compose down
    docker compose up --build -d
    ;;
  *)
    echo "Usage: ./docker-shell.sh [up|down|build|logs|backend|frontend|restart]"
    exit 1
    ;;
esac

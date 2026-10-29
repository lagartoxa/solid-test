#!/usr/bin/env bash
# Commands to run the project with Docker. Usage: ./dev.sh <command>
set -euo pipefail

cd "$(dirname "$0")"

# Docker Compose v2 ("docker compose") or v1 ("docker-compose").
if docker compose version >/dev/null 2>&1; then
    compose() { docker compose "$@"; }
else
    compose() { docker-compose "$@"; }
fi

usage() {
    cat <<USAGE
Usage: ./dev.sh <command>

  reset-db   Clear the database, create the tables and insert the sample data
  run        Run the API at http://localhost:5000 (Swagger at /docs); Ctrl+C stops it
  test       Run the automated tests
  settle     Mock payment provider: send the result of every pending payment
  down       Stop the containers (the data is kept)
USAGE
}

case "${1:-}" in
    reset-db)
        compose build app
        compose run --rm app sh -c "alembic downgrade base && alembic upgrade head && flask seed"
        ;;
    run)
        compose up --build app
        ;;
    test)
        compose build app
        compose run --rm app pytest
        ;;
    settle)
        compose run --rm app flask mock-provider settle
        ;;
    down)
        compose down
        ;;
    *)
        usage
        exit 1
        ;;
esac

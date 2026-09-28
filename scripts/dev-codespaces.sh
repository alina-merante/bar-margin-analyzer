#!/bin/sh
# Codespaces-only dev entrypoint: keeps PostgreSQL in Docker (published on
# 127.0.0.1:5432) but runs backend and frontend as native processes, since
# api<->db container-to-container communication over the Docker bridge is
# broken in this environment (see /memories/repo/docker-codespaces-issue.md).
set -eu

script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
cd "$repo_root"

export DATABASE_URL="postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/bar_margin_analyzer"

if ! command -v tesseract >/dev/null 2>&1 || ! command -v pdftoppm >/dev/null 2>&1 || ! python3.12 -m venv --help >/dev/null 2>&1; then
    echo "Installing OCR and Python venv system dependencies (tesseract-ocr, tesseract-ocr-ita, poppler-utils, python3.12-venv)..."
    sudo apt-get update
    sudo apt-get install -y tesseract-ocr tesseract-ocr-ita poppler-utils python3.12-venv
fi

echo "Starting PostgreSQL (db container)..."
docker compose up -d db

attempt=1
while ! docker compose exec -T db pg_isready -U postgres -d bar_margin_analyzer >/dev/null 2>&1; do
    if [ "$attempt" -ge 60 ]; then
        echo "PostgreSQL did not become ready" >&2
        docker compose logs db >&2 || true
        exit 1
    fi
    attempt=$((attempt + 1))
    sleep 2
done

venv_dir="$repo_root/backend/.venv"
if [ ! -d "$venv_dir" ]; then
    echo "Creating backend virtualenv..."
    python3.12 -m venv "$venv_dir"
fi
"$venv_dir/bin/pip" install --quiet --upgrade pip
"$venv_dir/bin/pip" install --quiet -r "$repo_root/backend/requirements.txt"

echo "Applying Alembic migrations..."
(cd "$repo_root/backend" && "$venv_dir/bin/alembic" upgrade head)

pid_file="$repo_root/backend/.uvicorn.pid"
log_file="$repo_root/backend/.uvicorn.log"

cleanup() {
    if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
        kill "$(cat "$pid_file")" 2>/dev/null || true
    fi
}
trap cleanup INT TERM EXIT

if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "Backend already running (pid $(cat "$pid_file"))"
else
    (
        cd "$repo_root/backend"
        nohup "$venv_dir/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload \
            > "$log_file" 2>&1 &
        echo $! > "$pid_file"
    )
fi

attempt=1
while ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; do
    if [ "$attempt" -ge 60 ]; then
        echo "API did not become ready" >&2
        cat "$log_file" >&2 || true
        exit 1
    fi
    attempt=$((attempt + 1))
    sleep 2
done

echo "Backend ready on http://127.0.0.1:8000"

if [ ! -d "$repo_root/frontend/node_modules" ]; then
    npm --prefix frontend ci
fi

trap - EXIT
exec npm --prefix frontend run dev

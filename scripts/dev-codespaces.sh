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
api_url="http://127.0.0.1:8000"
frontend_url="http://127.0.0.1:5173"

port_is_listening() {
    ss -H -ltn "sport = :$1" 2>/dev/null | grep -q .
}

api_is_ready() {
    health="$(curl -fsS --max-time 2 "$api_url/health" 2>/dev/null || true)"
    root="$(curl -fsS --max-time 2 "$api_url/" 2>/dev/null || true)"
    printf '%s' "$health" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"' &&
        printf '%s' "$root" | grep -Fq 'Bar Margin Analyzer backend is running'
}

frontend_is_ready() {
    page="$(curl -fsS --max-time 2 "$frontend_url/" 2>/dev/null || true)"
    vite_client="$(curl -fsS --max-time 2 "$frontend_url/@vite/client" 2>/dev/null || true)"
    printf '%s' "$page" | grep -Fq '<title>frontend</title>' &&
        printf '%s' "$page" | grep -Fq '/src/main.jsx' &&
        printf '%s' "$vite_client" | grep -Fq 'createHotContext'
}

api_already_running=0
if port_is_listening 8000; then
    if api_is_ready; then
        echo "Backend already ready on $api_url"
        api_already_running=1
    else
        echo "Port 8000 is occupied by a process other than this project's API." >&2
        exit 1
    fi
fi

frontend_already_running=0
if port_is_listening 5173; then
    if frontend_is_ready; then
        echo "Frontend already ready on $frontend_url"
        frontend_already_running=1
    else
        echo "Port 5173 is occupied by a process other than this project's Vite frontend." >&2
        exit 1
    fi
fi

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
requirements_file="$repo_root/backend/requirements.txt"
if [ "$api_already_running" -eq 0 ]; then
    if [ ! -x "$venv_dir/bin/python" ]; then
        echo "Creating backend virtualenv..."
        python3.12 -m venv "$venv_dir"
    fi

    requirements_hash="$(sha256sum "$requirements_file" | awk '{print $1}')"
    requirements_stamp="$venv_dir/.requirements.sha256"
    if [ ! -f "$requirements_stamp" ] || [ "$(cat "$requirements_stamp")" != "$requirements_hash" ]; then
        echo "Installing backend dependencies..."
        "$venv_dir/bin/pip" install --quiet -r "$requirements_file"
        printf '%s\n' "$requirements_hash" > "$requirements_stamp"
    else
        echo "Backend dependencies already current."
    fi

    echo "Applying Alembic migrations..."
    (cd "$repo_root/backend" && "$venv_dir/bin/alembic" upgrade head)
fi

pid_file="$repo_root/backend/.uvicorn.pid"
log_file="$repo_root/backend/.uvicorn.log"
backend_pid=""

cleanup() {
    if [ -n "$backend_pid" ] && kill -0 "$backend_pid" 2>/dev/null; then
        kill "$backend_pid" 2>/dev/null || true
    fi
    if [ -n "$backend_pid" ] && [ -f "$pid_file" ] && [ "$(cat "$pid_file")" = "$backend_pid" ]; then
        rm -f "$pid_file"
    fi
}
trap cleanup INT TERM EXIT

if [ "$api_already_running" -eq 0 ]; then
    echo "Starting backend on $api_url..."
    (
        cd "$repo_root/backend"
        nohup "$venv_dir/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload \
            > "$log_file" 2>&1 &
        echo $! > "$pid_file"
    )
    backend_pid="$(cat "$pid_file")"
fi

attempt=1
while ! api_is_ready; do
    if [ "$attempt" -ge 60 ]; then
        echo "API did not become ready" >&2
        cat "$log_file" >&2 || true
        exit 1
    fi
    attempt=$((attempt + 1))
    sleep 2
done

echo "Backend ready on $api_url"

if [ "$frontend_already_running" -eq 0 ] && [ ! -d "$repo_root/frontend/node_modules" ]; then
    npm --prefix frontend ci
fi

if [ "$frontend_already_running" -eq 1 ]; then
    echo "Environment already ready: $frontend_url"
    trap - INT TERM EXIT
    exit 0
fi

trap - INT TERM EXIT
exec npm --prefix frontend run dev -- --strictPort

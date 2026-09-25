#!/bin/sh
set -eu

npm --prefix frontend ci
docker compose up --build -d db api

attempt=1
while ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; do
    if [ "$attempt" -ge 60 ]; then
        echo "API did not become ready" >&2
        docker compose logs api db >&2 || true
        exit 1
    fi
    attempt=$((attempt + 1))
    sleep 2
done

exec npm --prefix frontend run dev

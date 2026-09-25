#!/bin/sh
set -eu

max_attempts=30
attempt=1

while ! alembic upgrade head; do
    if [ "$attempt" -ge "$max_attempts" ]; then
        echo "Alembic upgrade failed after $max_attempts attempts" >&2
        exit 1
    fi

    echo "Waiting for PostgreSQL before Alembic upgrade (attempt $attempt/$max_attempts)..." >&2
    attempt=$((attempt + 1))
    sleep 2
done

exec "$@"

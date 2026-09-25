#!/bin/sh
set -eu

project="bar-margin-analyzer-clean-${$}"
compose="docker compose -p $project -f docker-compose.yml -f docker-compose.clean-bootstrap.yml"

cleanup() {
    $compose down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

$compose up --build -d db api

if ! $compose exec -T api python -c 'import socket; socket.create_connection(("db", 5432), timeout=5).close()' >/dev/null 2>&1; then
    echo "Docker network check failed: api cannot reach db:5432" >&2
    $compose logs api db >&2 || true
    exit 1
fi

attempt=1
while ! $compose exec -T api python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2)' >/dev/null 2>&1; do
    if [ "$attempt" -ge 60 ]; then
        echo "API did not become ready" >&2
        $compose logs api db >&2 || true
        exit 1
    fi
    attempt=$((attempt + 1))
    sleep 2
done

expected_tables="category_rules daily_cash_closures documents expense_categories invoice_payment_links invoices payments products sale_lines transactions"
actual_tables=$($compose exec -T db psql -U postgres -d bar_margin_analyzer -Atc \
    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version' ORDER BY tablename" \
    | tr '\n' ' ' | sed 's/[[:space:]]*$//')

if [ "$actual_tables" != "$expected_tables" ]; then
    echo "Unexpected tables" >&2
    echo "Expected: $expected_tables" >&2
    echo "Actual:   $actual_tables" >&2
    exit 1
fi

echo "Schema tables: PASS (10 tables)"

$compose exec -T api python - <<'PY'
import urllib.request

paths = [
    "/health",
    "/invoices",
    "/categories",
    "/documents",
    "/analytics/overview?month=2026-09",
    "/analytics/pnl/trend?months=2&month=2026-09",
    "/analytics/top-products?month=2026-09",
    "/analytics/insights?month=2026-09",
]

for path in paths:
    with urllib.request.urlopen(f"http://127.0.0.1:8000{path}", timeout=10) as response:
        if response.status != 200:
            raise SystemExit(f"{path}: HTTP {response.status}")
    print(f"{path}: HTTP 200")
PY

echo "API endpoints: PASS"

npm --prefix frontend ci
npm --prefix frontend run build

echo "Frontend install/build: PASS"

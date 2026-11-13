#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
test_dir="$(mktemp -d)"
export HOME="$test_dir"
source "$repo_root/scripts/pwa-test-common.sh"
started=()
other=""
cleanup_test() {
    stop_managed backend || true
    if [[ -n "$other" ]]; then
        kill "$other" 2>/dev/null || true
        wait "$other" 2>/dev/null || true
    fi
    rm -rf -- "$test_dir"
}
trap cleanup_test EXIT
init_runtime

! process_start_time 999999999 2>"$test_dir/missing-error"
[[ ! -s "$test_dir/missing-error" ]]

start_managed backend sleep 300
pid="$(managed_pid backend)"
[[ "$pid" == "$(managed_pid backend)" ]]
stop_managed backend
! kill -0 "$pid" 2>/dev/null

sleep 300 &
other=$!
start="$(process_start_time "$other")"
printf '%s %s\n' "$other" "$start" > "$runtime_dir/backend.pid"
stop_managed backend
kill -0 "$other"

start_managed backend sleep 300
pid="$(managed_pid backend)"
printf '%s %s\n' "$pid" 1 > "$runtime_dir/backend.pid"
! managed_pid backend >/dev/null
kill -0 "$pid"
printf '%s %s\n' "$pid" "$(process_start_time "$pid")" > "$runtime_dir/backend.pid"
stop_managed backend
echo "Controlli PID PWA superati."

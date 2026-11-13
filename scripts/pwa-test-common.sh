#!/usr/bin/env bash

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
runtime_dir="$HOME/.local/state/barmanager-pwa-test"
socket=/tmp/barmanager-tailscale.sock
upload_dir=/tmp/barmanager_pwa_test_uploads

die() {
    printf 'Errore: %s\n' "$*" >&2
    exit 1
}

init_runtime() {
    umask 077
    mkdir -p -- "$runtime_dir"
    [[ -d "$runtime_dir" && ! -L "$runtime_dir" && -O "$runtime_dir" ]] ||
        die "Directory runtime non sicura: $runtime_dir"
    chmod 700 "$runtime_dir"
    exec 9>"$runtime_dir/lock"
    flock -n 9 || die "Un altro comando PWA è già in esecuzione."
}

process_start_time() {
    local stat
    IFS= read -r stat 2>/dev/null < "/proc/$1/stat" || return 1
    stat="${stat##*) }"
    awk '{print $20}' <<< "$stat"
}

managed_pid() {
    local name="$1" pid start current
    [[ -f "$runtime_dir/$name.pid" && ! -L "$runtime_dir/$name.pid" ]] || return 1
    read -r pid start < "$runtime_dir/$name.pid" || return 1
    [[ "$pid" =~ ^[0-9]+$ && "$start" =~ ^[0-9]+$ ]] || return 1
    current="$(process_start_time "$pid")" || return 1
    [[ "$current" == "$start" ]] || return 1
    grep -zFxq "BARMANAGER_PWA_PROCESS=$name" "/proc/$pid/environ" 2>/dev/null || return 1
    printf '%s\n' "$pid"
}

start_managed() {
    local name="$1" pid start i
    shift
    nohup setsid env "BARMANAGER_PWA_PROCESS=$name" "$@" \
        </dev/null >>"$runtime_dir/$name.log" 2>&1 9>&- &
    pid=$!
    start="$(process_start_time "$pid")" || die "Avvio di $name fallito; vedere $runtime_dir/$name.log"
    printf '%s %s\n' "$pid" "$start" > "$runtime_dir/$name.pid"
    started+=("$name")
    for ((i=0; i<50; i++)); do
        managed_pid "$name" >/dev/null && return 0
        sleep 0.1
    done
    die "Avvio di $name fallito; vedere $runtime_dir/$name.log"
}

stop_managed() {
    local name="$1" pid i
    if pid="$(managed_pid "$name")"; then
        kill "$pid" || { echo "Impossibile fermare $name (PID $pid)." >&2; return 1; }
        for ((i=0; i<50; i++)); do
            managed_pid "$name" >/dev/null || break
            sleep 0.1
        done
        if managed_pid "$name" >/dev/null; then
            echo "$name non si è arrestato; PID $pid ancora attivo." >&2
            return 1
        fi
        echo "$name arrestato."
    fi
    rm -f -- "$runtime_dir/$name.pid"
}

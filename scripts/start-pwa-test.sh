#!/usr/bin/env bash
set -Eeuo pipefail

source "$(dirname -- "${BASH_SOURCE[0]}")/pwa-test-common.sh"
init_runtime
started=()
temp_dir=""
cleanup() {
    local status=$? i
    trap - EXIT
    if (( status != 0 )); then
        for ((i=${#started[@]}-1; i>=0; i--)); do
            stop_managed "${started[i]}" || printf 'Arresto incompleto di %s\n' "${started[i]}" >&2
        done
    fi
    if [[ -n "$temp_dir" && -d "$temp_dir" ]]; then
        rm -rf -- "$temp_dir"
    fi
    exit "$status"
}
trap cleanup EXIT

for cmd in curl flock ss setsid nohup sha256sum tar node; do
    command -v "$cmd" >/dev/null || die "Comando richiesto mancante: $cmd"
done

python="$repo_root/backend/.venv/bin/python"
[[ -x "$python" ]] || python="$repo_root/.venv/bin/python"
[[ -x "$python" ]] || die "Virtualenv backend mancante; installare prima le dipendenze del progetto."
vite="$repo_root/frontend/node_modules/vite/bin/vite.js"
[[ -f "$vite" ]] || die "Dipendenze frontend mancanti; eseguire npm ci in frontend."

config="$repo_root/scripts/.pwa-test.env"
if [[ -f "$config" ]]; then
    [[ ! -L "$config" && -O "$config" ]] || die "Il file $config deve appartenere all'utente e non essere un link."
    mode="$(stat -c '%a' "$config")"
    (( (8#$mode & 077) == 0 )) || die "Proteggere $config con chmod 600."
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ -z "$line" || "$line" == \#* ]] && continue
        [[ "$line" == DATABASE_URL=* ]] || die "Il file locale ammette solo DATABASE_URL= senza virgolette."
        [[ -n "${DATABASE_URL:-}" ]] || DATABASE_URL="${line#DATABASE_URL=}"
    done < "$config"
fi
[[ -n "${DATABASE_URL:-}" ]] || die "Impostare DATABASE_URL o scripts/.pwa-test.env."
export DATABASE_URL

# Do not print connection exceptions: driver messages can contain credentials.
if ! "$python" - <<'PY'
import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

try:
    url = make_url(os.environ["DATABASE_URL"])
    if (url.drivername not in ("postgresql", "postgresql+psycopg2")
            or url.database != "bar_margin_analyzer_pwa_test"
            or url.host not in ("127.0.0.1", "localhost")
            or url.port not in (None, 5432)
            or url.query):
        sys.exit(1)
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    with engine.connect() as connection:
        if connection.execute(text("SELECT current_database()")).scalar_one() != url.database:
            sys.exit(1)
    engine.dispose()
except Exception:
    sys.exit(1)
PY
then
    die "Connessione PostgreSQL non riuscita o URL non riferito al database PWA locale; nessun database è stato modificato."
fi

for pair in backend:8001 frontend:5174; do
    name="${pair%:*}"; port="${pair#*:}"
    if ! managed_pid "$name" >/dev/null && ss -H -ltn "sport = :$port" | grep -q .; then
        die "Porta $port occupata da un processo non gestito; non verrà terminato."
    fi
done
if ! managed_pid tailscaled >/dev/null && [[ -e "$socket" || -L "$socket" ]]; then
    die "Socket $socket già presente e non gestito; non verrà modificato."
fi

if [[ -e "$upload_dir" || -L "$upload_dir" ]]; then
    [[ -d "$upload_dir" && ! -L "$upload_dir" && -O "$upload_dir" && "$(stat -c '%a' "$upload_dir")" == 700 ]] ||
        die "La directory upload esistente deve appartenere all'utente, non essere un link e avere permessi 700: $upload_dir"
else
    mkdir -m 700 -- "$upload_dir"
fi

ts_dir="$HOME/.local/share/tailscale/barmanager-pwa-test"
mkdir -p -- "$ts_dir"
[[ -d "$ts_dir" && ! -L "$ts_dir" && -O "$ts_dir" ]] || die "Directory Tailscale non sicura: $ts_dir"
chmod 700 "$ts_dir"

if command -v tailscale >/dev/null && command -v tailscaled >/dev/null; then
    ts="$(command -v tailscale)"
    tsd="$(command -v tailscaled)"
else
    bin_dir="$ts_dir/bin"
    ts="$bin_dir/tailscale"
    tsd="$bin_dir/tailscaled"
    if [[ ! -x "$ts" || ! -x "$tsd" ]]; then
        case "$(uname -m)" in
            x86_64) arch=amd64 ;;
            aarch64|arm64) arch=arm64 ;;
            *) die "Architettura Tailscale non supportata: $(uname -m)" ;;
        esac
        archive="tailscale_1.90.9_${arch}.tgz"
        temp_dir="$(mktemp -d "$ts_dir/download.XXXXXXXX")"
        url="https://pkgs.tailscale.com/stable/$archive"
        if ! curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 "$url" -o "$temp_dir/$archive" ||
           ! curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 "$url.sha256" -o "$temp_dir/checksum"; then
            rm -rf -- "$temp_dir"
            die "Download Tailscale ufficiale non riuscito."
        fi
        checksum="$(tr -d '[:space:]' < "$temp_dir/checksum")"
        if [[ ! "$checksum" =~ ^[0-9a-f]{64}$ ]] ||
           ! (cd "$temp_dir" && printf '%s  %s\n' "$checksum" "$archive" | sha256sum -c --status) ||
           ! tar -xzf "$temp_dir/$archive" -C "$temp_dir" -- "tailscale_1.90.9_$arch/tailscale" "tailscale_1.90.9_$arch/tailscaled"; then
            rm -rf -- "$temp_dir"
            die "Verifica o estrazione Tailscale non riuscita."
        fi
        mkdir -p -- "$bin_dir"
        install -m 700 "$temp_dir/tailscale_1.90.9_$arch/tailscale" "$ts"
        install -m 700 "$temp_dir/tailscale_1.90.9_$arch/tailscaled" "$tsd"
        rm -rf -- "$temp_dir"
    fi
fi

if ! managed_pid tailscaled >/dev/null; then
    start_managed tailscaled env -u DATABASE_URL "$tsd" --tun=userspace-networking --socket="$socket" \
        --state="$ts_dir/tailscaled.state" --statedir="$ts_dir"
fi
for ((i=0; i<50; i++)); do
    [[ -S "$socket" ]] && break
    managed_pid tailscaled >/dev/null || die "tailscaled si è arrestato; vedere $runtime_dir/tailscaled.log"
    sleep 0.1
done
[[ -S "$socket" ]] || die "Socket Tailscale non disponibile."
echo "Connessione Tailscale: se richiesto, aprire il link di autorizzazione mostrato."
"$ts" --socket="$socket" up --accept-dns=false

if managed_pid serve >/dev/null; then
    has_managed_serve=1
else
    has_managed_serve=0
fi
export has_managed_serve
if ! "$ts" --socket="$socket" serve status --json | "$python" -c '
import json, os, sys
try:
    config = json.load(sys.stdin) or {}
    foreground = config.get("Foreground") or {}
    unsafe = (config.get("TCP") or config.get("Web") or config.get("Services")
              or any((config.get("AllowFunnel") or {}).values())
              or (foreground and os.environ["has_managed_serve"] != "1")
              or any(any((c.get("AllowFunnel") or {}).values()) for c in foreground.values()))
    sys.exit(bool(unsafe))
except (ValueError, TypeError, AttributeError):
    sys.exit(1)
'; then
    die "Configurazione Serve preesistente o pubblica rilevata nel daemon dedicato; verificare manualmente prima di procedere."
fi

hostname="$("$ts" --socket="$socket" status --json | "$python" -c '
import json, re, sys
d = json.load(sys.stdin)
host = (d.get("Self") or {}).get("DNSName", "").rstrip(".").lower()
if d.get("BackendState") != "Running" or not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+ts\.net", host):
    sys.exit(1)
if host not in d.get("CertDomains", []):
    sys.exit(1)
print(host)
')" || die "Hostname HTTPS Tailscale non disponibile; verificare MagicDNS e HTTPS nella tailnet."
export AUTH_ALLOWED_ORIGINS="https://$hostname"
export AUTH_COOKIE_SECURE=true
export UPLOAD_BASE_PATH="$upload_dir"
export PWA_TEST_HOSTNAME="$hostname"

same_environment() {
    local pid="$1"
    "$python" - "$pid" <<'PY'
import os, sys
try:
    with open(f"/proc/{sys.argv[1]}/environ", "rb") as f:
        values = dict(item.split(b"=", 1) for item in f.read().split(b"\0") if b"=" in item)
    names = sys.argv[2:] or ["DATABASE_URL", "UPLOAD_BASE_PATH", "AUTH_ALLOWED_ORIGINS", "AUTH_COOKIE_SECURE"]
    sys.exit(any(values.get(name.encode()) != os.environ[name].encode() for name in names))
except (OSError, KeyError):
    sys.exit(1)
PY
}

if pid="$(managed_pid backend)"; then
    same_environment "$pid" || die "Configurazione backend cambiata; arrestare e riavviare l'ambiente PWA."
else
    cd "$repo_root/backend"
    start_managed backend "$python" -m uvicorn app.main:app --host 127.0.0.1 --port 8001
fi
if pid="$(managed_pid frontend)"; then
    "$python" - "$pid" <<'PY' || die "Hostname frontend cambiato; arrestare e riavviare l'ambiente PWA."
import os, sys
with open(f"/proc/{sys.argv[1]}/environ", "rb") as f:
    sys.exit(b"PWA_TEST_HOSTNAME=" + os.environ["PWA_TEST_HOSTNAME"].encode() not in f.read().split(b"\0"))
PY
else
    cd "$repo_root/frontend"
    start_managed frontend env -u DATABASE_URL node "$vite" --config vite.config.test.js
fi

for ((i=0; i<60; i++)); do
    if curl -fsS --max-time 2 http://127.0.0.1:8001/health | grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"' &&
       curl -fsS --max-time 2 -H "Host: $hostname" http://127.0.0.1:5174/api/health | grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"' &&
       curl -fsS --max-time 2 -H "Host: $hostname" http://127.0.0.1:5174/ | grep -Fq '/src/main.jsx'; then
        break
    fi
    managed_pid backend >/dev/null && managed_pid frontend >/dev/null ||
        die "Un servizio si è arrestato; controllare i log in $runtime_dir."
    sleep 1
done
(( i < 60 )) || die "Servizi PWA non pronti; controllare i log in $runtime_dir."

if ! managed_pid serve >/dev/null; then
    start_managed serve env -u DATABASE_URL "$ts" --socket="$socket" serve --https=443 http://127.0.0.1:5174
fi
for ((i=0; i<30; i++)); do
    if "$ts" --socket="$socket" serve status --json | "$python" -c '
import json, os, sys
try:
    d = json.load(sys.stdin)
    def valid(config):
        if any(config.get("AllowFunnel", {}).values()):
            return False
        host = os.environ["PWA_TEST_HOSTNAME"] + ":443"
        handler = config.get("Web", {}).get(host, {}).get("Handlers", {}).get("/", {})
        return (config.get("TCP", {}).get("443", {}).get("HTTPS") is True
                and handler.get("Proxy") == "http://127.0.0.1:5174")
    configs = [d] + list(d.get("Foreground", {}).values())
    sys.exit(not any(valid(c) for c in configs) or any(
        any(c.get("AllowFunnel", {}).values()) for c in configs))
except (ValueError, TypeError, AttributeError):
    sys.exit(1)
'; then
        break
    fi
    managed_pid serve >/dev/null || die "Tailscale Serve si è arrestato; vedere $runtime_dir/serve.log"
    sleep 1
done
(( i < 30 )) || die "Proxy Tailscale privato non pronto; vedere $runtime_dir/serve.log."
echo "Ambiente PWA pronto: https://$hostname"
echo "Log: $runtime_dir (verificare l'accesso HTTPS da un dispositivo della tailnet)."

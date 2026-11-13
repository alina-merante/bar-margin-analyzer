#!/usr/bin/env bash
set -Eeuo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
test_dir="$(mktemp -d)"
export TEST_AREA="$test_dir"
export HOME="$test_dir/home"
fixture="$test_dir/repo"
cleanup() {
    if [[ -f "$fixture/scripts/stop-pwa-test.sh" ]]; then
        bash "$fixture/scripts/stop-pwa-test.sh" >/dev/null || true
    fi
    rm -rf -- "$test_dir"
}
trap cleanup EXIT

mkdir -p "$HOME" "$fixture/scripts" "$fixture/backend/.venv/bin" \
    "$fixture/frontend/node_modules/vite/bin" "$test_dir/bin" "$test_dir/modules/sqlalchemy"
cp "$root/scripts/"{start-pwa-test.sh,stop-pwa-test.sh,pwa-test-common.sh} "$fixture/scripts/"
sed -i "s|/tmp/barmanager-tailscale.sock|$test_dir/tailscale.sock|; s|/tmp/barmanager_pwa_test_uploads|$test_dir/uploads|" "$fixture/scripts/pwa-test-common.sh"
ln -s "$(command -v python3)" "$fixture/backend/.venv/bin/python"
touch "$fixture/frontend/node_modules/vite/bin/vite.js"
export PYTHONPATH="$test_dir/modules"
export PATH="$test_dir/bin:$PATH"
export DATABASE_URL="postgresql://test@127.0.0.1:5432/bar_margin_analyzer_pwa_test"

cat > "$test_dir/modules/sqlalchemy/engine.py" <<'PY'
from urllib.parse import urlparse

def make_url(raw):
    p = urlparse(raw)
    class URL:
        drivername = p.scheme
        database = p.path.lstrip("/")
        host = p.hostname
        port = p.port
        query = p.query
    return URL()
PY
cat > "$test_dir/modules/sqlalchemy/__init__.py" <<'PY'
class Connection:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, query): return self
    def scalar_one(self): return "bar_margin_analyzer_pwa_test"
class Engine:
    def connect(self): return Connection()
    def dispose(self): pass
def create_engine(*args, **kwargs): return Engine()
def text(query): return query
PY
cat > "$test_dir/modules/uvicorn.py" <<'PY'
import time
time.sleep(3600)
PY
cat > "$test_dir/bin/ss" <<'SH'
#!/usr/bin/env bash
[[ ! -f "$TEST_AREA/occupied" ]] || echo "LISTEN occupied"
SH
cat > "$test_dir/bin/curl" <<'SH'
#!/usr/bin/env bash
if [[ "${*: -1}" == */health ]]; then
    echo '{"status":"ok"}'
else
    echo '<script src="/src/main.jsx"></script>'
fi
SH
cat > "$test_dir/bin/node" <<'SH'
#!/usr/bin/env bash
exec python3 -c 'import time; time.sleep(3600)'
SH
cat > "$test_dir/bin/tailscaled" <<'PY'
#!/usr/bin/env python3
import os, signal, socket, sys, time
path = next(arg.split("=", 1)[1] for arg in sys.argv if arg.startswith("--socket="))
sock = socket.socket(socket.AF_UNIX)
sock.bind(path)
def stop(*args):
    sock.close()
    os.unlink(path)
    sys.exit(0)
signal.signal(signal.SIGTERM, stop)
time.sleep(3600)
PY
cat > "$test_dir/bin/tailscale" <<'SH'
#!/usr/bin/env bash
shift
case "$1" in
    up) exit 0 ;;
    status) echo '{"BackendState":"Running","Self":{"DNSName":"test.tail123.ts.net."},"CertDomains":["test.tail123.ts.net"]}' ;;
    serve)
        if [[ "${2:-}" == status ]]; then
            if [[ -f "$TEST_AREA/public" ]]; then
                echo '{"AllowFunnel":{"test.tail123.ts.net:443":true}}'
                exit 0
            fi
            [[ -f "$TEST_AREA/serve-active" ]] || { echo '{}'; exit 0; }
            echo '{"Foreground":{"test":{"TCP":{"443":{"HTTPS":true}},"Web":{"test.tail123.ts.net:443":{"Handlers":{"/":{"Proxy":"http://127.0.0.1:5174"}}}}}}}'
        else
            touch "$TEST_AREA/serve-active"
            exec python3 -c 'import os,signal,time,sys; p=os.environ["TEST_AREA"]+"/serve-active"; signal.signal(signal.SIGTERM, lambda *_: (os.unlink(p), sys.exit(0))); time.sleep(3600)'
        fi ;;
    *) exit 1 ;;
esac
SH
chmod +x "$test_dir/bin/"*

for db in bar_margin_analyzer bar_margin_analyzer_ocr_test; do
    if DATABASE_URL="postgresql://test:sentinel-secret@127.0.0.1:5432/$db" \
        bash "$fixture/scripts/start-pwa-test.sh" >"$test_dir/database.log" 2>&1; then
        echo "Database non PWA accettato: $db" >&2
        exit 1
    fi
    ! grep -q 'sentinel-secret' "$test_dir/database.log"
done

touch "$test_dir/occupied"
if bash "$fixture/scripts/start-pwa-test.sh" >"$test_dir/conflict.log" 2>&1; then
    echo "La porta occupata non è stata rifiutata." >&2
    exit 1
fi
grep -q 'Porta 8001 occupata' "$test_dir/conflict.log"
rm "$test_dir/occupied"

touch "$test_dir/public"
if bash "$fixture/scripts/start-pwa-test.sh" >"$test_dir/public.log" 2>&1; then
    echo "La configurazione pubblica non è stata rifiutata." >&2
    exit 1
fi
grep -q 'Configurazione Serve preesistente o pubblica' "$test_dir/public.log"
[[ ! -e "$test_dir/tailscale.sock" ]]
rm "$test_dir/public"

bash "$fixture/scripts/start-pwa-test.sh" >"$test_dir/start.log"
grep -q 'https://test.tail123.ts.net' "$test_dir/start.log"
runtime="$HOME/.local/state/barmanager-pwa-test"
for name in tailscaled backend frontend serve; do
    read -r pid _ < "$runtime/$name.pid"
    kill -0 "$pid"
    printf '%s\n' "$pid" > "$test_dir/$name.first"
done
bash "$fixture/scripts/start-pwa-test.sh" >"$test_dir/restart.log"
for name in tailscaled backend frontend serve; do
    read -r pid _ < "$runtime/$name.pid"
    [[ "$pid" == "$(cat "$test_dir/$name.first")" ]]
done
bash "$fixture/scripts/stop-pwa-test.sh"
for name in tailscaled backend frontend serve; do
    pid="$(cat "$test_dir/$name.first")"
    ! kill -0 "$pid" 2>/dev/null
done
bash "$fixture/scripts/stop-pwa-test.sh" >/dev/null
echo "Ciclo di vita PWA simulato superato."

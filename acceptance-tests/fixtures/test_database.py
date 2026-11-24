from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

def get_test_engine():
    processes = []

    for p in Path("/proc").glob("[0-9]*"):
        try:
            args = (p / "cmdline").read_bytes().split(b"\0")
            if b"app.main:app" in args and b"8001" in args:
                processes.append(p)
        except OSError:
            pass

    assert len(processes) == 1, "Backend test non univoco"

    env = dict(
        item.split(b"=", 1)
        for item in (processes[0] / "environ").read_bytes().split(b"\0")
        if b"=" in item
    )

    url = make_url(env[b"DATABASE_URL"].decode())

    assert url.database == "bar_margin_analyzer_pwa_test"
    assert url.host in ("localhost", "127.0.0.1")
    assert url.get_backend_name() == "postgresql"
    assert url.port in (None, 5432)
    assert not url.query

    return create_engine(url)

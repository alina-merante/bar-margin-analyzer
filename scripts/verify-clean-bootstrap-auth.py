#!/usr/bin/env python3
"""Verify authenticated dashboard endpoints in an isolated GitHub Actions DB."""

import http.cookiejar
import json
import os
import secrets
import sys
import urllib.request
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.models import Bar, MembershipRole, User, UserBarMembership
from app.security import hash_password

BASE_URL = "http://127.0.0.1:8000"
ORIGIN = "http://localhost:5173"

PATHS = (
    "/health",
    "/invoices",
    "/categories",
    "/documents",
    "/analytics/overview?month=2026-09",
    "/analytics/pnl/trend?months=2&month=2026-09",
    "/analytics/top-products?month=2026-09",
    "/analytics/insights?month=2026-09",
)


def request(opener, path, *, method="GET", payload=None, csrf=None):
    headers = {}
    data = None

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    if method != "GET":
        headers["Origin"] = ORIGIN
        if csrf:
            headers["X-CSRF-Token"] = csrf

    req = urllib.request.Request(
        BASE_URL + path,
        data=data,
        method=method,
        headers=headers,
    )

    with opener.open(req, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"{path}: HTTP {response.status}")
        body = response.read()
        return json.loads(body) if body else None


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Questo script è riservato a GitHub Actions.")

    database_url = os.environ["DATABASE_URL"]
    parsed = make_url(database_url)

    if (
        parsed.database != "bar_margin_analyzer"
        or parsed.host not in ("127.0.0.1", "localhost")
    ):
        raise SystemExit("Database CI inatteso: verifica interrotta.")

    email = "clean-bootstrap-owner@example.test"
    password = secrets.token_urlsafe(32)

    engine = create_engine(database_url)

    try:
        with Session(engine) as db:
            bar = Bar(name="Clean Bootstrap Test Bar")
            owner = User(
                email=email,
                password_hash=hash_password(password),
            )
            db.add_all((bar, owner))
            db.flush()

            db.add(
                UserBarMembership(
                    user_id=owner.id,
                    bar_id=bar.id,
                    role=MembershipRole.owner,
                )
            )
            db.commit()
            bar_id = bar.id

        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )

        csrf = request(opener, "/auth/csrf")["csrf_token"]

        login = request(
            opener,
            "/auth/login",
            method="POST",
            payload={"email": email, "password": password},
            csrf=csrf,
        )
        csrf = login["csrf_token"]

        request(
            opener,
            "/auth/active-bar",
            method="PUT",
            payload={"bar_id": bar_id},
            csrf=csrf,
        )
        print("Login e selezione del bar CI: PASS", flush=True)

        # Required by tenant-scoped endpoints after selecting the active bar.
        opener.addheaders = [("X-Expected-Bar-ID", str(bar_id))]

        for round_number in range(1, 4):
            for path in PATHS:
                request(opener, path)
                print(
                    f"Round {round_number}: {path}: HTTP 200",
                    flush=True,
                )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

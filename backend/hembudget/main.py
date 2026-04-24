from __future__ import annotations

import argparse
import faulthandler
import logging
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Aktivera Pythons signalhanterare så ev. segfaults i C-moduler
# (sqlcipher3, pypdfium2, Pillow) dumpar en stacktrace i stderr innan
# processen dör — mycket lättare att felsöka än ett bart "core dumped".
faulthandler.enable()

from .api import (
    admin, auth, backup, balances, budget, chat, elpris, funds, ledger,
    loans, reports, scenarios, school, settings_kv, tax, transactions,
    transfers, upcoming, upload, utility,
)
from .config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def build_app() -> FastAPI:
    app = FastAPI(
        title="Hembudget API",
        version="0.1.0",
        description="Lokal AI-driven familjeekonomi (Nemotron Nano 3 via LM Studio)",
    )
    # CORS:
    # - demo-mode: tillåt alla origins (publik Render-deploy)
    # - lan-mode (HEMBUDGET_LAN=1): tillåt privata IP-ranges så familjen
    #   kan nå servern från andra enheter på samma WiFi
    # - default: bara localhost + Tauri (säkert för desktop-app)
    import os
    import re
    demo = os.environ.get("HEMBUDGET_DEMO_MODE", "").lower() in ("1", "true", "yes")
    school_mode = os.environ.get("HEMBUDGET_SCHOOL_MODE", "").lower() in ("1", "true", "yes")
    lan = os.environ.get("HEMBUDGET_LAN", "").lower() in ("1", "true", "yes")
    if demo or school_mode:
        cors_kwargs: dict = {
            "allow_origins": ["*"],
            "allow_credentials": False,
        }
    elif lan:
        # Tillåt alla privata IP-ranges + localhost på vilken port som helst
        cors_kwargs = {
            "allow_origin_regex": (
                r"^https?://("
                r"localhost|127\.0\.0\.1|"
                r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
                r"192\.168\.\d{1,3}\.\d{1,3}|"
                r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|"
                r"tauri\.localhost"
                r")(:\d+)?$"
            ),
            "allow_credentials": True,
        }
    else:
        cors_kwargs = {
            "allow_origins": [
                "tauri://localhost",
                "http://tauri.localhost",
                "http://localhost:1420",
                "http://127.0.0.1:1420",
            ],
            "allow_credentials": True,
        }
    app.add_middleware(
        CORSMiddleware,
        **cors_kwargs,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # School-mode middleware: sätt ContextVar för aktuell elev-DB
    # baserat på bearer-token + X-As-Student-header. MÅSTE vara
    # middleware (inte Depends) — FastAPI kör sync deps i en threadpool
    # med kopierad context, så ContextVar-set där propagerar inte ut.
    if school_mode:
        from starlette.middleware.base import BaseHTTPMiddleware
        from .api.deps import _ACTIVE_TOKENS, _token_info
        from .school.engines import set_current_student, master_session
        from .school.models import Student

        class StudentScopeMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                set_current_student(None)
                auth = request.headers.get("authorization")
                x_as = request.headers.get("x-as-student")
                if auth and auth.lower().startswith("bearer "):
                    info = _token_info(auth[7:])
                    if info:
                        if info.role == "student":
                            set_current_student(info.student_id)
                        elif info.role == "teacher" and x_as:
                            try:
                                sid = int(x_as)
                            except ValueError:
                                sid = None
                            if sid:
                                with master_session() as s:
                                    stu = s.query(Student).filter(
                                        Student.id == sid,
                                        Student.teacher_id == info.teacher_id,
                                    ).first()
                                    if stu:
                                        set_current_student(sid)
                return await call_next(request)

        app.add_middleware(StudentScopeMiddleware)

    app.include_router(auth.router)
    app.include_router(transactions.router)
    app.include_router(upload.router)
    app.include_router(budget.router)
    app.include_router(chat.router)
    app.include_router(scenarios.router)
    app.include_router(tax.router)
    app.include_router(reports.router)
    app.include_router(loans.router)
    app.include_router(transfers.router)
    app.include_router(upcoming.router)
    app.include_router(balances.router)
    app.include_router(elpris.router)
    app.include_router(funds.router)
    app.include_router(ledger.router)
    app.include_router(backup.router)
    app.include_router(settings_kv.router)
    app.include_router(utility.router)
    app.include_router(admin.router)
    app.include_router(school.router)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True, "version": "0.1.0"}

    # Servera byggd frontend (dist/) när den finns i containern.
    # Aktiveras via HEMBUDGET_SERVE_STATIC=1 (sätts i Dockerfile:n).
    # I desktop-läget är frontend en separat Vite-server → aldrig
    # mountat där.
    _serve_static = os.environ.get("HEMBUDGET_SERVE_STATIC", "").lower() in (
        "1", "true", "yes",
    )
    if _serve_static:
        _mount_frontend_static(app)

    return app


def _mount_frontend_static(app: FastAPI) -> None:
    """Mounta statisk frontend (Vite dist/) på roten av API:et. Kallas
    när HEMBUDGET_SERVE_STATIC=1, typiskt i Cloud Run / Docker-läge där
    en enda container ska servera både frontend och API. API-routrar
    är redan registrerade så SPA-fallbacken nedan slår bara in för
    okända paths (React Router-klient)."""
    import os as _os
    from pathlib import Path
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    # /app/frontend/dist är Dockerfile-sökvägen; fallback till
    # monorepo-layouten för lokal utveckling.
    candidates = [
        Path("/app/frontend/dist"),
        Path(__file__).resolve().parents[2] / "frontend" / "dist",
    ]
    dist = next((p for p in candidates if p.exists()), None)
    if dist is None:
        logging.getLogger(__name__).warning(
            "HEMBUDGET_SERVE_STATIC=1 men inget dist/-bygge hittat"
        )
        return
    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/", include_in_schema=False)
    def _spa_root() -> FileResponse:
        return FileResponse(str(dist / "index.html"))

    # Catch-all för React Router-paths (ej /api, ej /healthz, ej /assets).
    # Måste registreras SIST efter alla API-routers annars fångar den
    # alla requests. Vi lägger ingen prefix-check här eftersom FastAPI
    # matchar routes i ordning — konkreta API-routers tar sin request
    # först, den här tar resten.
    @app.get("/{full_path:path}", include_in_schema=False)
    def _spa_fallback(full_path: str) -> FileResponse:
        # Undvik att serva index.html för statiska filer i dist-roten
        # (favicon.ico, manifest.json etc.) — returnera dem direkt om
        # de finns.
        target = dist / full_path
        if target.is_file():
            return FileResponse(str(target))
        return FileResponse(str(dist / "index.html"))


app = build_app()


@app.on_event("startup")
def _demo_bootstrap() -> None:
    """Vid demo-mode: fyll databasen med användarens CSV/XLSX-data vid start."""
    try:
        from .demo import bootstrap_if_empty
        result = bootstrap_if_empty()
        if result and not result.get("skipped"):
            logging.getLogger(__name__).info("demo bootstrap: %s", result)
    except Exception:
        logging.getLogger(__name__).exception("demo bootstrap failed")


@app.on_event("startup")
def _school_bootstrap() -> None:
    """Vid school-mode: initiera master-DB + skapa första läraren från
    env-vars om de är satta och inga lärare finns."""
    import os as _os
    try:
        from .school import is_enabled
        if not is_enabled():
            return
        from .school.engines import init_master_engine, master_session
        from .school.models import Teacher
        from .security.crypto import hash_password

        init_master_engine()

        email = _os.environ.get("HEMBUDGET_BOOTSTRAP_TEACHER_EMAIL")
        password = _os.environ.get("HEMBUDGET_BOOTSTRAP_TEACHER_PASSWORD")
        name = _os.environ.get("HEMBUDGET_BOOTSTRAP_TEACHER_NAME", "Lärare")
        if email and password:
            with master_session() as s:
                if s.query(Teacher).count() == 0:
                    s.add(Teacher(
                        email=email.lower(),
                        name=name,
                        password_hash=hash_password(password),
                    ))
                    logging.getLogger(__name__).info(
                        "school: created bootstrap teacher %s", email,
                    )
    except Exception:
        logging.getLogger(__name__).exception("school bootstrap failed")


def main() -> None:
    import os as _os

    parser = argparse.ArgumentParser(description="Hembudget sidecar server")
    # Cloud Run injicerar PORT + förväntar sig bind på 0.0.0.0. HEMBUDGET_HOST
    # sätts i Dockerfile:n så den prioriteras över settings.host.
    default_host = _os.environ.get("HEMBUDGET_HOST") or settings.host
    # PORT (utan prefix) = Cloud Run-konvention. Fallback till settings.port.
    default_port = int(_os.environ.get("PORT") or settings.port or 0) or None
    parser.add_argument("--host", default=default_host)
    parser.add_argument("--port", type=int, default=default_port)
    parser.add_argument("--print-port", action="store_true",
                        help="Print chosen port on first line of stdout (for Tauri).")
    args = parser.parse_args()

    if args.print_port:
        # Bind to 0 first to discover port, then pass to uvicorn
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((args.host, 0))
        port = sock.getsockname()[1]
        sock.close()
        print(port, flush=True)
    else:
        port = args.port or 8765

    uvicorn.run(app, host=args.host, port=port, log_level="info")


if __name__ == "__main__":
    main()

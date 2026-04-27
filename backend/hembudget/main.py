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
    admin, ai, ai_admin, auth, backup, balances, bank, budget, chat,
    credit, elpris, email_auth, employer, funds, landing, ledger, loans,
    modules, reports, scenarios, school, settings_kv, smtp_admin,
    stock_trading, stocks, tax, events, teacher_credit, teacher_employer,
    teacher_stocks, teacher_wellbeing, transactions, transfers, upcoming,
    upload, utility, wellbeing,
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

    # School-mode middleware: sätt ContextVar för aktuell scope-DB
    # baserat på bearer-token + X-As-Student-header. Familjemedlemmar
    # delar samma scope; solo-elever får sin egen.
    # MÅSTE vara middleware (inte Depends) — FastAPI kör sync deps i en
    # threadpool med kopierad context, så ContextVar-set där propagerar
    # inte ut.
    if school_mode:
        from starlette.middleware.base import BaseHTTPMiddleware
        from .api.deps import _token_info
        from .school.engines import (
            master_session, scope_for_student,
            set_current_actor_student, set_current_scope,
        )
        from .school.models import Student

        class StudentScopeMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                set_current_scope(None)
                set_current_actor_student(None)
                auth = request.headers.get("authorization")
                x_as = request.headers.get("x-as-student")
                if auth and auth.lower().startswith("bearer "):
                    info = _token_info(auth[7:])
                    if info:
                        target_id: int | None = None
                        if info.role == "student":
                            target_id = info.student_id
                        elif info.role == "teacher" and x_as:
                            try:
                                target_id = int(x_as)
                            except ValueError:
                                target_id = None
                        if target_id is not None:
                            with master_session() as s:
                                q = s.query(Student).filter(
                                    Student.id == target_id,
                                )
                                if info.role == "teacher":
                                    q = q.filter(
                                        Student.teacher_id == info.teacher_id,
                                    )
                                stu = q.first()
                                if stu:
                                    set_current_scope(scope_for_student(stu))
                                    set_current_actor_student(stu.id)
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
    app.include_router(email_auth.router)
    app.include_router(modules.router)
    app.include_router(ai_admin.router)
    app.include_router(smtp_admin.router)
    app.include_router(landing.router)
    app.include_router(ai.router)
    # stock_trading måste includeas FÖRE stocks: stocks.py har en
    # catch-all `/stocks/{ticker}`-route som annars matchar
    # `/stocks/portfolio`, `/stocks/ledger`, `/stocks/orders`,
    # `/stocks/watchlist` etc. och svarar 404 'Okänd ticker'.
    app.include_router(stock_trading.router)
    app.include_router(stocks.router)
    app.include_router(teacher_stocks.router)
    app.include_router(credit.router)
    app.include_router(teacher_credit.router)
    app.include_router(wellbeing.router)
    app.include_router(events.router)
    app.include_router(teacher_wellbeing.router)
    app.include_router(employer.router)
    app.include_router(teacher_employer.router)
    app.include_router(bank.router)

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

# Global: när nästa demo-reset körs. Publik via /demo/status.
next_demo_reset_at = None


DEMO_RESET_INTERVAL_SECONDS = 600  # 10 min


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
async def _demo_seed_and_scheduler() -> None:
    """School-mode: bygg upp demo-läraren + starta 10-min-reset-loop.
    Skippas tyst om school-mode inte är aktivt eller om init misslyckas."""
    import os as _os
    import asyncio
    from datetime import datetime, timedelta
    global next_demo_reset_at

    try:
        from .school import is_enabled
        if not is_enabled():
            return
        from .school.engines import init_master_engine
        from .school.demo_seed import build_demo
        init_master_engine()
        # Första build
        stats = build_demo()
        next_demo_reset_at = datetime.utcnow() + timedelta(
            seconds=DEMO_RESET_INTERVAL_SECONDS,
        )
        logging.getLogger(__name__).info("demo seed: %s", stats)

        async def _reset_loop():
            global next_demo_reset_at
            while True:
                try:
                    await asyncio.sleep(DEMO_RESET_INTERVAL_SECONDS)
                    s = build_demo()
                    next_demo_reset_at = datetime.utcnow() + timedelta(
                        seconds=DEMO_RESET_INTERVAL_SECONDS,
                    )
                    logging.getLogger(__name__).info("demo reset: %s", s)
                except asyncio.CancelledError:
                    break
                except Exception:
                    logging.getLogger(__name__).exception("demo reset misslyckades")

        asyncio.create_task(_reset_loop())
    except Exception:
        logging.getLogger(__name__).exception("demo seed misslyckades")


@app.on_event("startup")
def _school_bootstrap() -> None:
    """Vid school-mode: initiera master-DB + skapa första läraren från
    env-vars om de är satta och inga lärare finns + seed räntor."""
    import os as _os
    try:
        from .school import is_enabled
        if not is_enabled():
            return
        from .school.engines import init_master_engine, master_session
        from .school.models import InterestRateSeries, Teacher
        from .school.rates import seed_static_series
        from .security.crypto import hash_password

        init_master_engine()

        email = _os.environ.get("HEMBUDGET_BOOTSTRAP_TEACHER_EMAIL")
        password = _os.environ.get("HEMBUDGET_BOOTSTRAP_TEACHER_PASSWORD")
        name = _os.environ.get("HEMBUDGET_BOOTSTRAP_TEACHER_NAME", "Lärare")
        with master_session() as s:
            # Ignorera demo-lärare vid denna check — demo-läraren
            # återskapas vid varje startup och ska inte blockera att
            # env-var-bootstrap skapar den första riktiga admin.
            real_count = s.query(Teacher).filter(
                Teacher.is_demo.is_(False),
            ).count()
            if email and password and real_count == 0:
                # Första riktiga läraren blir auto super-admin (kan toggla
                # AI för övriga lärare).
                s.add(Teacher(
                    email=email.lower(),
                    name=name,
                    password_hash=hash_password(password),
                    is_super_admin=True,
                ))
                logging.getLogger(__name__).info(
                    "school: created bootstrap teacher %s (super-admin)", email,
                )
            # Seed räntor om InterestRateSeries är tom
            if s.query(InterestRateSeries).count() == 0:
                n = seed_static_series(s)
                logging.getLogger(__name__).info(
                    "school: seeded %d interest rate rows (static)", n,
                )
            # Seed system-kompetenser
            from .school.competency_seed import seed_system_competencies
            n = seed_system_competencies(s)
            if n > 0:
                logging.getLogger(__name__).info(
                    "school: seeded %d system competencies", n,
                )
            # Seed systemmall-moduler
            from .school.module_seed import seed_system_modules
            nm = seed_system_modules(s)
            if nm > 0:
                logging.getLogger(__name__).info(
                    "school: seeded %d system modules", nm,
                )
            # Seed landningssidans gallery-slots (utan bilder — super-
            # admin laddar upp via /admin/landing/gallery)
            from .school.landing_seed import seed_landing_assets
            nl = seed_landing_assets(s)
            if nl > 0:
                logging.getLogger(__name__).info(
                    "school: seeded %d landing asset slots", nl,
                )
            # Seed aktie-universum + börskalender (idempotent).
            # Krävs innan POST /stocks/internal/poll-quotes kan användas.
            from .school.stock_seed import seed_all as seed_stocks_all
            ns = seed_stocks_all(s)
            if ns["stocks_added"] or ns["calendar_days_added"]:
                logging.getLogger(__name__).info(
                    "school: seeded %d stocks + %d calendar days",
                    ns["stocks_added"], ns["calendar_days_added"],
                )
            # Seed event-templates (Wellbeing-events fas 2). Idempotent.
            from .school.event_seed import seed_event_templates
            ne = seed_event_templates(s)
            if ne > 0:
                logging.getLogger(__name__).info(
                    "school: seeded %d event templates", ne,
                )
            # Seed kollektivavtal + yrke→avtal-mappningar
            # (idé 1 i dev_v1.md). Idempotent.
            from .school.employer_seed import seed_all as seed_employer_all
            ner = seed_employer_all(s)
            if ner["agreements_added"] or ner["profession_mappings_added"]:
                logging.getLogger(__name__).info(
                    "school: seeded %d agreements + %d profession mappings",
                    ner["agreements_added"], ner["profession_mappings_added"],
                )
            # Bootstrap: om LatestStockQuote är tom efter att StockMaster
            # har seedats, kör en force-poll så det finns kursdata direkt
            # vid boot — annars visar frontend tomma rader tills nästa
            # marknadsöppning.
            from .school.stock_models import LatestStockQuote
            from .stocks.poller import poll_quotes
            if s.query(LatestStockQuote).count() == 0:
                try:
                    pr = poll_quotes(s, force=True)
                    logging.getLogger(__name__).info(
                        "school: bootstrap-pollade %d kursrader (provider %s)",
                        pr["fetched"],
                        s.bind.dialect.name if s.bind else "?",
                    )
                except Exception:
                    logging.getLogger(__name__).exception(
                        "school: bootstrap-poll misslyckades — fortsätter ändå"
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

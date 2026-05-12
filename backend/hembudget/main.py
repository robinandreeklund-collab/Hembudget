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
    admin, ai, ai_admin, allabolag, arbetsformedlingen, auth, backup,
    balances, bank, biz_class_actions, boendemarknad, budget, chat,
    company_jobs, credit, elpris, email_auth, employer, foretag,
    foretag_annual_report, foretag_capacity, foretag_engine,
    foretag_growth, funds,
    game_engine, landing, leaderboard, ledger, loans, modules, reports,
    scenarios, school, settings_kv, shared_opportunities, smtp_admin,
    stock_trading, stocks, tax, events, teacher_ai_prompts, teacher_credit,
    teacher_employer, teacher_stocks, teacher_wellbeing, transactions,
    transfers, upcoming, upload, utility, v2, wellbeing,
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
        # FastAPI:s auto-docs flyttas till /api/* så /docs är fri för
        # editorial-dokumentationen som SPA:n serverar.
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
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

        # === V1 legacy gating ===
        # V2-frontend anropar bara /v2/*-endpoints (verifierat). V1
        # endpoints (/budget/*, /balances/*, /users, m.fl.) drog
        # tidigare ner scope-poolen eftersom legacy frontend-tabbar
        # eller cachade browser-states fortfarande pollade dem.
        # Pool 2+3 räckte inte → 13 parallella V1 requests timeoutade
        # på 30 s.
        # Vi returnerar nu 410 Gone direkt i middleware för dessa
        # paths i school-mode → frontend retryar inte, och inga
        # connections allokeras alls för legacy-trafik.
        # Lägg till mer paths här om Cloud Logging visar fler V1-fail.
        _V1_BLOCKED_PREFIXES = (
            "/budget/",
            "/balances/",
            "/wellbeing/",
            "/transfers/",
            "/upcoming/",
            "/funds/",
            "/scenarios/",
            "/reports/",
            "/ledger/",
            "/loans/",
            "/transactions",  # exact + sub-paths
            "/elpris",
            "/utility/",
        )
        _V1_BLOCKED_EXACT = {
            "/users",
            # /events/* används av V2 (sociala händelser, klasskompis-
            # bjudningar) — får INTE blockeras här. Tidigare blockerades
            # /events/pending + /events/decline-streak för att V1 drog
            # ner scope-poolen, men nu är endpointarna integrerade i
            # V2-frontenden (EventsV2 + Hub-feed + notifications).
        }

        class V1LegacyGateMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                path = request.url.path
                if (
                    path in _V1_BLOCKED_EXACT
                    or any(
                        path.startswith(p) for p in _V1_BLOCKED_PREFIXES
                    )
                ):
                    from starlette.responses import JSONResponse
                    return JSONResponse(
                        status_code=410,
                        content={
                            "detail": "Legacy V1-endpoint avstängd i "
                            "school-mode. Använd /v2/*-motsvarigheten.",
                        },
                    )
                return await call_next(request)

        app.add_middleware(V1LegacyGateMiddleware)

        # In-memory TTL-cache för (student_id, teacher_id) → scope_key.
        # Tidigare gjorde middlewaren EN master-DB-query per
        # autentiserad request bara för att slå upp scope-nyckeln.
        # Med Cloud SQL-poolen begränsad till 4+4 connections och
        # concurrency=40 blev detta en konstant flaskhals — eleven
        # såg "väntan hela tiden". Nu cachas resultatet 5 min per
        # (student_id, teacher_id)-kombination. När eleven byter
        # familj (s_X → f_Y) tar det max 5 min innan middlewaren
        # plockar upp den nya scope-nyckeln.
        import time as _time
        _scope_cache: dict[
            tuple[int, int | None], tuple[float, str, int]
        ] = {}
        _SCOPE_CACHE_TTL = 300.0

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
                            now = _time.monotonic()
                            cache_key = (
                                target_id,
                                info.teacher_id
                                if info.role == "teacher" else None,
                            )
                            entry = _scope_cache.get(cache_key)
                            scope_key: str | None = None
                            actor_id: int | None = None
                            if entry is not None and entry[0] > now:
                                _, scope_key, actor_id = entry
                            else:
                                with master_session() as s:
                                    q = s.query(Student).filter(
                                        Student.id == target_id,
                                    )
                                    if info.role == "teacher":
                                        q = q.filter(
                                            Student.teacher_id
                                            == info.teacher_id,
                                        )
                                    stu = q.first()
                                    if stu:
                                        scope_key = scope_for_student(stu)
                                        actor_id = stu.id
                                        _scope_cache[cache_key] = (
                                            now + _SCOPE_CACHE_TTL,
                                            scope_key, actor_id,
                                        )
                            if scope_key is not None and actor_id is not None:
                                set_current_scope(scope_key)
                                set_current_actor_student(actor_id)
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
    # V2-alias för ledger-routern. Eleven anropar /v2/ledger/... från
    # V2-frontenden så vi garanterat aldrig krockar med
    # V1LegacyGateMiddleware (/ledger/ är V1-blockerad pga
    # historisk pool-issues, men huvudbok-funktionen är pedagogiskt
    # värdefull även för V2). Båda paths landar på samma handlers.
    app.include_router(ledger.router, prefix="/v2")
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
    app.include_router(teacher_ai_prompts.router)
    app.include_router(allabolag.router)
    app.include_router(foretag_annual_report.router)
    app.include_router(shared_opportunities.router)
    app.include_router(company_jobs.owner_router)
    app.include_router(company_jobs.seeker_router)
    app.include_router(foretag_growth.router)
    app.include_router(foretag_capacity.router)
    app.include_router(leaderboard.router)
    app.include_router(biz_class_actions.mentor_router)
    app.include_router(biz_class_actions.event_router)
    app.include_router(wellbeing.router)
    app.include_router(events.router)
    # V2-alias för events-routern. Eleven anropar /v2/events/... från
    # V2-frontenden så vi garanterat aldrig krockar med V1LegacyGate-
    # middleware. Båda paths landar på samma handlers — tester och
    # V1-baserade kod fortsätter använda /events/...
    app.include_router(events.router, prefix="/v2")
    app.include_router(teacher_wellbeing.router)
    app.include_router(employer.router)
    app.include_router(teacher_employer.router)
    app.include_router(bank.router)

    # === V2 (parallell migration · ny dashboard) ===
    # Kör bredvid v1. Ingen befintlig endpoint berörs.
    app.include_router(v2.router)
    # Spelmotor: ClassCalendar + Profile Generator preview-endpoint.
    # Spec: dev/game-motor/
    app.include_router(game_engine.router)
    # Boendemarknad (Sprint 5 · B1-B5): listings, valuation, köp/sälj.
    app.include_router(boendemarknad.router)
    app.include_router(boendemarknad.teacher_router)
    # Arbetsförmedlingen (Sprint 6 · A1-A5): jobs + 5-rond intervju.
    app.include_router(arbetsformedlingen.router)
    app.include_router(arbetsformedlingen.teacher_router)
    # Företagsläget (Bug #7-utbyggnad): bolag + transaktioner + lön + moms.
    app.include_router(foretag.router)
    app.include_router(foretag.teacher_router)
    # Företagsläget · spelmotor (deb/README.md fas 2-3):
    # offerter, jobb, marknadsföring, beslut, leverantörsfakturor, tick.
    app.include_router(foretag_engine.router)
    app.include_router(foretag_engine.teacher_router)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True, "version": "0.1.0"}

    # === In-memory ring-buffer för senaste exceptions ===
    # Auth-fri exposure via /healthz/errors. Eliminerar behovet av
    # gcloud logging read när vi behöver felsöka prod snabbt.
    # Begränsat till 50 senaste, max ~50 KB minne.
    from collections import deque as _deque_err
    import threading as _threading_err
    import traceback as _tb_err
    from datetime import datetime as _dt_err
    _error_buffer: _deque_err = _deque_err(maxlen=50)
    _error_lock = _threading_err.Lock()

    def _record_exception(
        request: "Request | None", exc: BaseException,
    ) -> None:
        try:
            # Följ chain till ROOT-exception (cause/context). En
            # 'generator didn't stop after throw()' är vanligen ett
            # CLEANUP-fel — det riktiga felet ligger i .__context__
            # eller .__cause__.
            root = exc
            seen = {id(root)}
            while True:
                inner = root.__cause__ or root.__context__
                if inner is None or id(inner) in seen:
                    break
                seen.add(id(inner))
                root = inner

            with _error_lock:
                _error_buffer.append({
                    "ts": _dt_err.utcnow().isoformat() + "Z",
                    "type": type(exc).__name__,
                    "message": str(exc)[:500],
                    "root_type": type(root).__name__ if root is not exc else None,
                    "root_message": (
                        str(root)[:500] if root is not exc else None
                    ),
                    "path": (
                        str(request.url.path) if request is not None
                        else None
                    ),
                    "method": (
                        request.method if request is not None else None
                    ),
                    "traceback": "".join(
                        _tb_err.format_exception(
                            type(exc), exc, exc.__traceback__,
                        ),
                    )[-2000:],
                    "root_traceback": (
                        "".join(
                            _tb_err.format_exception(
                                type(root), root, root.__traceback__,
                            ),
                        )[-2000:]
                        if root is not exc else None
                    ),
                })
        except Exception:
            pass

    # Globalexception-handler som loggar in errors EFTER att
    # FastAPI:s default-handler kört.
    from fastapi import Request as _RequestFastAPI
    from fastapi.responses import JSONResponse as _JSONResponseFastAPI

    @app.exception_handler(Exception)
    async def _capture_exception(
        request: _RequestFastAPI, exc: Exception,
    ):
        _record_exception(request, exc)
        # Re-raise vanlig 500 så FastAPI:s default-error-page visas
        return _JSONResponseFastAPI(
            status_code=500,
            content={"detail": "Internal Server Error"},
        )

    @app.get("/healthz/errors")
    def healthz_errors(limit: int = 20) -> dict:
        """Senaste exceptions in-memory (för snabb felsökning utan
        gcloud logging). Auth-fri."""
        with _error_lock:
            items = list(_error_buffer)[-limit:]
        return {
            "count": len(items),
            "errors": list(reversed(items)),  # nyast först
        }

    @app.get("/healthz/cleanup-stale-conns")
    def healthz_cleanup_stale_conns() -> dict:
        """Manuell fix för Cloud SQL-saturation: pg_terminate_backend
        på alla connections från ANDRA Cloud Run-revisioner (gamla
        revisioner som hänger kvar med idle conn).

        Auth-fri så användaren kan curla från mobilen för att
        omedelbart frigöra Cloud SQL-slots utan gcloud-tillgång.

        Använder master_engine:s EXISTERANDE pool så vi återanvänder
        en redan-öppen connection. Om vi öppnade en ny via NullPool
        skulle den failas när Cloud SQL är fullt — och det är
        precis då vi behöver detta verktyg.
        """
        import os as _os_clean
        out: dict = {
            "current_revision": _os_clean.environ.get("K_REVISION", ""),
            "killed": [],
            "total_killed": 0,
        }
        try:
            from sqlalchemy import text as _text_clean
            from .school.engines import _master_engine as _me_clean
            if _me_clean is None:
                out["error"] = "master_engine not initialized"
                return out
            current_rev = _os_clean.environ.get("K_REVISION", "")
            current_marker = (
                f"@{current_rev}" if current_rev else "@local"
            )
            with _me_clean.connect() as conn:
                # Lista connections som är "stale":
                # - andra revisioner (application_name börjar med
                #   'hembudget' men matchar inte current)
                # - ELLER application_name är NULL/tom OCH connection
                #   är "idle in transaction" eller "idle" + > 60s gammal
                #   (gamla revisioners glömda connections)
                rows = conn.execute(_text_clean(
                    """
                    SELECT pid, application_name, state,
                           extract(epoch from now() - backend_start)::int
                             as age_seconds
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                      AND pid <> pg_backend_pid()
                      AND (
                        (application_name LIKE 'hembudget%'
                         AND application_name NOT LIKE :current)
                        OR (
                          (application_name IS NULL
                           OR application_name = '')
                          AND state IN ('idle', 'idle in transaction')
                          AND extract(epoch from now() - backend_start) > 60
                        )
                      )
                    """,
                ), {"current": f"%{current_marker}%"}).fetchall()
                for pid, app_name, state, age in rows:
                    try:
                        conn.execute(_text_clean(
                            "SELECT pg_terminate_backend(:p)",
                        ), {"p": pid})
                        out["killed"].append({
                            "pid": int(pid),
                            "application": app_name or "(unset)",
                            "state": state,
                            "age_seconds": int(age) if age else None,
                        })
                    except Exception as e:
                        out["killed"].append({
                            "pid": int(pid),
                            "application": app_name or "(unset)",
                            "state": state,
                            "error": str(e)[:200],
                        })
                conn.commit()
            out["total_killed"] = sum(
                1 for k in out["killed"] if "error" not in k
            )
        except Exception as e:
            out["error"] = repr(e)
        return out

    @app.get("/healthz/db")
    def healthz_db() -> dict:
        """Diagnostik · pool-config + aktuell användning + Cloud SQL
        connection-state via pg_stat_activity. Auth-fri så man kan
        curla från terminalen för att se vad SOM faktiskt händer i
        prod (gamla revisioner som håller connections etc.)."""
        import os as _os_diag
        import socket as _socket_diag
        out: dict = {
            "hostname": _socket_diag.gethostname(),
            "revision": _os_diag.environ.get(
                "K_REVISION", "",
            ),  # Cloud Run sätter K_REVISION
            "school_mode": _os_diag.environ.get(
                "HEMBUDGET_SCHOOL_MODE", "",
            ),
            "has_database_url": bool(
                _os_diag.environ.get("HEMBUDGET_DATABASE_URL", "").strip(),
            ),
            "engines": {},
            "postgres": {},
        }
        try:
            from .school import engines as _eng
            for label, engine in (
                ("master", _eng._master_engine),
                ("scope_shared", _eng._shared_scope_engine),
            ):
                if engine is None:
                    out["engines"][label] = {"initialized": False}
                    continue
                pool = engine.pool
                stats: dict = {
                    "initialized": True,
                    "is_same_as_master": (
                        engine is _eng._master_engine
                        and label != "master"
                    ),
                    "pool_class": type(pool).__name__,
                }
                # NullPool och QueuePool har olika introspection-API.
                # Inget av dessa får krascha här — endpoint:en är
                # diagnostik och måste alltid svara.
                for attr_name in (
                    "size", "checkedout", "checkedin", "overflow",
                ):
                    try:
                        fn = getattr(pool, attr_name, None)
                        stats[attr_name] = fn() if callable(fn) else None
                    except Exception:
                        stats[attr_name] = None
                out["engines"][label] = stats
        except Exception as e:
            out["engines_error"] = repr(e)

        # === Cloud SQL postgres-state via pg_stat_activity ===
        # Visar TOTAL connection-bild på Postgres-sidan, inte bara vår
        # pool. Använder en EGEN connection (NullPool) som bypass:ar
        # vår vanliga pool — annars går diagnostiken inte att köra
        # när poolen är saturerad (vilket är PRECIS NÄR vi behöver den).
        try:
            from sqlalchemy import (
                create_engine as _ce_diag, text as _text_diag,
            )
            from sqlalchemy.pool import NullPool as _NullPool_diag
            from .school.engines import (
                _master_engine as _me_diag, _master_db_url as _murl_diag,
            )
            if _me_diag is not None:
                _diag_url = _murl_diag()
                _diag_engine = _ce_diag(
                    _diag_url, poolclass=_NullPool_diag,
                    connect_args={
                        "connect_timeout": 3,
                        "application_name": "hembudget-diag",
                        "options": "-c statement_timeout=5000",
                    } if _diag_url.startswith("postgresql") else {},
                )
                with _diag_engine.connect() as conn:
                    result = conn.execute(_text_diag(
                        """
                        SELECT
                            state,
                            count(*) as n,
                            min(extract(epoch from now() - state_change))::int as oldest_seconds,
                            max(extract(epoch from now() - backend_start))::int as oldest_backend_seconds
                        FROM pg_stat_activity
                        WHERE datname = current_database()
                          AND pid <> pg_backend_pid()
                        GROUP BY state
                        ORDER BY state NULLS FIRST
                        """,
                    ))
                    by_state: list[dict] = []
                    total = 0
                    for row in result:
                        by_state.append({
                            "state": row[0] or "(null)",
                            "count": int(row[1]),
                            "oldest_in_state_seconds": (
                                int(row[2]) if row[2] is not None else None
                            ),
                            "oldest_backend_seconds": (
                                int(row[3]) if row[3] is not None else None
                            ),
                        })
                        total += int(row[1])
                    out["postgres"]["by_state"] = by_state
                    out["postgres"]["total_connections"] = total
                    # max_connections från servern
                    mc = conn.execute(_text_diag(
                        "SHOW max_connections",
                    )).scalar()
                    out["postgres"]["max_connections"] = int(mc)
                    # Connections per application_name (visar om gamla
                    # revisioner håller pool — de använder sannolikt
                    # samma SQLAlchemy-default name).
                    apps = conn.execute(_text_diag(
                        """
                        SELECT
                            application_name,
                            count(*) as n
                        FROM pg_stat_activity
                        WHERE datname = current_database()
                          AND pid <> pg_backend_pid()
                        GROUP BY application_name
                        ORDER BY n DESC
                        """,
                    ))
                    out["postgres"]["by_application"] = [
                        {"application": r[0] or "(unset)", "count": int(r[1])}
                        for r in apps
                    ]
        except Exception as e:
            out["postgres"]["error"] = repr(e)

        return out

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

    # Cache-Control för SPA-shell — viktigt: HTML får ALDRIG cachas
    # av webbläsaren, annars kan en gammal index.html peka på en
    # raderad /assets/index-XXX.js efter deploy. Vite genererar
    # hash-baserade asset-namn så /assets/* får långtids-cache, men
    # själva index.html måste alltid revalideras.
    _NO_CACHE_HEADERS = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    @app.get("/", include_in_schema=False)
    def _spa_root() -> FileResponse:
        # Public landing = demo-landing/index.html (editorial sida som
        # presenterar Linda/Peter/Evelina). SPA-shellet bor på /login
        # och underliggande react-routes; alla SPA-routes faller tillbaka
        # via _spa_fallback nedan.
        landing = dist / "demo-landing" / "index.html"
        if landing.is_file():
            return FileResponse(str(landing), headers=_NO_CACHE_HEADERS)
        return FileResponse(str(dist / "index.html"), headers=_NO_CACHE_HEADERS)

    # Snygga URLs för persona-sagorna — pekar på respektive saga-HTML
    # som ligger statiskt under demo-landing/. Linda kvar på pretty-URL
    # `/linda` istället för dess legacy-filnamn.
    _SAGA_FILES = {
        "linda":   dist / "demo-landing" / "4-vecka-djupdyk.html",
        "peter":   dist / "demo-landing" / "peter-vecka.html",
        "evelina": dist / "demo-landing" / "evelina-vecka.html",
    }
    for _slug, _path in _SAGA_FILES.items():
        def _make(p: Path):
            def _serve() -> FileResponse:
                if p.is_file():
                    return FileResponse(str(p), headers=_NO_CACHE_HEADERS)
                return FileResponse(
                    str(dist / "index.html"), headers=_NO_CACHE_HEADERS,
                )
            return _serve
        app.add_api_route(
            "/" + _slug,
            _make(_path),
            methods=["GET"],
            include_in_schema=False,
        )

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
            # Statiska assets (bilder, fonts, /assets/*) får cachas länge
            # — Vite hashar filnamn så de invalideras automatiskt vid
            # ny deploy. Men HTML-filer (t.ex. demo-landing-sagor) ska
            # aldrig cachas.
            if target.suffix.lower() in (".html", ".htm"):
                return FileResponse(str(target), headers=_NO_CACHE_HEADERS)
            return FileResponse(str(target))
        # Directory? → serva dess egna index.html om den finns
        # (gör att /demo-landing/ pekar på frontend/dist/demo-landing/index.html
        # istället för huvudappens SPA)
        if target.is_dir():
            dir_index = target / "index.html"
            if dir_index.is_file():
                return FileResponse(
                    str(dir_index), headers=_NO_CACHE_HEADERS,
                )
        return FileResponse(str(dist / "index.html"), headers=_NO_CACHE_HEADERS)


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

        # build_demo() är TUNG (rensar + återskapar lärare + 5 elever +
        # 15 batchar + 69 artefakter på ~6 s lokalt, längre på Cloud Run
        # där varje DB-rundtur kostar mer). Synkron i startup-hook
        # spränger Cloud Run:s 240 s startup-probe-timeout.
        # Lösning: kör först-bygget i background-tråd. Eleverna har
        # redan data från förra deployens reset-loop, så det är OK
        # att vänta in 5-10 s tills bakgrunden klar.
        async def _initial_build_then_loop():
            global next_demo_reset_at
            import asyncio as _aio
            try:
                stats = await _aio.to_thread(build_demo)
                next_demo_reset_at = datetime.utcnow() + timedelta(
                    seconds=DEMO_RESET_INTERVAL_SECONDS,
                )
                logging.getLogger(__name__).info("demo seed: %s", stats)
            except Exception:
                logging.getLogger(__name__).exception(
                    "demo seed (initial) misslyckades"
                )

            while True:
                try:
                    await _aio.sleep(DEMO_RESET_INTERVAL_SECONDS)
                    s = await _aio.to_thread(build_demo)
                    next_demo_reset_at = datetime.utcnow() + timedelta(
                        seconds=DEMO_RESET_INTERVAL_SECONDS,
                    )
                    logging.getLogger(__name__).info("demo reset: %s", s)
                except _aio.CancelledError:
                    break
                except Exception:
                    logging.getLogger(__name__).exception(
                        "demo reset misslyckades"
                    )

        asyncio.create_task(_initial_build_then_loop())
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
            # Seed initiala beta-koder från env-var (en gång per kod —
            # idempotent via uq_beta_code_norm).
            # Format: HEMBUDGET_BETA_INITIAL_CODES="CODE1:50,CODE2:5"
            #         där siffran är max_uses (default 1 om utelämnad).
            try:
                from .school.models import BetaCode
                raw = _os.environ.get(
                    "HEMBUDGET_BETA_INITIAL_CODES", "",
                ).strip()
                added_codes = 0
                for entry in raw.split(","):
                    entry = entry.strip()
                    if not entry:
                        continue
                    if ":" in entry:
                        code_part, max_part = entry.split(":", 1)
                        try:
                            max_uses = max(1, int(max_part.strip()))
                        except ValueError:
                            max_uses = 1
                    else:
                        code_part, max_uses = entry, 1
                    code_part = code_part.strip()
                    if not code_part:
                        continue
                    norm = code_part.upper()
                    existing = (
                        s.query(BetaCode)
                        .filter(BetaCode.code_norm == norm)
                        .first()
                    )
                    if existing is None:
                        s.add(BetaCode(
                            code=code_part, code_norm=norm,
                            max_uses=max_uses, uses_count=0, active=True,
                            notes="seedad från HEMBUDGET_BETA_INITIAL_CODES",
                        ))
                        added_codes += 1
                if added_codes > 0:
                    s.flush()
                    logging.getLogger(__name__).info(
                        "school: seeded %d beta-codes", added_codes,
                    )
            except Exception:
                logging.getLogger(__name__).exception(
                    "school: beta-code seed failed — fortsätter",
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
            # Bug #9 · Seed AgreementBenefit + MarketSalaryRange så att
            # ArbetsgivarenV2 visar förmåner direkt utan att lärar-
            # action behövs.
            from .school.employer_market_seed import (
                seed_default_agreement_benefits,
                seed_default_market_salary_ranges,
            )
            try:
                nab = seed_default_agreement_benefits(s)
                nms = seed_default_market_salary_ranges(s)
                if nab or nms:
                    logging.getLogger(__name__).info(
                        "school: seeded %d agreement benefits + %d market ranges",
                        nab, nms,
                    )
            except Exception:
                logging.getLogger(__name__).exception(
                    "school: agreement-benefits/market-ranges seed failed",
                )
            # Bootstrap: om LatestStockQuote är tom efter att StockMaster
            # har seedats, kör en force-poll så det finns kursdata direkt
            # vid boot — annars visar frontend tomma rader tills nästa
            # marknadsöppning.
            #
            # OBS: poll_quotes anropar yfinance/finnhub som kan blockera
            # i flera SEKUNDER per ticker. På Cloud Run hängde detta
            # förbi startup-probe-timeouten (240 s) → containern
            # bands aldrig till port 8080 → CI rött. Lösning: trigga
            # i en bakgrundstråd så startup-hooken returnerar direkt.
            from .school.stock_models import LatestStockQuote
            from .stocks.poller import poll_quotes
            # Bootstrap-poll trigger om:
            # · LatestStockQuote tom (första container-starten)
            # · ELLER senaste kurs är > 24 h gammal (deploy efter
            #   helg, eller poller-tråden dog och datan blev stale)
            from datetime import datetime as _dt_boot
            needs_bootstrap_poll = False
            try:
                latest = (
                    s.query(LatestStockQuote)
                    .order_by(LatestStockQuote.ts.desc())
                    .first()
                )
                if latest is None:
                    needs_bootstrap_poll = True
                elif latest.ts is not None:
                    age_h = (
                        _dt_boot.utcnow() - latest.ts
                    ).total_seconds() / 3600
                    if age_h > 24:
                        needs_bootstrap_poll = True
            except Exception:
                needs_bootstrap_poll = True

            if needs_bootstrap_poll:
                def _bg_stock_poll():
                    import logging as _log
                    try:
                        from .school.engines import master_session as _ms
                        with _ms() as _s:
                            pr = poll_quotes(_s, force=True)
                            _log.getLogger(__name__).info(
                                "school: bootstrap-pollade %d "
                                "kursrader (background)",
                                pr["fetched"],
                            )
                    except Exception:
                        _log.getLogger(__name__).exception(
                            "school: bootstrap-poll misslyckades "
                            "(background) — fortsätter ändå"
                        )
                import threading as _threading
                _threading.Thread(
                    target=_bg_stock_poll,
                    name="bootstrap-stock-poll",
                    daemon=True,
                ).start()

            # ===========================================================
            # Periodisk kurs-poller · uppdaterar LatestStockQuote var 5 min
            # under börstid. Utan denna stannar kurserna på det pris som
            # bootstrap-pollen satte → eleven ser samma siffror oavsett
            # hur länge appen körts. Cloud Scheduler kan också pinga
            # /stocks/internal/poll-quotes men vi vill inte kräva extern
            # konfig för att grunddata ska vara levande.
            #
            # daemon=True → tråden stoppar när containern stängs. Cloud
            # Run --max-instances=1 garanterar att bara EN tråd pollar.
            # ===========================================================
            from .school.stock_models import LatestStockQuote as _LSQ_p
            from .stocks.poller import poll_quotes as _pq
            import threading as _threading_p

            def _periodic_stock_poll() -> None:
                import logging as _log_p
                import time as _time_p
                from .school.engines import master_session as _ms_p
                # Vänta 60 s första gången så bootstrap-pollen hinner
                # klart innan vi börjar konkurrera om DB-locket.
                _time_p.sleep(60)
                while True:
                    try:
                        with _ms_p() as _s_p:
                            res = _pq(_s_p, force=False)
                        if res.get("fetched", 0) > 0:
                            _log_p.getLogger(__name__).info(
                                "periodic-stock-poll: uppdaterade %d kurser",
                                res["fetched"],
                            )
                    except Exception:
                        _log_p.getLogger(__name__).exception(
                            "periodic-stock-poll: pollning misslyckades "
                            "— försöker igen om 5 min",
                        )
                    # 5 min mellan körningar · under börstid blir det
                    # ~10 polls per dag, well within yfinance/finnhub limits.
                    _time_p.sleep(300)

            _threading_p.Thread(
                target=_periodic_stock_poll,
                name="periodic-stock-poll",
                daemon=True,
            ).start()
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

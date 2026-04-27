"""Super-admin-endpoints för att styra AI-åtkomst per lärare.

Endast lärare med `is_super_admin = True` får anropa dessa. Första
bootstrap-läraren blir auto super-admin. Övriga lärare får AI som
default = False — inga AI-anrop går igenom förrän super-admin toggar
på det.

Endpoints:
- GET  /admin/ai/status             — är AI-klienten över huvud taget uppe?
- GET  /admin/ai/teachers           — lista lärare + deras ai_enabled-flagga
- POST /admin/ai/teachers/{id}/ai   — toggla ai_enabled för en lärare
- POST /admin/ai/teachers/{id}/super — toggla is_super_admin för en lärare
- GET  /admin/ai/api-key            — visa källa + sista-4 av aktiv nyckel
- POST /admin/ai/api-key            — sätt eller uppdatera nyckel (DB)
- DELETE /admin/ai/api-key          — rensa DB-nyckeln (faller ev. tillbaka
                                       till env-var)
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..school import is_enabled as school_enabled
from ..school import ai as ai_core
from ..school.ai import is_available as ai_available
from ..school.engines import master_session
from ..school.models import AppConfig, Teacher
from .deps import TokenInfo, require_teacher

router = APIRouter(prefix="/admin/ai", tags=["admin-ai"])


def _require_super_admin(info: TokenInfo = Depends(require_teacher)) -> TokenInfo:
    if not school_enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "School mode inaktivt")
    with master_session() as s:
        t = s.get(Teacher, info.teacher_id)
        if not t or not t.is_super_admin:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Super-admin krävs",
            )
    return info


class AIStatusOut(BaseModel):
    client_available: bool
    """Om ANTHROPIC_API_KEY är satt + anthropic-paketet kunde laddas."""


class TeacherAIRow(BaseModel):
    id: int
    email: str
    name: str
    active: bool
    is_super_admin: bool
    is_demo: bool
    ai_enabled: bool
    ai_requests_count: int
    ai_input_tokens: int
    ai_output_tokens: int


class ToggleIn(BaseModel):
    enabled: bool


@router.get("/status", response_model=AIStatusOut)
def ai_status(_: TokenInfo = Depends(_require_super_admin)) -> AIStatusOut:
    return AIStatusOut(client_available=ai_available())


@router.get("/teachers", response_model=list[TeacherAIRow])
def list_teachers(
    _: TokenInfo = Depends(_require_super_admin),
) -> list[TeacherAIRow]:
    with master_session() as s:
        teachers = s.query(Teacher).order_by(Teacher.id.asc()).all()
        return [
            TeacherAIRow(
                id=t.id,
                email=t.email,
                name=t.name,
                active=t.active,
                is_super_admin=t.is_super_admin,
                is_demo=t.is_demo,
                ai_enabled=t.ai_enabled,
                ai_requests_count=t.ai_requests_count,
                ai_input_tokens=t.ai_input_tokens,
                ai_output_tokens=t.ai_output_tokens,
            )
            for t in teachers
        ]


@router.post("/teachers/{teacher_id}/ai", response_model=TeacherAIRow)
def toggle_ai(
    teacher_id: int,
    payload: ToggleIn,
    _: TokenInfo = Depends(_require_super_admin),
) -> TeacherAIRow:
    with master_session() as s:
        t = s.get(Teacher, teacher_id)
        if not t:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Lärare finns ej")
        t.ai_enabled = payload.enabled
        s.flush()
        return TeacherAIRow(
            id=t.id,
            email=t.email,
            name=t.name,
            active=t.active,
            is_super_admin=t.is_super_admin,
            is_demo=t.is_demo,
            ai_enabled=t.ai_enabled,
            ai_requests_count=t.ai_requests_count,
            ai_input_tokens=t.ai_input_tokens,
            ai_output_tokens=t.ai_output_tokens,
        )


@router.post("/teachers/{teacher_id}/super", response_model=TeacherAIRow)
def toggle_super(
    teacher_id: int,
    payload: ToggleIn,
    info: TokenInfo = Depends(_require_super_admin),
) -> TeacherAIRow:
    if teacher_id == info.teacher_id and not payload.enabled:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Du kan inte ta bort din egen super-admin-status",
        )
    with master_session() as s:
        t = s.get(Teacher, teacher_id)
        if not t:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Lärare finns ej")
        t.is_super_admin = payload.enabled
        s.flush()
        return TeacherAIRow(
            id=t.id,
            email=t.email,
            name=t.name,
            active=t.active,
            is_super_admin=t.is_super_admin,
            is_demo=t.is_demo,
            ai_enabled=t.ai_enabled,
            ai_requests_count=t.ai_requests_count,
            ai_input_tokens=t.ai_input_tokens,
            ai_output_tokens=t.ai_output_tokens,
        )


# ---------- API-nyckel-hantering ----------

class ApiKeyStatusOut(BaseModel):
    configured: bool
    """True om det finns en nyckel (DB eller env) som klienten kan använda."""
    source: str
    """'db' (satt via UI), 'env' (fallback till miljövar) eller '' (ingen)."""
    preview: str
    """Sista 4 tecknen, t.ex. '…fG8w'. Tom om ingen nyckel."""
    client_available: bool
    """True om anthropic-klienten kunde initieras med nuvarande nyckel."""


class ApiKeyIn(BaseModel):
    key: str = Field(min_length=20, max_length=500)
    """Hela nyckeln från Anthropic. Valideras bara på längd — riktig
    verifiering sker vid första anrop."""


@router.get("/api-key", response_model=ApiKeyStatusOut)
def api_key_status(
    _: TokenInfo = Depends(_require_super_admin),
) -> ApiKeyStatusOut:
    return ApiKeyStatusOut(
        configured=ai_core.has_key_configured(),
        source=ai_core.key_source(),
        preview=ai_core.key_preview(),
        client_available=ai_available(),
    )


@router.post("/api-key", response_model=ApiKeyStatusOut)
def set_api_key(
    payload: ApiKeyIn,
    _: TokenInfo = Depends(_require_super_admin),
) -> ApiKeyStatusOut:
    """Spara (eller ersätta) API-nyckeln i master-DB:n. Skriver över
    ev. env-var eftersom DB vinner."""
    key = payload.key.strip()
    if not key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tom nyckel")
    with master_session() as s:
        cfg = s.get(AppConfig, ai_core.AI_KEY_CONFIG_KEY)
        if cfg is None:
            cfg = AppConfig(key=ai_core.AI_KEY_CONFIG_KEY, value={"key": key})
            s.add(cfg)
        else:
            cfg.value = {"key": key}
            cfg.updated_at = datetime.utcnow()
    ai_core.invalidate_client()
    # Tvinga omedelbar re-init så "client_available" i responsen är korrekt
    ai_core.is_available()
    return ApiKeyStatusOut(
        configured=ai_core.has_key_configured(),
        source=ai_core.key_source(),
        preview=ai_core.key_preview(),
        client_available=ai_available(),
    )


@router.delete("/api-key", response_model=ApiKeyStatusOut)
def delete_api_key(
    _: TokenInfo = Depends(_require_super_admin),
) -> ApiKeyStatusOut:
    """Rensa DB-nyckeln. Om ANTHROPIC_API_KEY finns i env faller vi
    tillbaka till den; annars blir AI inaktiverat."""
    with master_session() as s:
        cfg = s.get(AppConfig, ai_core.AI_KEY_CONFIG_KEY)
        if cfg is not None:
            s.delete(cfg)
    ai_core.invalidate_client()
    return ApiKeyStatusOut(
        configured=ai_core.has_key_configured(),
        source=ai_core.key_source(),
        preview=ai_core.key_preview(),
        client_available=ai_available(),
    )


@router.get("/me")
def ai_me(info: TokenInfo = Depends(require_teacher)) -> dict:
    """Används av frontend för att veta om den inloggade läraren har AI
    aktiverat OCH är super-admin (visar i så fall admin-länken)."""
    with master_session() as s:
        t = s.get(Teacher, info.teacher_id)
        if not t:
            return {
                "ai_enabled": False,
                "is_super_admin": False,
                "ai_available": False,
            }
        return {
            "ai_enabled": bool(t.ai_enabled),
            "is_super_admin": bool(t.is_super_admin),
            "ai_available": ai_available(),
        }


# ---------- Finnhub-API-nyckel (super-admin) ----------

class FinnhubKeyStatusOut(BaseModel):
    configured: bool
    source: str          # "db" | "env" | ""
    preview: str         # "…1234" eller ""


class FinnhubKeyIn(BaseModel):
    key: str


@router.get("/finnhub-key", response_model=FinnhubKeyStatusOut)
def finnhub_key_status(
    _: TokenInfo = Depends(_require_super_admin),
) -> FinnhubKeyStatusOut:
    from ..stocks.quote_providers import (
        finnhub_key_configured,
        finnhub_key_preview,
        finnhub_key_source,
    )
    return FinnhubKeyStatusOut(
        configured=finnhub_key_configured(),
        source=finnhub_key_source(),
        preview=finnhub_key_preview(),
    )


@router.post("/finnhub-key", response_model=FinnhubKeyStatusOut)
def set_finnhub_key(
    payload: FinnhubKeyIn,
    _: TokenInfo = Depends(_require_super_admin),
) -> FinnhubKeyStatusOut:
    """Spara/uppdatera Finnhub-nyckel i master-DB. Skriver över ev.
    env-var. Pollern plockar upp den vid nästa anrop."""
    from ..stocks.quote_providers import (
        FINNHUB_KEY_CONFIG_KEY,
        finnhub_key_configured,
        finnhub_key_preview,
        finnhub_key_source,
    )
    key = payload.key.strip()
    if not key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tom nyckel")
    with master_session() as s:
        cfg = s.get(AppConfig, FINNHUB_KEY_CONFIG_KEY)
        if cfg is None:
            cfg = AppConfig(key=FINNHUB_KEY_CONFIG_KEY, value={"key": key})
            s.add(cfg)
        else:
            cfg.value = {"key": key}
            cfg.updated_at = datetime.utcnow()
    return FinnhubKeyStatusOut(
        configured=finnhub_key_configured(),
        source=finnhub_key_source(),
        preview=finnhub_key_preview(),
    )


@router.delete("/finnhub-key", response_model=FinnhubKeyStatusOut)
def delete_finnhub_key(
    _: TokenInfo = Depends(_require_super_admin),
) -> FinnhubKeyStatusOut:
    """Rensa DB-nyckeln. Faller tillbaka till FINNHUB_API_KEY-env om
    satt, annars använder pollern MockQuoteProvider."""
    from ..stocks.quote_providers import (
        FINNHUB_KEY_CONFIG_KEY,
        finnhub_key_configured,
        finnhub_key_preview,
        finnhub_key_source,
    )
    with master_session() as s:
        cfg = s.get(AppConfig, FINNHUB_KEY_CONFIG_KEY)
        if cfg is not None:
            s.delete(cfg)
    return FinnhubKeyStatusOut(
        configured=finnhub_key_configured(),
        source=finnhub_key_source(),
        preview=finnhub_key_preview(),
    )


@router.post("/finnhub-test")
def finnhub_test(
    _: TokenInfo = Depends(_require_super_admin),
) -> dict:
    """Test-anrop: hämtar 1 quote från Finnhub för VOLV-B.ST. Bra för
    super-admin att verifiera att nyckeln fungerar utan att vänta på
    nästa polltick."""
    from ..stocks.quote_providers import FinnhubProvider
    p = FinnhubProvider()
    if not p.api_key:
        return {"ok": False, "error": "Ingen Finnhub-nyckel konfigurerad."}
    quotes = p.fetch_quotes(["VOLV-B.ST"])
    if not quotes:
        return {
            "ok": False,
            "error": "Inget kursvärde returnerat — verifiera nyckeln eller kontrollera nätverk.",
        }
    q = quotes[0]
    return {
        "ok": True,
        "ticker": q.ticker,
        "last": float(q.last),
        "change_pct": q.change_pct,
        "ts": q.ts.isoformat(),
    }


# ---------- Klassdisplay-inställningar (super-admin) ----------
#
# Per-lärar-toggles för klassgemensamma funktioner: anonymiserad
# rangordning, klasskompis-bjudningar, kostnadsmodell, anti-spam-tak.
# Default: minimal exponering (allt utom invitations är AV).

class ClassDisplaySettingsOut(BaseModel):
    teacher_id: int
    teacher_email: str
    teacher_name: str
    class_list_enabled: bool
    show_full_names: bool
    invite_classmates_enabled: bool
    cost_split_model: str  # "split" | "inviter_pays" | "each_pays_own"
    class_event_creation_enabled: bool
    max_invites_per_week: int


class ClassDisplaySettingsIn(BaseModel):
    teacher_id: int
    class_list_enabled: bool | None = None
    show_full_names: bool | None = None
    invite_classmates_enabled: bool | None = None
    cost_split_model: str | None = None
    class_event_creation_enabled: bool | None = None
    max_invites_per_week: int | None = None


@router.get("/class-display", response_model=list[ClassDisplaySettingsOut])
def list_class_display(
    _: TokenInfo = Depends(_require_super_admin),
) -> list[ClassDisplaySettingsOut]:
    """Lista klassdisplay-inställning per lärare. Lärare utan rad får
    default-värden (allt avstängt utom invitations)."""
    from ..school.social_models import ClassDisplaySettings

    out = []
    with master_session() as s:
        teachers = s.query(Teacher).order_by(Teacher.name).all()
        configs_by_id = {
            c.teacher_id: c
            for c in s.query(ClassDisplaySettings).all()
        }
        for t in teachers:
            cfg = configs_by_id.get(t.id)
            if cfg is None:
                out.append(ClassDisplaySettingsOut(
                    teacher_id=t.id,
                    teacher_email=t.email,
                    teacher_name=t.name,
                    class_list_enabled=False,
                    show_full_names=False,
                    invite_classmates_enabled=True,
                    cost_split_model="split",
                    class_event_creation_enabled=False,
                    max_invites_per_week=3,
                ))
            else:
                out.append(ClassDisplaySettingsOut(
                    teacher_id=t.id,
                    teacher_email=t.email,
                    teacher_name=t.name,
                    class_list_enabled=cfg.class_list_enabled,
                    show_full_names=cfg.show_full_names,
                    invite_classmates_enabled=cfg.invite_classmates_enabled,
                    cost_split_model=cfg.cost_split_model,
                    class_event_creation_enabled=cfg.class_event_creation_enabled,
                    max_invites_per_week=cfg.max_invites_per_week,
                ))
    return out


@router.post("/class-display", response_model=ClassDisplaySettingsOut)
def set_class_display(
    payload: ClassDisplaySettingsIn,
    _: TokenInfo = Depends(_require_super_admin),
) -> ClassDisplaySettingsOut:
    """Uppdatera klassdisplay-inställningarna för en specifik lärare.
    Skapa rad om den inte finns. Bara fält som skickas in uppdateras."""
    from ..school.social_models import ClassDisplaySettings

    with master_session() as s:
        teacher = s.get(Teacher, payload.teacher_id)
        if teacher is None:
            raise HTTPException(404, "Lärare saknas")

        cfg = (
            s.query(ClassDisplaySettings)
            .filter(ClassDisplaySettings.teacher_id == payload.teacher_id)
            .first()
        )
        if cfg is None:
            cfg = ClassDisplaySettings(teacher_id=payload.teacher_id)
            s.add(cfg)

        if payload.class_list_enabled is not None:
            cfg.class_list_enabled = payload.class_list_enabled
        if payload.show_full_names is not None:
            cfg.show_full_names = payload.show_full_names
        if payload.invite_classmates_enabled is not None:
            cfg.invite_classmates_enabled = payload.invite_classmates_enabled
        if payload.cost_split_model is not None:
            if payload.cost_split_model not in {"split", "inviter_pays", "each_pays_own"}:
                raise HTTPException(400, "Ogiltig cost_split_model")
            cfg.cost_split_model = payload.cost_split_model
        if payload.class_event_creation_enabled is not None:
            cfg.class_event_creation_enabled = payload.class_event_creation_enabled
        if payload.max_invites_per_week is not None:
            if not (0 <= payload.max_invites_per_week <= 50):
                raise HTTPException(400, "max_invites_per_week måste vara 0-50")
            cfg.max_invites_per_week = payload.max_invites_per_week

        s.flush()

        return ClassDisplaySettingsOut(
            teacher_id=teacher.id,
            teacher_email=teacher.email,
            teacher_name=teacher.name,
            class_list_enabled=cfg.class_list_enabled,
            show_full_names=cfg.show_full_names,
            invite_classmates_enabled=cfg.invite_classmates_enabled,
            cost_split_model=cfg.cost_split_model,
            class_event_creation_enabled=cfg.class_event_creation_enabled,
            max_invites_per_week=cfg.max_invites_per_week,
        )


# ---------- DB-diagnostik (super-admin) ----------

@router.get("/db/diagnose")
def diagnose_master_db(
    _: TokenInfo = Depends(_require_super_admin),
) -> dict:
    """Returnerar exakt vilka kolumner master-DB har på de viktigaste
    tabellerna. Används för att felsöka migration-problem på prod
    utan att behöva SSH:a till Cloud Run."""
    from sqlalchemy import inspect as _inspect
    from ..school.engines import _master_engine, init_master_engine

    if _master_engine is None:
        init_master_engine()
    insp = _inspect(_master_engine)

    tables_to_check = [
        "teachers", "students", "student_profiles", "families",
        "assignments", "modules", "module_steps",
        "event_templates", "class_event_invites",
        "class_display_settings", "teacher_class_events",
        "stock_master", "stock_quotes", "latest_stock_quotes",
        "market_calendar",
    ]
    out = {"dialect": _master_engine.dialect.name, "tables": {}}
    for tbl in tables_to_check:
        try:
            cols = insp.get_columns(tbl)
            out["tables"][tbl] = {
                "exists": True,
                "columns": [c["name"] for c in cols],
            }
        except Exception as e:
            out["tables"][tbl] = {"exists": False, "error": str(e)[:100]}
    return out


@router.post("/db/run-migrations")
def force_run_migrations(
    _: TokenInfo = Depends(_require_super_admin),
) -> dict:
    """Tvinga _run_master_migrations() att köra direkt. Returnerar
    diagnostisk info efteråt så super-admin kan se vad som skedde."""
    import logging as _logging
    from ..school import engines as _eng
    from ..school.engines import (
        _refresh_master_columns_cache,
        _run_master_migrations,
        init_master_engine,
    )

    if _eng._master_engine is None:
        init_master_engine()

    log_msgs: list[str] = []

    class _CaptureHandler(_logging.Handler):
        def emit(self, record):
            log_msgs.append(f"{record.levelname}: {record.getMessage()}")

    handler = _CaptureHandler()
    handler.setLevel(_logging.INFO)
    target_logger = _logging.getLogger("hembudget.school.engines")
    target_logger.addHandler(handler)
    try:
        _run_master_migrations(_eng._master_engine)
        # Uppdatera kolumn-cachen så master_has_column() omedelbart
        # ser de nya kolumnerna utan omstart
        _refresh_master_columns_cache(_eng._master_engine)
        log_msgs.append("INFO: master-columns-cache uppdaterad")
    except Exception as e:
        log_msgs.append(f"EXCEPTION: {e}")
    finally:
        target_logger.removeHandler(handler)

    return {"ok": True, "log": log_msgs}


@router.post("/db/run-scope-migrations")
def force_run_scope_migrations(
    _: TokenInfo = Depends(_require_super_admin),
) -> dict:
    """Tvinga scope-DB-migrationerna att köra mot shared-Postgres
    eller SQLite-per-scope. Adresserar fel som 'column loans.loan_kind
    does not exist' efter en deploy där migrationen aldrig hann köra."""
    import logging as _logging
    import os
    from ..db.migrate import run_migrations as _run_scope_migrations
    from ..school import engines as _eng
    from ..school.engines import _refresh_scope_columns_cache

    log_msgs: list[str] = []

    class _CaptureHandler(_logging.Handler):
        def emit(self, record):
            log_msgs.append(f"{record.levelname}: {record.getMessage()}")

    handler = _CaptureHandler()
    handler.setLevel(_logging.INFO)
    for name in ("hembudget.db.migrate", "hembudget.school.engines"):
        _logging.getLogger(name).addHandler(handler)

    try:
        if os.environ.get("HEMBUDGET_DATABASE_URL", "").strip():
            # Postgres-läge: kör mot shared-engine
            from ..school.engines import _init_shared_scope_engine
            engine, _ = _init_shared_scope_engine()
            _run_scope_migrations(engine)
            _refresh_scope_columns_cache(engine)
            log_msgs.append("INFO: shared-Postgres scope-migrations körda")
        else:
            # SQLite-läge: kör mot alla cachade scope-engines
            for key, eng in _eng._scope_engines.items():
                _run_scope_migrations(eng)
                _refresh_scope_columns_cache(eng)
                log_msgs.append(f"INFO: SQLite-scope {key} migrerad")
    except Exception as e:
        log_msgs.append(f"EXCEPTION: {type(e).__name__}: {e}")
    finally:
        for name in ("hembudget.db.migrate", "hembudget.school.engines"):
            _logging.getLogger(name).removeHandler(handler)

    return {"ok": True, "log": log_msgs}


@router.get("/db/scope-columns")
def get_scope_columns(
    _: TokenInfo = Depends(_require_super_admin),
) -> dict:
    """Returnerar nuvarande scope-DB-kolumnstatus per relevant tabell.
    Snabb verifiering att t.ex. loans.loan_kind faktiskt finns."""
    from ..school.engines import _scope_columns
    return {
        "tables": {
            tbl: sorted(cols) for tbl, cols in _scope_columns.items()
        },
    }


@router.get("/db/stocks-status")
def stocks_diagnose(
    _: TokenInfo = Depends(_require_super_admin),
) -> dict:
    """Diagnostik för aktiekurs-poller. Visar:
    - antal stocks i universum (StockMaster)
    - antal kursrader i StockQuote (totalt + senaste 24 h)
    - antal LatestStockQuote
    - vilken provider som används
    - is_market_open just nu
    - dagens MarketCalendar-rad
    - om Finnhub-key är konfigurerad
    """
    from datetime import datetime, timedelta
    from ..school.engines import master_session
    from ..school.stock_models import (
        LatestStockQuote, MarketCalendar, StockMaster, StockQuote,
    )
    from ..stocks.calendar import is_market_open
    from ..stocks.quote_providers import (
        finnhub_key_configured, get_provider,
    )

    yesterday = datetime.utcnow() - timedelta(hours=24)
    with master_session() as s:
        n_stocks = s.query(StockMaster).count()
        n_quotes_total = s.query(StockQuote).count()
        n_quotes_24h = (
            s.query(StockQuote)
            .filter(StockQuote.ts >= yesterday)
            .count()
        )
        n_latest = s.query(LatestStockQuote).count()
        latest = (
            s.query(StockQuote)
            .order_by(StockQuote.ts.desc())
            .first()
        )
        last_quote = {
            "ticker": latest.ticker,
            "ts": latest.ts.isoformat() if latest.ts else None,
            "last": float(latest.last),
            "source": latest.source,
        } if latest else None
        market_open = is_market_open(s)
        from datetime import date as _d
        today_cal = (
            s.query(MarketCalendar)
            .filter(
                MarketCalendar.calendar_date == _d.today(),
                MarketCalendar.exchange == "XSTO",
            )
            .first()
        )
        cal_row = {
            "date": today_cal.calendar_date.isoformat(),
            "status": today_cal.status,
            "open_time": today_cal.open_time,
            "close_time": today_cal.close_time,
            "note": today_cal.note,
        } if today_cal else None

    return {
        "stocks_in_universe": n_stocks,
        "total_quotes": n_quotes_total,
        "quotes_last_24h": n_quotes_24h,
        "latest_quotes_table": n_latest,
        "last_quote": last_quote,
        "market_open_now": market_open,
        "today_calendar": cal_row,
        "provider": type(get_provider()).__name__,
        "finnhub_key_configured": finnhub_key_configured(),
    }


@router.post("/db/stocks-poll-now")
def stocks_poll_now(
    _: TokenInfo = Depends(_require_super_admin),
) -> dict:
    """Tvinga en kurs-poll direkt (även om börsen är stängd). Returnerar
    antal hämtade rader + ev. fel."""
    from ..school.engines import master_session
    from ..stocks.poller import poll_quotes

    with master_session() as s:
        try:
            res = poll_quotes(s, force=True)
            return {"ok": True, **res}
        except Exception as e:
            return {
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
            }


@router.post("/db/yfinance-test")
def yfinance_test(
    _: TokenInfo = Depends(_require_super_admin),
) -> dict:
    """Testa yfinance-providern direkt mot 3 svenska + 3 USA-aktier
    + USD/SEK-kursen. Visar exakt vad som returneras eller failar."""
    import logging as _logging
    log_msgs: list[str] = []

    class _CaptureHandler(_logging.Handler):
        def emit(self, record):
            log_msgs.append(f"{record.levelname}: {record.getMessage()}")

    handler = _CaptureHandler()
    handler.setLevel(_logging.DEBUG)
    target_logger = _logging.getLogger("hembudget.stocks.quote_providers")
    target_logger.addHandler(handler)
    target_logger.setLevel(_logging.DEBUG)

    result: dict = {"yfinance_available": False}
    try:
        try:
            import yfinance as yf  # type: ignore
            result["yfinance_available"] = True
            result["yfinance_version"] = getattr(yf, "__version__", "?")
        except ImportError as e:
            result["import_error"] = f"{type(e).__name__}: {e}"
            return {"ok": False, **result, "log": log_msgs}

        from ..stocks.quote_providers import (
            YFinanceProvider, fetch_fx_rate_yfinance,
        )
        provider = YFinanceProvider()
        sthlm_test = ["VOLV-B.ST", "ERIC-B.ST", "HM-B.ST"]
        us_test = ["AAPL", "MSFT", "TSLA"]

        try:
            sthlm_quotes = provider.fetch_quotes(sthlm_test)
            result["stockholm_quotes"] = [
                {
                    "ticker": q.ticker,
                    "last": float(q.last),
                    "change_pct": q.change_pct,
                }
                for q in sthlm_quotes
            ]
            result["stockholm_count"] = len(sthlm_quotes)
        except Exception as e:
            result["stockholm_error"] = f"{type(e).__name__}: {e}"

        try:
            us_quotes = provider.fetch_quotes(us_test)
            result["us_quotes"] = [
                {
                    "ticker": q.ticker,
                    "last": float(q.last),
                    "change_pct": q.change_pct,
                }
                for q in us_quotes
            ]
            result["us_count"] = len(us_quotes)
        except Exception as e:
            result["us_error"] = f"{type(e).__name__}: {e}"

        try:
            fx = fetch_fx_rate_yfinance("USD", "SEK")
            result["usd_sek_rate"] = float(fx) if fx else None
        except Exception as e:
            result["fx_error"] = f"{type(e).__name__}: {e}"

    finally:
        target_logger.removeHandler(handler)

    return {"ok": True, **result, "log": log_msgs[-30:]}


@router.get("/db/inspect-stock-trades")
def inspect_stock_trades(
    student_id: int,
    info: TokenInfo = Depends(_require_super_admin),
) -> dict:
    """Lista raw StockHolding + StockTransaction för en specifik elev.
    Bypassar tenant-filter via direkt SQL-query mot scope-engine.
    Hjälper debugga 'jag köpte men det syns inte i portfolio'."""
    from sqlalchemy import text as _text
    from ..school.engines import (
        _shared_scope_engine, master_session, scope_for_student,
        _scope_engines,
    )
    from ..school.models import Student

    with master_session() as s:
        student = s.query(Student).filter(Student.id == student_id).first()
        if not student:
            return {"error": f"Student {student_id} finns inte"}
        scope_key = scope_for_student(student)

    # Hitta engine — shared (Postgres) eller per-fil (SQLite)
    engine = _shared_scope_engine or _scope_engines.get(scope_key)
    if engine is None:
        return {"error": f"Ingen scope-engine för {scope_key}"}

    out: dict = {
        "student_id": student_id,
        "scope_key": scope_key,
        "engine_type": engine.dialect.name,
    }

    # Räkna alla rader (utan tenant-filter) + filter per tenant
    try:
        with engine.connect() as conn:
            # Cash tx (oberoende verifiering)
            row = conn.execute(_text(
                "SELECT COUNT(*), COALESCE(MIN(tenant_id), '?') "
                "FROM transactions "
                "WHERE raw_description LIKE 'Köp%' OR raw_description LIKE 'Sälj%'"
            )).first()
            out["cash_tx_count"] = row[0] if row else 0
            out["cash_tx_sample_tenant"] = row[1] if row else None

            row = conn.execute(_text(
                "SELECT COUNT(*), COALESCE(MIN(tenant_id), '?') "
                "FROM stock_transactions"
            )).first()
            out["stock_tx_count_total"] = row[0] if row else 0
            out["stock_tx_sample_tenant"] = row[1] if row else None

            row = conn.execute(_text(
                "SELECT COUNT(*) FROM stock_transactions "
                "WHERE tenant_id = :t"
            ), {"t": scope_key}).first()
            out["stock_tx_count_for_scope"] = row[0] if row else 0

            row = conn.execute(_text(
                "SELECT COUNT(*), COALESCE(MIN(tenant_id), '?') "
                "FROM stock_holdings"
            )).first()
            out["stock_holding_count_total"] = row[0] if row else 0
            out["stock_holding_sample_tenant"] = row[1] if row else None

            row = conn.execute(_text(
                "SELECT COUNT(*) FROM stock_holdings "
                "WHERE tenant_id = :t"
            ), {"t": scope_key}).first()
            out["stock_holding_count_for_scope"] = row[0] if row else 0

            # Sista 5 stock-transaktionerna oavsett scope
            rows = conn.execute(_text(
                "SELECT id, tenant_id, ticker, side, quantity, price, "
                "executed_at FROM stock_transactions "
                "ORDER BY id DESC LIMIT 5"
            )).fetchall()
            out["last_5_stock_tx"] = [
                {
                    "id": r[0], "tenant_id": r[1], "ticker": r[2],
                    "side": r[3], "quantity": r[4],
                    "price": float(r[5]),
                    "executed_at": r[6].isoformat() if r[6] else None,
                }
                for r in rows
            ]
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"

    return out

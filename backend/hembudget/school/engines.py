"""Master-DB + per-scope-DB engines med context-styrd scope.

Scope-nyckeln är en sträng:
- "s_<student_id>"  — elev utan familj, egen DB
- "f_<family_id>"   — elev som tillhör en familj; alla familjemedlemmar
                      delar samma DB

ContextVar sätts av StudentScopeMiddleware baserat på Bearer-token +
X-As-Student-header. session_scope() i db/base.py läser den och
öppnar rätt DB-fil.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from ..config import settings

log = logging.getLogger(__name__)


# --- ContextVar: scope-nyckel för aktuell request ---
_current_scope: ContextVar[str | None] = ContextVar(
    "current_scope", default=None,
)


def set_current_scope(scope_key: str | None) -> None:
    _current_scope.set(scope_key)


def get_current_scope() -> str | None:
    return _current_scope.get()


@contextmanager
def scope_context(scope_key: str | None) -> Iterator[None]:
    token = _current_scope.set(scope_key)
    try:
        yield
    finally:
        _current_scope.reset(token)


# Aktör-student-id för aktivitetsloggning. Sätts i StudentScopeMiddleware
# för elev-tokens; läraren som impersonerar (x-as-student) hamnar också
# här så audit-spåret tillskrivs eleven (det är trots allt i elevens DB
# läraren agerar). För familje-scope är detta vilken specifik elev/
# vårdnadshavare som loggat in just nu — viktigt eftersom flera personer
# delar samma scope-DB.
_current_actor_student: ContextVar[int | None] = ContextVar(
    "current_actor_student", default=None,
)


def set_current_actor_student(student_id: int | None) -> None:
    _current_actor_student.set(student_id)


def get_current_actor_student() -> int | None:
    return _current_actor_student.get()


# --- Bekvämlighet: scope-nyckel från Student-objekt ---

def scope_for_student(student) -> str:
    """En elev utan familj får sin egen DB; familjemedlemmar delar."""
    if student.family_id:
        return f"f_{student.family_id}"
    return f"s_{student.id}"


# --- Bakåtkompat-aliasar (gamla tester använder student_scope) ---
def set_current_student(student_id: int | None) -> None:
    set_current_scope(f"s_{student_id}" if student_id is not None else None)


def get_current_student() -> int | None:
    s = get_current_scope()
    if s and s.startswith("s_"):
        try:
            return int(s[2:])
        except ValueError:
            return None
    return None


@contextmanager
def student_scope(student_id: int | None) -> Iterator[None]:
    token = _current_scope.set(
        f"s_{student_id}" if student_id is not None else None
    )
    try:
        yield
    finally:
        _current_scope.reset(token)


# --- Master-DB (delad) ---

_master_engine: Engine | None = None
_master_session: sessionmaker[Session] | None = None


def _school_root() -> Path:
    root = settings.data_dir / "school"
    root.mkdir(parents=True, exist_ok=True)
    (root / "students").mkdir(parents=True, exist_ok=True)
    return root


def _master_db_path() -> Path:
    return _school_root() / "master.db"


def _master_db_url() -> str:
    """Vilken DB-URL master-engine ska använda.

    Prioritet:
    1. HEMBUDGET_DATABASE_URL — riktig managed Postgres (Cloud SQL i prod).
       Detta är vad vi vill ha: data persisterar mellan deploys, automatisk
       backup, point-in-time-restore.
    2. Fallback: SQLite-fil i HEMBUDGET_DATA_DIR — används lokalt och i
       pytest. SQLite-filen försvinner vid Cloud Run-restart om volymen
       inte är monterad.
    """
    import os
    url = os.environ.get("HEMBUDGET_DATABASE_URL", "").strip()
    if url:
        # SQLAlchemy använder "postgresql+psycopg2://" men gcloud genererar
        # "postgresql://"-URL:er. Acceptera båda.
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://") and "+psycopg2" not in url:
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url
    return f"sqlite:///{_master_db_path().as_posix()}"


def init_master_engine() -> Engine:
    """Skapa master-engine + kör create_all för MasterBase. Idempotent."""
    global _master_engine, _master_session
    if _master_engine is not None:
        return _master_engine
    from .models import MasterBase

    url = _master_db_url()
    is_sqlite = url.startswith("sqlite:")
    engine_kwargs: dict = {"future": True}
    if not is_sqlite:
        # Postgres: pre-ping så stale connections från Cloud SQL inte
        # smäller. Cloud SQL db-f1-micro har max ~25 connections totalt.
        # Vi delar mellan master + shared-scope + Postgres internal, så
        # håll pools små: 2+3=5 per engine = 10 totalt med headroom.
        engine_kwargs.update(
            pool_pre_ping=True, pool_size=2, max_overflow=3,
            pool_recycle=1800,
        )
    engine = create_engine(url, **engine_kwargs)

    if is_sqlite:
        @event.listens_for(engine, "connect")
        def _set_pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys = ON")
            cur.close()

    # Bulletproof: även om create_all eller migrationerna failar
    # MÅSTE engine cachas så hela appen inte 500:ar varje request.
    try:
        MasterBase.metadata.create_all(engine)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "master create_all failed — fortsätter med befintliga tabeller",
        )
    try:
        _run_master_migrations(engine)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "master migrations failed — fortsätter ändå så master-engine "
            "kan returneras (login + demo förblir funktionella)",
        )
    _master_engine = engine
    _master_session = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False,
    )
    # Cacha kolumn-existens efter migrations. API-lagret konsulterar
    # detta innan deferred-fält accessas så att SELECT inte kraschar
    # mot prod-Postgres där en migration eventuellt failat.
    try:
        _refresh_master_columns_cache(engine)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "master-columns-cache refresh misslyckades",
        )
    return engine


# Cache av kolumner per master-tabell. Populeras av init_master_engine
# efter att migrationerna körts. Används av master_has_column() för att
# avgöra om en deferred-kolumn är säker att läsa.
_master_columns: dict[str, set[str]] = {}


def _refresh_master_columns_cache(engine: Engine) -> None:
    from sqlalchemy import inspect as _inspect
    try:
        insp = _inspect(engine)
        for table in ("teachers", "students", "student_profiles", "assignments"):
            try:
                _master_columns[table] = {
                    c["name"] for c in insp.get_columns(table)
                }
            except Exception:
                _master_columns[table] = set()
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "kunde inte cacha master-kolumner — fortsätter med tom cache",
        )


def master_has_column(table: str, column: str) -> bool:
    """True om kolumnen finns i master-DB:n. Används som guard innan
    deferred-fält accessas — annars kraschar SELECT i prod om migration
    inte hunnit lägga till kolumnen.

    Default True om cachen inte är populerad ännu (t.ex. i test) — då
    förlitar vi oss på att SQLAlchemy-create_all skapat kolumnerna."""
    cols = _master_columns.get(table)
    if cols is None:
        return True
    return column in cols


# Cache för scope-DB-kolumner. Inga kolumner returneras tomt = "antar
# att de finns" (för SQLite-fil-per-scope där create_all lagt till allt).
# I prod-Postgres blir denna cachen källan-av-sanning för säkra
# deferred-fält (t.ex. loans.loan_kind innan migrationen körts).
_scope_columns: dict[str, set[str]] = {}


def _refresh_scope_columns_cache(engine: Engine) -> None:
    from sqlalchemy import inspect as _inspect
    try:
        insp = _inspect(engine)
        for table in (
            "loans", "transactions", "accounts", "categories",
            "upcoming_transactions", "transaction_splits",
            "fund_holdings", "stock_holdings", "stock_transactions",
            "credit_applications", "wellbeing_scores",
        ):
            try:
                _scope_columns[table] = {
                    c["name"] for c in insp.get_columns(table)
                }
            except Exception:
                _scope_columns[table] = set()
    except Exception:
        log.exception(
            "kunde inte cacha scope-kolumner — fortsätter med tom cache",
        )


def scope_has_column(table: str, column: str) -> bool:
    """Som master_has_column men för scope-DB-tabeller.

    Default True om cachen är tom — då förlitar vi oss på att
    create_all + run_migrations skapat allt. Endast i prod-Postgres
    där en migration kan ha failat blir denna cachen viktig."""
    cols = _scope_columns.get(table)
    if cols is None or not cols:
        return True
    return column in cols


def _run_master_migrations(engine: Engine) -> None:
    """ALTER-TABLE-migrations för master-DB:n.

    `create_all()` lägger inte till nya kolumner i en befintlig tabell, så
    när nya fält läggs på Teacher/Family/Student måste vi lägga till dem
    här. Idempotent — säker att köra varje uppstart.

    Stödjer både SQLite (pytest, lokalt) och Postgres (prod) — använder
    SQLAlchemy-inspector så ingen DB-specifik PRAGMA behövs.
    """
    from sqlalchemy import inspect as _inspect, text as _text

    inspector = _inspect(engine)

    def _cols(table: str) -> set[str]:
        try:
            return {c["name"] for c in inspector.get_columns(table)}
        except Exception:
            return set()

    import logging as _logging
    _log = _logging.getLogger(__name__)

    is_postgres = engine.dialect.name == "postgresql"

    def _translate(col_sql: str) -> str:
        """Översätt SQLite-typer till Postgres-ekvivalenter när dialekten
        är postgresql. SQLite tillåter 'DATETIME' och 'BOOLEAN DEFAULT 0'
        men Postgres kräver 'TIMESTAMP' resp. 'DEFAULT FALSE'.
        """
        if is_postgres:
            col_sql = col_sql.replace(" DATETIME", " TIMESTAMP")
            col_sql = col_sql.replace(
                "BOOLEAN NOT NULL DEFAULT 0", "BOOLEAN NOT NULL DEFAULT FALSE",
            ).replace(
                "BOOLEAN NOT NULL DEFAULT 1", "BOOLEAN NOT NULL DEFAULT TRUE",
            ).replace(
                "BOOLEAN DEFAULT 0", "BOOLEAN DEFAULT FALSE",
            ).replace(
                "BOOLEAN DEFAULT 1", "BOOLEAN DEFAULT TRUE",
            )
        return col_sql

    def _add(table: str, col_sql: str) -> None:
        """Idempotent ALTER TABLE ADD COLUMN. Fail-soft: en kraschad
        migration får inte ta ner hela master-init eftersom det skulle
        ge 500 på alla endpoints (login, demo, reset).

        Vi använder INTE 'IF NOT EXISTS' (gav 'syntax error near OR' på
        en del Postgres-versioner). Istället litar vi på _cols-guarden
        som körs INNAN _add anropas.

        Vid fel: logga och fortsätt. På Postgres kan 'duplicate column'
        vara ofarligt; på SQLite kan en parallell init ha hunnit före.
        """
        translated = _translate(col_sql)
        stmt = f"ALTER TABLE {table} ADD COLUMN {translated}"
        try:
            with engine.begin() as conn:
                conn.execute(_text(stmt))
            _log.info("migration: %s.%s tillagd", table, col_sql.split()[0])
        except Exception as exc:
            msg = str(exc).lower()
            if "already exists" in msg or "duplicate" in msg:
                _log.info(
                    "migration: %s.%s redan tillagd — hoppar över",
                    table, col_sql.split()[0],
                )
            else:
                _log.exception(
                    "migration: ALTER TABLE %s ADD COLUMN %s misslyckades",
                    table, col_sql,
                )

    t_cols = _cols("teachers")
    if "is_super_admin" not in t_cols:
        _add("teachers", "is_super_admin BOOLEAN NOT NULL DEFAULT 0")
    if "ai_enabled" not in t_cols:
        _add("teachers", "ai_enabled BOOLEAN NOT NULL DEFAULT 0")
    if "ai_requests_count" not in t_cols:
        _add("teachers", "ai_requests_count INTEGER NOT NULL DEFAULT 0")
    if "ai_input_tokens" not in t_cols:
        _add("teachers", "ai_input_tokens INTEGER NOT NULL DEFAULT 0")
    if "ai_output_tokens" not in t_cols:
        _add("teachers", "ai_output_tokens INTEGER NOT NULL DEFAULT 0")
    a_cols = _cols("assignments")
    if "teacher_feedback" not in a_cols:
        _add("assignments", "teacher_feedback TEXT")
    if "teacher_feedback_at" not in a_cols:
        _add("assignments", "teacher_feedback_at DATETIME")

    if "email_verified_at" not in t_cols:
        # SQLite tillåter inte non-constant default med ALTER TABLE,
        # så vi lämnar NULL som default. Befintliga lärare blir ej-
        # verifierade rent tekniskt — men backfill:en nedan sätter
        # dem verifierade eftersom de redan fungerar (inloggat konto).
        _add("teachers", "email_verified_at DATETIME")
        # Backfill: alla existerande lärare (före den här migrationen)
        # räknas verifierade — annars skulle super-admins låsas ute.
        with engine.begin() as conn:
            conn.execute(_text(
                "UPDATE teachers SET email_verified_at = CURRENT_TIMESTAMP "
                "WHERE email_verified_at IS NULL"
            ))
    if "is_family_account" not in t_cols:
        _add("teachers", "is_family_account BOOLEAN NOT NULL DEFAULT 0")

    # StudentProfile partner-fält + cost-split-preference (Wellbeing Fas
    # 7+: 'veil of ignorance'-onboarding där eleven väljer fördelnings-
    # modell innan partner-lön avslöjas).
    sp_cols = _cols("student_profiles")
    if sp_cols:  # Skippa om tabellen inte finns ännu
        if "partner_profession" not in sp_cols:
            _add("student_profiles", "partner_profession VARCHAR(80)")
        if "partner_gross_salary" not in sp_cols:
            _add("student_profiles", "partner_gross_salary INTEGER")
        if "cost_split_preference" not in sp_cols:
            _add("student_profiles", "cost_split_preference VARCHAR(20)")
        if "cost_split_decided_at" not in sp_cols:
            _add("student_profiles", "cost_split_decided_at DATETIME")

    # ALTER COLUMN TYPE: konvertera INTEGER → BIGINT på seed-kolumner
    # som lagrar uint32-värden (kan vara > 2^31-1). create_all ändrar
    # inte typen på existerande kolumner, så prod-Postgres kan ha
    # tabellen med INTEGER trots att modellen säger BigInteger →
    # 'integer out of range' vid INSERT.
    if is_postgres:
        for table, col in (
            ("student_generation_runs", "seed"),
            ("scenario_batches", "seed"),
        ):
            try:
                inspector2 = _inspect(engine)
                cols = inspector2.get_columns(table)
                for c in cols:
                    if c["name"] == col:
                        # SQLAlchemy returnerar SQLAlchemy-typer; vi vill
                        # se om det är 32-bit Integer
                        col_type_str = str(c["type"]).upper()
                        if "BIGINT" not in col_type_str and "INTEGER" in col_type_str:
                            _log.info(
                                "migration: %s.%s är INTEGER, alterar till BIGINT",
                                table, col,
                            )
                            with engine.begin() as conn:
                                conn.execute(_text(
                                    f"ALTER TABLE {table} "
                                    f"ALTER COLUMN {col} TYPE BIGINT"
                                ))
                        break
            except Exception:
                _log.exception(
                    "migration: kunde inte ALTER %s.%s till BIGINT",
                    table, col,
                )


@contextmanager
def master_session() -> Iterator[Session]:
    if _master_session is None:
        init_master_engine()
    assert _master_session is not None
    session = _master_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# --- Per-scope-DB engines (cache) ---

_scope_engines: dict[str, Engine] = {}
_scope_sessions: dict[str, sessionmaker[Session]] = {}


def _scope_db_path(scope_key: str) -> Path:
    return _school_root() / "students" / f"{scope_key}.db"


# Delad Postgres-engine när HEMBUDGET_DATABASE_URL är satt. Då samlas
# all scope-data i en enda Postgres med tenant_id-isolering, och
# fil-per-scope-cachen nedan används aldrig.
_shared_scope_engine: Engine | None = None
_shared_scope_session: sessionmaker[Session] | None = None
_seeded_tenants: set[str] = set()


def _init_shared_scope_engine() -> tuple[Engine, sessionmaker[Session]]:
    """Lazy-init en gemensam Postgres-engine för ALLA scope-keys.
    Bara när HEMBUDGET_DATABASE_URL är satt.

    Bulletproof: även om create_all eller migrationerna failar ska vi
    kunna returnera en användbar engine + sessionmaker. Annars cachas
    inte engine, varje request retry:ar och hela tjänsten blir 500.
    """
    global _shared_scope_engine, _shared_scope_session
    if _shared_scope_engine is not None:
        assert _shared_scope_session is not None
        return _shared_scope_engine, _shared_scope_session

    from ..db import models as _models  # noqa: F401  (registrera modeller)
    from ..db.base import Base
    from ..db.migrate import run_migrations

    url = _master_db_url()
    engine_kwargs: dict = {"future": True}
    if url.startswith("postgresql"):
        # Cloud SQL har låg connection-limit. Håll båda engines små.
        engine_kwargs.update(
            pool_pre_ping=True, pool_size=2, max_overflow=3,
            pool_recycle=1800,
        )
    engine = create_engine(url, **engine_kwargs)

    # create_all kan misslyckas mot existerande Postgres-schema (typkonflikt,
    # FK-konflikt, etc). Logga och fortsätt — engine är fortfarande
    # användbar för befintliga tabeller.
    try:
        Base.metadata.create_all(engine)
    except Exception:
        log.exception(
            "shared scope create_all failed — fortsätter ändå med "
            "befintliga tabeller",
        )

    # ALTER-migrationer för befintliga tabeller. create_all hanterar bara
    # NYA tabeller, så när vi lägger till kolumner på befintliga tabeller
    # (t.ex. loans.loan_kind) MÅSTE migrationerna köras här. Annars
    # kraschar SELECT på Postgres med 'column does not exist'.
    try:
        run_migrations(engine)
    except Exception:
        log.exception(
            "shared scope migrations failed — fortsätter ändå (login + "
            "nya elever ska funka, gamla kan ha schema-skev)",
        )

    try:
        _refresh_scope_columns_cache(engine)
    except Exception:
        log.exception("scope-columns-cache refresh misslyckades")

    # CACHE engine OBEROENDE av om migrationerna gick bra. Annars
    # försöker varje ny request init:a om → blockerar hela skol-läget.
    _shared_scope_engine = engine
    _shared_scope_session = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False,
    )
    return engine, _shared_scope_session


def _seed_tenant_if_needed(scope_key: str) -> None:
    """Säkerställ att en ny scope (t.ex. en just-skapad elev) har
    default-kategorier + regler i den delade Postgres. Idempotent
    via in-memory-cache + DB-check."""
    if scope_key in _seeded_tenants:
        return
    assert _shared_scope_session is not None
    from ..db.models import Category
    with scope_context(scope_key):
        with _shared_scope_session() as s:
            existing = s.query(Category).first()
            if existing is None:
                try:
                    from ..categorize.rules import seed_categories_and_rules
                    seed_categories_and_rules(s)
                    s.commit()
                except Exception:
                    s.rollback()
                    log.exception(
                        "Failed seeding categories for tenant %s", scope_key,
                    )
    _seeded_tenants.add(scope_key)


def get_scope_engine(scope_key: str) -> Engine:
    """Skapa (eller återanvänd cachead) engine för en scope-nyckel.

    - Postgres-läge: returnerar samma delade engine för alla scopes;
      tenant-isolering sker via tenant_id-kolumn + session-events i
      db/base.py.
    - SQLite-läge: en fil per scope (oförändrat — pytest + dev).
    """
    import os
    if os.environ.get("HEMBUDGET_DATABASE_URL", "").strip():
        engine, _ = _init_shared_scope_engine()
        _seed_tenant_if_needed(scope_key)
        return engine

    if scope_key in _scope_engines:
        return _scope_engines[scope_key]

    # models måste vara importerad så Base.metadata har alla tabeller
    from ..db import models as _models  # noqa: F401
    from ..db.base import Base
    from ..db.migrate import run_migrations

    url = f"sqlite:///{_scope_db_path(scope_key).as_posix()}"
    engine = create_engine(url, future=True, poolclass=NullPool)

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.close()

    try:
        Base.metadata.create_all(engine)
    except Exception:
        log.exception(
            "scope create_all failed for %s — fortsätter ändå", scope_key,
        )
    try:
        run_migrations(engine)
    except Exception:
        log.exception(
            "scope migrations failed for %s — fortsätter ändå", scope_key,
        )
    _refresh_scope_columns_cache(engine)

    _scope_engines[scope_key] = engine
    _scope_sessions[scope_key] = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False,
    )

    # Seed default categories/rules första gången
    with _scope_sessions[scope_key]() as s:
        try:
            from ..categorize.rules import seed_categories_and_rules
            seed_categories_and_rules(s)
            s.commit()
        except Exception:
            s.rollback()
            log.exception("Failed seeding categories for scope %s", scope_key)

    return engine


def get_scope_session(scope_key: str) -> sessionmaker[Session]:
    """Returnerar sessionmaker för en scope.

    - Postgres-läge: alla scopes delar samma sessionmaker; isolering
      sker via tenant_id-event-listeners.
    - SQLite-läge: en sessionmaker per scope-fil.
    """
    import os
    if os.environ.get("HEMBUDGET_DATABASE_URL", "").strip():
        if _shared_scope_session is None:
            _init_shared_scope_engine()
        _seed_tenant_if_needed(scope_key)
        assert _shared_scope_session is not None
        return _shared_scope_session

    if scope_key not in _scope_sessions:
        get_scope_engine(scope_key)
    return _scope_sessions[scope_key]


# --- Bakåtkompat-aliasar ---
def get_student_engine(student_id: int) -> Engine:
    return get_scope_engine(f"s_{student_id}")


def get_student_session(student_id: int) -> sessionmaker[Session]:
    return get_scope_session(f"s_{student_id}")


def drop_scope_db(scope_key: str) -> None:
    """Stäng engine + radera filen."""
    eng = _scope_engines.pop(scope_key, None)
    _scope_sessions.pop(scope_key, None)
    if eng is not None:
        eng.dispose()
    path = _scope_db_path(scope_key)
    if path.exists():
        path.unlink()


def dispose_scope_engine(scope_key: str) -> None:
    """Stäng engine + töm cachen MEN behåll filen på disk.
    Används när en elev byter scope-nyckel (t.ex. flyttar till familj)
    och vi inte vill läcka engine-handles. Filen ligger kvar ifall
    eleven senare flyttar tillbaka, eller om en administratör vill
    inspektera datat."""
    eng = _scope_engines.pop(scope_key, None)
    _scope_sessions.pop(scope_key, None)
    if eng is not None:
        eng.dispose()


def reset_scope_db(scope_key: str) -> None:
    drop_scope_db(scope_key)


def drop_student_db(student_id: int) -> None:
    drop_scope_db(f"s_{student_id}")


def reset_student_db(student_id: int) -> None:
    reset_scope_db(f"s_{student_id}")

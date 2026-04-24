"""Master-DB + per-elev-DB engines med context-styrd scope.

Design:
- En global engine för "master" (teachers/students).
- En cache av engines per student_id — en SQLite-fil per elev på
  {data_dir}/students/{student_id}.db.
- En ContextVar sätts av require_auth baserat på bearer-tokenen så att
  db/base.session_scope() öppnar rätt student-DB när endpoints som
  /transactions körs.

Trådfriskt: FastAPI kör varje request i en async task eller worker, och
ContextVar är per-task/per-thread isolerad.
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


# --- ContextVar: vilken elev-DB som aktuell request ska använda ---
# None = master/ingen scope (t.ex. teacher som hanterar elever, inte
# elevdata). Sätts av require_auth när student loggar in, eller av
# impersonation-helpers när lärare tittar på en elev.
_current_student_id: ContextVar[int | None] = ContextVar(
    "current_student_id", default=None,
)


def set_current_student(student_id: int | None) -> None:
    _current_student_id.set(student_id)


def get_current_student() -> int | None:
    return _current_student_id.get()


@contextmanager
def student_scope(student_id: int | None) -> Iterator[None]:
    """Tillfälligt sätt current_student_id. Används när lärare vill
    generera data eller kolla på en elev utan att behöva ändra tokens."""
    token = _current_student_id.set(student_id)
    try:
        yield
    finally:
        _current_student_id.reset(token)


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


def init_master_engine() -> Engine:
    """Skapa master-engine + kör create_all för MasterBase. Idempotent."""
    global _master_engine, _master_session
    if _master_engine is not None:
        return _master_engine
    from .models import MasterBase

    url = f"sqlite:///{_master_db_path().as_posix()}"
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.close()

    MasterBase.metadata.create_all(engine)
    _master_engine = engine
    _master_session = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False,
    )
    return engine


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


# --- Per-elev-DB engines (cache) ---

_student_engines: dict[int, Engine] = {}
_student_sessions: dict[int, sessionmaker[Session]] = {}


def _student_db_path(student_id: int) -> Path:
    return _school_root() / "students" / f"{student_id}.db"


def get_student_engine(student_id: int) -> Engine:
    """Skapa (eller återanvänd cachead) engine för en elev.

    Kör create_all + run_migrations + seed_categories_and_rules första
    gången så att elevens DB har schema + default-kategorier.
    """
    if student_id in _student_engines:
        return _student_engines[student_id]

    # Viktigt: använd huvudmodellernas Base (samma schema som vanlig app).
    # models-modulen MÅSTE importeras så Base.metadata får alla tabeller
    # innan create_all körs — annars får elev-DB:n ett tomt schema.
    from ..db import models as _models  # noqa: F401
    from ..db.base import Base
    from ..db.migrate import run_migrations

    url = f"sqlite:///{_student_db_path(student_id).as_posix()}"
    engine = create_engine(url, future=True, poolclass=NullPool)

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.close()

    Base.metadata.create_all(engine)
    run_migrations(engine)

    _student_engines[student_id] = engine
    _student_sessions[student_id] = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False,
    )

    # Seed default categories/rules första gången
    with _student_sessions[student_id]() as s:
        try:
            from ..categorize.rules import seed_categories_and_rules
            seed_categories_and_rules(s)
            s.commit()
        except Exception:
            s.rollback()
            log.exception("Failed seeding categories for student %d", student_id)

    return engine


def get_student_session(student_id: int) -> sessionmaker[Session]:
    if student_id not in _student_sessions:
        get_student_engine(student_id)
    return _student_sessions[student_id]


def drop_student_db(student_id: int) -> None:
    """Stäng engine + radera filen. Används när lärare tar bort en elev."""
    eng = _student_engines.pop(student_id, None)
    _student_sessions.pop(student_id, None)
    if eng is not None:
        eng.dispose()
    path = _student_db_path(student_id)
    if path.exists():
        path.unlink()


def reset_student_db(student_id: int) -> None:
    """Nollställ innehåll — behåll filen men rensa alla transaktioner
    och konton. Används för att "börja om"."""
    drop_student_db(student_id)
    # Ny skapas on-demand av get_student_engine nästa gång

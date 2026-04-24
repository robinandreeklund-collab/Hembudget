from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from ..config import settings

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _build_engine(db_path: Path, key: str | None) -> Engine:
    try:
        import sqlcipher3  # type: ignore

        url = f"sqlite+pysqlcipher://:{key or ''}@/{db_path.as_posix()}"
        # NullPool: öppna ny connection per checkout, stäng rent när vi är
        # klara. QueuePool (default) återanvänder anslutningar och har gett
        # segfaults med sqlcipher3 i WSL. NullPool är lite långsammare men
        # stabilt. Desktop-app med få parallella requests — OK trade-off.
        engine = create_engine(
            url, module=sqlcipher3, future=True, poolclass=NullPool,
        )

        @event.listens_for(engine, "connect")
        def _set_cipher_pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            if key:
                cur.execute(f"PRAGMA key = '{key}'")
            cur.execute("PRAGMA cipher_page_size = 4096")
            cur.execute("PRAGMA kdf_iter = 256000")
            cur.execute("PRAGMA cipher_hmac_algorithm = HMAC_SHA512")
            cur.execute("PRAGMA foreign_keys = ON")
            cur.close()

        return engine
    except ImportError:
        log.warning("sqlcipher3 unavailable; falling back to plaintext SQLite. Do NOT use in prod.")
        url = f"sqlite:///{db_path.as_posix()}"
        engine = create_engine(url, future=True)

        @event.listens_for(engine, "connect")
        def _set_pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys = ON")
            cur.close()

        return engine


def init_engine(key: str | None = None) -> Engine:
    global _engine, _SessionLocal
    _engine = _build_engine(settings.db_path, key)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        init_engine()
    assert _engine is not None
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    # School-mode: om aktuell request har en current_student_id i context,
    # öppna elevens egna SQLite-fil i stället för den globala.
    from ..school import is_enabled as _school_enabled
    if _school_enabled():
        from ..school.engines import get_current_student, get_student_session
        sid = get_current_student()
        if sid is not None:
            maker = get_student_session(sid)
            session = maker()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
            return

    if _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    with session_scope() as s:
        yield s

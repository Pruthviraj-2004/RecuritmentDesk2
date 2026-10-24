from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        url = get_settings().database_url
        kwargs: dict = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            from sqlalchemy.pool import StaticPool

            kwargs = {"connect_args": {"check_same_thread": False}}
            if ":memory:" in url or url in ("sqlite://", "sqlite:///"):
                kwargs["poolclass"] = StaticPool
        schema = get_settings().database_schema
        if schema and url.startswith("postgresql"):
            if not schema.replace("_", "").isalnum():
                raise ValueError("DATABASE_SCHEMA must be alphanumeric/underscore")
            # schema_translate_map qualifies every table with the schema; unlike the search_path startup option it
            # also works through PgBouncer-style poolers (e.g. Neon's -pooler endpoints).
            kwargs["execution_options"] = {"schema_translate_map": {None: schema}}
        _engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):

            @event.listens_for(_engine, "connect")
            def _fk(dbapi_conn, _):  # enforce FK constraints on SQLite as PostgreSQL does
                dbapi_conn.isolation_level = None  # take over transaction control (pysqlite's default breaks SAVEPOINT)
                dbapi_conn.execute("PRAGMA foreign_keys=ON")
                dbapi_conn.execute("PRAGMA busy_timeout=10000")
                dbapi_conn.execute("PRAGMA journal_mode=WAL")  # readers never block writers (dev/test only; production uses PostgreSQL)

            @event.listens_for(_engine, "begin")
            def _begin(conn):
                conn.exec_driver_sql("BEGIN")

        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    return _engine


def reset_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_db() -> Iterator[Session]:
    db = session_factory()()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for workers and scripts."""
    db = session_factory()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

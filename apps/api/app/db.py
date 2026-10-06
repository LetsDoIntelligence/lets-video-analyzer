"""Database engine, session handling and migrations."""

from collections.abc import Iterator
from pathlib import Path

from alembic.config import Config
from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from alembic import command
from app.config import API_ROOT


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args)

    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")  # needed for ON DELETE CASCADE
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def run_migrations(database_url: str) -> None:
    """Bring the database up to the latest schema."""
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(API_ROOT / "alembic")))
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(cfg, "head")


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        yield session

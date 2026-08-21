from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings


class Base(DeclarativeBase):
    pass


def build_engine(settings: Settings):
    kwargs = {"pool_pre_ping": True}
    if settings.database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in settings.database_url:
            kwargs["poolclass"] = StaticPool
    return create_engine(settings.database_url, **kwargs)


def build_session_factory(engine):
    return sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )


@contextmanager
def session_scope(factory) -> Generator[Session, None, None]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

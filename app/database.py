from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.settings import PROJECT_ROOT, get_settings


class Base(DeclarativeBase):
    pass


def normalized_database_url(value: str) -> str:
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


def build_engine():
    settings = get_settings()
    url = normalized_database_url(settings.database_url)
    if url.startswith("sqlite:///./"):
        relative = url.removeprefix("sqlite:///./")
        target = PROJECT_ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{target.as_posix()}"
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite:"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(engine)

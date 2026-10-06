from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
# Each pytest process owns its database so parallel contributor/agent runs cannot
# drop each other's tables. Never reuse DATABASE_URL from the developer's shell.
_database_fd, _database_path = tempfile.mkstemp(prefix="aiat-tests-", suffix=".sqlite")
os.close(_database_fd)
TEST_DATABASE = Path(_database_path)
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE.as_posix()}"
os.environ["APP_ENV"] = "local"
os.environ["PUBLIC_DATA_VALUES_ENABLED"] = "false"
os.environ["ALLOW_PENDING_OWNER_SOURCES"] = "false"


@pytest.fixture(autouse=True)
def clean_database():
    from app.database import Base, engine

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def pytest_sessionfinish(session, exitstatus):
    from app.database import engine

    engine.dispose()
    TEST_DATABASE.unlink(missing_ok=True)

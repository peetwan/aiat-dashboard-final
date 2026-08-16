from __future__ import annotations

import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE = ROOT / "data/runtime/test_dashboard.sqlite"
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

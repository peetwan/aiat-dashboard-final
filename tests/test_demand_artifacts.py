from __future__ import annotations

import re

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.demand_artifacts import REQUIRED_DEMAND_COUNT, sync_housing_demand
from app.models import Base, HousingDemandRecord, HousingDemandSnapshot


EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(r"(?<![\dA-Za-z])(?:\+?66|0)\s*\d(?:[\s().-]*\d){7,9}(?!\d)")
CONTACT_FIELD_RE = re.compile(
    r"(?i)(?:^|_)(?:first_name|last_name|full_name|person_name|name|"
    r"phone|telephone|tel|mobile|email|e_mail|contact)(?:_|$)"
)


def test_housing_demand_sync_is_exact_private_and_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'demand.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        first = sync_housing_demand(session)
        assert first == {
            "expected": REQUIRED_DEMAND_COUNT,
            "loaded": REQUIRED_DEMAND_COUNT,
            "count": REQUIRED_DEMAND_COUNT,
            "changed": True,
        }
        assert session.scalar(
            select(func.count()).select_from(HousingDemandRecord)
        ) == REQUIRED_DEMAND_COUNT
        assert session.scalar(
            select(func.count()).select_from(HousingDemandSnapshot)
        ) == 1

        province_counts = dict(
            session.execute(
                select(
                    HousingDemandRecord.living_province_code,
                    func.count(),
                ).group_by(HousingDemandRecord.living_province_code)
            ).all()
        )
        assert len(province_counts) == 77
        assert sum(province_counts.values()) == REQUIRED_DEMAND_COUNT

        for payload in session.scalars(select(HousingDemandRecord.payload)):
            assert not any(CONTACT_FIELD_RE.search(key) for key in payload)
            text = " ".join(str(value) for value in payload.values())
            assert EMAIL_RE.search(text) is None
            assert PHONE_RE.search(text) is None

        second = sync_housing_demand(session)
        assert second == {
            "expected": REQUIRED_DEMAND_COUNT,
            "loaded": 0,
            "count": REQUIRED_DEMAND_COUNT,
            "changed": False,
        }

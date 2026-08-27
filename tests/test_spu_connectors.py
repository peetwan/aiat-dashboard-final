from __future__ import annotations

import pytest

from app.connectors.base import ConnectorContext
from app.connectors.spu_nsn_flood import SpuNsnFloodConnector
from app.connectors.spu_rawangphai_uru import SpuRawangphaiUruConnector
from app.connectors.spu_sukhothai_care import SpuSukhothaiCareConnector
from app.connectors.spu_sukhothai_water import SpuSukhothaiWaterConnector
from app.settings import Settings


class StubResponse:
    def __init__(self, payload=None, text=""):
        self.payload = payload
        self.text = text

    def json(self):
        return self.payload


class NamedRecorder:
    def __init__(self, responses):
        self.responses = responses

    def request(self, method, url, **kwargs):
        return self.responses[kwargs["name"]], None


def context(plan: dict, responses: dict, *, limit: int = 0) -> ConnectorContext:
    return ConnectorContext(
        source={"source_id": "spu_test"},
        plan=plan,
        settings=Settings(
            database_url="sqlite:///unused.sqlite",
            max_records_per_source=limit,
        ),
        recorder=NamedRecorder(responses),
    )


def test_sukhothai_care_rejects_pagination_beyond_max_pages():
    plan = {
        "datasets": [
            {
                "name": "announcements",
                "url": "https://example.test/announcements",
                "paginate": True,
                "page_size": 100,
                "max_pages": 1,
            }
        ]
    }
    responses = {
        "announcements_p1": StubResponse({"data": [{"id": 1}], "totalPages": 2})
    }
    with pytest.raises(RuntimeError, match="partial commits are forbidden"):
        SpuSukhothaiCareConnector().fetch(context(plan, responses))


def test_sukhothai_care_preserves_single_object_summary():
    plan = {
        "datasets": [
            {
                "name": "incident_stats",
                "url": "https://example.test/stats",
                "paginate": False,
            }
        ]
    }
    records = SpuSukhothaiCareConnector().fetch(
        context(plan, {"incident_stats": StubResponse({"total": 3, "open": 1})})
    )
    assert len(records) == 1
    assert records[0][0] == "incident_stats.row"
    assert records[0][1]["total"] == 3


def test_thaiwater_rejects_schema_drift_and_record_truncation():
    plan = {
        "datasets": [
            {"name": "water_levels", "url": "https://example.test/water-levels"}
        ]
    }
    with pytest.raises(RuntimeError, match="unexpected schema"):
        SpuSukhothaiWaterConnector().fetch(
            context(plan, {"water_levels": StubResponse({"waterlevel_data": {}})})
        )

    payload = {"waterlevel_data": {"data": [{"id": 1}, {"id": 2}]}}
    with pytest.raises(RuntimeError, match="partial commits are forbidden"):
        SpuSukhothaiWaterConnector().fetch(
            context(plan, {"water_levels": StubResponse(payload)}, limit=1)
        )


def test_rawangphai_and_nsn_fail_closed_on_schema_drift():
    rawang_plan = {
        "datasets": [
            {"name": "water_levels", "url": "https://example.test/water-levels"}
        ]
    }
    with pytest.raises(RuntimeError, match="no supported object-list payload"):
        SpuRawangphaiUruConnector().fetch(
            context(rawang_plan, {"water_levels": StubResponse({"unexpected": {}})})
        )

    nsn_plan = {
        "datasets": [
            {"name": "water_level_page", "url": "https://example.test/water-level"}
        ]
    }
    with pytest.raises(RuntimeError, match="returned no station links"):
        SpuNsnFloodConnector().fetch(
            context(nsn_plan, {"water_level_page": StubResponse(text="<html></html>")})
        )

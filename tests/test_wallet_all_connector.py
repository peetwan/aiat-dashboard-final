from __future__ import annotations

import pytest

from app.connectors.base import ConnectorContext
from app.connectors.wallet_all_realtime import (
    CURRENT_MONTH_BODY,
    EXPECTED_RECORD_COUNT,
    WalletAllRealtimeConnector,
    build_candidate_records,
)
from app.settings import Settings

HH_URL = "https://lesuper.app/api/opendata/superapp/gen4/hh"
BU_URL = "https://lesuper.app/api/opendata/superapp/gen4/bu"
PLAN = {
    "driver": "wallet_all_realtime",
    "connector": "app.connectors.wallet_all_realtime:WalletAllRealtimeConnector",
    "expected_record_count": EXPECTED_RECORD_COUNT,
    "requests": [
        {"name": "household_month", "url": HH_URL, "json_body": {"date": ""}},
        {"name": "business_month", "url": BU_URL, "json_body": {"date": ""}},
    ],
}


class StubJsonResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class NamedRecorder:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return StubJsonResponse(self.payloads[kwargs["name"]]), None


def complete_payloads(*, this_month: str = "2026-08") -> dict:
    household = {
        "thisMonth": this_month,
        "thisMonthName": "สิงหาคม 69",
        "yesterdayName": "19 สิงหาคม 2569",
        "diffName": "19 กรกฎาคม 2569",
        "snapshot": {"totalCash": 1, "totalIncome": 1, "totalExpense": 1},
        "snapshotDiff": {"totalCash": 1},
        "timeseries": [["วันที่", "รายได้"], ["1", 1]],
        "debtseries": [["วันที่", "สร้างหนี้"], ["1", 1]],
    }
    business = {
        "thisMonth": this_month,
        "thisMonthName": "สิงหาคม 69",
        "yesterdayName": "19 สิงหาคม 2569",
        "diffName": "19 กรกฎาคม 2569",
        "snapshot": {"totalCash": 1, "totalStock": 1},
        "snapshotDiff": {"totalCash": 1},
        "timeseries": [["วันที่", "สภาพคล่อง"], ["1", 1]],
        "cashSeries": [["วันที่", "สภาพคล่อง"], ["1", 1]],
        "cSeries": [["วันที่", "จำนวน"], ["1", 1]],
        "deSeries": [["วันที่", "จำนวน"], ["1", 1]],
    }
    return {"household_month": household, "business_month": business}


def test_wallet_all_connector_emits_two_current_month_grains_without_network():
    payloads = complete_payloads()
    recorder = NamedRecorder(payloads)
    context = ConnectorContext(
        source={"source_id": "f2_wallet_all_realtime"},
        plan=PLAN,
        settings=Settings(database_url="sqlite:///unused.sqlite", max_records_per_source=0),
        recorder=recorder,
    )

    records = WalletAllRealtimeConnector().fetch(context)
    assert len(records) == EXPECTED_RECORD_COUNT
    assert [key for key, _ in records] == ["household_month", "business_month"]
    assert all(payload["as_of"] == "2026-08" for _, payload in records)
    assert all(payload["thisMonth"] == "2026-08" for _, payload in records)
    assert [call[0] for call in recorder.calls] == ["POST", "POST"]
    assert [call[2]["json_body"] for call in recorder.calls] == [CURRENT_MONTH_BODY, CURRENT_MONTH_BODY]
    assert [call[2]["name"] for call in recorder.calls] == ["household_month", "business_month"]


def test_wallet_all_connector_fails_when_schema_or_month_drifts():
    payloads = complete_payloads()
    del payloads["household_month"]["snapshot"]
    with pytest.raises(RuntimeError, match="missing keys"):
        build_candidate_records(
            household=payloads["household_month"],
            business=complete_payloads()["business_month"],
        )

    mismatched = complete_payloads()
    mismatched["business_month"]["thisMonth"] = "2026-07"
    with pytest.raises(RuntimeError, match="thisMonth do not match"):
        build_candidate_records(
            household=mismatched["household_month"],
            business=mismatched["business_month"],
        )

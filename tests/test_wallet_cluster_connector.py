from __future__ import annotations

import pytest

from app.connectors.base import ConnectorContext
from app.connectors.wallet_cluster_realtime import (
    CURRENT_MONTH_BODY,
    WalletClusterRealtimeConnector,
    build_candidate_records,
)
from app.settings import Settings

HH_URL = "https://lesuper.app/api/opendata/superapp/gen4/cluster/hh"
BU_URL = "https://lesuper.app/api/opendata/superapp/gen4/cluster/bu"
CATEGORIES = ("กลุ่มตัวอย่าง ก", "กลุ่มตัวอย่าง ข")
PLAN = {
    "driver": "wallet_cluster_realtime",
    "connector": "app.connectors.wallet_cluster_realtime:WalletClusterRealtimeConnector",
    "expected_cluster_count": 2,
    "expected_record_count": 4,
    "requests": [
        {"name": "household_cluster", "url": HH_URL, "json_body": {}},
        {"name": "business_cluster", "url": BU_URL, "json_body": {}},
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


def _cluster(category: str, *, cash: int = 1) -> dict:
    return {"category": category, "totalCash": cash}


def complete_payloads(*, categories: tuple[str, ...] = CATEGORIES) -> dict:
    household_rows = [_cluster(name) for name in categories]
    business_rows = [_cluster(name, cash=2) for name in categories]
    household = {
        "thisMonth": "2026-08",
        "thisMonthName": "สิงหาคม 69",
        "yesterdayName": "19 สิงหาคม 2569",
        "categories": [["Category", "Popularity"], *[[name, 1] for name in categories]],
        "snapshotClusters": household_rows,
        "clustersName": list(categories),
    }
    business = {
        "thisMonth": "2026-08",
        "thisMonthName": "สิงหาคม 69",
        "yesterdayName": "19 สิงหาคม 2569",
        "categories": [["Category", "Popularity"], *[[name, 1] for name in categories]],
        "clusters": [{"id": f"cat{index}", "name": name} for index, name in enumerate(categories)],
        "snapshotClusters": business_rows,
        "clustersName": list(categories),
    }
    return {"household_cluster": household, "business_cluster": business}


def test_wallet_cluster_connector_emits_matching_hh_and_bu_categories_without_network():
    payloads = complete_payloads()
    recorder = NamedRecorder(payloads)
    context = ConnectorContext(
        source={"source_id": "f2_wallet_cluster_realtime"},
        plan=PLAN,
        settings=Settings(database_url="sqlite:///unused.sqlite", max_records_per_source=0),
        recorder=recorder,
    )

    records = WalletClusterRealtimeConnector().fetch(context)
    assert len(records) == 4
    assert [key for key, _ in records] == [
        "household_cluster",
        "household_cluster",
        "business_cluster",
        "business_cluster",
    ]
    assert [payload["category"] for _, payload in records] == [
        "กลุ่มตัวอย่าง ก",
        "กลุ่มตัวอย่าง ข",
        "กลุ่มตัวอย่าง ก",
        "กลุ่มตัวอย่าง ข",
    ]
    assert all(payload["as_of"] == "2026-08" for _, payload in records)
    assert [call[2]["json_body"] for call in recorder.calls] == [CURRENT_MONTH_BODY, CURRENT_MONTH_BODY]


def test_wallet_cluster_connector_fails_when_category_inventories_diverge():
    payloads = complete_payloads()
    payloads["business_cluster"]["snapshotClusters"][1]["category"] = "กลุ่มอื่น"
    payloads["business_cluster"]["clustersName"][1] = "กลุ่มอื่น"
    with pytest.raises(RuntimeError, match="category inventories do not match"):
        build_candidate_records(
            household=payloads["household_cluster"],
            business=payloads["business_cluster"],
            expected_cluster_count=2,
            expected_record_count=4,
        )


def test_wallet_cluster_connector_does_not_use_frontend_population_total_as_a_gate():
    payloads = complete_payloads()
    payloads["household_cluster"]["categories"] = [
        ["Category", "Popularity"],
        ["กลุ่มตัวอย่าง ก", 100],
        ["กลุ่มตัวอย่าง ข", 275],
    ]
    records = build_candidate_records(
        household=payloads["household_cluster"],
        business=payloads["business_cluster"],
        expected_cluster_count=2,
        expected_record_count=4,
    )
    assert len(records) == 4

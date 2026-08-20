"""Current-month Super App wallet cluster aggregates (household + business).

Serving ingest follows the public cluster dashboard: unauthenticated POST with
an empty JSON body. Category inventories on the two endpoints must match. Small
cells stay as the website published them; they are still Candidate/needs_review.
Do not compare frontend hardcoded population totals with API category sizes.
"""

from __future__ import annotations

import re
from typing import Any

from app.connectors.base import ConnectorContext, DatasetRecord

THIS_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
HOUSEHOLD_REQUIRED_KEYS = frozenset(
    {
        "thisMonth",
        "thisMonthName",
        "yesterdayName",
        "categories",
        "snapshotClusters",
        "clustersName",
    }
)
BUSINESS_REQUIRED_KEYS = frozenset(
    {
        "thisMonth",
        "thisMonthName",
        "yesterdayName",
        "categories",
        "clusters",
        "clustersName",
        "snapshotClusters",
    }
)
REQUIRED_REQUESTS = ("household_cluster", "business_cluster")
EXPECTED_CLUSTER_COUNT = 7
EXPECTED_RECORD_COUNT = 14
CURRENT_MONTH_BODY: dict[str, Any] = {}


def _require_object(payload: Any, label: str) -> dict:
    if not isinstance(payload, dict):
        raise RuntimeError(f"wallet cluster {label} response is not an object")
    return payload


def _require_keys(payload: dict, required: frozenset[str], label: str) -> None:
    missing = sorted(required - set(payload))
    if missing:
        raise RuntimeError(f"wallet cluster {label} missing keys: {', '.join(missing)}")


def _this_month(payload: dict, label: str) -> str:
    value = payload.get("thisMonth")
    if not isinstance(value, str) or not THIS_MONTH_RE.fullmatch(value):
        raise RuntimeError(f"wallet cluster {label} thisMonth is not YYYY-MM")
    return value


def _cluster_rows(payload: dict, label: str) -> list[dict]:
    rows = payload.get("snapshotClusters")
    names = payload.get("clustersName")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f"wallet cluster {label} snapshotClusters is not a non-empty array")
    if not isinstance(names, list) or not names:
        raise RuntimeError(f"wallet cluster {label} clustersName is not a non-empty array")
    categories: list[str] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise RuntimeError(f"wallet cluster {label} snapshotClusters[{index}] is not an object")
        category = row.get("category")
        if not isinstance(category, str) or not category.strip():
            raise RuntimeError(f"wallet cluster {label} snapshotClusters[{index}] has no category")
        categories.append(category)
    declared = [str(item) for item in names]
    if declared != categories:
        raise RuntimeError(f"wallet cluster {label} clustersName does not match snapshotClusters")
    if len(set(categories)) != len(categories):
        raise RuntimeError(f"wallet cluster {label} snapshotClusters has duplicate categories")
    return rows


def build_candidate_records(
    *,
    household: dict,
    business: dict,
    expected_cluster_count: int = EXPECTED_CLUSTER_COUNT,
    expected_record_count: int = EXPECTED_RECORD_COUNT,
) -> list[DatasetRecord]:
    household = _require_object(household, "household_cluster")
    business = _require_object(business, "business_cluster")
    _require_keys(household, HOUSEHOLD_REQUIRED_KEYS, "household_cluster")
    _require_keys(business, BUSINESS_REQUIRED_KEYS, "business_cluster")
    household_month = _this_month(household, "household_cluster")
    business_month = _this_month(business, "business_cluster")
    if household_month != business_month:
        raise RuntimeError(
            "wallet cluster household and business thisMonth do not match: "
            f"{household_month} vs {business_month}"
        )
    household_rows = _cluster_rows(household, "household_cluster")
    business_rows = _cluster_rows(business, "business_cluster")
    household_names = [row["category"] for row in household_rows]
    business_names = [row["category"] for row in business_rows]
    if household_names != business_names:
        raise RuntimeError("wallet cluster household and business category inventories do not match")
    if len(household_rows) != expected_cluster_count:
        raise RuntimeError(
            "wallet cluster incomplete: "
            f"clusters={len(household_rows)}; expected {expected_cluster_count}"
        )

    records: list[DatasetRecord] = []
    for row in household_rows:
        records.append(
            (
                "household_cluster",
                {
                    "thisMonth": household_month,
                    "thisMonthName": household.get("thisMonthName"),
                    "category": row["category"],
                    "as_of": household_month,
                    "snapshot": row,
                },
            )
        )
    for row in business_rows:
        records.append(
            (
                "business_cluster",
                {
                    "thisMonth": business_month,
                    "thisMonthName": business.get("thisMonthName"),
                    "category": row["category"],
                    "as_of": business_month,
                    "snapshot": row,
                },
            )
        )
    if len(records) != expected_record_count:
        raise RuntimeError(
            f"wallet cluster incomplete: records={len(records)}; expected {expected_record_count}"
        )
    return records


class WalletClusterRealtimeConnector:
    driver_name = "wallet_cluster_realtime"

    def fetch(self, context: ConnectorContext) -> list[DatasetRecord]:
        requests = list(context.plan.get("requests") or [])
        names = [str(request.get("name") or "") for request in requests]
        if names != list(REQUIRED_REQUESTS):
            raise RuntimeError(
                "wallet cluster plan must declare household_cluster then business_cluster POST requests"
            )
        payloads: dict[str, dict] = {}
        for request in requests:
            json_body = request.get("json_body")
            if json_body != CURRENT_MONTH_BODY:
                raise RuntimeError(
                    "wallet cluster serving ingest only posts the public dashboard empty JSON body"
                )
            response, _ = context.recorder.request(
                "POST",
                request["url"],
                name=request["name"],
                json_body=json_body,
            )
            payloads[request["name"]] = response.json()
        expected_cluster_count = int(
            context.plan.get("expected_cluster_count") or EXPECTED_CLUSTER_COUNT
        )
        expected_record_count = int(
            context.plan.get("expected_record_count") or (expected_cluster_count * 2)
        )
        return build_candidate_records(
            household=payloads["household_cluster"],
            business=payloads["business_cluster"],
            expected_cluster_count=expected_cluster_count,
            expected_record_count=expected_record_count,
        )

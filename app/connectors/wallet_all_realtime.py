"""Current-month Super App wallet aggregates (household + business).

Serving ingest follows the public open-data dashboard default: POST
``{"date": ""}`` to the two unauthenticated gen4 endpoints. Monthly history
stays in the evidence workspace / R2. GET is 405 on these routes and is not
called. Amounts are the public page aggregates, not person-level rows.
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
        "diffName",
        "snapshot",
        "snapshotDiff",
        "timeseries",
        "debtseries",
    }
)
BUSINESS_REQUIRED_KEYS = frozenset(
    {
        "thisMonth",
        "thisMonthName",
        "yesterdayName",
        "diffName",
        "snapshot",
        "snapshotDiff",
        "timeseries",
        "cashSeries",
        "cSeries",
        "deSeries",
    }
)
REQUIRED_REQUESTS = ("household_month", "business_month")
EXPECTED_RECORD_COUNT = 2
CURRENT_MONTH_BODY = {"date": ""}


def _require_object(payload: Any, label: str) -> dict:
    if not isinstance(payload, dict):
        raise RuntimeError(f"wallet all {label} response is not an object")
    return payload


def _require_keys(payload: dict, required: frozenset[str], label: str) -> None:
    missing = sorted(required - set(payload))
    if missing:
        raise RuntimeError(f"wallet all {label} missing keys: {', '.join(missing)}")


def _this_month(payload: dict, label: str) -> str:
    value = payload.get("thisMonth")
    if not isinstance(value, str) or not THIS_MONTH_RE.fullmatch(value):
        raise RuntimeError(f"wallet all {label} thisMonth is not YYYY-MM")
    return value


def _snapshot(payload: dict, label: str) -> dict:
    snapshot = payload.get("snapshot")
    if not isinstance(snapshot, dict) or not snapshot:
        raise RuntimeError(f"wallet all {label} snapshot is not an object")
    return snapshot


def build_candidate_records(
    *,
    household: dict,
    business: dict,
    expected_record_count: int = EXPECTED_RECORD_COUNT,
) -> list[DatasetRecord]:
    household = _require_object(household, "household_month")
    business = _require_object(business, "business_month")
    _require_keys(household, HOUSEHOLD_REQUIRED_KEYS, "household_month")
    _require_keys(business, BUSINESS_REQUIRED_KEYS, "business_month")
    household_month = _this_month(household, "household_month")
    business_month = _this_month(business, "business_month")
    if household_month != business_month:
        raise RuntimeError(
            "wallet all household and business thisMonth do not match: "
            f"{household_month} vs {business_month}"
        )
    _snapshot(household, "household_month")
    _snapshot(business, "business_month")

    records: list[DatasetRecord] = [
        (
            "household_month",
            {
                "thisMonth": household_month,
                "thisMonthName": household.get("thisMonthName"),
                "as_of": household_month,
                "snapshot": household["snapshot"],
                "snapshotDiff": household.get("snapshotDiff"),
                "timeseries": household.get("timeseries"),
                "debtseries": household.get("debtseries"),
            },
        ),
        (
            "business_month",
            {
                "thisMonth": business_month,
                "thisMonthName": business.get("thisMonthName"),
                "as_of": business_month,
                "snapshot": business["snapshot"],
                "snapshotDiff": business.get("snapshotDiff"),
                "timeseries": business.get("timeseries"),
                "cashSeries": business.get("cashSeries"),
                "cSeries": business.get("cSeries"),
                "deSeries": business.get("deSeries"),
            },
        ),
    ]
    if len(records) != expected_record_count:
        raise RuntimeError(
            f"wallet all incomplete: records={len(records)}; expected {expected_record_count}"
        )
    return records


class WalletAllRealtimeConnector:
    driver_name = "wallet_all_realtime"

    def fetch(self, context: ConnectorContext) -> list[DatasetRecord]:
        requests = list(context.plan.get("requests") or [])
        names = [str(request.get("name") or "") for request in requests]
        if names != list(REQUIRED_REQUESTS):
            raise RuntimeError(
                "wallet all plan must declare household_month then business_month POST requests"
            )
        payloads: dict[str, dict] = {}
        for request in requests:
            json_body = request.get("json_body")
            if json_body != CURRENT_MONTH_BODY:
                raise RuntimeError(
                    "wallet all serving ingest only posts the public dashboard current-month body"
                )
            response, _ = context.recorder.request(
                "POST",
                request["url"],
                name=request["name"],
                json_body=json_body,
            )
            payloads[request["name"]] = response.json()
        return build_candidate_records(
            household=payloads["household_month"],
            business=payloads["business_month"],
            expected_record_count=int(
                context.plan.get("expected_record_count") or EXPECTED_RECORD_COUNT
            ),
        )

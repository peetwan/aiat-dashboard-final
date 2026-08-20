from __future__ import annotations

from pathlib import Path

import pytest

from app.connectors.base import ConnectorContext
from app.connectors.pppconnext import (
    EXPECTED_PROVINCE_COUNT,
    EXPECTED_RECORD_COUNT,
    PppconnextConnector,
    build_candidate_records,
)
from app.settings import Settings

PLAN = {
    "driver": "pppconnext",
    "connector": "app.connectors.pppconnext:PppconnextConnector",
    "expected_record_count": EXPECTED_RECORD_COUNT,
    "requests": [
        {
            "name": "national_bootstrap",
            "url": "https://ppaos.com/2026/api/khm/v1/dashboard/ppaos-national-bootstrap?metric=poor_households_rate&survey_year=all",
        },
        {
            "name": "province_analytics",
            "url": "https://ppaos.com/2026/api/khm/v1/dashboard/ppaos-province-analytics?prov_code=0&survey_year=all&chart_years=2563%2C2564%2C2565%2C2566%2C2567%2C2568%2C2569&chart_sections=cumulative",
        },
        {
            "name": "poor_capital_potential",
            "url": "https://ppaos.com/2026/api/khm/v1/dashboard/ppaos-poor-capital-potential?prov_code=0&survey_year=all",
        },
        {
            "name": "assistance_summary",
            "url": "https://ppaos.com/2026/api/khm/v1/dashboard/ppaos-assistance-summary?prov_code=0&survey_year=all",
        },
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
        return StubJsonResponse(self.payloads[kwargs["name"]]), Path("fixture.json")


def _province(code: int) -> dict:
    return {
        "prov_code": code,
        "prov_name": f"จังหวัด{code:02d}",
        "households_total": code,
        "avg_score": 1.0,
    }


def complete_payloads(*, province_count: int = EXPECTED_PROVINCE_COUNT) -> dict:
    codes = list(range(1, province_count + 1))
    years = [2563, 2564, 2565, 2566, 2567, 2568, 2569]
    capital_keys = ("human", "physical", "economic", "natural", "social")
    assistance_keys = ("health", "education", "living", "gov", "other")
    return {
        "national_bootstrap": {
            "success": True,
            "data": {
                "available_survey_years": {
                    "households_by_year": [
                        {"survey_year": year, "households_total": year} for year in years
                    ]
                },
                "map_summary": {
                    "items": [_province(code) for code in codes],
                    "summary": {"households_total": 20, "avg_score": 2.0},
                },
            },
            "meta": {"allowed_province_codes": [f"{code:02d}" for code in codes]},
        },
        "province_analytics": {
            "success": True,
            "data": {
                "households_in_system_total": 1,
                "members_in_system_total": 2,
                "member_registration": {"members_total": 2, "named_present": 1},
                "by_year_cumulative": [
                    {
                        "survey_year": year,
                        "households_total": year,
                        "members_total": year,
                    }
                    for year in years
                ],
            },
        },
        "poor_capital_potential": {
            "success": True,
            "data": {
                "household_count": 20,
                "overall_avg": 2.0,
                "overall_sd": 0.1,
                "dimensions": [
                    {"key": key, "label": key, "avg": 1.5, "sd": 0.1} for key in capital_keys
                ],
            },
        },
        "assistance_summary": {
            "success": True,
            "data": {
                "year": "all",
                "year_label": "พ.ศ. 2563 – 2569",
                "total_households": 1,
                "total_episodes": 1,
                "total_budget_baht": 1,
                "dimensions": [
                    {
                        "key": key,
                        "title": key,
                        "households": 1,
                        "episode_count": 1,
                        "budget_baht": 1,
                        "share_pct": 1,
                        "episode_share_pct": 1,
                        "budget_share_pct": 1,
                    }
                    for key in assistance_keys
                ],
            },
        },
    }


def test_pppconnext_connector_emits_reviewed_47_grains_without_network():
    payloads = complete_payloads()
    recorder = NamedRecorder(payloads)
    context = ConnectorContext(
        source={"source_id": "f1_pppconnext"},
        plan=PLAN,
        settings=Settings(database_url="sqlite:///unused.sqlite", max_records_per_source=0),
        recorder=recorder,
    )

    records = PppconnextConnector().fetch(context)
    counts = {}
    for dataset_key, _payload in records:
        counts[dataset_key] = counts.get(dataset_key, 0) + 1

    assert len(records) == EXPECTED_RECORD_COUNT
    assert counts == {
        "national_summary": 1,
        "province_summary": 20,
        "survey_year_households": 7,
        "survey_year_cumulative": 7,
        "capital_dimension": 5,
        "capital_overall": 1,
        "assistance_dimension": 5,
        "assistance_summary": 1,
    }
    assert all(payload["as_of"] is None for _, payload in records)
    assert [call[0] for call in recorder.calls] == ["GET"] * 4
    assert [call[2]["name"] for call in recorder.calls] == [
        "national_bootstrap",
        "province_analytics",
        "poor_capital_potential",
        "assistance_summary",
    ]


def test_pppconnext_connector_fails_closed_when_province_inventory_drifts():
    payloads = complete_payloads(province_count=19)
    with pytest.raises(RuntimeError, match="province inventory incomplete"):
        build_candidate_records(
            national_bootstrap=payloads["national_bootstrap"],
            province_analytics=payloads["province_analytics"],
            poor_capital_potential=payloads["poor_capital_potential"],
            assistance_summary=payloads["assistance_summary"],
        )

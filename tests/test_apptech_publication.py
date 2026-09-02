from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.connectors.target_household import FAMILY_DASHBOARD_URL, INNOVATOR_DASHBOARD_URL
from tools.build_apptech_aggregates import SOURCE_ID, build


@pytest.fixture()
def recorded_run(tmp_path):
    fixture = json.loads((Path(__file__).parent / "fixtures/apptech_dashboard_aggregates.json").read_text(encoding="utf-8"))
    artifacts = []
    for year in ("all", "2025", "2026"):
        for kind, endpoint in (("innovator", INNOVATOR_DASHBOARD_URL), ("family", FAMILY_DASHBOARD_URL)):
            path = tmp_path / f"{kind}_{year}.bin"
            raw = fixture[f"{kind}_html"].encode("utf-8")
            path.write_bytes(raw)
            artifacts.append({"path": f"data/runtime/raw/{SOURCE_ID}/fixture/{path.name}", "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "method": "GET", "http_status": 200, "url": endpoint + (f"?year_filter={year}" if year != "all" else "")})
    manifest = {"source_id": SOURCE_ID, "run_id": "fixture", "status": "complete", "fetched_at": "2026-09-02T00:00:00+00:00", "artifacts": artifacts}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


def test_apptech_builder_is_deterministic_and_projects_only_reviewed_aggregate_fields(recorded_run, monkeypatch):
    import httpx

    def no_network(*args, **kwargs):
        pytest.fail("Publication builder attempted an upstream request")

    monkeypatch.setattr(httpx.Client, "request", no_network)
    first = build(recorded_run, ["all", "2025", "2026"])
    assert first == build(recorded_run, ["all", "2025", "2026"])
    payload, manifest = first
    assert payload["as_of"] is None
    assert payload["generated_at"] == "2026-09-02T00:00:00+00:00"
    assert len(payload["innovator_dashboard_province"]) == 3
    assert len(payload["household_economic_summary"]) == 3
    assert {row["geography"] for row in payload["household_economic_summary"]} == {"country"}
    assert payload["innovator_dashboard_province"][0]["total_inno"] == 787
    assert "unpublished_marker" not in json.dumps(payload)
    assert "raw-only" not in json.dumps(payload)
    assert len(manifest["inputs"]) == 6


@pytest.mark.parametrize("problem", ["missing_page", "duplicate_page", "wrong_source", "failed_run", "failed_response", "wrong_year", "tampered_response", "invalid_schema"])
def test_apptech_builder_rejects_incomplete_or_unverified_runs(recorded_run, problem):
    path = recorded_run / "manifest.json"
    manifest = json.loads(path.read_text())
    if problem == "missing_page":
        manifest["artifacts"].pop()
    elif problem == "duplicate_page":
        manifest["artifacts"].append(manifest["artifacts"][0])
    elif problem == "wrong_source":
        manifest["source_id"] = "other_source"
    elif problem == "failed_run":
        manifest["status"] = "failed"
    elif problem == "failed_response":
        manifest["artifacts"][0]["http_status"] = 503
    elif problem == "wrong_year":
        manifest["artifacts"][0]["url"] += "?year_filter=2099"
    else:
        artifact = manifest["artifacts"][0]
        raw = b'const provData = {"province": {}};'
        (recorded_run / Path(artifact["path"]).name).write_bytes(raw)
        if problem == "invalid_schema":
            artifact.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises((ValueError, RuntimeError)):
        build(recorded_run, ["all", "2025", "2026"])


def test_committed_apptech_release_has_unique_province_years_and_country_only_money():
    root = Path(__file__).resolve().parents[1]
    payload = json.loads((root / "data/public/apptech_aggregates.json").read_text(encoding="utf-8"))
    rows = payload["innovator_dashboard_province"]
    assert len({(row["year_filter"], row["province_name_th"]) for row in rows}) == len(rows)
    assert {row["year_filter"] for row in rows} == set(payload["year_filters"])
    economics = payload["household_economic_summary"]
    assert len(economics) == len(payload["year_filters"])
    assert {row["year_filter"] for row in economics} == set(payload["year_filters"])
    assert all(row["geography"] == "country" and "province_name_th" not in row for row in economics)

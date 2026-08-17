from __future__ import annotations

import gzip
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.main import app
from app.models import SpatialFeature
from app import spatial_artifacts
from app.settings import PROJECT_ROOT


def write_gzip_row(path, row: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as handle:
            handle.write(
                (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
            )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_spatial_sync_is_transactional_and_idempotent(tmp_path, monkeypatch):
    counts = {layer_id: 1 for layer_id in spatial_artifacts.REQUIRED_SPATIAL_COUNTS}
    monkeypatch.setattr(spatial_artifacts, "REQUIRED_SPATIAL_COUNTS", counts)
    monkeypatch.setattr(spatial_artifacts, "REQUIRED_SPATIAL_TOTAL", 4)
    spatial_root = tmp_path / "data" / "spatial"
    layers = {}
    for index, layer_id in enumerate(counts, start=1):
        artifact_path = spatial_root / f"{layer_id}.ndjson.gz"
        row = {
            "source_id": "f3_housing_portal",
            "layer_id": layer_id,
            "feature_id": f"feature-{index}",
            "geometry_type": "Point",
            "bbox": [100.0, 13.0, 100.0, 13.0],
            "geometry": {"type": "Point", "coordinates": [100.0, 13.0]},
            "properties": {"adm3_pcode": "TH100101"},
            "endpoint": "https://data.thaihousingportal.com/example",
            "fetched_at": "2026-08-17T00:00:00+00:00",
            "as_of": "ไม่ระบุ",
            "evidence_path": "data/raw/example.json",
            "evidence_sha256": "a" * 64,
            "quality_status": "needs_review",
        }
        digest = write_gzip_row(artifact_path, row)
        layers[layer_id] = {
            "feature_count": 1,
            "artifact_path": f"data/spatial/{artifact_path.name}",
            "artifact_bytes": artifact_path.stat().st_size,
            "artifact_sha256": digest,
        }
    manifest = {
        "validation_status": "pass",
        "source_id": "f3_housing_portal",
        "layers": layers,
        "privacy_projection": {
            "demand_respondent_rows_included": 0,
            "contact_fields_included": 0,
        },
    }
    manifest_path = spatial_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with TestClient(app):
        with SessionLocal() as session:
            first = spatial_artifacts.sync_spatial_layers(session, manifest_path)
            assert first["loaded"] == 4
            assert first["counts"] == counts
            assert session.scalar(select(func.count()).select_from(SpatialFeature)) == 4
            second = spatial_artifacts.sync_spatial_layers(session, manifest_path)
            assert second["loaded"] == 0
            assert sorted(second["unchanged_layers"]) == sorted(counts)

    artifact_path.write_bytes(artifact_path.read_bytes() + b"corrupt")
    with pytest.raises(RuntimeError, match="byte count mismatch"):
        spatial_artifacts.load_spatial_manifest(manifest_path)


def test_housing_spatial_summary_and_query_contract():
    with TestClient(app) as client:
        summary = client.get("/api/public/v1/housing-spatial/summary")
        assert summary.status_code == 200
        payload = summary.json()
        assert set(payload["counts"]) == {
            "subdistrict_boundaries",
            "housing_points",
            "accessibility_grid",
            "flood_grid",
        }
        assert all(count >= 0 for count in payload["counts"].values())
        assert payload["total_spatial_features"] == sum(payload["counts"].values())
        assert payload["database_contract"]["layer_counts"] == payload["counts"]
        assert payload["database_contract"]["demand_respondent_rows_included"] == 0

        unsupported = client.get(
            "/api/public/v1/housing-spatial/features",
            params={"layer_id": "demand_respondents"},
        )
        assert unsupported.status_code == 422


def test_spatial_mapping_rejects_private_properties():
    row = {
        "source_id": "f3_housing_portal",
        "layer_id": "housing_points",
        "feature_id": "private-point",
        "geometry_type": "Point",
        "bbox": [100.0, 13.0, 100.0, 13.0],
        "geometry": {"type": "Point", "coordinates": [100.0, 13.0]},
        "properties": {"contact_email": "person@example.com"},
        "evidence_path": "data/raw/example.json",
        "evidence_sha256": "a" * 64,
        "fetched_at": "2026-08-17T00:00:00+00:00",
        "as_of": "ไม่ระบุ",
        "quality_status": "needs_review",
    }

    with pytest.raises(ValueError, match="private/contact value"):
        spatial_artifacts._mapping(row, "housing_points")


def test_housing_demand_public_summary_privacy_contract():
    contract = json.loads(
        (
            PROJECT_ROOT
            / "config"
            / "publication_contracts"
            / "housing_summaries.json"
        ).read_text(encoding="utf-8")
    )
    expected_provinces = contract["completeness"]["province_count"]
    with TestClient(app) as client:
        response = client.get("/api/public/v1/housing-demand/summary")
        assert response.status_code == 200
        payload = response.json()
        assert payload["source_id"] == "f3_housing_portal"
        assert payload["province_count"] == len(payload["provinces"])
        assert payload["province_count"] == expected_provinces
        assert sum(
            int(item["respondents_living"])
            for item in payload["provinces"].values()
        ) == payload["record_count"]
        privacy = payload["privacy_projection"]
        assert privacy["excluded_source_fields"] == ["id"]
        assert privacy["source_identifier_published"] is False
        assert privacy["name_fields_in_source_schema"] == 0
        assert privacy["phone_fields_in_source_schema"] == 0
        assert privacy["email_fields_in_source_schema"] == 0

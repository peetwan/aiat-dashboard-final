from __future__ import annotations

import gzip
import hashlib
import json

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.main import app
from app.models import SpatialFeature
from app import spatial_artifacts


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


def test_housing_spatial_summary_and_query_contract():
    with TestClient(app) as client:
        summary = client.get("/api/public/v1/housing-spatial/summary")
        assert summary.status_code == 200
        payload = summary.json()
        assert payload["counts"] == {
            "subdistrict_boundaries": 169,
            "housing_points": 28694,
            "accessibility_grid": 6543,
            "flood_grid": 159126,
        }
        assert payload["total_spatial_features"] == 194532
        assert payload["database_contract"]["demand_respondent_rows_included"] == 0

        unsupported = client.get(
            "/api/public/v1/housing-spatial/features",
            params={"layer_id": "demand_respondents"},
        )
        assert unsupported.status_code == 422

from __future__ import annotations

import gzip
import json
import socket
from pathlib import Path

import pytest

from tools.f2_pipeline.common import digest, write_json
from tools.f2_pipeline.field_approval import (
    C02_ACCEPTED_FIELD_REVIEW_STATUS,
    C02_FIELD_REVIEW_ID,
    C02_OWNER_ACCEPTANCE_ID,
    C02_REVIEW_SCOPE_SHA256,
    C02_REVIEWED_SOURCE_MANIFEST_SHA256,
)


@pytest.fixture(autouse=True)
def clean_database():
    # These offline file pipelines have no database dependency.
    yield


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("F2 builds and tests must not access the network")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


@pytest.fixture
def c02_owner_acceptance():
    """Fresh test-only approval metadata; never reads or grants real approval."""
    return {
        "schema_version": 1,
        "acceptance_id": C02_OWNER_ACCEPTANCE_ID,
        "acceptance_status": C02_ACCEPTED_FIELD_REVIEW_STATUS,
        "review_id": C02_FIELD_REVIEW_ID,
        "reviewed_measures": ["C02_COMMUNITY"],
        "review_scope_sha256": C02_REVIEW_SCOPE_SHA256,
        "source_candidate_manifest_sha256": C02_REVIEWED_SOURCE_MANIFEST_SHA256,
        "scope": "c02_person_fields_only",
        "public_promotion_approved": False,
        "deployment_approved": False,
    }


def mapped_record(key, title="Synthetic temple", province="Alpha", code="10", category="AA", additional=()):
    return {
        "external_id": key, "title": title, "source_url": f"https://www.culturalmapthailand.info/{key}",
        "data": {
            "names": {"th": title},
            "classification": {"primary_category": {"code": category, "name_th": category, "name_en": category},
                               "additional_categories": [{"code": value} for value in additional], "cultural_type": {"code": "synthetic"}},
            "location": {"administrative": {"province": {"name_th": province, "code": code}, "amphure": None, "tambon": None},
                         "coordinates": {"latitude": 13.0, "longitude": 100.0}, "address_raw": "private home must not be public"},
            "description": {"history": "<p>A synthetic public cultural work.</p>", "identity": "A fixture, not a real source record."},
            "people": {"contact_raw": "private@example.invalid", "informants_raw": "Private respondent"},
            "assessment": {"private_score": 9}, "dates": {"recorded": "2020-01-01"},
            "media": {"images": [{"url": "https://dp.culturalmapthailand.info/images/synthetic.jpg"}],
                      "clips": [], "documents": [], "links": [], "narration_links": []},
        },
    }


@pytest.fixture
def record_factory():
    return mapped_record


@pytest.fixture
def build_inputs(tmp_path):
    def create(rows=None, merges=()):
        root = tmp_path / "inputs"
        config_root = root / "config"
        evidence_root = root / "evidence"
        source_id, run_id = "f2_culturalmap_university", "20260101T000000Z"
        source_dir = evidence_root / source_id / run_id
        source_dir.mkdir(parents=True)
        records = rows if rows is not None else [mapped_record("CD-1", additional=("AR",)), mapped_record("CD-2", province="Beta", code="20", category="AR")]
        files, declared = [], []
        for dataset in ("map_inspiration", "products", "activities", "recreation", "team"):
            payload = {"schema_version": 2, "run_id": run_id, "page_id": dataset, "scraped_at": "2026-01-01T00:00:00Z",
                       "data": {"records": records if dataset == "map_inspiration" else []}}
            path = source_dir / f"{dataset}.json"
            write_json(path, payload)
            compressed = path.with_suffix(".json.gz")
            compressed.write_bytes(gzip.compress(path.read_bytes(), mtime=0))
            for artifact, kind in ((path, "support"), (compressed, "evidence")):
                item = {"path": artifact.name, "sha256": digest(artifact), "size": artifact.stat().st_size, "dataset_key": dataset,
                        "kind": kind, "captured_at": "2026-01-01T00:00:00Z", "grain": "one captured envelope with data.records"}
                if artifact == path:
                    item.update(provenance_class="local_expanded_copy_of_canonical_evidence", canonical_evidence_path=compressed.name)
                files.append(item)
            declared.append({"file": compressed.name, "sha256": digest(compressed), "dataset_key": dataset, "row_count": 1})
        manifest = {"source_id": source_id, "run_id": run_id, "datasets": declared, "extra_files": []}
        write_json(source_dir / "manifest.json", manifest)
        files.append({"path": "manifest.json", "sha256": digest(source_dir / "manifest.json"), "size": (source_dir / "manifest.json").stat().st_size,
                      "kind": "manifest", "dataset_key": "capture_manifest", "captured_at": "2026-01-01T00:00:00Z", "grain": "capture_manifest"})
        lock = {"schema_version": 1, "sources": [{"source_id": source_id, "run_id": run_id, "relative_dir": f"{source_id}/{run_id}",
                                                "originating_system": "Synthetic Cultural Map", "files": files,
                                                "manifest_validation": {"path": "manifest.json"}}], "integrity_exceptions": []}
        write_json(config_root / "inputs.json", lock)
        definition = {"measure_id": "K12", "label_th": "ทุนวัฒนธรรม", "unit": "mapped_subject", "status": "available_snapshot",
                      "formula": "COUNT DISTINCT subject_id", "scope": "synthetic captured records", "limitations": "synthetic snapshot",
                      "display_order": 14, "supported_filters": ["province", "category"]}
        write_json(config_root / "measures.json", {"schema_version": 1, "measures": [definition]})
        reviews = {"subject_identity": {"reviewed_merges": list(merges)}, "source": {"source_id": source_id, "run_id": run_id,
                   "validation": {"capture_sha256": digest(source_dir / "map_inspiration.json"), "record_count": len(records)}}}
        write_json(config_root / "reviews.json", reviews)
        hierarchy = [{"provinceCode": 10, "provinceNameTh": "Alpha"}, {"provinceCode": 20, "provinceNameTh": "Beta"}]
        geography = config_root / "geography"
        for name, data in (("provinces", hierarchy), ("districts", []), ("subdistricts", [])):
            write_json(geography / f"{name}.json", data)
        write_json(geography / "thailand_geography_manifest.json", {"files": {name + ".json": {"sha256": digest(geography / f"{name}.json")} for name in ("provinces", "districts", "subdistricts")}})
        write_json(config_root / "dashboard.json", {"provinces": [{"province_code": "10", "province_name_th": "Alpha", "dashboard_region": "Region"},
                                                                  {"province_code": "20", "province_name_th": "Beta", "dashboard_region": "Region"}]})
        policy_path = Path(__file__).resolve().parents[2] / "config/f2_pipeline/k12_projection_policy.json"
        policy = json.loads(policy_path.read_text())
        write_json(config_root / "policy.json", policy)
        roles = {"inputs.json": "input_lock", "measures.json": "measures", "reviews.json": "reviews", "dashboard.json": "dashboard_provinces", "policy.json": "projection_policy"}
        config_files = [{"path": path.relative_to(config_root).as_posix(), "sha256": digest(path), "role": roles.get(path.name)} for path in sorted(config_root.rglob("*.json"))]
        config = {"schema_version": 1, "release_id": "f2-dashboard-k12-checkpoint-test", "release_date": "2026-01-01", "complete": False,
                  "publication_status": "development_only", "enabled_measures": ["K12"], "enabled_sources": [source_id],
                  "expected_province_count": 2, "geography_directory": "geography", "config_files": config_files}
        config_path = config_root / "checkpoint.json"
        write_json(config_path, config)
        return {"config": config_path, "evidence_root": evidence_root, "source_dir": source_dir, "lock": lock, "config_root": config_root}
    return create

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app import demand_artifacts, public_artifacts, spatial_artifacts
from app.models import PublicArtifact


@pytest.fixture
def public_sync_workspace(tmp_path, monkeypatch):
    contracts = public_artifacts.load_contracts(
        public_artifacts.PROJECT_ROOT / "config/publication_contracts"
    )
    monkeypatch.setattr(public_artifacts, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(public_artifacts, "load_contracts", lambda root: contracts)
    inputs = []
    for index in range(3):
        path = tmp_path / f"example-{index}.json"
        path.write_text(json.dumps({"items": [{"value": index}]}), encoding="utf-8")
        inputs.append(public_artifacts.ArtifactInput(f"example/{index}", "example", path))
    engine = create_engine("sqlite://")
    PublicArtifact.__table__.create(engine)
    try:
        yield engine, inputs
    finally:
        engine.dispose()


def test_unchanged_public_sync_reads_metadata_once_without_database_payloads(
    public_sync_workspace,
):
    engine, inputs = public_sync_workspace
    with Session(engine, autoflush=False) as session:
        first = public_artifacts.sync_public_artifacts(session, inputs)
        assert first == {"expected": 3, "inserted": 3, "updated": 0, "unchanged": 0}
    statements = []

    @event.listens_for(engine, "before_cursor_execute")
    def record_statement(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    with Session(engine, autoflush=False) as session:
        report = public_artifacts.sync_public_artifacts(session, inputs)

    assert report == {"expected": 3, "inserted": 0, "updated": 0, "unchanged": 3}
    reads = [statement for statement in statements if statement.startswith("SELECT")]
    assert len(reads) == 1
    assert "public_artifacts.payload" not in reads[0]
    assert not any(statement.startswith(("INSERT", "UPDATE")) for statement in statements)


def test_public_sync_preserves_replace_update_and_delete_semantics(public_sync_workspace):
    engine, inputs = public_sync_workspace
    with Session(engine, autoflush=False) as session:
        public_artifacts.sync_public_artifacts(session, inputs)
    changed_payload = {"items": [{"value": "revised"}, {"value": "second"}]}
    inputs[0].path.write_text(json.dumps(changed_payload), encoding="utf-8")
    changed = replace(inputs[0], group="revised", province_code="10")
    added = replace(inputs[1], key="example/new")
    selected = [changed, inputs[2], added]

    with Session(engine, autoflush=False) as session:
        report = public_artifacts.sync_public_artifacts(session, selected)
        assert report == {"expected": 3, "inserted": 1, "updated": 1, "unchanged": 1}

    with Session(engine) as session:
        rows = {row.artifact_key: row for row in session.scalars(select(PublicArtifact))}
        assert set(rows) == {item.key for item in selected}
        revised = rows[changed.key]
        assert revised.payload == changed_payload
        assert revised.item_count == 2
        assert revised.artifact_group == "revised"
        assert revised.province_code == "10"
        assert revised.source_path == changed.path.name

        changed.path.write_text('{"items":[{"value":"must not publish"}]}', encoding="utf-8")
        inputs[2].path.write_text('{"email":"person@example.test"}', encoding="utf-8")
        with pytest.raises(RuntimeError, match="public artifact policy rejected"):
            public_artifacts.sync_public_artifacts(session, selected)
        session.expire_all()
        assert session.get(PublicArtifact, changed.key).payload == changed_payload


@pytest.mark.parametrize("kind", ["demand", "spatial"])
def test_large_artifact_manifest_hash_checks_stream_and_reject_tampering(
    kind, tmp_path, monkeypatch,
):
    raw = b"reviewed-artifact-bytes"
    artifact_path = tmp_path / "records.ndjson.gz"
    artifact_path.write_bytes(raw)
    manifest = {"validation_status": "pass", "source_id": "f3_housing_portal"}
    if kind == "demand":
        monkeypatch.setattr(demand_artifacts, "REQUIRED_DEMAND_COUNT", 1)
        manifest.update({
            "record_count": 1,
            "privacy_projection": {
                "excluded_source_fields": ["id"],
                "source_identifier_published": False,
                "name_fields_in_source_schema": 0,
                "phone_fields_in_source_schema": 0,
                "email_fields_in_source_schema": 0,
            },
            "artifacts": {"records": {
                "path": artifact_path.name,
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }},
        })
        load_manifest = demand_artifacts.load_demand_manifest
    else:
        monkeypatch.setattr(spatial_artifacts, "REQUIRED_SPATIAL_COUNTS", {"housing_points": 1})
        manifest.update({
            "privacy_projection": {
                "demand_respondent_rows_included": 0,
                "contact_fields_included": 0,
            },
            "layers": {"housing_points": {
                "feature_count": 1,
                "artifact_path": artifact_path.name,
                "artifact_bytes": len(raw),
                "artifact_sha256": hashlib.sha256(raw).hexdigest(),
            }},
        })
        load_manifest = spatial_artifacts.load_spatial_manifest
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def reject_whole_file_read(path):
        pytest.fail(f"manifest validation must stream binary artifacts: {path}")

    monkeypatch.setattr(Path, "read_bytes", reject_whole_file_read)
    assert load_manifest(manifest_path) == manifest
    artifact_path.write_bytes(b"x" + raw[1:])
    with pytest.raises(RuntimeError, match="hash mismatch"):
        load_manifest(manifest_path)
    artifact_path.write_bytes(raw + b"x")
    with pytest.raises(RuntimeError, match="byte count mismatch"):
        load_manifest(manifest_path)

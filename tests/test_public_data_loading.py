from __future__ import annotations

import json

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app import public_data
from app.database import SessionLocal, engine
from app.models import PublicArtifact


def add_artifact(session, code, payload, kind="briefing"):
    session.add(PublicArtifact(
        artifact_key=f"province/{code}/{kind}", artifact_group="province",
        province_code=code, content_hash="a" * 64,
        source_path=f"data/public/fixture/{code}.json", item_count=1, payload=payload,
    ))


def test_batch_reads_only_requested_reviewed_artifacts_in_one_query(tmp_path, monkeypatch):
    monkeypatch.setattr(public_data, "PUBLIC_DATA_ROOT", tmp_path)
    with SessionLocal() as session:
        for number in range(1, 21):
            add_artifact(session, f"{number:02}", {"fixture_count": number})
        add_artifact(session, "01", {"fixture_count": 999}, kind="summary")
        session.commit()

    statements = []
    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(engine, "before_cursor_execute", capture)
    try:
        result = public_data._load_provincial_artifacts(
            [str(number) for number in range(1, 21)] + [" 01 "],
            "briefing", "provincial_briefings",
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert result == {f"{number:02}": {"fixture_count": number} for number in range(1, 21)}
    assert len(statements) == 1
    assert "dashboard_records" not in statements[0]


def test_batch_falls_back_only_for_missing_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(public_data, "PUBLIC_DATA_ROOT", tmp_path)
    root = tmp_path / "provincial_briefings"
    root.mkdir()
    (root / "01.json").write_text('{"fixture_count": 999}', encoding="utf-8")
    (root / "02.json").write_text('{"fixture_count": 2}', encoding="utf-8")
    with SessionLocal() as session:
        # An empty but present reviewed payload must not trigger a file fallback.
        add_artifact(session, "01", {})
        session.commit()
    assert public_data._load_provincial_artifacts(
        ["1", "2"], "briefing", "provincial_briefings",
    ) == {"01": {}, "02": {"fixture_count": 2}}


@pytest.mark.parametrize("kind,directory", [
    ("briefing", "provincial_briefings"), ("summary", "executive_summaries"),
])
def test_province_fallback_works_before_database_init(tmp_path, monkeypatch, kind, directory):
    monkeypatch.setattr(public_data, "PUBLIC_DATA_ROOT", tmp_path)
    root = tmp_path / directory
    root.mkdir()
    (root / "01.json").write_text(json.dumps({"fixture_kind": kind}), encoding="utf-8")
    def unavailable():
        raise OperationalError("fixture unavailable", {}, Exception())
    monkeypatch.setattr(public_data, "SessionLocal", unavailable)
    assert public_data._load_provincial_artifacts(["1"], kind, directory) == {
        "01": {"fixture_kind": kind},
    }
    (tmp_path / "outside.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        public_data._load_provincial_artifacts(["../outside"], kind, directory)
    with pytest.raises(FileNotFoundError):
        public_data._load_provincial_artifacts(["99"], kind, directory)


def test_empty_batch_does_not_open_a_database_connection(monkeypatch):
    def unexpected():
        raise AssertionError("Empty scope needs no database query")
    monkeypatch.setattr(public_data, "SessionLocal", unexpected)
    assert public_data._load_provincial_artifacts([], "briefing", "provincial_briefings") == {}


def test_f1_overview_normalizes_catalog_codes_before_batch_lookup(monkeypatch):
    monkeypatch.setattr(public_data, "public_catalog", lambda: {"provinces": [{
        "province_code": " 01 ", "province_name_th": "จังหวัดตัวอย่าง",
        "region": "ภาคตัวอย่าง", "sra_scope_status": "in_scope",
    }]})
    monkeypatch.setattr(public_data, "f1_details", lambda: {})
    monkeypatch.setattr(public_data, "source_insights", lambda: {})
    with SessionLocal() as session:
        add_artifact(session, "01", {"sections": {}})
        session.commit()
    public_data.f1_overview.cache_clear()
    try:
        overview = public_data.f1_overview()
        assert overview["scope"]["province_codes"] == ["01"]
        assert overview["provinces"][0]["province_code"] == "01"
        assert overview["totals"]["province_count"] == 1
    finally:
        public_data.f1_overview.cache_clear()

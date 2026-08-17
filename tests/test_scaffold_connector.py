from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.connector_contracts import prepare_contract_records
from tools.scaffold_connector import (
    PROJECT_ROOT,
    ScaffoldError,
    ScaffoldSpec,
    parse_identity_options,
    scaffold_connector,
)


def sample_spec(**overrides) -> ScaffoldSpec:
    values = {
        "source_id": "f9_sample_source",
        "transport": "arcgis_rest",
        "dataset_key": "features.layer:1",
        "grain_th": "หนึ่งแถวแทนแผนที่หนึ่ง feature",
        "identity_options": (("attributes.OBJECTID",), ("$payload_hash",)),
        "geography_fields": ("attributes.province",),
        "as_of_fields": ("attributes.updated_at",),
    }
    values.update(overrides)
    return ScaffoldSpec(**values)


def test_scaffold_creates_connector_contract_redacted_fixture_and_offline_test(tmp_path):
    paths = scaffold_connector(sample_spec(), output_root=tmp_path)

    relative_paths = {path.relative_to(tmp_path).as_posix() for path in paths}
    assert relative_paths == {
        "app/connectors/f9_sample_source.py",
        "config/connector_contracts/f9_sample_source.json",
        "tests/fixtures/connectors/f9_sample_source.json",
        "tests/test_f9_sample_source_connector.py",
    }
    assert not (tmp_path / "config" / "source_catalog.json").exists()
    assert not (tmp_path / "config" / "ingestion_sources.json").exists()

    contract = json.loads(
        (tmp_path / "config/connector_contracts/f9_sample_source.json").read_text(
            encoding="utf-8"
        )
    )
    assert contract["contract_version"] == "1.1"
    assert contract["transport"] == "arcgis_rest"
    assert contract["connector"] == (
        "app.connectors.f9_sample_source:F9SampleSourceConnector"
    )
    grain = contract["dataset_grains"][0]
    assert grain["key_pattern"].startswith("^") and grain["key_pattern"].endswith("$")
    assert re.fullmatch(grain["key_pattern"], "features.layer:1")
    assert grain["identity_options"] == [
        ["attributes.OBJECTID"],
        ["$payload_hash"],
    ]

    fixture = json.loads(
        (
            tmp_path
            / "tests/fixtures/connectors/f9_sample_source.json"
        ).read_text(encoding="utf-8")
    )
    assert fixture == {
        "fixture_version": "1.0",
        "source_id": "f9_sample_source",
        "records": [
            {
                "dataset_key": "features.layer:1",
                "payload": {
                    "attributes": {
                        "OBJECTID": "example-1",
                        "province": "จังหวัดตัวอย่าง",
                        "updated_at": "2026-01-01",
                    }
                },
            }
        ],
    }
    serialized = json.dumps(fixture, ensure_ascii=False).lower()
    assert "example.com" not in serialized
    assert "phone" not in serialized
    prepared = prepare_contract_records(
        contract,
        [
            (record["dataset_key"], record["payload"])
            for record in fixture["records"]
        ],
    )
    assert prepared[0].record_id == "example-1"
    assert prepared[0].as_of == "2026-01-01"

    for python_path in (
        tmp_path / "app/connectors/f9_sample_source.py",
        tmp_path / "tests/test_f9_sample_source_connector.py",
    ):
        source = python_path.read_text(encoding="utf-8")
        assert not re.search(r"__[A-Z0-9_]+__", source)
        compile(source, str(python_path), "exec")


def test_scaffold_dry_run_lists_targets_without_writing(tmp_path):
    paths = scaffold_connector(sample_spec(), output_root=tmp_path, dry_run=True)

    assert len(paths) == 4
    assert all(path.is_relative_to(tmp_path) for path in paths)
    assert list(tmp_path.iterdir()) == []


def test_scaffold_refuses_overwrite_before_creating_any_other_file(tmp_path):
    conflict = tmp_path / "app/connectors/f9_sample_source.py"
    conflict.parent.mkdir(parents=True)
    conflict.write_text("user work\n", encoding="utf-8")

    with pytest.raises(ScaffoldError, match="refusing to overwrite"):
        scaffold_connector(sample_spec(), output_root=tmp_path)

    assert conflict.read_text(encoding="utf-8") == "user work\n"
    assert not (tmp_path / "config").exists()
    assert not (tmp_path / "tests").exists()


@pytest.mark.parametrize(
    "source_id",
    ["../escape", "nested/source", r"nested\source", ".hidden", "UpperCase"],
)
def test_scaffold_rejects_source_ids_that_could_escape_or_confuse_paths(tmp_path, source_id):
    with pytest.raises(ScaffoldError, match="source_id"):
        scaffold_connector(sample_spec(source_id=source_id), output_root=tmp_path)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "field",
    ["email", "contact.phone", "auth.token", "contact_email", "api_key", "secret"],
)
def test_scaffold_rejects_personal_or_secret_fixture_fields(tmp_path, field):
    with pytest.raises(ScaffoldError, match="forbidden"):
        scaffold_connector(
            sample_spec(identity_options=((field,),)),
            output_root=tmp_path,
        )

    assert list(tmp_path.iterdir()) == []


def test_identity_option_parser_supports_composite_and_hash_fallback():
    assert parse_identity_options(["project_id, revision", "$payload_hash"]) == (
        ("project_id", "revision"),
        ("$payload_hash",),
    )

    with pytest.raises(ScaffoldError, match="only field"):
        parse_identity_options(["id,$payload_hash"])


def test_repository_templates_are_the_templates_used_by_default():
    assert (PROJECT_ROOT / "templates/connector/connector.py").is_file()
    assert (PROJECT_ROOT / "templates/connector/contract.json").is_file()
    assert (PROJECT_ROOT / "templates/connector/fixture.json").is_file()
    assert (PROJECT_ROOT / "templates/connector/connector_test.py.tmpl").is_file()

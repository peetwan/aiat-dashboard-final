from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.publication import load_contracts
from tools.scaffold_publication import (
    PublicationSpec,
    ScaffoldError,
    UNKNOWN,
    scaffold,
)


def test_scaffold_can_declare_public_work_contact_columns(tmp_path):
    _write_catalog(tmp_path)
    spec = _spec(output_format="csv", output_path="data/public/sample_dataset.csv", records_pointer="$", as_of_pointer=None,
                 csv_headers=("project_id", "province_code", "as_of", "project_count", "owner_name", "email"),
                 field_contexts=(("/*/owner_name", "work_attribution"), ("/*/email", "public_contact")))
    scaffold(spec, project_root=tmp_path)
    contracts = load_contracts(tmp_path / "config/publication_contracts")
    assert contracts[0][1]["outputs"][0]["field_contexts"]["/*/email"] == "public_contact"


@pytest.mark.parametrize("pointer,context_pointer", [("$", "/owner_name"), ("/", "/owner_name"), ("$", "/*/owner_name")])
def test_scaffold_resolves_public_attribution_for_root_objects_and_arrays(tmp_path, pointer, context_pointer):
    _write_catalog(tmp_path)
    spec = _spec(records_pointer=pointer, identity_fields=("owner_name",),
                 field_contexts=((context_pointer, "work_attribution"),))
    scaffold(spec, project_root=tmp_path)
    contract = load_contracts(tmp_path / "config/publication_contracts")[0][1]
    assert contract["outputs"][0]["field_contexts"] == {context_pointer: "work_attribution"}


def _write_catalog(root: Path) -> None:
    path = root / "config" / "source_catalog.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "source_a",
                        "production_values_allowed": True,
                        "cloud_policy": "team_approved_public",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _spec(**overrides: object) -> PublicationSpec:
    values: dict[str, object] = {
        "dataset_key": "sample_dataset",
        "source_ids": ("source_a",),
        "source_scope": "approved_values",
        "grain": "หนึ่งแถวต่อหนึ่งโครงการแบบสังเคราะห์",
        "identity_fields": ("project_id",),
        "geography_level": "province",
        "geography_fields": ("province_code",),
        "as_of_status": "field",
        "as_of_fields": ("as_of",),
        "measure_name": "จำนวนโครงการ",
        "measure_field": "project_count",
        "measure_unit": "โครงการ",
        "measure_denominator": "ไม่เกี่ยวข้อง",
        "output_path": "data/public/sample_dataset.json",
        "output_format": "json",
        "output_role": "database",
        "downloadable": True,
        "records_pointer": "/items",
        "privacy_profile": "aggregate_public",
        "max_bytes": 100_000,
        "minimum_count": 1,
        "expected_count": None,
        "max_count_drop_ratio": 0.0,
        "max_count_increase_ratio": 1.0,
        "max_identity_churn_ratio": 0.0,
        "as_of_pointer": "/generated_at",
        "csv_headers": (),
    }
    values.update(overrides)
    return PublicationSpec(**values)  # type: ignore[arg-type]


def test_happy_path_creates_four_reviewable_files_without_public_output(tmp_path):
    _write_catalog(tmp_path)

    result = scaffold(_spec(), project_root=tmp_path)

    assert result.dry_run is False
    assert result.paths == (
        "tools/publication_builders/sample_dataset.py",
        "config/publication_contracts/sample_dataset.json",
        "tests/fixtures/publication/sample_dataset.json",
        "tests/generated/test_publication_sample_dataset.py",
    )
    assert not (tmp_path / "data" / "public" / "sample_dataset.json").exists()

    contract = json.loads(
        (tmp_path / "config/publication_contracts/sample_dataset.json").read_text(
            encoding="utf-8"
        )
    )
    fixture = json.loads(
        (tmp_path / "tests/fixtures/publication/sample_dataset.json").read_text(
            encoding="utf-8"
        )
    )
    builder = (
        tmp_path / "tools/publication_builders/sample_dataset.py"
    ).read_text(encoding="utf-8")

    assert contract["grain_th"] == "หนึ่งแถวต่อหนึ่งโครงการแบบสังเคราะห์"
    assert contract["identity"]["fields"] == ["project_id"]
    assert contract["outputs"][0]["path"] == "data/public/sample_dataset.json"
    assert contract["outputs"][0]["max_identity_churn_ratio"] == 0.0
    assert contract["completeness"]["policy"] == "output_contracts"
    assert contract["completeness"]["needs_review"] is False
    loaded = load_contracts(tmp_path / "config/publication_contracts")
    assert loaded[0][1] == contract
    assert fixture["synthetic"] is True
    assert fixture["redacted"] is True
    assert fixture["reviewed_records"][0]["project_id"].startswith("synthetic-")
    assert "raise PublicationMappingRequired" in builder
    assert "subprocess" not in builder


def test_dry_run_reports_paths_without_creating_directories(tmp_path):
    _write_catalog(tmp_path)

    result = scaffold(_spec(), project_root=tmp_path, dry_run=True)

    assert result.dry_run is True
    assert len(result.paths) == 4
    assert not (tmp_path / "tools").exists()
    assert not (tmp_path / "tests").exists()
    assert not (tmp_path / "config/publication_contracts").exists()


def test_second_run_refuses_overwrite_and_preserves_existing_file(tmp_path):
    _write_catalog(tmp_path)
    scaffold(_spec(), project_root=tmp_path)
    builder_path = tmp_path / "tools/publication_builders/sample_dataset.py"
    original = builder_path.read_text(encoding="utf-8")

    with pytest.raises(ScaffoldError, match="refusing to overwrite"):
        scaffold(_spec(), project_root=tmp_path)

    assert builder_path.read_text(encoding="utf-8") == original


@pytest.mark.parametrize(
    "overrides",
    [
        {"dataset_key": "../escape"},
        {"output_path": "data/public/../../outside.json"},
        {"output_path": "C:/outside.json"},
        {"records_pointer": "/items/../raw"},
    ],
)
def test_path_traversal_and_absolute_paths_are_rejected(tmp_path, overrides):
    _write_catalog(tmp_path)

    with pytest.raises(ScaffoldError):
        scaffold(_spec(**overrides), project_root=tmp_path)


@pytest.mark.parametrize(
    "field",
    [
        "email",
        "contact.phone",
        "api_token",
        "person_name",
        "residential_address",
    ],
)
def test_personal_contact_and_secret_identity_fields_are_rejected(tmp_path, field):
    _write_catalog(tmp_path)

    with pytest.raises(ScaffoldError, match="forbidden personal/contact/secret"):
        scaffold(
            _spec(identity_fields=(field,)),
            project_root=tmp_path,
        )


def test_csv_map_key_identity_is_rejected_before_scaffolding(tmp_path):
    _write_catalog(tmp_path)

    with pytest.raises(
        ScaffoldError,
        match=r"\$key identity is unavailable for CSV records",
    ):
        scaffold(
            _spec(
                identity_fields=("$key",),
                output_path="data/public/sample_dataset.csv",
                output_format="csv",
                records_pointer="$",
                as_of_pointer=None,
                csv_headers=("province_code", "as_of", "project_count"),
            ),
            project_root=tmp_path,
        )

    assert not (tmp_path / "tools").exists()
    assert not (tmp_path / "config/publication_contracts").exists()


@pytest.mark.parametrize(
    "overrides,error",
    [
        (
            {"identity_fields": ("$key",), "records_pointer": "$"},
            "non-root records_pointer",
        ),
        (
            {"identity_fields": ("$key",), "records_pointer": "/"},
            "non-root records_pointer",
        ),
        (
            {
                "identity_fields": ("$key",),
                "output_path": "data/public/sample_dataset.geojson",
                "output_format": "geojson",
                "records_pointer": "/features",
            },
            "GeoJSON /features array",
        ),
    ],
)
def test_map_key_identity_rejects_known_non_object_record_shapes(
    tmp_path, overrides, error
):
    _write_catalog(tmp_path)

    with pytest.raises(ScaffoldError, match=error):
        scaffold(_spec(**overrides), project_root=tmp_path)


def test_nested_json_object_map_preserves_map_key_identity_support(tmp_path):
    _write_catalog(tmp_path)

    scaffold(
        _spec(identity_fields=("$key",), records_pointer="/items"),
        project_root=tmp_path,
    )

    contract = json.loads(
        (tmp_path / "config/publication_contracts/sample_dataset.json").read_text(
            encoding="utf-8"
        )
    )
    assert contract["identity"]["fields"] == ["$key"]
    assert contract["outputs"][0]["records_pointer"] == "/items"
    assert contract["outputs"][0]["identity_fields"] == ["$key"]


def test_unknown_semantics_are_explicitly_marked_needs_review(tmp_path):
    _write_catalog(tmp_path)
    spec = _spec(
        grain=UNKNOWN,
        geography_level=UNKNOWN,
        geography_fields=(),
        as_of_status=UNKNOWN,
        as_of_fields=(),
        measure_unit=UNKNOWN,
        measure_denominator=UNKNOWN,
    )

    scaffold(spec, project_root=tmp_path)

    contract = json.loads(
        (tmp_path / "config/publication_contracts/sample_dataset.json").read_text(
            encoding="utf-8"
        )
    )
    assert contract["completeness"]["needs_review"] is True
    assert contract["completeness"]["review_items"] == [
        "grain",
        "geography",
        "as_of",
        "measure.unit",
        "measure.denominator",
    ]
    assert contract["geography"]["fields"] == []
    assert contract["as_of"]["fields"] == []


def test_reference_geography_can_be_scaffolded_without_source_ids(tmp_path):
    _write_catalog(tmp_path)

    result = scaffold(
        _spec(
            source_ids=(),
            source_scope="reference_geography",
            privacy_profile="reference_geography",
        ),
        project_root=tmp_path,
        dry_run=True,
    )

    assert result.dry_run is True


def test_non_reference_scope_still_requires_source_id(tmp_path):
    _write_catalog(tmp_path)

    with pytest.raises(ScaffoldError, match="at least one source_id"):
        scaffold(_spec(source_ids=()), project_root=tmp_path, dry_run=True)


def test_existing_public_output_is_never_overwritten(tmp_path):
    _write_catalog(tmp_path)
    output = tmp_path / "data/public/sample_dataset.json"
    output.parent.mkdir(parents=True)
    output.write_text('{"kept": true}\n', encoding="utf-8")

    with pytest.raises(ScaffoldError, match="data/public/sample_dataset.json"):
        scaffold(_spec(), project_root=tmp_path)

    assert output.read_text(encoding="utf-8") == '{"kept": true}\n'

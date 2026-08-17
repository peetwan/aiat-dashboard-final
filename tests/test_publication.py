from __future__ import annotations

import csv
import io
import json
import subprocess
from pathlib import Path

import pytest

from app.publication import (
    PublicationError,
    build_receipt,
    downloadable_public_files,
    load_json_bytes,
    load_contracts,
    validate_workspace,
    validate_git_revision,
    write_receipt,
)
from app.settings import PROJECT_ROOT


CONTRACTS_ROOT = PROJECT_ROOT / "config" / "publication_contracts"
CATALOG_PATH = PROJECT_ROOT / "config" / "source_catalog.json"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _fixture(tmp_path: Path, *, include_csv: bool = False) -> tuple[Path, Path, Path]:
    root = tmp_path / "repo"
    contracts_root = root / "config" / "publication_contracts"
    catalog_path = root / "config" / "source_catalog.json"
    public_root = root / "data" / "public"
    public_root.mkdir(parents=True)
    contracts_root.mkdir(parents=True)
    _write_json(
        catalog_path,
        {
            "sources": [
                {
                    "source_id": "source_a",
                    "production_values_allowed": True,
                    "cloud_policy": "team_approved_public",
                }
            ]
        },
    )
    _write_json(
        public_root / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "items": [{"id": "one", "count": 2}],
        },
    )
    _write_json(
        public_root / "serving_manifest.json",
        {
            "manifest_version": "1.0",
            "artifacts": [
                {
                    "key": "sample",
                    "group": "source_dataset",
                    "path": "artifact.json",
                    "source_ids": ["source_a"],
                }
            ],
        },
    )
    outputs: list[dict[str, object]] = [
        {
            "path": "data/public/artifact.json",
            "format": "json",
            "role": "database",
            "downloadable": True,
            "max_bytes": 100_000,
            "records_pointer": "/items",
            "identity_fields": ["id"],
            "max_identity_churn_ratio": 0,
            "minimum_count": 1,
            "max_count_drop_ratio": 0,
            "max_count_increase_ratio": 1,
            "as_of_pointer": "/generated_at",
            "schema_policy": "stable",
        }
    ]
    if include_csv:
        (public_root / "rows.csv").write_text(
            "id,count\none,2\n",
            encoding="utf-8",
        )
        outputs.append(
            {
                "path": "data/public/rows.csv",
                "format": "csv",
                "role": "download",
                "downloadable": True,
                "max_bytes": 100_000,
                "records_pointer": "$",
                "identity_fields": ["id"],
                "max_identity_churn_ratio": 0,
                "minimum_count": 1,
                "headers": ["id", "count"],
                "schema_policy": "stable",
            }
        )
    _write_json(
        contracts_root / "sample.json",
        {
            "contract_version": "1.0",
            "contract_id": "sample",
            "dataset_key": "sample",
            "source_scope": "approved_values",
            "source_ids": ["source_a"],
            "builder": "tests.fixture:build",
            "grain_th": "หนึ่งแถวต่อหนึ่งรายการทดสอบ",
            "identity": {"fields": ["id"]},
            "geography": {"level": "none", "fields": []},
            "as_of": {"status": "field", "fields": ["generated_at"]},
            "measures": [
                {"name": "count", "unit": "รายการ", "denominator": "ไม่เกี่ยวข้อง"}
            ],
            "completeness": {"minimum_count": 1},
            "privacy_profile": "aggregate_public",
            "outputs": outputs,
        },
    )
    write_receipt(root, contracts_root, catalog_path)
    return root, contracts_root, catalog_path


def _geojson_payload(
    geometries: list[dict[str, object]],
    *,
    generated_at: str = "2026-08-17T00:00:00+00:00",
) -> dict[str, object]:
    return {
        "type": "FeatureCollection",
        "generated_at": generated_at,
        "features": [
            {
                "type": "Feature",
                "properties": {"id": f"feature-{index}"},
                "geometry": geometry,
            }
            for index, geometry in enumerate(geometries)
        ],
    }


def _install_geojson(
    root: Path,
    contracts_root: Path,
    catalog_path: Path,
    payload: dict[str, object],
) -> None:
    contract_path = contracts_root / "sample.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    output = contract["outputs"][0]
    output["format"] = "geojson"
    output["records_pointer"] = "/features"
    output["identity_fields"] = ["properties.id"]
    _write_json(contract_path, contract)
    _write_json(root / "data" / "public" / "artifact.json", payload)
    write_receipt(root, contracts_root, catalog_path)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _commit_all(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(
        root,
        "-c",
        "user.name=Publication Test",
        "-c",
        "user.email=publication-test@example.invalid",
        "commit",
        "-m",
        message,
    )
    return _git(root, "rev-parse", "HEAD")


def test_current_publication_release_is_fully_classified_and_valid():
    report = validate_workspace(PROJECT_ROOT, CONTRACTS_ROOT, CATALOG_PATH)

    assert report["status"] == "valid"
    assert report["public_file_count"] == report["artifact_count"] + 2
    assert report["contract_count"] == len(list(CONTRACTS_ROOT.glob("*.json")))
    assert report["problems"] == []


def test_receipt_is_deterministic_and_binds_every_contract_output(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)

    first = build_receipt(root, contracts_root, catalog_path)
    second = build_receipt(root, contracts_root, catalog_path)

    assert first == second
    assert first["artifact_count"] == 1
    assert first["artifacts"][0]["path"] == "data/public/artifact.json"
    assert len(first["artifacts"][0]["sha256"]) == 64
    assert len(first["artifacts"][0]["contract_sha256"]) == 64


def test_orphan_public_file_fails_closed(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    _write_json(root / "data" / "public" / "orphan.json", {"safe": True})

    report = validate_workspace(root, contracts_root, catalog_path)

    assert report["status"] == "invalid"
    assert any("orphan.json: no trusted publication contract" in item for item in report["problems"])


def test_json_private_field_is_rejected_without_logging_the_value(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "items": [{"id": "one", "count": 1, "contact_email": "person@example.com"}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "private/contact field" in encoded
    assert "person@example.com" not in encoded


def test_embedded_source_provenance_must_match_contract_without_logging_value(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    undeclared_source = "source_not_declared"
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "source_id": undeclared_source,
            "items": [{"id": "one", "count": 1}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "source provenance is not declared" in encoded
    assert undeclared_source not in encoded


def test_duplicate_identity_is_rejected(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "items": [{"id": "same", "count": 1}, {"id": "same", "count": 2}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)

    assert report["status"] == "invalid"
    assert any("duplicate record identity" in item for item in report["problems"])


@pytest.mark.parametrize(
    ("unsafe_value", "reason"),
    [
        ("https://example.test/data?signature=top-secret", "signed/credential URL"),
        ("-".join(("sk", "proj", "abcdefghijklmnopqrstuvwxyz")), "credential-like value"),
    ],
)
def test_secret_or_signed_url_value_is_rejected(tmp_path, unsafe_value, reason):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "items": [{"id": "one", "count": 1, "source_url": unsafe_value}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)

    assert report["status"] == "invalid"
    assert reason in json.dumps(report, ensure_ascii=False)
    assert unsafe_value not in json.dumps(report, ensure_ascii=False)


def test_csv_contact_value_is_rejected_without_logging_the_value(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path, include_csv=True)
    (root / "data" / "public" / "rows.csv").write_text(
        "id,count\none,person@example.com\n",
        encoding="utf-8",
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "email-like value" in encoded
    assert "person@example.com" not in encoded


@pytest.mark.parametrize(
    "formula_value",
    ["=1+1", "@SUM(1,2)", "\t=1+1", "\r@SUM(1,2)", "+cmd", "-cmd"],
)
def test_csv_spreadsheet_formula_is_rejected_without_logging_value(
    tmp_path, formula_value
):
    root, contracts_root, catalog_path = _fixture(tmp_path, include_csv=True)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["id", "count"])
    writer.writerow(["one", formula_value])
    (root / "data" / "public" / "rows.csv").write_text(
        buffer.getvalue(), encoding="utf-8"
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "spreadsheet formula-like cell" in encoded
    assert formula_value not in encoded


@pytest.mark.parametrize("numeric_value", ["-1", "+1", "-.5", "+1.25", "-1e3"])
def test_csv_signed_numeric_cells_remain_valid(tmp_path, numeric_value):
    root, contracts_root, catalog_path = _fixture(tmp_path, include_csv=True)
    (root / "data" / "public" / "rows.csv").write_text(
        f"id,count\none,{numeric_value}\n", encoding="utf-8"
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)

    assert report["status"] == "valid"


def test_duplicate_json_keys_and_stale_receipt_are_rejected(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    (root / "data" / "public" / "artifact.json").write_bytes(
        b'{"generated_at":"2026-08-17T00:00:00+00:00","items":[],"items":[]}'
    )

    report = validate_workspace(root, contracts_root, catalog_path)

    assert report["status"] == "invalid"
    assert any("duplicate JSON key" in item for item in report["problems"])
    assert any("receipt does not match" in item for item in report["problems"])


def test_json_with_utf8_bom_is_rejected_before_runtime_serving():
    with pytest.raises(PublicationError, match="UTF-8 without a BOM"):
        load_json_bytes(b"\xef\xbb\xbf{}", path="data/public/artifact.json")


def test_contract_requires_explicit_semantics(tmp_path):
    root, contracts_root, _ = _fixture(tmp_path)
    path = contracts_root / "sample.json"
    contract = json.loads(path.read_text(encoding="utf-8"))
    del contract["grain_th"]
    _write_json(path, contract)

    with pytest.raises(PublicationError, match="grain_th"):
        load_contracts(contracts_root)


def test_download_allowlist_excludes_receipt_and_provenance(tmp_path):
    root, contracts_root, _ = _fixture(tmp_path, include_csv=True)

    allowed = downloadable_public_files(root, contracts_root)

    assert sorted(allowed) == ["artifact.json", "rows.csv"]
    assert "publication_receipt.json" not in allowed


def test_geojson_accepts_every_rfc7946_geometry_type(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    ring = [[100, 13], [101, 13], [101, 14], [100, 13]]
    payload = _geojson_payload(
        [
            {"type": "Point", "coordinates": [100, 13]},
            {"type": "MultiPoint", "coordinates": [[100, 13], [101, 14]]},
            {
                "type": "LineString",
                "coordinates": [[100, 13], [101, 14]],
            },
            {
                "type": "MultiLineString",
                "coordinates": [
                    [[100, 13], [101, 14]],
                    [[102, 15], [103, 16]],
                ],
            },
            {"type": "Polygon", "coordinates": [ring]},
            {"type": "MultiPolygon", "coordinates": [[ring]]},
            {
                "type": "GeometryCollection",
                "geometries": [
                    {"type": "Point", "coordinates": [100, 13]},
                    {
                        "type": "GeometryCollection",
                        "geometries": [
                            {
                                "type": "LineString",
                                "coordinates": [[100, 13], [101, 14]],
                            }
                        ],
                    },
                ],
            },
        ]
    )
    _install_geojson(root, contracts_root, catalog_path, payload)

    report = validate_workspace(root, contracts_root, catalog_path)

    assert report["status"] == "valid"
    assert report["problems"] == []


@pytest.mark.parametrize(
    ("geometry", "reason"),
    [
        (
            {"type": "Point", "coordinates": [[100, 13]]},
            "position must contain longitude and latitude",
        ),
        (
            {"type": "MultiPoint", "coordinates": [100, 13]},
            "position must contain longitude and latitude",
        ),
        (
            {"type": "LineString", "coordinates": [[100, 13]]},
            "line string must contain at least 2 positions",
        ),
        (
            {"type": "MultiLineString", "coordinates": [[100, 13]]},
            "position must contain longitude and latitude",
        ),
        (
            {
                "type": "Polygon",
                "coordinates": [
                    [[100, 13], [101, 13], [101, 14], [100, 14]]
                ],
            },
            "linear ring must be closed",
        ),
        (
            {
                "type": "MultiPolygon",
                "coordinates": [
                    [[[100, 13], [101, 13], [101, 14], [100, 14]]]
                ],
            },
            "linear ring must be closed",
        ),
        (
            {"type": "GeometryCollection", "geometries": {}},
            "geometries must be an array",
        ),
    ],
)
def test_geojson_rejects_malformed_coordinate_nesting(tmp_path, geometry, reason):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    _install_geojson(
        root,
        contracts_root,
        catalog_path,
        _geojson_payload([geometry]),
    )

    report = validate_workspace(root, contracts_root, catalog_path)

    assert report["status"] == "invalid"
    assert any(reason in problem for problem in report["problems"])


def test_geojson_rejects_non_finite_coordinate_without_reporting_value(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    _install_geojson(
        root,
        contracts_root,
        catalog_path,
        _geojson_payload([{"type": "Point", "coordinates": [100, 13]}]),
    )
    artifact_path = root / "data" / "public" / "artifact.json"
    artifact_path.write_text(
        artifact_path.read_text(encoding="utf-8").replace("100,", "1e309,"),
        encoding="utf-8",
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "GeoJSON coordinate must be finite" in encoded
    assert "1e309" not in encoded


def test_geojson_semantic_diff_blocks_out_of_range_coordinates_without_values(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    _install_geojson(
        root,
        contracts_root,
        catalog_path,
        _geojson_payload([{"type": "Point", "coordinates": [100, 13]}]),
    )
    _git(root, "init", "-b", "main")
    base_sha = _commit_all(root, "base geojson")
    _install_geojson(
        root,
        contracts_root,
        catalog_path,
        _geojson_payload(
            [{"type": "Point", "coordinates": [999, 999]}],
            generated_at="2026-08-18T00:00:00+00:00",
        ),
    )
    head_sha = _commit_all(root, "out of range coordinates")

    report, valid = validate_git_revision(
        root,
        contracts_root,
        catalog_path,
        base_sha,
        head_sha,
    )
    encoded = json.dumps(report, ensure_ascii=False)

    assert valid is False
    assert report["status"] == "blocked"
    assert any("outside WGS84 range" in problem for problem in report["problems"])
    assert "[999, 999]" not in encoded


def test_geojson_invalid_geometry_type_does_not_echo_untrusted_value(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    untrusted_value = "raw-geometry-value-must-not-be-reported"
    _install_geojson(
        root,
        contracts_root,
        catalog_path,
        _geojson_payload([{"type": [untrusted_value], "coordinates": [100, 13]}]),
    )

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "geometry type is unsupported" in encoded
    assert untrusted_value not in encoded


def test_git_semantic_diff_passes_a_routine_refresh_without_values(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    _git(root, "init", "-b", "main")
    base_sha = _commit_all(root, "base")
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-18T00:00:00+00:00",
            "items": [{"id": "one", "count": 3}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)
    head_sha = _commit_all(root, "refresh")

    report, valid = validate_git_revision(
        root,
        contracts_root,
        catalog_path,
        base_sha,
        head_sha,
    )
    encoded = json.dumps(report, ensure_ascii=False)

    assert valid is True
    assert report["status"] == "pass"
    assert report["lane"] == "routine_refresh"
    assert len(report["semantic_diff"]) == 1
    assert '"count": 3' not in encoded


def test_git_semantic_diff_blocks_schema_drift(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    _git(root, "init", "-b", "main")
    base_sha = _commit_all(root, "base")
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-18T00:00:00+00:00",
            "items": [{"id": "one", "count": 3, "new_meaning": "manual"}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)
    head_sha = _commit_all(root, "schema drift")

    report, valid = validate_git_revision(
        root,
        contracts_root,
        catalog_path,
        base_sha,
        head_sha,
    )

    assert valid is False
    assert report["status"] == "blocked"
    assert any("schema changed under stable contract" in item for item in report["problems"])


def test_git_semantic_diff_blocks_complete_identity_replacement(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    _git(root, "init", "-b", "main")
    base_sha = _commit_all(root, "base")
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-18T00:00:00+00:00",
            "items": [{"id": "replacement", "count": 3}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)
    head_sha = _commit_all(root, "replace identity")

    report, valid = validate_git_revision(
        root,
        contracts_root,
        catalog_path,
        base_sha,
        head_sha,
    )
    encoded = json.dumps(report, ensure_ascii=False)

    assert valid is False
    assert report["status"] == "blocked"
    assert any("identity churn exceeds contract" in item for item in report["problems"])
    assert report["semantic_diff"][0]["identity_churn_ratio"] == 1.0
    assert len(report["semantic_diff"][0]["before"]["identity_sha256"]) == 64
    assert len(report["semantic_diff"][0]["after"]["identity_sha256"]) == 64
    assert "replacement" not in encoded


def test_git_semantic_diff_blocks_naive_as_of_without_type_error(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    _git(root, "init", "-b", "main")
    base_sha = _commit_all(root, "base")
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-18T00:00:00",
            "items": [{"id": "one", "count": 3}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)
    head_sha = _commit_all(root, "naive as of")

    report, valid = validate_git_revision(
        root,
        contracts_root,
        catalog_path,
        base_sha,
        head_sha,
    )

    assert valid is False
    assert report["status"] == "blocked"
    assert any("as_of_pointer" in item for item in report["problems"])

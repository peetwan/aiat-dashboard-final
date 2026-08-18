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


def _deep_object(leaf: object, depth: int = 45) -> object:
    value = leaf
    for _ in range(depth):
        value = {"next": value}
    return value


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
                    "url": "https://source-a.example/",
                    "endpoints": [
                        {"url": "https://api.source-a.example/v1/records"}
                    ],
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
            "completeness": {"policy": "output_contracts"},
            "privacy_profile": "aggregate_public",
            "outputs": outputs,
        },
    )
    write_receipt(root, contracts_root, catalog_path)
    return root, contracts_root, catalog_path


def _declare_source_b(contracts_root: Path, catalog_path: Path) -> None:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["sources"].append(
        {
            "source_id": "source_b",
            "url": "https://source-b.example/",
            "endpoints": [],
            "production_values_allowed": True,
            "cloud_policy": "team_approved_public",
        }
    )
    _write_json(catalog_path, catalog)
    contract_path = contracts_root / "sample.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["source_ids"].append("source_b")
    _write_json(contract_path, contract)


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


@pytest.mark.parametrize(
    "field_name",
    [
        "opaque_id",
        "opaque_code",
        "record_hash",
        "total_count",
        "fiscal_year",
        "source_url",
    ],
)
def test_phone_shaped_value_is_rejected_in_every_opaque_field_without_logging(
    tmp_path, field_name
):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    phone_value = "081-234-5678"
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "items": [{"id": "one", "count": 1, field_name: phone_value}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "Thai phone-like value" in encoded
    assert phone_value not in encoded


@pytest.mark.parametrize(
    "phone_value",
    [
        "66812345678",
        "+66812345678",
        66812345678,
        66812345678.0,
        6.6812345678e10,
    ],
)
def test_country_code_phone_string_or_numeric_is_rejected_without_logging(
    tmp_path, phone_value
):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "items": [{"id": "one", "count": 1, "opaque_code": phone_value}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "Thai phone-like" in encoded
    assert str(phone_value) not in encoded


def test_machine_ids_codes_hashes_and_counts_that_are_not_phone_tokens_remain_valid(
    tmp_path,
):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "source_id": "source_a",
            "source_url": "https://source-a.example/items/RID0812345678",
            "items": [
                {
                    "id": "one",
                    "record_id": "RID0812345678",
                    "province_code": "10",
                    "record_hash": "a0812345678b7c2d",
                    "total_count": "1083458",
                    "fiscal_year": "2569",
                    "count": 1,
                }
            ],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)

    assert report["status"] == "valid"
    assert report["problems"] == []


@pytest.mark.parametrize(
    ("unsafe_key", "reason"),
    [
        ("person@example.com", "email-like value in object key"),
        ("081-234-5678", "Thai phone-like value in object key"),
        ("บ้านเลขที่ 99", "home-address-like value in object key"),
        (
            "https://source-a.example/?signature=top-secret",
            "signed/credential URL in object key",
        ),
        (
            "-".join(("sk", "proj", "abcdefghijklmnopqrstuvwxyz")),
            "credential-like value in object key",
        ),
    ],
)
def test_sensitive_json_map_key_is_rejected_and_redacted(
    tmp_path, unsafe_key, reason
):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "items": [
                {
                    "id": "one",
                    "count": 1,
                    "metadata": {unsafe_key: _deep_object(True)},
                }
            ],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert reason in encoded
    assert "payload exceeds depth" in encoded
    assert unsafe_key not in encoded
    assert "<map-key>" in encoded


def test_restricted_source_identifier_in_json_map_key_is_rejected_and_redacted(
    tmp_path,
):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    restricted_source = "source_restricted"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["sources"].append(
        {
            "source_id": restricted_source,
            "url": "https://restricted.example/",
            "endpoints": [],
            "production_values_allowed": False,
            "cloud_policy": "restricted_local_only",
        }
    )
    _write_json(catalog_path, catalog)
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "items": [
                {
                    "id": "one",
                    "count": 1,
                    "metadata": {restricted_source: _deep_object(True)},
                }
            ],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "restricted source identifier in object key" in encoded
    assert "payload exceeds depth" in encoded
    assert restricted_source not in encoded


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


def test_registered_source_landing_descendant_and_exact_endpoint_are_valid(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "source_id": "source_a",
            "source_url": "https://source-a.example/datasets/current",
            "endpoint_url": "https://api.source-a.example/v1/records",
            "items": [{"id": "one", "count": 1}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)

    assert report["status"] == "valid"
    assert report["problems"] == []


@pytest.mark.parametrize(
    "unregistered_url",
    [
        "https://unregistered.example/data",
        "https://api.source-a.example/v1/unrelated-dataset",
        "https://api.source-a.example/v1/records?dataset=unregistered",
    ],
)
def test_unregistered_source_url_is_rejected_without_logging_value(
    tmp_path, unregistered_url
):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "source_id": "source_a",
            "source_urls": ["https://source-a.example/datasets/current", unregistered_url],
            "items": [{"id": "one", "count": 1}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "provenance URL is not registered for its declared source" in encoded
    assert unregistered_url not in encoded


@pytest.mark.parametrize(
    "url_key", ["url", "urls", "documentation_url", "website", "uri"]
)
def test_generic_url_fields_are_validated_and_redacted(tmp_path, url_key):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    unregistered_url = "https://unregistered.example/generic"
    value: object = [unregistered_url] if url_key == "urls" else unregistered_url
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            url_key: value,
            "items": [{"id": "one", "count": 1}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "provenance URL is not registered for its declared source" in encoded
    assert unregistered_url not in encoded


@pytest.mark.parametrize("url_key", ["website", "uri", "source_link"])
def test_list_valued_link_aliases_are_validated_and_redacted(tmp_path, url_key):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    unregistered_url = "https://unregistered.example/list-alias"
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            url_key: [unregistered_url],
            "items": [{"id": "one", "count": 1}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "provenance URL is not registered for its declared source" in encoded
    assert unregistered_url not in encoded


def test_generic_url_in_csv_row_is_validated_and_redacted(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path, include_csv=True)
    unregistered_url = "https://unregistered.example/csv"
    contract_path = contracts_root / "sample.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["outputs"][1]["headers"] = ["id", "count", "url"]
    _write_json(contract_path, contract)
    (root / "data" / "public" / "rows.csv").write_text(
        f"id,count,url\none,2,{unregistered_url}\n",
        encoding="utf-8",
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "provenance URL is not registered for its declared source" in encoded
    assert unregistered_url not in encoded


def test_declared_source_id_map_key_is_the_local_url_context(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    _declare_source_b(contracts_root, catalog_path)
    mismatched_url = "https://source-b.example/data"
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "by_source": {"source_a": {"url": mismatched_url}},
            "items": [{"id": "one", "count": 1}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "provenance URL is not registered for its declared source" in encoded
    assert mismatched_url not in encoded


def test_git_diff_blocks_switch_to_another_declared_provenance_rule(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    _declare_source_b(contracts_root, catalog_path)
    artifact_path = root / "data" / "public" / "artifact.json"
    base_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    base_payload["url"] = "https://source-a.example/datasets/first"
    _write_json(artifact_path, base_payload)
    write_receipt(root, contracts_root, catalog_path)
    _git(root, "init", "-b", "main")
    base_sha = _commit_all(root, "base provenance rule")

    head_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    head_payload["generated_at"] = "2026-08-18T00:00:00+00:00"
    head_payload["url"] = "https://source-b.example/datasets/first"
    _write_json(artifact_path, head_payload)
    write_receipt(root, contracts_root, catalog_path)
    head_sha = _commit_all(root, "switch provenance rule")

    report, valid = validate_git_revision(
        root, contracts_root, catalog_path, base_sha, head_sha
    )
    encoded = json.dumps(report, ensure_ascii=False)

    assert valid is False
    assert report["status"] == "blocked"
    assert any("provenance rule changed" in item for item in report["problems"])
    assert "source-a.example" not in encoded
    assert "source-b.example" not in encoded
    assert len(report["semantic_diff"][0]["before"]["provenance_sha256"]) == 64
    assert len(report["semantic_diff"][0]["after"]["provenance_sha256"]) == 64


def test_git_diff_allows_descendant_url_refresh_under_same_landing_rule(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    artifact_path = root / "data" / "public" / "artifact.json"
    base_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    base_payload["url"] = "https://source-a.example/datasets/first"
    _write_json(artifact_path, base_payload)
    write_receipt(root, contracts_root, catalog_path)
    _git(root, "init", "-b", "main")
    base_sha = _commit_all(root, "base descendant URL")

    head_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    head_payload["generated_at"] = "2026-08-18T00:00:00+00:00"
    head_payload["url"] = "https://source-a.example/datasets/second"
    _write_json(artifact_path, head_payload)
    write_receipt(root, contracts_root, catalog_path)
    head_sha = _commit_all(root, "refresh descendant URL")

    report, valid = validate_git_revision(
        root, contracts_root, catalog_path, base_sha, head_sha
    )

    assert valid is True
    assert report["status"] == "pass"
    assert report["semantic_diff"][0]["before"]["provenance_sha256"] == report[
        "semantic_diff"
    ][0]["after"]["provenance_sha256"]


def test_restricted_catalog_endpoint_is_denied_for_approved_values(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    restricted_url = "https://source-a.example/private/records"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["sources"][0]["endpoints"].append(
        {"url": restricted_url, "restricted": True, "runtime_enabled": True}
    )
    _write_json(catalog_path, catalog)
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "source_id": "source_a",
            "url": restricted_url,
            "items": [{"id": "one", "count": 1}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "restricted catalog endpoint cannot be value provenance" in encoded
    assert restricted_url not in encoded


def test_catalog_metadata_may_cite_restricted_endpoint(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    restricted_url = "https://source-a.example/private/records"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["sources"][0]["endpoints"].append(
        {"url": restricted_url, "restricted": True, "runtime_enabled": False}
    )
    _write_json(catalog_path, catalog)
    contract_path = contracts_root / "sample.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["source_scope"] = "catalog_metadata"
    contract["privacy_profile"] = "catalog_metadata"
    _write_json(contract_path, contract)
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "source_id": "source_a",
            "url": restricted_url,
            "items": [{"id": "one", "count": 1}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)

    assert report["status"] == "valid"


def test_runtime_disabled_nonrestricted_endpoint_remains_valid_provenance(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    archived_url = "https://source-a.example/archive/records"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["sources"][0]["endpoints"].append(
        {"url": archived_url, "restricted": False, "runtime_enabled": False}
    )
    _write_json(catalog_path, catalog)
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "source_id": "source_a",
            "url": archived_url,
            "items": [{"id": "one", "count": 1}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)

    assert report["status"] == "valid"


@pytest.mark.parametrize(
    ("field_name", "unsafe_value", "reason"),
    [
        (
            "address",
            "123 ถนนสุขุมวิท แขวงคลองตันเหนือ เขตวัฒนา กรุงเทพมหานคร 10110",
            "home-address-like value",
        ),
        ("address", "99 Sukhumvit Rd., Bangkok 10110", "home-address-like value"),
        ("contact", "+66 (0) 81 234 5678", "Thai phone-like value"),
        ("credential", "AIza" + "A" * 35, "credential-like value"),
        ("credential", "sk_live_" + "A" * 30, "credential-like value"),
    ],
)
def test_exact_sensitive_alias_and_value_pattern_are_rejected_without_logging(
    tmp_path, field_name, unsafe_value, reason
):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "items": [{"id": "one", "count": 1, field_name: unsafe_value}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "private/contact field" in encoded
    assert reason in encoded
    assert unsafe_value not in encoded


def test_routine_refresh_rejects_unregistered_source_link_without_logging(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    artifact_path = root / "data" / "public" / "artifact.json"
    base_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    base_payload["source_link"] = "https://source-a.example/datasets/base"
    _write_json(artifact_path, base_payload)
    write_receipt(root, contracts_root, catalog_path)
    _git(root, "init", "-b", "main")
    base_sha = _commit_all(root, "base source link")

    head_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    head_payload["generated_at"] = "2026-08-18T00:00:00+00:00"
    unsafe_value = "https://unregistered.example/alias"
    head_payload["source_link"] = unsafe_value
    _write_json(artifact_path, head_payload)
    write_receipt(root, contracts_root, catalog_path)
    head_sha = _commit_all(root, "unregistered source link")

    report, valid = validate_git_revision(
        root, contracts_root, catalog_path, base_sha, head_sha
    )
    encoded = json.dumps(report, ensure_ascii=False)

    assert valid is False
    assert report["status"] == "blocked"
    assert report["lane"] == "routine_refresh"
    assert "provenance URL is not registered for its declared source" in encoded
    assert unsafe_value not in encoded


def test_percent_encoded_restricted_endpoint_is_denied_and_redacted(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    restricted_url = "https://source-a.example/private/records"
    encoded_url = "https://source-a.example/private/%72ecords"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["sources"][0]["endpoints"].append(
        {"url": restricted_url, "restricted": True, "runtime_enabled": True}
    )
    _write_json(catalog_path, catalog)
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "source_id": "source_a",
            "source_link": encoded_url,
            "items": [{"id": "one", "count": 1}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "restricted catalog endpoint cannot be value provenance" in encoded
    assert encoded_url not in encoded


def test_restricted_endpoint_descendant_is_denied_before_broad_landing_rule(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    restricted_url = "https://source-a.example/private/records"
    descendant_url = restricted_url + "/child"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["sources"][0]["endpoints"].append(
        {"url": restricted_url, "restricted": True, "runtime_enabled": True}
    )
    _write_json(catalog_path, catalog)
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "source_link": descendant_url,
            "items": [{"id": "one", "count": 1}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "restricted catalog endpoint cannot be value provenance" in encoded
    assert descendant_url not in encoded


@pytest.mark.parametrize(
    "ambiguous_url",
    [
        "https://source-a.example/private/%2e%2e/records",
        "https://source-a.example/private/%252e%252e/records",
        "https://source-a.example/private/records%3Bchild",
    ],
)
def test_ambiguous_encoded_provenance_path_is_rejected_and_redacted(
    tmp_path, ambiguous_url
):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "source_link": ambiguous_url,
            "items": [{"id": "one", "count": 1}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "ambiguous encoded path" in encoded
    assert ambiguous_url not in encoded


@pytest.mark.parametrize("encoded_separator", ["%5f", "%255f"])
def test_percent_encoded_credential_query_key_is_rejected_and_redacted(
    tmp_path, encoded_separator
):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    credential_url = (
        f"https://source-a.example/data?api{encoded_separator}key=" + "A" * 24
    )
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "source_link": credential_url,
            "items": [{"id": "one", "count": 1}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "credential query parameter" in encoded
    assert credential_url not in encoded


@pytest.mark.parametrize("separator", [";", "%3B"])
def test_semicolon_credential_query_key_is_rejected_and_redacted(
    tmp_path, separator
):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    credential_url = (
        f"https://source-a.example/data?view=public{separator}api_key="
        + "TOPSECRET"
    )
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "source_link": credential_url,
            "items": [{"id": "one", "count": 1}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "credential query parameter" in encoded
    assert "TOPSECRET" not in encoded
    assert credential_url not in encoded


def test_percent_encoded_credential_query_in_map_key_is_rejected_and_redacted(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    credential_url = "https://source-a.example/data?api%5fkey=" + "A" * 24
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "lookup": {credential_url: "redacted"},
            "items": [{"id": "one", "count": 1}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "signed/credential URL in object key" in encoded
    assert "<map-key>" in encoded
    assert credential_url not in encoded


def test_unapproved_excluded_list_cannot_bypass_sensitive_field_scan(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    private_name = "Alice Smith"
    _write_json(
        root / "data" / "public" / "artifact.json",
        {
            "generated_at": "2026-08-17T00:00:00+00:00",
            "person_name_excluded": [private_name],
            "items": [{"id": "one", "count": 1}],
        },
    )
    write_receipt(root, contracts_root, catalog_path)

    report = validate_workspace(root, contracts_root, catalog_path)
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["status"] == "invalid"
    assert "private/contact field" in encoded
    assert private_name not in encoded


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


def test_contract_rejects_opaque_completeness_claims(tmp_path):
    _, contracts_root, _ = _fixture(tmp_path)
    contract_path = contracts_root / "sample.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["completeness"]["secondary_count"] = 2
    _write_json(contract_path, contract)

    with pytest.raises(PublicationError, match="unexpected completeness fields"):
        load_contracts(contracts_root)


def test_git_completeness_rule_blocks_secondary_collection_loss(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    artifact_path = root / "data" / "public" / "artifact.json"
    contract_path = contracts_root / "sample.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["outputs"][0]["completeness_rules"] = [
        {
            "pointer": "/secondary",
            "minimum_count": 1,
            "max_count_drop_ratio": 0,
            "max_count_increase_ratio": 1,
        }
    ]
    _write_json(contract_path, contract)
    base_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    base_payload["secondary"] = [
        {"opaque": "first-private-value"},
        {"opaque": "second-private-value"},
    ]
    _write_json(artifact_path, base_payload)
    write_receipt(root, contracts_root, catalog_path)
    _git(root, "init", "-b", "main")
    base_sha = _commit_all(root, "base secondary completeness")

    head_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    head_payload["generated_at"] = "2026-08-18T00:00:00+00:00"
    head_payload["secondary"] = head_payload["secondary"][:1]
    _write_json(artifact_path, head_payload)
    write_receipt(root, contracts_root, catalog_path)
    head_sha = _commit_all(root, "drop secondary collection")

    report, valid = validate_git_revision(
        root, contracts_root, catalog_path, base_sha, head_sha
    )
    encoded = json.dumps(report, ensure_ascii=False)

    assert valid is False
    assert any(
        "secondary completeness count drop exceeds contract" in problem
        for problem in report["problems"]
    )
    assert "first-private-value" not in encoded
    assert "second-private-value" not in encoded


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


def test_git_semantic_diff_blocks_geometry_type_reinterpretation(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    coordinates = [
        [
            [100.0, 13.0],
            [101.0, 13.0],
            [101.0, 14.0],
            [100.0, 13.0],
        ]
    ]
    _install_geojson(
        root,
        contracts_root,
        catalog_path,
        _geojson_payload([{"type": "Polygon", "coordinates": coordinates}]),
    )
    _git(root, "init", "-b", "main")
    base_sha = _commit_all(root, "base polygon geometry")

    _install_geojson(
        root,
        contracts_root,
        catalog_path,
        _geojson_payload(
            [{"type": "MultiLineString", "coordinates": coordinates}],
            generated_at="2026-08-18T00:00:00+00:00",
        ),
    )
    head_sha = _commit_all(root, "reinterpret geometry type")

    report, valid = validate_git_revision(
        root, contracts_root, catalog_path, base_sha, head_sha
    )

    assert valid is False
    assert report["status"] == "blocked"
    assert report["lane"] == "routine_refresh"
    assert any("semantic meaning changed" in item for item in report["problems"])
    assert not any("schema changed" in item for item in report["problems"])


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


@pytest.mark.parametrize(
    ("semantic_key", "changed_value"),
    [
        ("unit", "people"),
        ("denominator", "eligible population"),
        ("grain_th", "one row per district"),
        ("publication_status", "accepted_fact"),
        ("geography_level", "district"),
    ],
)
def test_git_semantic_diff_blocks_meaning_reinterpretation_without_logging_values(
    tmp_path, semantic_key, changed_value
):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    artifact_path = root / "data" / "public" / "artifact.json"
    base_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    base_payload["semantics"] = {
        "unit": "records",
        "denominator": "all records",
        "grain_th": "one row per record",
        "publication_status": "candidate",
        "geography_level": "province",
    }
    _write_json(artifact_path, base_payload)
    write_receipt(root, contracts_root, catalog_path)
    _git(root, "init", "-b", "main")
    base_sha = _commit_all(root, "base semantics")

    head_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    head_payload["generated_at"] = "2026-08-18T00:00:00+00:00"
    head_payload["semantics"][semantic_key] = changed_value
    _write_json(artifact_path, head_payload)
    write_receipt(root, contracts_root, catalog_path)
    head_sha = _commit_all(root, "reinterpret semantics")

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
    assert any(
        "semantic meaning changed under stable contract" in problem
        for problem in report["problems"]
    )
    assert not any("schema changed" in problem for problem in report["problems"])
    assert changed_value not in encoded
    assert len(report["semantic_diff"][0]["before"]["semantic_sha256"]) == 64
    assert len(report["semantic_diff"][0]["after"]["semantic_sha256"]) == 64


def test_git_semantic_diff_does_not_freeze_ordinary_geography_record_values(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    artifact_path = root / "data" / "public" / "artifact.json"
    base_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    base_payload["items"][0].update(
        {"province_code": "10", "province_name_th": "กรุงเทพมหานคร"}
    )
    _write_json(artifact_path, base_payload)
    write_receipt(root, contracts_root, catalog_path)
    _git(root, "init", "-b", "main")
    base_sha = _commit_all(root, "base geography values")

    head_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    head_payload["generated_at"] = "2026-08-18T00:00:00+00:00"
    head_payload["items"][0].update(
        {"province_code": "11", "province_name_th": "สมุทรปราการ"}
    )
    _write_json(artifact_path, head_payload)
    write_receipt(root, contracts_root, catalog_path)
    head_sha = _commit_all(root, "refresh geography values")

    report, valid = validate_git_revision(
        root,
        contracts_root,
        catalog_path,
        base_sha,
        head_sha,
    )

    assert valid is True
    assert report["status"] == "pass"
    assert report["semantic_diff"][0]["before"]["semantic_sha256"] == report[
        "semantic_diff"
    ][0]["after"]["semantic_sha256"]


def test_git_semantic_diff_blocks_unit_and_status_swaps_between_stable_records(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    artifact_path = root / "data" / "public" / "artifact.json"
    base_payload = {
        "generated_at": "2026-08-17T00:00:00+00:00",
        "items": [
            {"id": "one", "count": 2, "unit": "records", "quality_status": "candidate"},
            {"id": "two", "count": 3, "unit": "people", "quality_status": "reviewed"},
        ],
    }
    _write_json(artifact_path, base_payload)
    write_receipt(root, contracts_root, catalog_path)
    _git(root, "init", "-b", "main")
    base_sha = _commit_all(root, "base stable record semantics")

    head_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    head_payload["generated_at"] = "2026-08-18T00:00:00+00:00"
    for field in ("unit", "quality_status"):
        head_payload["items"][0][field], head_payload["items"][1][field] = (
            head_payload["items"][1][field],
            head_payload["items"][0][field],
        )
    _write_json(artifact_path, head_payload)
    write_receipt(root, contracts_root, catalog_path)
    head_sha = _commit_all(root, "swap stable record semantics")

    report, valid = validate_git_revision(
        root, contracts_root, catalog_path, base_sha, head_sha
    )

    assert valid is False
    assert any("semantic meaning changed" in item for item in report["problems"])


def test_git_semantic_diff_blocks_partial_semantic_field_removal(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    artifact_path = root / "data" / "public" / "artifact.json"
    base_payload = {
        "generated_at": "2026-08-17T00:00:00+00:00",
        "items": [
            {"id": "one", "count": 2, "quality_status": "candidate"},
            {"id": "two", "count": 3, "quality_status": "candidate"},
        ],
    }
    _write_json(artifact_path, base_payload)
    write_receipt(root, contracts_root, catalog_path)
    _git(root, "init", "-b", "main")
    base_sha = _commit_all(root, "base repeated status")

    head_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    head_payload["generated_at"] = "2026-08-18T00:00:00+00:00"
    del head_payload["items"][0]["quality_status"]
    _write_json(artifact_path, head_payload)
    write_receipt(root, contracts_root, catalog_path)
    head_sha = _commit_all(root, "remove one status")

    report, valid = validate_git_revision(
        root, contracts_root, catalog_path, base_sha, head_sha
    )

    assert valid is False
    assert any("semantic meaning changed" in item for item in report["problems"])
    assert not any("schema changed" in item for item in report["problems"])


@pytest.mark.parametrize(
    ("target", "changed_value"),
    [
        ("quality_label_th", "รับรองแล้ว"),
        ("metric_label_th", "ตัวชี้วัดที่เปลี่ยนความหมาย"),
        ("province_join_method", "unreviewed_guess"),
    ],
)
def test_git_semantic_diff_blocks_displayed_meaning_changes(
    tmp_path, target, changed_value
):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    artifact_path = root / "data" / "public" / "artifact.json"
    base_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    base_payload["items"][0].update(
        {
            "quality_label_th": "ข้อมูลทดลอง ต้องตรวจทาน",
            "metric_label_th": "จำนวนรายการ",
        }
    )
    base_payload["quality"] = {"province_join_method": "official_code"}
    _write_json(artifact_path, base_payload)
    write_receipt(root, contracts_root, catalog_path)
    _git(root, "init", "-b", "main")
    base_sha = _commit_all(root, "base displayed semantics")

    head_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    head_payload["generated_at"] = "2026-08-18T00:00:00+00:00"
    if target == "province_join_method":
        head_payload["quality"][target] = changed_value
    else:
        head_payload["items"][0][target] = changed_value
    _write_json(artifact_path, head_payload)
    write_receipt(root, contracts_root, catalog_path)
    head_sha = _commit_all(root, "change displayed semantics")

    report, valid = validate_git_revision(
        root, contracts_root, catalog_path, base_sha, head_sha
    )
    encoded = json.dumps(report, ensure_ascii=False)

    assert valid is False
    assert any("semantic meaning changed" in item for item in report["problems"])
    assert changed_value not in encoded


@pytest.mark.parametrize(
    ("field", "base_value", "head_value"),
    [
        ("verification_state", "candidate", "reviewed"),
        ("classification", "public_candidate", "public_reviewed"),
        ("candidate_not_fact", True, False),
        ("workflow_marker", "candidate", "accepted"),
    ],
)
def test_git_semantic_diff_blocks_candidate_promotion_aliases(
    tmp_path, field, base_value, head_value
):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    artifact_path = root / "data" / "public" / "artifact.json"
    base_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    base_payload["items"][0]["public_visibility"] = {field: base_value}
    _write_json(artifact_path, base_payload)
    write_receipt(root, contracts_root, catalog_path)
    _git(root, "init", "-b", "main")
    base_sha = _commit_all(root, "base candidate marker")

    head_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    head_payload["generated_at"] = "2026-08-18T00:00:00+00:00"
    head_payload["items"][0]["public_visibility"][field] = head_value
    _write_json(artifact_path, head_payload)
    write_receipt(root, contracts_root, catalog_path)
    head_sha = _commit_all(root, "promote candidate marker")

    report, valid = validate_git_revision(
        root, contracts_root, catalog_path, base_sha, head_sha
    )
    encoded = json.dumps(report, ensure_ascii=False)

    assert valid is False
    assert any("semantic meaning changed" in item for item in report["problems"])
    assert str(head_value) not in encoded


def test_git_semantic_diff_allows_dynamic_geography_row_counts(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    artifact_path = root / "data" / "public" / "artifact.json"
    base_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    base_payload["coverage"] = {"geography_rows": 6}
    _write_json(artifact_path, base_payload)
    write_receipt(root, contracts_root, catalog_path)
    _git(root, "init", "-b", "main")
    base_sha = _commit_all(root, "base geography count")

    head_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    head_payload["generated_at"] = "2026-08-18T00:00:00+00:00"
    head_payload["coverage"]["geography_rows"] = 7
    _write_json(artifact_path, head_payload)
    write_receipt(root, contracts_root, catalog_path)
    head_sha = _commit_all(root, "refresh geography count")

    report, valid = validate_git_revision(
        root, contracts_root, catalog_path, base_sha, head_sha
    )

    assert valid is True
    assert report["semantic_diff"][0]["before"]["semantic_sha256"] == report[
        "semantic_diff"
    ][0]["after"]["semantic_sha256"]


def test_git_semantic_diff_blocks_nested_record_as_of_regression(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    artifact_path = root / "data" / "public" / "artifact.json"
    base_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    base_payload["items"][0]["nested"] = {
        "observed_as_of": "2026-08-16T00:00:00+00:00"
    }
    _write_json(artifact_path, base_payload)
    write_receipt(root, contracts_root, catalog_path)
    _git(root, "init", "-b", "main")
    base_sha = _commit_all(root, "base nested as of")

    head_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    head_payload["generated_at"] = "2026-08-18T00:00:00+00:00"
    head_payload["items"][0]["nested"]["observed_as_of"] = (
        "2026-08-15T00:00:00+00:00"
    )
    _write_json(artifact_path, head_payload)
    write_receipt(root, contracts_root, catalog_path)
    head_sha = _commit_all(root, "regress nested as of")

    report, valid = validate_git_revision(
        root, contracts_root, catalog_path, base_sha, head_sha
    )
    encoded = json.dumps(report, ensure_ascii=False)

    assert valid is False
    assert any("per-record as_of moved backwards" in item for item in report["problems"])
    assert "2026-08-15" not in encoded


def test_git_semantic_diff_allows_new_records_with_unchanged_semantics(tmp_path):
    root, contracts_root, catalog_path = _fixture(tmp_path)
    artifact_path = root / "data" / "public" / "artifact.json"
    contract_path = contracts_root / "sample.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["outputs"][0]["max_identity_churn_ratio"] = 1
    _write_json(contract_path, contract)
    base_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    base_payload["items"][0].update(
        {"unit": "records", "publication_status": "candidate"}
    )
    _write_json(artifact_path, base_payload)
    write_receipt(root, contracts_root, catalog_path)
    _git(root, "init", "-b", "main")
    base_sha = _commit_all(root, "base record semantics")

    head_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    head_payload["generated_at"] = "2026-08-18T00:00:00+00:00"
    head_payload["items"].append(
        {
            "id": "two",
            "count": 3,
            "unit": "records",
            "publication_status": "candidate",
        }
    )
    _write_json(artifact_path, head_payload)
    write_receipt(root, contracts_root, catalog_path)
    head_sha = _commit_all(root, "add record without changing semantics")

    report, valid = validate_git_revision(
        root,
        contracts_root,
        catalog_path,
        base_sha,
        head_sha,
    )

    assert valid is True
    assert report["status"] == "pass"
    assert report["semantic_diff"][0]["before"]["semantic_sha256"] == report[
        "semantic_diff"
    ][0]["after"]["semantic_sha256"]


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

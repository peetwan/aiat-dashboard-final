from __future__ import annotations

import json
import shutil

import pytest

from app.connector_contracts import (
    CONTRACTS_ROOT,
    ConnectorContractError,
    load_connector_contract,
    load_runtime_connector_contract,
    prepare_contract_records,
    validate_connector_contracts,
)
from app.connectors.registry import ConnectorLoadError, load_connector


def test_every_executable_source_has_an_importable_connector_contract():
    report = validate_connector_contracts()

    assert report["status"] == "valid"
    assert report["contract_version"] == "1.1"
    assert report["connector_count"] == 6
    assert {item["source_id"] for item in report["connectors"]} == {
        "f1_sradss_ppaos",
        "f2_apptech_mtr",
        "f2_apptech_mru",
        "f2_learning_dashboard",
        "f2_learning_area_based",
        "f3_housing_portal",
    }
    assert all(item["grains"] >= 1 for item in report["connectors"])
    assert all(item["completeness_checks"] >= 1 for item in report["connectors"])


def test_contract_validation_rejects_candidate_to_public_shortcut(tmp_path):
    for path in CONTRACTS_ROOT.glob("*.json"):
        shutil.copy2(path, tmp_path / path.name)
    target = tmp_path / "f2_apptech_mtr.json"
    contract = json.loads(target.read_text(encoding="utf-8"))
    contract["privacy"]["candidate_only"] = False
    target.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ConnectorContractError, match="candidate-only"):
        validate_connector_contracts(contracts_root=tmp_path)


def test_connector_loader_rejects_modules_outside_reviewed_namespace():
    with pytest.raises(ConnectorLoadError, match="app.connectors"):
        load_connector("os:path")


def test_contract_transport_is_extensible_lower_snake_case(tmp_path):
    for path in CONTRACTS_ROOT.glob("*.json"):
        shutil.copy2(path, tmp_path / path.name)
    target = tmp_path / "f2_apptech_mtr.json"
    contract = json.loads(target.read_text(encoding="utf-8"))
    contract["transport"] = "arcgis_rest"
    target.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")

    report = validate_connector_contracts(contracts_root=tmp_path)
    assert next(
        item for item in report["connectors"] if item["source_id"] == "f2_apptech_mtr"
    )["transport"] == "arcgis_rest"

    contract["transport"] = "ArcGIS REST"
    target.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ConnectorContractError, match="lower_snake_case"):
        validate_connector_contracts(contracts_root=tmp_path)


def test_runtime_contract_load_does_not_require_test_fixture_files_in_deploy_image(tmp_path):
    source_id = "f2_apptech_mtr"
    shutil.copy2(CONTRACTS_ROOT / f"{source_id}.json", tmp_path / f"{source_id}.json")

    contract = load_runtime_connector_contract(source_id, contracts_root=tmp_path)
    assert contract is not None
    assert contract["sample_fixture"] == f"tests/fixtures/connectors/{source_id}.json"


def test_contract_requires_anchored_unambiguous_dataset_patterns(tmp_path):
    for path in CONTRACTS_ROOT.glob("*.json"):
        shutil.copy2(path, tmp_path / path.name)
    target = tmp_path / "f2_apptech_mtr.json"
    contract = json.loads(target.read_text(encoding="utf-8"))
    contract["dataset_grains"][0]["key_pattern"] = "innovations"
    target.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ConnectorContractError, match="fully anchored"):
        validate_connector_contracts(contracts_root=tmp_path)

    contract["dataset_grains"][0]["key_pattern"] = "^innovations$"
    overlapping = dict(contract["dataset_grains"][0])
    overlapping["key_pattern"] = "^innovation.*$"
    contract["dataset_grains"].append(overlapping)
    target.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ConnectorContractError, match="exactly one grain"):
        validate_connector_contracts(contracts_root=tmp_path)


def test_contract_rejects_legacy_or_unknown_grain_fields(tmp_path):
    for path in CONTRACTS_ROOT.glob("*.json"):
        shutil.copy2(path, tmp_path / path.name)
    target = tmp_path / "f2_apptech_mtr.json"
    contract = json.loads(target.read_text(encoding="utf-8"))
    contract["dataset_grains"][0]["identity_fields"] = ["id"]
    target.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ConnectorContractError, match="unexpected fields.*identity_fields"):
        validate_connector_contracts(contracts_root=tmp_path)


def test_contract_requires_as_of_fields_to_match_the_published_schema(tmp_path):
    for path in CONTRACTS_ROOT.glob("*.json"):
        shutil.copy2(path, tmp_path / path.name)
    target = tmp_path / "f2_apptech_mtr.json"
    contract = json.loads(target.read_text(encoding="utf-8"))
    del contract["dataset_grains"][0]["as_of_fields"]
    target.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ConnectorContractError, match=r"as_of_fields must be an array"):
        validate_connector_contracts(contracts_root=tmp_path)


def test_runtime_contract_identity_is_explicit_unique_and_extracts_as_of():
    contract = load_connector_contract(CONTRACTS_ROOT / "f2_apptech_mtr.json")
    prepared = prepare_contract_records(
        contract,
        [("innovations", {"id": "record-1", "year": "2569", "name": "fixture"})],
    )
    assert prepared[0].record_id == "record-1"
    assert prepared[0].as_of == "2569"

    with pytest.raises(ConnectorContractError, match="none of the contract identity_options"):
        prepare_contract_records(contract, [("innovations", {"name": "missing id"})])
    with pytest.raises(ConnectorContractError, match="duplicate identity"):
        prepare_contract_records(
            contract,
            [
                ("innovations", {"id": "same", "name": "first"}),
                ("innovations", {"id": "same", "name": "second"}),
            ],
        )
    with pytest.raises(ConnectorContractError, match="dataset_key exceeds 200"):
        prepare_contract_records(contract, [("i" * 201, {"id": "record-1"})])

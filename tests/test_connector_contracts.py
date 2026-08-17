from __future__ import annotations

import json
import shutil

import pytest

from app.connector_contracts import (
    CONTRACTS_ROOT,
    ConnectorContractError,
    validate_connector_contracts,
)
from app.connectors.registry import ConnectorLoadError, load_connector


def test_every_executable_source_has_an_importable_connector_contract():
    report = validate_connector_contracts()

    assert report["status"] == "valid"
    assert report["contract_version"] == "1.0"
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

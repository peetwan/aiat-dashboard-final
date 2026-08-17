from __future__ import annotations

import json
from pathlib import Path

from app.catalog import load_catalog, load_ingestion_plans
from app.connectors import ConnectorLoadError, load_connector
from app.settings import PROJECT_ROOT


CONTRACTS_ROOT = PROJECT_ROOT / "config" / "connector_contracts"
CONTRACT_VERSION = "1.0"
TRANSPORTS = {"http_json", "http_form_json", "ckan_csv", "snapshot"}
REQUIRED_PRIVACY_FIELDS = {
    "email",
    "phone",
    "address",
    "token",
    "password",
    "cookie",
    "authorization",
}


class ConnectorContractError(ValueError):
    pass


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConnectorContractError(f"{label} must be a non-empty string")
    return value


def _require_string_list(value: object, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ConnectorContractError(f"{label} must be a non-empty string array")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ConnectorContractError(f"{label} contains an empty or non-string value")
    return value


def load_connector_contract(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConnectorContractError(f"cannot read {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConnectorContractError(f"{path.name} must contain a JSON object")
    return payload


def validate_connector_contracts(
    *,
    contracts_root: Path = CONTRACTS_ROOT,
    catalog: dict | None = None,
    plans_document: dict | None = None,
) -> dict:
    """Validate every executable connector without contacting upstream systems."""

    catalog = catalog or load_catalog()
    plans_document = plans_document or load_ingestion_plans()
    plans = plans_document.get("sources")
    if not isinstance(plans, dict) or not plans:
        raise ConnectorContractError("ingestion plans must contain a non-empty sources object")
    catalog_by_id = {item["source_id"]: item for item in catalog.get("sources", [])}
    paths = sorted(contracts_root.glob("*.json"))
    contract_ids = {path.stem for path in paths}
    planned_ids = set(plans)
    if contract_ids != planned_ids:
        raise ConnectorContractError(
            "connector contract set mismatch: "
            f"missing={sorted(planned_ids - contract_ids)}, extra={sorted(contract_ids - planned_ids)}"
        )

    validated: list[dict] = []
    seen_entrypoints: set[str] = set()
    for source_id in sorted(planned_ids):
        path = contracts_root / f"{source_id}.json"
        contract = load_connector_contract(path)
        if contract.get("contract_version") != CONTRACT_VERSION:
            raise ConnectorContractError(f"{source_id}: contract_version must be {CONTRACT_VERSION}")
        if contract.get("source_id") != source_id:
            raise ConnectorContractError(f"{source_id}: source_id must match the filename")
        source = catalog_by_id.get(source_id)
        if source is None:
            raise ConnectorContractError(f"{source_id}: source is missing from source_catalog.json")
        if source.get("cloud_policy") == "restricted_local_only":
            raise ConnectorContractError(f"{source_id}: restricted source cannot have an executable connector")
        if source.get("production_values_allowed") is not True:
            raise ConnectorContractError(f"{source_id}: executable connector is not production-approved")

        plan = plans[source_id]
        entrypoint = _require_string(contract.get("connector"), f"{source_id}.connector")
        if entrypoint != plan.get("connector"):
            raise ConnectorContractError(f"{source_id}: contract and plan connector entrypoints differ")
        if entrypoint in seen_entrypoints:
            raise ConnectorContractError(f"{source_id}: connector entrypoint is duplicated")
        seen_entrypoints.add(entrypoint)
        try:
            connector = load_connector(entrypoint)
        except ConnectorLoadError as exc:
            raise ConnectorContractError(f"{source_id}: {exc}") from exc
        if connector.driver_name != plan.get("driver"):
            raise ConnectorContractError(
                f"{source_id}: driver mismatch plan={plan.get('driver')} "
                f"connector={connector.driver_name}"
            )

        transport = contract.get("transport")
        if transport not in TRANSPORTS:
            raise ConnectorContractError(f"{source_id}.transport is not supported")
        grains = contract.get("dataset_grains")
        if not isinstance(grains, list) or not grains:
            raise ConnectorContractError(f"{source_id}.dataset_grains must be a non-empty array")
        grain_patterns: list[str] = []
        for index, grain in enumerate(grains):
            if not isinstance(grain, dict):
                raise ConnectorContractError(f"{source_id}.dataset_grains[{index}] must be an object")
            label = f"{source_id}.dataset_grains[{index}]"
            grain_patterns.append(_require_string(grain.get("key_pattern"), f"{label}.key_pattern"))
            _require_string(grain.get("grain_th"), f"{label}.grain_th")
            _require_string_list(grain.get("identity_fields"), f"{label}.identity_fields")
            _require_string_list(
                grain.get("geography_fields"),
                f"{label}.geography_fields",
                allow_empty=True,
            )
            if "as_of_fields" in grain:
                _require_string_list(
                    grain.get("as_of_fields"),
                    f"{label}.as_of_fields",
                    allow_empty=True,
                )
        if len(grain_patterns) != len(set(grain_patterns)):
            raise ConnectorContractError(f"{source_id}: dataset key_pattern values must be unique")

        completeness = _require_string_list(
            contract.get("completeness_checks"),
            f"{source_id}.completeness_checks",
        )
        privacy = contract.get("privacy")
        if not isinstance(privacy, dict):
            raise ConnectorContractError(f"{source_id}.privacy must be an object")
        if privacy.get("candidate_only") is not True:
            raise ConnectorContractError(f"{source_id}: connector output must remain candidate-only")
        if privacy.get("contact_value_scan") is not True:
            raise ConnectorContractError(f"{source_id}: contact value scan must remain enabled")
        forbidden = set(
            _require_string_list(
                privacy.get("forbidden_public_fields"),
                f"{source_id}.privacy.forbidden_public_fields",
            )
        )
        if not REQUIRED_PRIVACY_FIELDS.issubset(forbidden):
            missing = sorted(REQUIRED_PRIVACY_FIELDS - forbidden)
            raise ConnectorContractError(f"{source_id}: missing forbidden public fields {missing}")

        fixture = contract.get("sample_fixture")
        if fixture is not None:
            fixture_path = (PROJECT_ROOT / _require_string(fixture, f"{source_id}.sample_fixture")).resolve()
            fixtures_root = (PROJECT_ROOT / "tests" / "fixtures" / "connectors").resolve()
            if fixture_path.parent != fixtures_root and fixtures_root not in fixture_path.parents:
                raise ConnectorContractError(f"{source_id}: fixture must stay under tests/fixtures/connectors")
            if not fixture_path.is_file():
                raise ConnectorContractError(f"{source_id}: fixture does not exist: {fixture}")

        validated.append(
            {
                "source_id": source_id,
                "driver": connector.driver_name,
                "connector": entrypoint,
                "transport": transport,
                "grains": len(grains),
                "completeness_checks": len(completeness),
            }
        )

    return {
        "status": "valid",
        "contract_version": CONTRACT_VERSION,
        "connector_count": len(validated),
        "connectors": validated,
    }

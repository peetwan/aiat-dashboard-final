from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from app.catalog import load_catalog, load_ingestion_plans
from app.connectors import ConnectorLoadError, load_connector
from app.privacy import (
    RecordIdentityError,
    contract_as_of,
    contract_record_id,
    payload_hash,
    sanitize_payload,
)
from app.settings import PROJECT_ROOT


CONTRACTS_ROOT = PROJECT_ROOT / "config" / "connector_contracts"
CONTRACT_VERSION = "1.1"
TRANSPORT_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
MAX_DATASET_KEY_LENGTH = 200
MAX_FIXTURE_BYTES = 64 * 1024
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


@dataclass(frozen=True)
class ValidatedConnectorRecord:
    dataset_key: str
    payload: dict
    record_hash: str
    record_id: str
    as_of: str | None


def _reject_unknown_fields(value: dict, allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ConnectorContractError(f"{label} contains unexpected fields: {unknown}")


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConnectorContractError(f"{label} must be a non-empty string")
    return value


def _require_string_list(value: object, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        qualifier = "an array" if allow_empty else "a non-empty string array"
        raise ConnectorContractError(f"{label} must be {qualifier}")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ConnectorContractError(f"{label} contains an empty or non-string value")
    return value


def _require_identity_options(value: object, label: str) -> list[list[str]]:
    if not isinstance(value, list) or not value:
        raise ConnectorContractError(f"{label} must be a non-empty array of composite alternatives")
    options: list[list[str]] = []
    for index, option in enumerate(value):
        fields = _require_string_list(option, f"{label}[{index}]")
        if "$payload_hash" in fields and fields != ["$payload_hash"]:
            raise ConnectorContractError(
                f"{label}[{index}]: $payload_hash must be the only field in its alternative"
            )
        if any(field.startswith("$") and field != "$payload_hash" for field in fields):
            raise ConnectorContractError(f"{label}[{index}] contains an unknown special field")
        for field in fields:
            if field == "$payload_hash":
                continue
            if any(not part for part in field.split(".")):
                raise ConnectorContractError(f"{label}[{index}] contains an invalid dotted path")
        options.append(fields)
    fingerprints = [tuple(option) for option in options]
    if len(fingerprints) != len(set(fingerprints)):
        raise ConnectorContractError(f"{label} contains a duplicate alternative")
    return options


def load_connector_contract(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConnectorContractError(f"cannot read {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConnectorContractError(f"{path.name} must contain a JSON object")
    return payload


def _validated_grains(contract: dict, source_id: str) -> list[dict]:
    grains = contract.get("dataset_grains")
    if not isinstance(grains, list) or not grains:
        raise ConnectorContractError(f"{source_id}.dataset_grains must be a non-empty array")
    validated: list[dict] = []
    patterns: list[str] = []
    for index, grain in enumerate(grains):
        if not isinstance(grain, dict):
            raise ConnectorContractError(f"{source_id}.dataset_grains[{index}] must be an object")
        label = f"{source_id}.dataset_grains[{index}]"
        _reject_unknown_fields(
            grain,
            {"key_pattern", "grain_th", "identity_options", "geography_fields", "as_of_fields"},
            label,
        )
        pattern = _require_string(grain.get("key_pattern"), f"{label}.key_pattern")
        if not (pattern.startswith("^") and pattern.endswith("$")):
            raise ConnectorContractError(f"{label}.key_pattern must be a fully anchored regex")
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            raise ConnectorContractError(f"{label}.key_pattern is invalid: {exc}") from exc
        _require_string(grain.get("grain_th"), f"{label}.grain_th")
        identity_options = _require_identity_options(
            grain.get("identity_options"),
            f"{label}.identity_options",
        )
        _require_string_list(
            grain.get("geography_fields"),
            f"{label}.geography_fields",
            allow_empty=True,
        )
        as_of_fields = _require_string_list(
            grain.get("as_of_fields"),
            f"{label}.as_of_fields",
            allow_empty=True,
        )
        patterns.append(pattern)
        validated.append(
            {
                "pattern": compiled,
                "identity_options": identity_options,
                "as_of_fields": as_of_fields,
            }
        )
    if len(patterns) != len(set(patterns)):
        raise ConnectorContractError(f"{source_id}: dataset key_pattern values must be unique")
    return validated


def prepare_contract_records(
    contract: dict,
    records: Iterable[tuple[str, dict]],
) -> list[ValidatedConnectorRecord]:
    """Sanitize and validate a full connector batch without writing to the database."""

    source_id = _require_string(contract.get("source_id"), "contract.source_id")
    grains = _validated_grains(contract, source_id)
    prepared: list[ValidatedConnectorRecord] = []
    identities: set[tuple[str, str]] = set()
    for index, item in enumerate(records):
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise ConnectorContractError(f"{source_id}: record[{index}] must be (dataset_key, payload)")
        dataset_key, raw_payload = item
        if not isinstance(dataset_key, str) or not dataset_key:
            raise ConnectorContractError(f"{source_id}: record[{index}] dataset_key is empty or invalid")
        if len(dataset_key) > MAX_DATASET_KEY_LENGTH:
            raise ConnectorContractError(
                f"{source_id}: record[{index}] dataset_key exceeds {MAX_DATASET_KEY_LENGTH} characters"
            )
        if not isinstance(raw_payload, dict):
            raise ConnectorContractError(f"{source_id}: record[{index}] payload must be an object")
        matching = [grain for grain in grains if grain["pattern"].fullmatch(dataset_key)]
        if len(matching) != 1:
            raise ConnectorContractError(
                f"{source_id}: dataset_key {dataset_key!r} must match exactly one grain; "
                f"matched={len(matching)}"
            )
        payload = sanitize_payload(raw_payload)
        digest = payload_hash(payload)
        grain = matching[0]
        try:
            record_id = contract_record_id(payload, grain["identity_options"], digest)
            as_of = contract_as_of(payload, grain["as_of_fields"])
        except RecordIdentityError as exc:
            raise ConnectorContractError(
                f"{source_id}: record[{index}] {dataset_key!r}: {exc}"
            ) from exc
        identity = (dataset_key, record_id)
        if identity in identities:
            raise ConnectorContractError(
                f"{source_id}: duplicate identity dataset={dataset_key!r} record_id={record_id!r}"
            )
        identities.add(identity)
        prepared.append(
            ValidatedConnectorRecord(
                dataset_key=dataset_key,
                payload=payload,
                record_hash=digest,
                record_id=record_id,
                as_of=as_of,
            )
        )
    return prepared


def _fixture_reference(contract: dict, source_id: str) -> str:
    fixture = _require_string(contract.get("sample_fixture"), f"{source_id}.sample_fixture")
    relative = Path(fixture)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or len(relative.parts) != 4
        or relative.parts[:3] != ("tests", "fixtures", "connectors")
        or relative.name != f"{source_id}.json"
    ):
        raise ConnectorContractError(
            f"{source_id}: fixture must be tests/fixtures/connectors/{source_id}.json"
        )
    return fixture


def _fixture_path(contract: dict, source_id: str) -> Path:
    fixture = _fixture_reference(contract, source_id)
    fixture_path = (PROJECT_ROOT / fixture).resolve()
    fixtures_root = (PROJECT_ROOT / "tests" / "fixtures" / "connectors").resolve()
    if fixture_path.parent != fixtures_root and fixtures_root not in fixture_path.parents:
        raise ConnectorContractError(f"{source_id}: fixture must stay under tests/fixtures/connectors")
    if not fixture_path.is_file():
        raise ConnectorContractError(f"{source_id}: fixture does not exist: {fixture}")
    if fixture_path.stat().st_size > MAX_FIXTURE_BYTES:
        raise ConnectorContractError(
            f"{source_id}: fixture exceeds the {MAX_FIXTURE_BYTES}-byte size limit"
        )
    return fixture_path


def _validate_fixture(contract: dict, source_id: str) -> None:
    fixture_path = _fixture_path(contract, source_id)
    fixture = load_connector_contract(fixture_path)
    _reject_unknown_fields(fixture, {"fixture_version", "source_id", "records"}, source_id)
    if fixture.get("fixture_version") != "1.0":
        raise ConnectorContractError(f"{source_id}: fixture_version must be 1.0")
    if fixture.get("source_id") != source_id:
        raise ConnectorContractError(f"{source_id}: fixture source_id does not match")
    records = fixture.get("records")
    if not isinstance(records, list) or not records:
        raise ConnectorContractError(f"{source_id}: fixture records must be a non-empty array")
    batch: list[tuple[str, dict]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ConnectorContractError(f"{source_id}: fixture record[{index}] must be an object")
        _reject_unknown_fields(record, {"dataset_key", "payload"}, f"{source_id}.record[{index}]")
        dataset_key = record.get("dataset_key")
        payload = record.get("payload")
        if not isinstance(payload, dict):
            raise ConnectorContractError(f"{source_id}: fixture record[{index}].payload must be an object")
        if sanitize_payload(payload) != payload:
            raise ConnectorContractError(f"{source_id}: fixture record[{index}] is not redacted")
        batch.append((dataset_key, payload))
    prepare_contract_records(contract, batch)


def _validate_contract_document(contract: dict, source_id: str, *, validate_fixture: bool) -> None:
    _reject_unknown_fields(
        contract,
        {
            "contract_version",
            "source_id",
            "connector",
            "transport",
            "dataset_grains",
            "completeness_checks",
            "privacy",
            "sample_fixture",
            "notes_th",
        },
        source_id,
    )
    if contract.get("contract_version") != CONTRACT_VERSION:
        raise ConnectorContractError(f"{source_id}: contract_version must be {CONTRACT_VERSION}")
    if contract.get("source_id") != source_id:
        raise ConnectorContractError(f"{source_id}: source_id must match the filename")
    if SOURCE_ID_PATTERN.fullmatch(source_id) is None:
        raise ConnectorContractError(f"{source_id}: source_id must be lower_snake_case")
    _require_string(contract.get("connector"), f"{source_id}.connector")
    transport = contract.get("transport")
    if not isinstance(transport, str) or TRANSPORT_PATTERN.fullmatch(transport) is None:
        raise ConnectorContractError(f"{source_id}.transport must be lower_snake_case")
    _validated_grains(contract, source_id)
    _require_string_list(contract.get("completeness_checks"), f"{source_id}.completeness_checks")
    privacy = contract.get("privacy")
    if not isinstance(privacy, dict):
        raise ConnectorContractError(f"{source_id}.privacy must be an object")
    _reject_unknown_fields(
        privacy,
        {"candidate_only", "contact_value_scan", "forbidden_public_fields"},
        f"{source_id}.privacy",
    )
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
    # Runtime images intentionally exclude tests.  Validate the reviewed path
    # here, while the full CI validator below also opens and checks the fixture.
    _fixture_reference(contract, source_id)
    if validate_fixture:
        _validate_fixture(contract, source_id)


def load_runtime_connector_contract(
    source_id: str,
    *,
    contracts_root: Path = CONTRACTS_ROOT,
) -> dict | None:
    path = contracts_root / f"{source_id}.json"
    if not path.is_file():
        return None
    contract = load_connector_contract(path)
    _validate_contract_document(contract, source_id, validate_fixture=False)
    return contract


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
        _validate_contract_document(contract, source_id, validate_fixture=True)
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

        validated.append(
            {
                "source_id": source_id,
                "driver": connector.driver_name,
                "connector": entrypoint,
                "transport": contract["transport"],
                "grains": len(contract["dataset_grains"]),
                "completeness_checks": len(contract["completeness_checks"]),
            }
        )

    return {
        "status": "valid",
        "contract_version": CONTRACT_VERSION,
        "connector_count": len(validated),
        "connectors": validated,
    }

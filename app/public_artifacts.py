from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.catalog import load_catalog
from app.models import PublicArtifact, utc_now
from app.privacy import EMAIL_RE, PHONE_RE
from app.field_contexts import is_contact_exposure_metadata, key_kind
from app.settings import PROJECT_ROOT
from app.publication import _privacy_problems, bind_outputs, load_contracts


PUBLIC_DATA_ROOT = PROJECT_ROOT / "data" / "public"
SERVING_MANIFEST_NAME = "serving_manifest.json"
MANIFEST_VERSION = "1.0"
SAFE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_/-]*$")
SOURCE_ID_RE = re.compile(r"^[a-z0-9_]+$")
MAX_ARTIFACT_KEY_LENGTH = 200
MAX_ARTIFACT_GROUP_LENGTH = 60
SENSITIVE_KEY_RE = re.compile(
    r"(?:^|_)(?:phone|telephone|tel|mobile|email|e_mail|contact|address)(?:_|$)"
)
THAI_PHONE_VALUE_RE = PHONE_RE
LABELLED_CONTACT_VALUE_RE = re.compile(
    r"(?i)(?:\b(?:phone|telephone|mobile|tel|email)\s*(?:no\.?|number)?\s*[:：]|"
    r"(?:โทรศัพท์|เบอร์โทร|อีเมล|อีเมล์)\s*[:：])"
)
ADDRESS_VALUE_RE = re.compile(
    r"(?i)(?:\b(?:home|residential|mailing)\s+address\b|"
    r"ที่อยู่(?:บ้าน|ปัจจุบัน|ตามทะเบียนบ้าน)|บ้านเลขที่)"
)
SENSITIVE_THAI_KEY_PARTS = ("โทรศัพท์", "เบอร์โทร", "อีเมล", "อีเมล์", "ที่อยู่", "ผู้ติดต่อ")
NEGATIVE_PRIVACY_AUDIT_KEYS = {"contact_fields_exposed"}
NON_CONTACT_KEY_ALLOWLIST = {"mobile_home_park"}
OPAQUE_PHONE_VALUE_KEYS = {
    "amount",
    "code",
    "count",
    "date",
    "external_id",
    "hash",
    "id",
    "item_id",
    "latitude",
    "longitude",
    "province_code",
    "record_hash",
    "record_id",
    "resource_id",
    "source_row_number",
    "time",
    "updated_at",
    "year",
}
OPAQUE_PHONE_VALUE_KEY_PARTS = {
    "amount",
    "area",
    "average",
    "avg",
    "count",
    "index",
    "mean",
    "median",
    "metric",
    "percent",
    "population",
    "rate",
    "ratio",
    "score",
    "share",
    "sum",
    "total",
    "value",
}
RESTRICTED_ID_AUDIT_GROUPS = {"provincial_briefing", "executive_summary"}
REQUIRED_CORE_ARTIFACTS = {
    "catalog": "catalog",
    "source-insights": "source_insights",
    "source-coverage": "source_coverage",
    "unmapped-records": "unmapped_records",
    "housing-spatial-summary": "housing_spatial_summary",
    "housing-demand-summary": "housing_demand_summary",
    "learning-dashboard": "source_dataset",
    "map/provinces": "map",
    "map/cultural-points": "map",
}
REQUIRED_CORE_GLOBS = {
    "provincial_briefing": "province/{stem}/briefing",
    "executive_summary": "province/{stem}/summary",
}


@dataclass(frozen=True)
class ArtifactInput:
    key: str
    group: str
    path: Path
    province_code: str | None = None
    source_ids: tuple[str, ...] = ()


def _approved_and_restricted_source_ids() -> tuple[set[str], set[str]]:
    catalog = load_catalog()
    sources = catalog.get("sources", [])
    approved = {
        source["source_id"]
        for source in sources
        if source.get("production_values_allowed") is True
        and source.get("cloud_policy") == "team_approved_public"
    }
    restricted = {
        source["source_id"]
        for source in sources
        if source.get("cloud_policy") == "restricted_local_only"
    }
    return approved, restricted


def artifact_inputs(
    root: Path = PUBLIC_DATA_ROOT,
    *,
    enforce_core: bool = True,
) -> list[ArtifactInput]:
    """Expand the reviewed, data-driven serving manifest shipped with the app."""

    manifest_path = root / SERVING_MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read public serving manifest: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("manifest_version") != MANIFEST_VERSION:
        raise RuntimeError(f"public serving manifest must use version {MANIFEST_VERSION}")
    unknown_manifest_fields = sorted(set(manifest) - {"manifest_version", "artifacts"})
    if unknown_manifest_fields:
        raise RuntimeError(
            "public serving manifest contains unexpected fields: "
            f"{unknown_manifest_fields}"
        )
    entries = manifest.get("artifacts")
    if not isinstance(entries, list) or not entries:
        raise RuntimeError("public serving manifest must contain a non-empty artifacts array")

    root_resolved = root.resolve()

    def safe_relative(value: object, label: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"{label} must be a non-empty relative path")
        candidate = Path(value)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise RuntimeError(f"{label} must stay under data/public")
        return value.replace("\\", "/")

    def safe_path(value: object, label: str) -> Path:
        relative = safe_relative(value, label)
        candidate = (root / relative).resolve()
        if candidate != root_resolved and root_resolved not in candidate.parents:
            raise RuntimeError(f"{label} escapes data/public")
        return candidate

    approved_source_ids, _ = _approved_and_restricted_source_ids()
    inputs: list[ArtifactInput] = []
    for index, entry in enumerate(entries):
        label = f"artifacts[{index}]"
        if not isinstance(entry, dict):
            raise RuntimeError(f"{label} must be an object")
        group = entry.get("group")
        if not isinstance(group, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", group):
            raise RuntimeError(f"{label}.group must be lower_snake_case")
        if len(group) > MAX_ARTIFACT_GROUP_LENGTH:
            raise RuntimeError(
                f"{label}.group exceeds {MAX_ARTIFACT_GROUP_LENGTH} characters"
            )
        has_path = "path" in entry
        has_glob = "path_glob" in entry
        if has_path == has_glob:
            raise RuntimeError(f"{label} must declare exactly one of path or path_glob")

        allowed_fields = (
            {"key", "group", "path", "province_code", "source_ids"}
            if has_path
            else {
                "key_template",
                "group",
                "path_glob",
                "province_code_from",
                "expected_count",
                "source_ids",
            }
        )
        unknown_fields = sorted(set(entry) - allowed_fields)
        if unknown_fields:
            raise RuntimeError(f"{label} contains unexpected fields: {unknown_fields}")

        raw_source_ids = entry.get("source_ids", [])
        if not isinstance(raw_source_ids, list) or any(
            not isinstance(source_id, str) or SOURCE_ID_RE.fullmatch(source_id) is None
            for source_id in raw_source_ids
        ):
            raise RuntimeError(f"{label}.source_ids must be a lower_snake_case string array")
        if len(raw_source_ids) != len(set(raw_source_ids)):
            raise RuntimeError(f"{label}.source_ids contains duplicates")
        source_ids = tuple(raw_source_ids)
        is_core_entry = (
            has_path and entry.get("key") in REQUIRED_CORE_ARTIFACTS
        ) or (
            has_glob and entry.get("key_template") == REQUIRED_CORE_GLOBS.get(group)
        )
        if not is_core_entry and not source_ids:
            raise RuntimeError(f"{label}.source_ids is required for a non-core artifact")
        if group == "source_dataset" and not source_ids:
            raise RuntimeError(f"{label}.source_ids is required for source_dataset")
        disallowed_source_ids = sorted(set(source_ids) - approved_source_ids)
        if disallowed_source_ids:
            raise RuntimeError(
                f"{label}.source_ids contains non-approved sources: {disallowed_source_ids}"
            )

        if has_path:
            key = entry.get("key")
            if not isinstance(key, str) or not SAFE_NAME_RE.fullmatch(key):
                raise RuntimeError(f"{label}.key contains unsupported characters")
            if len(key) > MAX_ARTIFACT_KEY_LENGTH:
                raise RuntimeError(
                    f"{label}.key exceeds {MAX_ARTIFACT_KEY_LENGTH} characters"
                )
            path = safe_path(entry.get("path"), f"{label}.path")
            if not path.is_file():
                raise RuntimeError(f"public serving artifact is missing: {path.name}")
            province_code = entry.get("province_code")
            if province_code is not None and not re.fullmatch(r"[0-9]{2}", str(province_code)):
                raise RuntimeError(f"{label}.province_code must contain two digits")
            inputs.append(ArtifactInput(key, group, path, province_code, source_ids))
            continue

        pattern = safe_relative(entry.get("path_glob"), f"{label}.path_glob")
        key_template = entry.get("key_template")
        if not isinstance(key_template, str) or key_template.count("{stem}") != 1:
            raise RuntimeError(f"{label}.key_template must contain one {{stem}} placeholder")
        expected_count = entry.get("expected_count")
        if type(expected_count) is not int or expected_count < 1:
            raise RuntimeError(f"{label}.expected_count must be a positive integer")
        province_code_from = entry.get("province_code_from")
        if province_code_from not in (None, "stem"):
            raise RuntimeError(f"{label}.province_code_from must be stem when present")
        if group in {"provincial_briefing", "executive_summary"} and province_code_from != "stem":
            raise RuntimeError(
                f"{label}.province_code_from must be stem for the province serving core"
            )
        paths = sorted(root.glob(pattern))
        if len(paths) != expected_count:
            raise RuntimeError(f"{label} matched {len(paths)} files; expected {expected_count}")
        for path in paths:
            resolved = path.resolve()
            if root_resolved not in resolved.parents or not resolved.is_file():
                raise RuntimeError(f"{label}.path_glob resolved outside data/public")
            key = key_template.replace("{stem}", path.stem)
            if not SAFE_NAME_RE.fullmatch(key):
                raise RuntimeError(f"{label}.key_template produced an invalid key: {key}")
            if len(key) > MAX_ARTIFACT_KEY_LENGTH:
                raise RuntimeError(
                    f"{label}.key_template produced a key over "
                    f"{MAX_ARTIFACT_KEY_LENGTH} characters"
                )
            province_code = path.stem if province_code_from == "stem" else None
            if province_code is not None and not re.fullmatch(r"[0-9]{2}", province_code):
                raise RuntimeError(f"{label} produced an invalid province code")
            inputs.append(ArtifactInput(key, group, resolved, province_code, source_ids))

    keys = [item.key for item in inputs]
    if len(keys) != len(set(keys)):
        raise RuntimeError("public serving manifest produces duplicate artifact keys")
    if enforce_core:
        group_by_key = {item.key: item.group for item in inputs}
        missing = sorted(set(REQUIRED_CORE_ARTIFACTS) - set(group_by_key))
        wrong_groups = sorted(
            key
            for key, expected_group in REQUIRED_CORE_ARTIFACTS.items()
            if key in group_by_key and group_by_key[key] != expected_group
        )
        group_counts = Counter(item.group for item in inputs)
        briefing_codes = {
            item.province_code for item in inputs if item.group == "provincial_briefing"
        }
        summary_codes = {
            item.province_code for item in inputs if item.group == "executive_summary"
        }
        if (
            missing
            or wrong_groups
            or group_counts["provincial_briefing"] != 77
            or group_counts["executive_summary"] != 77
            or None in briefing_codes
            or None in summary_codes
            or len(briefing_codes) != 77
            or len(summary_codes) != 77
            or briefing_codes != summary_codes
        ):
            raise RuntimeError(
                "public serving core is incomplete: "
                f"missing={missing}, wrong_groups={wrong_groups}, "
                f"briefings={group_counts['provincial_briefing']}, "
                f"summaries={group_counts['executive_summary']}"
            )
    return inputs


def required_group_counts(
    root: Path = PUBLIC_DATA_ROOT,
    *,
    enforce_core: bool = True,
) -> dict[str, int]:
    return dict(Counter(item.group for item in artifact_inputs(root, enforce_core=enforce_core)))


REQUIRED_GROUP_COUNTS = required_group_counts()
REQUIRED_ARTIFACT_COUNT = sum(REQUIRED_GROUP_COUNTS.values())


def _item_count(payload: Any) -> int:
    if isinstance(payload, dict):
        for key in ("features", "provinces", "sources", "items"):
            value = payload.get(key)
            if isinstance(value, (list, dict)):
                return len(value)
        return 1
    if isinstance(payload, list):
        return len(payload)
    return 1


def _load_input(item: ArtifactInput) -> tuple[dict, str, int]:
    raw = item.path.read_bytes()
    payload = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"public artifact must be a JSON object: {item.path}")
    return payload, hashlib.sha256(raw).hexdigest(), _item_count(payload)


def _normalise_key(key: object) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(key))
    return re.sub(r"[^a-z0-9ก-๙]+", "_", value.lower()).strip("_")


def _negative_privacy_audit_value(key: str, value: Any) -> bool:
    if key in NEGATIVE_PRIVACY_AUDIT_KEYS and value is False:
        return True
    if key in {"email_values_redacted", "phone_values_redacted"}:
        return type(value) is int and value >= 0
    if key.endswith(("_fields_in_source_schema", "_field_count")) and value in (0, False, None):
        return True
    return False


def _is_core_artifact(item: ArtifactInput) -> bool:
    if item.key in REQUIRED_CORE_ARTIFACTS:
        return True
    expected_suffix = {
        "provincial_briefing": "briefing",
        "executive_summary": "summary",
    }.get(item.group)
    return (
        expected_suffix is not None
        and item.province_code is not None
        and item.key == f"province/{item.province_code}/{expected_suffix}"
    )


def _opaque_phone_value_key(item: ArtifactInput, key: str | None) -> bool:
    if key is None:
        return False
    if key in OPAQUE_PHONE_VALUE_KEYS or key.endswith("_url"):
        return True
    # The reviewed core contains numeric measures serialized as strings.  Keep
    # that narrow compatibility exception out of the generic extension lane,
    # where a phone-looking string under a vague `value` key must fail closed.
    return _is_core_artifact(item) and bool(
        set(key.split("_")) & OPAQUE_PHONE_VALUE_KEY_PARTS
    )


def _artifact_policy_violations(
    item: ArtifactInput,
    payload: dict,
    restricted_source_ids: set[str],
) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []

    def restricted_id_allowed(path: str) -> bool:
        if item.key == "source-coverage":
            return True
        if item.group not in RESTRICTED_ID_AUDIT_GROUPS or item.province_code is None:
            return False
        audit_list_path = f"{item.key}.quality.restricted_source_ids_excluded"
        return re.fullmatch(rf"{re.escape(audit_list_path)}\[\d+\]", path) is not None

    def walk(value: Any, path: str, leaf_key: str | None = None) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = _normalise_key(key)
                child_path = f"{path}.{key}"
                sensitive_key = normalized not in NON_CONTACT_KEY_ALLOWLIST and (
                    bool(SENSITIVE_KEY_RE.search(normalized))
                    or key_kind(str(key)) in {"private", "name", "contact"}
                    or any(marker in str(key) for marker in SENSITIVE_THAI_KEY_PARTS)
                )
                contact_audit_flag = is_contact_exposure_metadata(path.rsplit(".", 1)[-1], str(key), child)
                if sensitive_key and not contact_audit_flag and not _negative_privacy_audit_value(normalized, child):
                    violations.append((child_path, "contact/private field"))
                if str(key) in restricted_source_ids and not restricted_id_allowed(child_path):
                    violations.append((child_path, "restricted source identifier"))
                walk(child, child_path, normalized)
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]", leaf_key)
            return
        if not isinstance(value, str):
            return
        if value in restricted_source_ids and not restricted_id_allowed(path):
            violations.append((path, "restricted source identifier"))
        if EMAIL_RE.search(value):
            violations.append((path, "email value"))
        if LABELLED_CONTACT_VALUE_RE.search(value):
            violations.append((path, "labelled contact value"))
        if ADDRESS_VALUE_RE.search(value):
            violations.append((path, "home address value"))
        if (
            not _opaque_phone_value_key(item, leaf_key)
            and THAI_PHONE_VALUE_RE.search(value)
        ):
            violations.append((path, "Thai phone-like value"))

    walk(payload, item.key)
    return violations


def validate_public_artifacts(
    inputs: Iterable[ArtifactInput] | None = None,
    *,
    contracts_root: Path | None = None,
) -> list[tuple[ArtifactInput, dict, str, int]]:
    """Load every selected artifact and fail closed on public-policy violations."""

    selected = list(inputs if inputs is not None else artifact_inputs())
    approved_source_ids, restricted_source_ids = _approved_and_restricted_source_ids()
    contracts = load_contracts(contracts_root or PROJECT_ROOT / "config/publication_contracts")
    relative_paths = {
        item.path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
        for item in selected if item.path.resolve().is_relative_to(PROJECT_ROOT.resolve())
    }
    # Serving validates the selected database artifacts. Publication separately
    # checks that every support/download output exists in the complete release.
    bindings = bind_outputs(relative_paths, contracts, require_all=False)
    loaded: list[tuple[ArtifactInput, dict, str, int]] = []
    violations: list[tuple[str, str]] = []
    for item in selected:
        payload, digest, item_count = _load_input(item)
        loaded.append((item, payload, digest, item_count))
        relative = item.path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix() if item.path.resolve().is_relative_to(PROJECT_ROOT.resolve()) else None
        binding = bindings.get(relative)
        contexts = binding.output.get("field_contexts", {}) if binding else {}
        if contexts:
            if not set(binding.contract["source_ids"]).issubset(approved_source_ids):
                violations.append((item.key, "field context source is not approved"))
            # ใช้ contract ของไฟล์จริง การผ่าน publication จึงไม่ถูกตัวกรอง
            # แบบเหมารวมใน startup ปฏิเสธชื่อ/ข้อมูลติดต่องานซ้ำอีกครั้ง
            violations.extend((item.key, problem) for problem in _privacy_problems(
                payload, artifact_path=relative, restricted_source_ids=restricted_source_ids,
                profile=binding.contract["privacy_profile"], field_contexts=contexts,
            ))
        else:
            violations.extend(_artifact_policy_violations(item, payload, restricted_source_ids))
    if violations:
        evidence = "; ".join(f"{path}: {reason}" for path, reason in violations[:20])
        remainder = len(violations) - 20
        if remainder > 0:
            evidence += f"; ... and {remainder} more"
        raise RuntimeError(
            f"public artifact policy rejected {len(violations)} value(s): {evidence}"
        )
    return loaded


def sync_public_artifacts(
    session: Session,
    inputs: Iterable[ArtifactInput] | None = None,
) -> dict[str, Any]:
    """Idempotently synchronize cleaned public artifacts into the active DB."""

    selected = list(inputs if inputs is not None else artifact_inputs())
    if inputs is None:
        group_counts = Counter(item.group for item in selected)
        if dict(group_counts) != REQUIRED_GROUP_COUNTS:
            raise RuntimeError(
                "public serving artifact groups do not match the required contract: "
                f"actual={dict(group_counts)}, expected={REQUIRED_GROUP_COUNTS}"
            )
    loaded_inputs = validate_public_artifacts(selected)
    expected_keys: list[str] = []
    inserted = 0
    updated = 0
    unchanged = 0
    for item, payload, digest, item_count in loaded_inputs:
        expected_keys.append(item.key)
        artifact = session.get(PublicArtifact, item.key)
        changed = (
            artifact is None
            or artifact.content_hash != digest
            or artifact.artifact_group != item.group
            or artifact.province_code != item.province_code
            or artifact.source_path != item.path.relative_to(PROJECT_ROOT).as_posix()
            or artifact.item_count != item_count
        )
        if artifact is None:
            artifact = PublicArtifact(artifact_key=item.key)
            inserted += 1
        elif not changed:
            unchanged += 1
        else:
            updated += 1
        if changed:
            artifact.artifact_group = item.group
            artifact.province_code = item.province_code
            artifact.content_hash = digest
            artifact.source_path = item.path.relative_to(PROJECT_ROOT).as_posix()
            artifact.item_count = item_count
            artifact.payload = payload
            artifact.updated_at = utc_now()
        session.add(artifact)

    if expected_keys:
        session.execute(
            delete(PublicArtifact).where(PublicArtifact.artifact_key.not_in(expected_keys))
        )
    else:
        session.execute(delete(PublicArtifact))
    session.commit()
    return {
        "expected": len(expected_keys),
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
    }


def artifact_payload(session: Session, artifact_key: str) -> dict | None:
    return session.scalar(
        select(PublicArtifact.payload).where(PublicArtifact.artifact_key == artifact_key)
    )


def database_artifact_counts(session: Session) -> dict[str, int]:
    return {
        group: count
        for group, count in session.execute(
            select(PublicArtifact.artifact_group, func.count())
            .group_by(PublicArtifact.artifact_group)
            .order_by(PublicArtifact.artifact_group)
        ).all()
    }

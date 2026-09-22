"""Shared pure-input helpers for reviewed cross-source identity domains."""

from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any

from .raw_inputs import observation_uri, resolve_evidence
from ..common import PipelineError, normalize

# Review payloads use legacy producer names while source tables are keyed by the
# canonical IDs in inputs.v3.json.  Keep this map explicit; a new producer must
# be reviewed rather than silently accepted through punctuation folding.
SOURCE_ALIASES: dict[str, tuple[str, ...]] = {
    "icommunity": ("icommunity", "f2_icommunity"),
    "pmua_apptech": ("pmua_apptech", "pmua-apptech", "f2_target_household"),
    "rinmp": ("rinmp", "f2_apptech_mtr"),
    "apptech_mru": ("apptech_mru", "apptech-mru", "f2_apptech_mru"),
    "atlocal": ("atlocal", "f2_cultural_market_civil"),
    "cultural_map": ("cultural_map", "cultural-map", "f2_culturalmap_university"),
    "learning_area_based": (
        "learning_area_based",
        "learning-area-based",
        "f2_learning_area_based",
    ),
    "learning_dashboard": (
        "learning_dashboard",
        "learning-dashboard",
        "f2_learning_dashboard",
    ),
}


def fail(domain: str, message: str) -> None:
    raise PipelineError(f"{domain} input contract: {message}")


def json_value(value: Any, expected: type | tuple[type, ...] | None = None) -> Any:
    """Decode a CSV JSON scalar while leaving already-decoded injected values alone."""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped and stripped[0] in '[{"' or stripped in {"null", "true", "false"}:
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError:
                pass
    if expected is not None and not isinstance(value, expected):
        raise PipelineError(
            f"Expected {getattr(expected, '__name__', expected)}, got {type(value).__name__}"
        )
    return value


def json_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    decoded = json_value(value)
    if not isinstance(decoded, list):
        raise PipelineError(f"Expected JSON list, got {type(decoded).__name__}")
    return decoded


def json_object(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    decoded = json_value(value)
    if not isinstance(decoded, dict):
        raise PipelineError(f"Expected JSON object, got {type(decoded).__name__}")
    return decoded


def truth(value: Any) -> bool:
    return value is True or str(value).strip().casefold() in {"1", "true", "yes"}


def logical_source(value: str) -> str:
    for logical, aliases in SOURCE_ALIASES.items():
        if value in aliases:
            return logical
    fail("resolver", f"unknown source alias {value!r}")
    raise AssertionError


def source_tables_for(
    source_tables: dict[str, dict[str, list[dict]]], logical: str
) -> tuple[str, dict[str, list[dict]]]:
    aliases = SOURCE_ALIASES[logical]
    matches = [(key, value) for key, value in source_tables.items() if key in aliases]
    if len(matches) != 1:
        fail(
            "resolver",
            f"expected exactly one {logical} source table bundle; found {[key for key, _ in matches]}",
        )
    canonical, tables = matches[0]
    if not isinstance(tables, dict) or not all(
        isinstance(rows, list) for rows in tables.values()
    ):
        fail("resolver", f"{canonical} source tables must map table names to row lists")
    return canonical, tables


def review_payload(
    reviews: dict[str, Any], legacy_path: str, *, required: bool = True
) -> Any:
    """Resolve a lock-decoded review by its immutable legacy-relative identity."""
    exact = [
        value
        for key, value in reviews.items()
        if key == legacy_path
        or key == f"review-config://{legacy_path}"
        or key.endswith("/" + legacy_path)
    ]
    if len(exact) > 1:
        fail("reviews", f"duplicate payload for {legacy_path}")
    if exact:
        return exact[0]
    if required:
        fail("reviews", f"missing locked payload {legacy_path}")
    return None


def review_payloads_under(
    reviews: dict[str, Any], legacy_directory: str
) -> list[tuple[str, Any]]:
    prefix = legacy_directory.rstrip("/") + "/"
    found: list[tuple[str, Any]] = []
    for key, value in reviews.items():
        comparable = key.removeprefix("review-config://")
        position = comparable.find(prefix)
        if position >= 0 and comparable[position:].startswith(prefix):
            relative = comparable[position:]
            if relative.endswith(".json"):
                found.append((relative, value))
    unique = {key: value for key, value in found}
    if len(unique) != len(found):
        fail("reviews", f"duplicate payload under {legacy_directory}")
    return sorted(unique.items())


def evidence_locator(
    raw_input: dict[str, Any], observation: dict[str, Any], suffix: str = ""
) -> str:
    """Return and validate the canonical immutable locator for one observation."""
    metadata = raw_input.get("metadata", {}) if isinstance(raw_input, dict) else {}
    source_ids = {
        normalize(item.get("source_id"))
        for item in metadata.values()
        if isinstance(item, dict) and normalize(item.get("source_id"))
    }
    if len(source_ids) != 1:
        fail(
            "provenance",
            "raw input bundle does not identify exactly one canonical source",
        )
    source_id = next(iter(source_ids))
    base = observation_uri({source_id: raw_input}, source_id, observation)
    return base.rstrip("/") + suffix


def contextual_evidence_locator(
    raw_input: dict[str, Any],
    observation: dict[str, Any],
    locator: Any = "",
) -> str:
    """Resolve an assertion within its observation, not merely the same source."""
    observation_base = evidence_locator(raw_input, observation)
    source_id = observation_base.removeprefix("evidence://").split("/", 1)[0]
    if not locator:
        result = observation_base
    elif str(locator).startswith("evidence://"):
        result = str(locator)
    else:
        result = observation_base.split("#", 1)[0] + "#" + str(locator).lstrip("#/")
    source, run, filename, pointer = locator_parts(result)
    owner_source, owner_run, owner_file, owner_pointer = locator_parts(observation_base)
    if (
        (source, run, filename.removesuffix(".gz"))
        != (owner_source, owner_run, owner_file.removesuffix(".gz"))
        or (
            owner_pointer
            and pointer != owner_pointer
            and not pointer.startswith(owner_pointer + "/")
        )
    ):
        fail("provenance", "assertion evidence belongs to another observation")
    resolve_evidence({source_id: raw_input}, result)
    return result


def locator_parts(locator: str) -> tuple[str, str, str, str]:
    if (
        not isinstance(locator, str)
        or not locator.startswith("evidence://")
        or "#" not in locator
    ):
        fail("provenance", f"non-immutable evidence locator {locator!r}")
    stem, pointer = locator.split("#", 1)
    parts = stem.removeprefix("evidence://").split("/", 2)
    if len(parts) != 3 or not all(parts):
        fail("provenance", f"invalid evidence locator {locator!r}")
    return parts[0], parts[1], parts[2], pointer.strip("/")


def locator_matches(review_locator: str, current_locator: str) -> bool:
    """Permit a reviewed child/parent pointer only within the same locked file."""
    reviewed_source, reviewed_run, reviewed_file, reviewed_pointer = locator_parts(
        review_locator
    )
    current_source, current_run, current_file, current_pointer = locator_parts(
        current_locator
    )
    same_source = logical_source(reviewed_source) == logical_source(current_source)
    same_file = PurePosixPath(reviewed_file).name.removesuffix(".gz") == PurePosixPath(
        current_file
    ).name.removesuffix(".gz")
    same_pointer = (
        reviewed_pointer == current_pointer
        or reviewed_pointer.startswith(current_pointer + "/")
        or current_pointer.startswith(reviewed_pointer + "/")
    )
    return same_source and reviewed_run == current_run and same_file and same_pointer


class _LocatorNode:
    __slots__ = ("children", "rows")

    def __init__(self) -> None:
        self.children: dict[str, _LocatorNode] = {}
        self.rows: list[tuple[int, Any]] = []


class EvidenceLocatorIndex:
    """Index immutable locators with the same exact/ancestor/child relation as locator_matches."""

    def __init__(self) -> None:
        self._groups: dict[tuple[str, str, str], _LocatorNode] = {}
        self._ordinal = 0

    @staticmethod
    def _key(locator: str) -> tuple[tuple[str, str, str], tuple[str, ...]]:
        source, run_id, filename, pointer = locator_parts(locator)
        group = (
            logical_source(source),
            run_id,
            PurePosixPath(filename).name.removesuffix(".gz"),
        )
        return group, tuple(pointer.split("/")) if pointer else ()

    def add(self, locator: str, value: Any) -> None:
        group, tokens = self._key(locator)
        node = self._groups.setdefault(group, _LocatorNode())
        for token in tokens:
            node = node.children.setdefault(token, _LocatorNode())
        node.rows.append((self._ordinal, value))
        self._ordinal += 1

    def related(self, locator: str) -> list[Any]:
        group, tokens = self._key(locator)
        node = self._groups.get(group)
        if node is None:
            return []
        if not tokens:
            return [value for _, value in node.rows]
        matches: list[tuple[int, Any]] = []
        for token in tokens:
            node = node.children.get(token)
            if node is None:
                return [value for _, value in sorted(matches)]
            matches.extend(node.rows)
        stack = list(node.children.values())
        while stack:
            descendant = stack.pop()
            matches.extend(descendant.rows)
            stack.extend(descendant.children.values())
        return [value for _, value in sorted(matches)]

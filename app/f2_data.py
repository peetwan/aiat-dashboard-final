from __future__ import annotations

import hashlib
import json
import re
import threading
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.database import SessionLocal
from app.models import PublicArtifact
from app.settings import PROJECT_ROOT


F2_ROOT = PROJECT_ROOT / "data" / "public" / "f2"
F2_MANIFEST = F2_ROOT / "manifest.json"
SERVING_MANIFEST = PROJECT_ROOT / "data" / "public" / "serving_manifest.json"
PAGE_DEFAULT = 25
PAGE_MAX = 100
QUERY_MAX = 200
_CACHE_MAX_ENTRIES = 12
_CACHE_MAX_BYTES = 32 * 1024 * 1024
_FILTER_ORDER = (
    "province",
    "category",
    "source_level",
    "source_region",
    "component",
    "source_dimension",
)

_THAI_UNITS = {
    "province": "จังหวัด",
    "area": "แห่ง",
    "person": "คน",
    "activity": "ครั้ง",
    "innovation": "นวัตกรรม",
    "operator": "ร้านค้า",
    "offering_family": "รายการ",
    "business": "ธุรกิจชุมชน",
    "participating_business_unit": "ธุรกิจชุมชน",
    "person_per_month": "คนต่อเดือน",
    "million_THB_per_month": "ล้านบาทต่อเดือน",
    "cluster": "คลัสเตอร์",
    "mapped_subject": "รายการ",
}


def _thai_unit(unit: Any) -> Any:
    if unit is None:
        return None
    localized = _THAI_UNITS.get(str(unit))
    if localized is not None:
        return localized
    if re.search(r"[A-Za-z]", str(unit)):
        raise F2DataError(f"F2 KPI unit has no Thai display mapping: {unit}")
    return unit


def _localize_result(result: Any) -> Any:
    if not isinstance(result, dict):
        return result
    localized = dict(result)
    if "unit" in localized:
        localized["unit"] = _thai_unit(localized["unit"])
    return localized


def _localize_measure_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    localized = dict(payload)
    if "unit" in localized:
        localized["unit"] = _thai_unit(localized["unit"])
    if "result" in localized:
        localized["result"] = _localize_result(localized["result"])
    return localized


class F2DataError(RuntimeError):
    status_code = 503


class F2NotFound(F2DataError):
    status_code = 404


class F2InvalidQuery(F2DataError):
    status_code = 422


class F2RevisionConflict(F2DataError):
    status_code = 409


@dataclass(frozen=True)
class RevisionSnapshot:
    revision: str
    release_id: str
    release_date: str
    files: dict[str, dict[str, Any]]
    source_ids: list[str]


@dataclass
class _CachedArtifact:
    payload: dict[str, Any]
    size: int


_cache_lock = threading.RLock()
_revision_signature: tuple[int, int, int, int] | None = None
_revision_snapshot: RevisionSnapshot | None = None
_artifact_cache: OrderedDict[tuple[str, str], _CachedArtifact] = OrderedDict()
_artifact_cache_bytes = 0
_artifact_db_reads: dict[str, int] = {}


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError, TypeError) as error:
        raise F2DataError(f"F2 publication artifact unavailable: {path.name}") from error
    if not isinstance(payload, dict):
        raise F2DataError(f"F2 publication artifact is not an object: {path.name}")
    return payload, raw


def _manifest_signature() -> tuple[int, int, int, int]:
    try:
        f2_stat = F2_MANIFEST.stat()
        serving_stat = SERVING_MANIFEST.stat()
    except OSError as error:
        raise F2DataError("F2 publication manifest unavailable") from error
    return (
        f2_stat.st_mtime_ns,
        f2_stat.st_size,
        serving_stat.st_mtime_ns,
        serving_stat.st_size,
    )


def _active_revision() -> RevisionSnapshot:
    global _revision_signature, _revision_snapshot, _artifact_cache_bytes
    signature = _manifest_signature()
    with _cache_lock:
        if signature == _revision_signature and _revision_snapshot is not None:
            return _revision_snapshot

        manifest, raw = _read_json(F2_MANIFEST)
        serving, _ = _read_json(SERVING_MANIFEST)
        if (
            manifest.get("complete") is not True
            or manifest.get("validation_status") != "passed"
            or manifest.get("publication_status") != "approved_local_publication"
            or manifest.get("publication_approval_claimed") is not True
            or manifest.get("staged_for_review") is not False
        ):
            raise F2DataError("F2 publication manifest is not an active approved release")

        files = manifest.get("files")
        if not isinstance(files, list):
            raise F2DataError("F2 publication manifest has no file inventory")
        by_key: dict[str, dict[str, Any]] = {}
        for item in files:
            if not isinstance(item, dict):
                raise F2DataError("F2 publication manifest file inventory is invalid")
            key = item.get("artifact_key")
            digest = item.get("sha256")
            size = item.get("size")
            if (
                not isinstance(key, str)
                or not key.startswith("f2/")
                or not isinstance(digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or not isinstance(size, int)
                or size < 0
                or key in by_key
            ):
                raise F2DataError("F2 publication manifest file inventory is invalid")
            by_key[key] = item

        serving_keys = {
            item.get("key")
            for item in serving.get("artifacts", [])
            if isinstance(item, dict) and str(item.get("key", "")).startswith("f2/")
        }
        if set(by_key) != serving_keys:
            raise F2DataError("F2 active manifest and serving manifest disagree")
        expected_core = {"f2/overview", "f2/geography"} | {
            f"f2/topic/{topic}" for topic in (
                "k01a", "k01b", "k02", "k03", "k04", "k05", "k06",
                "k07", "k08", "k09", "k10", "k11a", "k11b", "k12",
            )
        }
        if not expected_core.issubset(by_key):
            raise F2DataError("F2 active manifest is missing required artifacts")

        snapshot = RevisionSnapshot(
            revision=hashlib.sha256(raw).hexdigest(),
            release_id=str(manifest.get("release_id", "")),
            release_date=str(manifest.get("release_date", "")),
            files=by_key,
            source_ids=list(manifest.get("source_ids") or []),
        )
        _revision_signature = signature
        _revision_snapshot = snapshot
        _artifact_cache.clear()
        _artifact_cache_bytes = 0
        _artifact_db_reads.clear()
        return snapshot


def _require_revision(snapshot: RevisionSnapshot, requested: str | None) -> None:
    if requested is not None and requested != snapshot.revision:
        raise F2RevisionConflict("requested F2 revision is no longer active")


def _load_artifact(snapshot: RevisionSnapshot, artifact_key: str) -> dict[str, Any]:
    global _artifact_cache_bytes
    declared = snapshot.files.get(artifact_key)
    if declared is None:
        raise F2NotFound("unknown F2 artifact")
    cache_key = (snapshot.revision, artifact_key)
    with _cache_lock:
        cached = _artifact_cache.get(cache_key)
        if cached is not None:
            _artifact_cache.move_to_end(cache_key)
            return cached.payload

    with SessionLocal() as session:
        row = session.execute(
            select(PublicArtifact.content_hash, PublicArtifact.payload).where(
                PublicArtifact.artifact_key == artifact_key
            )
        ).one_or_none()
    if row is None:
        raise F2DataError(f"required F2 artifact is not synchronized: {artifact_key}")
    content_hash, payload = row
    if content_hash != declared["sha256"]:
        raise F2DataError(f"F2 artifact hash does not belong to active revision: {artifact_key}")
    if not isinstance(payload, dict) or payload.get("release_id") != snapshot.release_id:
        raise F2DataError(f"F2 artifact release is inconsistent: {artifact_key}")

    size = int(declared["size"])
    with _cache_lock:
        _artifact_db_reads[artifact_key] = _artifact_db_reads.get(artifact_key, 0) + 1
        if size <= _CACHE_MAX_BYTES:
            while _artifact_cache and (
                len(_artifact_cache) >= _CACHE_MAX_ENTRIES
                or _artifact_cache_bytes + size > _CACHE_MAX_BYTES
            ):
                _, evicted = _artifact_cache.popitem(last=False)
                _artifact_cache_bytes -= evicted.size
            _artifact_cache[cache_key] = _CachedArtifact(payload=payload, size=size)
            _artifact_cache_bytes += size
    return payload


def reset_f2_cache() -> None:
    global _revision_signature, _revision_snapshot, _artifact_cache_bytes
    with _cache_lock:
        _revision_signature = None
        _revision_snapshot = None
        _artifact_cache.clear()
        _artifact_cache_bytes = 0
        _artifact_db_reads.clear()


def f2_cache_stats() -> dict[str, Any]:
    with _cache_lock:
        return {
            "entries": len(_artifact_cache),
            "bytes": _artifact_cache_bytes,
            "database_reads": dict(_artifact_db_reads),
        }


def _scope_key(province: str | None, source_region: str | None) -> str:
    if province and source_region:
        raise F2InvalidQuery("province and source_region are mutually exclusive")
    if province:
        return f"province/{province}"
    if source_region:
        return f"source_region/{source_region}"
    return "national"


def _validate_province(geography: dict[str, Any], province: str | None) -> str | None:
    if province is None:
        return None
    code = province.strip()
    if not re.fullmatch(r"\d{2}", code) or code not in geography.get("provinces", {}):
        raise F2InvalidQuery("unknown province code")
    return code


def _topic_and_contract(
    snapshot: RevisionSnapshot, topic_id: str, measure_id: str | None
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    normalized_topic = topic_id.strip().lower()
    topic_key = f"f2/topic/{normalized_topic}"
    if topic_key not in snapshot.files:
        raise F2NotFound("unknown F2 topic")
    topic = _load_artifact(snapshot, topic_key)
    measure_ids = topic.get("measure_ids") or []
    selected_measure = measure_id or (measure_ids[0] if measure_ids else None)
    if selected_measure not in measure_ids:
        raise F2NotFound("measure does not belong to topic")
    contract = (topic.get("filter_contracts") or {}).get(selected_measure)
    if not isinstance(contract, dict):
        raise F2DataError("F2 topic filter contract is inconsistent")
    return topic, str(selected_measure), contract


def _requested_filters(**values: str | None) -> dict[str, list[str]]:
    return {key: [value] for key in _FILTER_ORDER if (value := values.get(key)) is not None}


def _select_precomputed(
    topic: dict[str, Any],
    measure_id: str,
    contract: dict[str, Any],
    requested: dict[str, list[str]],
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    combination = [key for key in _FILTER_ORDER if key in requested]
    permitted = contract.get("permitted_combinations") or []
    if combination not in permitted:
        raise F2InvalidQuery("unsupported filter combination for measure")
    province = requested.get("province", [None])[0]
    source_region = requested.get("source_region", [None])[0]
    scope_key = _scope_key(province, source_region)
    scope = (topic.get("scopes") or {}).get(scope_key)
    if not isinstance(scope, dict):
        raise F2InvalidQuery("unsupported scope for measure")
    prepared = (scope.get("prepared_filters") or {}).get(measure_id)
    if not isinstance(prepared, dict):
        raise F2DataError("F2 prepared filter data is inconsistent")

    candidates = [prepared.get("default")] + list((prepared.get("selections") or {}).values())
    for selected in candidates:
        if not isinstance(selected, dict):
            continue
        result = selected.get("result")
        if not isinstance(result, dict):
            continue
        normalized = {
            key: [str(value) for value in values]
            for key, values in (result.get("requested_filters") or {}).items()
        }
        if normalized == requested:
            return scope_key, scope, selected
    raise F2InvalidQuery("unsupported or unknown filter value for measure")


def _normalize_label(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(text.split())


def _provenance(snapshot: RevisionSnapshot, artifact_keys: list[str]) -> dict[str, Any]:
    return {
        "release_date": snapshot.release_date,
        "source_ids": snapshot.source_ids,
        "artifact_keys": artifact_keys,
    }


def get_overview(*, province: str | None = None, revision: str | None = None) -> dict[str, Any]:
    snapshot = _active_revision()
    _require_revision(snapshot, revision)
    overview = _load_artifact(snapshot, "f2/overview")
    geography = _load_artifact(snapshot, "f2/geography")
    province = _validate_province(geography, province)
    scope_key = _scope_key(province, None)
    geographic_scope = geography["national"] if province is None else geography["provinces"][province]
    results = geographic_scope.get("results") or {}
    coverage = geographic_scope.get("coverage") or {}
    context_by_measure = {
        item.get("measure_id"): item
        for item in geographic_scope.get("context_results") or []
        if isinstance(item, dict)
    }

    def scoped_measure(item: dict[str, Any]) -> dict[str, Any]:
        measure_id = item.get("measure_id")
        response = {
            key: value
            for key, value in item.items()
            if key not in {"companions", "limitations"}
        }
        response["result"] = _localize_result(
            results.get(measure_id, item.get("result"))
        )
        if "unit" in response:
            response["unit"] = _thai_unit(response["unit"])
        response["coverage"] = coverage.get(measure_id, item.get("coverage"))
        response["limitations"] = item.get("limitations") or []
        if measure_id in context_by_measure:
            response["national_context"] = _localize_measure_payload(
                context_by_measure[measure_id]
            )
        response["companions"] = [scoped_measure(child) for child in item.get("companions") or []]
        return response

    headlines = [scoped_measure(item) for item in overview.get("headlines") or []]
    return {
        "revision": snapshot.revision,
        "release_id": snapshot.release_id,
        "scope": scope_key,
        "requested_scope": {
            "province": province,
            "province_name_th": geographic_scope.get("province_name_th"),
        },
        "availability": "available",
        "headlines": headlines,
        "limitations": overview.get("limitations") or [],
        "provenance": _provenance(snapshot, ["f2/overview", "f2/geography"]),
    }


def get_map(
    *,
    measure_id: str,
    category: str | None = None,
    source_level: str | None = None,
    component: str | None = None,
    source_dimension: str | None = None,
    revision: str | None = None,
) -> dict[str, Any]:
    snapshot = _active_revision()
    _require_revision(snapshot, revision)
    geography = _load_artifact(snapshot, "f2/geography")
    overview = _load_artifact(snapshot, "f2/overview")
    all_measures = {
        row.get("measure_id"): row
        for headline in overview.get("headlines") or []
        for row in [headline, *(headline.get("companions") or [])]
    }
    measure = all_measures.get(measure_id)
    if measure is None:
        raise F2NotFound("unknown F2 measure")
    if measure.get("map_availability") != "province":
        raise F2InvalidQuery("measure does not support a province map")
    topic_id = str(measure.get("topic_id") or "")
    topic, _, contract = _topic_and_contract(snapshot, topic_id, measure_id)
    non_geographic = _requested_filters(
        category=category,
        source_level=source_level,
        component=component,
        source_dimension=source_dimension,
    )
    cells = []
    for code, province_row in geography.get("provinces", {}).items():
        requested = {"province": [code], **non_geographic}
        _, scope, selected = _select_precomputed(topic, measure_id, contract, requested)
        cells.append(
            {
                "province_code": code,
                "province_name_th": province_row.get("province_name_th"),
                "result": _localize_result(selected["result"]),
                "coverage": (scope.get("coverage") or {}).get(measure_id),
            }
        )
    national_requested = non_geographic
    _, national_scope, national_selected = _select_precomputed(
        topic, measure_id, contract, national_requested
    )
    result = national_selected["result"]
    return {
        "revision": snapshot.revision,
        "release_id": snapshot.release_id,
        "measure_id": measure_id,
        "availability": result.get("availability", "unavailable"),
        "unit": _thai_unit(result.get("unit")),
        "coverage": (national_scope.get("coverage") or {}).get(measure_id),
        "legend": {
            "label_th": measure.get("label_th"),
            "meaning_th": measure.get("map_legend_th")
            or "สีแสดงค่าที่เผยแพร่ของมาตรวัดนี้ในแต่ละจังหวัด สีเทาหมายถึงไม่มีค่าที่รองรับ",
        },
        "filters": {
            "applied": result.get("applied_filters") or {},
            "choices": ((national_scope.get("prepared_filters") or {}).get(measure_id) or {}).get("choices", {}),
        },
        "cells": cells,
        "provenance": _provenance(snapshot, ["f2/geography", f"f2/topic/{topic_id}"]),
    }


def get_topic(
    topic_id: str,
    *,
    measure_id: str | None = None,
    province: str | None = None,
    category: str | None = None,
    source_level: str | None = None,
    source_region: str | None = None,
    component: str | None = None,
    source_dimension: str | None = None,
    q: str | None = None,
    limit: int = PAGE_DEFAULT,
    offset: int = 0,
    revision: str | None = None,
) -> dict[str, Any]:
    snapshot = _active_revision()
    _require_revision(snapshot, revision)
    geography = _load_artifact(snapshot, "f2/geography")
    province = _validate_province(geography, province)
    topic, measure_id, contract = _topic_and_contract(snapshot, topic_id, measure_id)
    requested = _requested_filters(
        province=province,
        category=category,
        source_level=source_level,
        source_region=source_region,
        component=component,
        source_dimension=source_dimension,
    )
    scope_key, scope, selected = _select_precomputed(topic, measure_id, contract, requested)
    result = selected["result"]
    detail_availability = contract.get("detail_availability")
    list_capability = "available" if detail_availability == "available" else "none"
    if list_capability == "none" and (q is not None or limit != PAGE_DEFAULT or offset != 0):
        raise F2InvalidQuery("list and search parameters are not supported for this measure")

    query = q or ""
    if len(query) > QUERY_MAX:
        raise F2InvalidQuery("q must not exceed 200 characters")
    if limit < 1 or limit > PAGE_MAX or offset < 0:
        raise F2InvalidQuery("invalid paging parameters")

    item_ids: list[str] = []
    if list_capability == "available":
        selected_ids = selected.get("item_ids")
        if selected_ids is None:
            selected_ids = (
                (topic.get("item_ids_by_measure_and_scope") or {})
                .get(measure_id, {})
                .get(scope_key, [])
            )
        if not isinstance(selected_ids, list):
            raise F2DataError("F2 item index is inconsistent")
        item_ids = list(dict.fromkeys(str(item_id) for item_id in selected_ids))

    compact_items = topic.get("items_by_id") or {}
    normalized_query = _normalize_label(query)
    matched_ids = [
        item_id
        for item_id in item_ids
        if not normalized_query
        or normalized_query in _normalize_label((compact_items.get(item_id) or {}).get("label"))
    ]
    page_ids = matched_ids[offset : offset + limit]
    page = []
    for item_id in page_ids:
        compact = compact_items.get(item_id)
        if not isinstance(compact, dict):
            continue
        province_names = [
            geography["provinces"][code]["province_name_th"]
            for code in compact.get("province_codes") or []
            if code in geography.get("provinces", {})
        ]
        page.append(
            {
                "entity_id": item_id,
                **compact,
                "province_names_th": province_names,
            }
        )
    source_region_results: list[dict[str, Any]] = []
    if province is None and "source_region" in (contract.get("supported_filters") or []):
        national_prepared = (
            ((topic.get("scopes") or {}).get("national") or {})
            .get("prepared_filters", {})
            .get(measure_id, {})
        )
        region_choices = (national_prepared.get("choices") or {}).get("source_region") or []
        for choice in region_choices:
            if not isinstance(choice, dict) or not choice.get("id"):
                continue
            region_requested = {
                key: values
                for key, values in requested.items()
                if key not in {"province", "source_region"}
            }
            region_requested["source_region"] = [str(choice["id"])]
            _, _, region_selection = _select_precomputed(
                topic, measure_id, contract, region_requested
            )
            source_region_results.append(
                {
                    "source_region_id": choice["id"],
                    "label_th": choice.get("label_th") or choice["id"],
                    "result": _localize_result(region_selection["result"]),
                }
            )
    return {
        "revision": snapshot.revision,
        "release_id": snapshot.release_id,
        "topic_id": topic.get("topic_id"),
        "measure_id": measure_id,
        "scope": scope_key,
        "availability": result.get("availability", "unavailable"),
        "result": _localize_result(result),
        "filter_contract": contract,
        "filters": {
            "requested": requested,
            "applied": result.get("applied_filters") or {},
            "choices": ((scope.get("prepared_filters") or {}).get(measure_id) or {}).get("choices", {}),
        },
        "coverage": (scope.get("coverage") or {}).get(measure_id),
        "context_results": [
            _localize_measure_payload(item)
            for item in scope.get("context_results") or []
        ],
        "sources": topic.get("sources") or [],
        "limitations": topic.get("limitations") or [],
        "source_region_results": source_region_results,
        "list": {
            "capability": list_capability,
            "scoped_item_count": len(item_ids),
            "matching_item_count": len(matched_ids),
            "offset": offset,
            "limit": limit,
            "returned_count": len(page),
            "items": page,
        },
        "provenance": _provenance(snapshot, [f"f2/topic/{topic.get('topic_id')}"]),
    }


def get_detail(
    topic_id: str,
    entity_id: str,
    *,
    measure_id: str,
    province: str | None = None,
    category: str | None = None,
    source_level: str | None = None,
    source_region: str | None = None,
    component: str | None = None,
    source_dimension: str | None = None,
    revision: str | None = None,
) -> dict[str, Any]:
    topic_response = get_topic(
        topic_id,
        measure_id=measure_id,
        province=province,
        category=category,
        source_level=source_level,
        source_region=source_region,
        component=component,
        source_dimension=source_dimension,
        limit=PAGE_MAX,
        revision=revision,
    )
    if topic_response["list"]["capability"] != "available":
        raise F2NotFound("measure has no public detail capability")

    snapshot = _active_revision()
    topic = _load_artifact(snapshot, f"f2/topic/{topic_id.strip().lower()}")
    requested = (topic_response.get("filters") or {}).get("requested") or {}
    contract = (topic.get("filter_contracts") or {})[measure_id]
    _, _, selected = _select_precomputed(topic, measure_id, contract, requested)
    item_ids = selected.get("item_ids")
    if item_ids is None:
        item_ids = (
            (topic.get("item_ids_by_measure_and_scope") or {})
            .get(measure_id, {})
            .get(topic_response["scope"], [])
        )
    if entity_id not in item_ids:
        raise F2NotFound("detail is not a member of the requested measure and scope")

    artifact_key = (topic.get("detail_artifacts") or {}).get(entity_id)
    artifact_keys = [f"f2/topic/{topic_id.strip().lower()}"]
    if artifact_key is None:
        details = topic.get("details_by_id") or {}
    else:
        if artifact_key not in snapshot.files:
            raise F2DataError("F2 detail mapping points outside the active revision")
        shard = _load_artifact(snapshot, artifact_key)
        details = shard.get("details_by_id") or {}
        artifact_keys.append(artifact_key)
    detail = details.get(entity_id)
    if not isinstance(detail, dict):
        raise F2DataError("admitted F2 detail is missing from its declared artifact")
    return {
        "revision": snapshot.revision,
        "release_id": snapshot.release_id,
        "topic_id": topic.get("topic_id"),
        "measure_id": measure_id,
        "scope": topic_response["scope"],
        "availability": "available",
        "detail": detail,
        "provenance": {
            **_provenance(snapshot, artifact_keys),
            "sources": topic.get("sources") or [],
        },
    }


def variant_etag(revision: str, route: str, parameters: dict[str, Any]) -> str:
    canonical = json.dumps(
        [revision, route, sorted((key, value) for key, value in parameters.items() if value is not None)],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return f'"{hashlib.sha256(canonical).hexdigest()}"'

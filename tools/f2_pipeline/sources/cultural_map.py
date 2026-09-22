"""Pure, source-local normalization for the Cultural Map K12 slice."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..common import normalize, stable_id
from ..geography import ThaiGeography

DATASET_KEYS = ("map_inspiration", "products", "activities", "recreation", "team")


def _fail(message: str) -> None:
    raise ValueError(f"Cultural Map input contract: {message}")


def _source_key(dataset: str, external_id: Any) -> str:
    return f"{dataset}:{external_id}"


def _records(capture: Any, dataset: str) -> list[dict[str, Any]]:
    if isinstance(capture, list):
        records = capture
    elif isinstance(capture, dict):
        data = capture.get("data")
        records = data.get("records") if isinstance(data, dict) else capture.get("records")
    else:
        records = None
    if not isinstance(records, list):
        _fail(f"{dataset} must be a capture envelope with data.records")
    if not all(isinstance(record, dict) for record in records):
        _fail(f"{dataset} has a non-object record")
    return records


def _metadata(metadata: dict[str, Any], dataset: str) -> dict[str, Any]:
    value = metadata.get(dataset)
    if not isinstance(value, dict):
        _fail(f"missing input metadata for {dataset}")
    missing = [key for key in ("sha256", "captured_at", "source_id", "run_id", "file") if not value.get(key)]
    if missing:
        _fail(f"metadata for {dataset} is missing {', '.join(missing)}")
    return value


def _identity_config(reviews: dict[str, Any]) -> dict[str, Any]:
    identity = reviews.get("subject_identity", reviews)
    if not isinstance(identity, dict):
        _fail("subject_identity review must be an object")
    return identity


def _groups(value: Any, label: str) -> list[list[str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        _fail(f"{label} must be a list")
    groups: list[list[str]] = []
    for index, group in enumerate(value):
        if not isinstance(group, list) or len(group) < 2:
            _fail(f"{label}[{index}] must contain at least two source IDs")
        values = [str(item) for item in group]
        if len(set(values)) != len(values):
            _fail(f"{label}[{index}] repeats a source ID")
        groups.append(values)
    return groups


class _Components:
    """Component union which checks cannot-links across complete components."""

    def __init__(self, keys: list[str], cannot: set[frozenset[str]]):
        self.parent = {key: key for key in keys}
        self.members = {key: {key} for key in keys}
        self.cannot = cannot

    def find(self, key: str) -> str:
        while self.parent[key] != key:
            self.parent[key] = self.parent[self.parent[key]]
            key = self.parent[key]
        return key

    def merge(self, left: str, right: str) -> str:
        left, right = self.find(left), self.find(right)
        if left == right:
            return "already_linked"
        if any(frozenset((a, b)) in self.cannot for a in self.members[left] for b in self.members[right]):
            return "blocked_cannot_link"
        left, right = sorted((left, right))
        self.parent[right] = left
        self.members[left] |= self.members.pop(right)
        return "merged"


def _review_groups(identity: dict[str, Any], modern: str, legacy: str) -> list[list[str]]:
    return _groups(identity.get(modern, identity.get(legacy)), modern)


def _location(row: dict[str, Any], geography: ThaiGeography) -> dict[str, Any]:
    data = row.get("data")
    location = data.get("location") if isinstance(data, dict) else None
    if not isinstance(location, dict):
        _fail(f"map listing {row.get('external_id')!r} lacks data.location")
    admin = location.get("administrative")
    if not isinstance(admin, dict) or not isinstance(admin.get("province"), dict):
        _fail(f"map listing {row.get('external_id')!r} lacks administrative province")
    province, district, subdistrict = admin["province"], admin.get("amphure"), admin.get("tambon")
    if not isinstance(province.get("name_th"), str) or not province["name_th"].strip():
        _fail(f"map listing {row.get('external_id')!r} lacks province name_th")
    district_name = district.get("name_th") if isinstance(district, dict) else None
    resolved = geography.resolve(province["name_th"], district_name)
    if not isinstance(resolved, dict):
        _fail("ThaiGeography.resolve must return a dictionary")
    source_province_code = str(province.get("code") or "")
    source_district_code = str(district.get("code") or "") if isinstance(district, dict) else ""
    source_subdistrict_code = str(subdistrict.get("code") or "") if isinstance(subdistrict, dict) else ""
    conflicts: list[str] = []
    if resolved.get("province_code") and source_province_code != str(resolved["province_code"]):
        conflicts.append("source province code differs from pinned reference")
    if isinstance(district, dict) and resolved.get("district_code") and source_district_code != str(resolved["district_code"]):
        conflicts.append("source district code differs from pinned reference")
    subdistrict_match = None
    if isinstance(subdistrict, dict):
        reference_subdistricts = getattr(geography, "subdistricts", [])
        if not isinstance(reference_subdistricts, list):
            _fail("ThaiGeography.subdistricts must be a list")
        candidates = [
            value for value in reference_subdistricts
            if isinstance(value, dict)
            and value.get("subdistrictNameTh") == subdistrict.get("name_th")
            and str(value.get("districtCode")) == str(resolved.get("district_code") or "")
        ]
        if len(candidates) == 1:
            subdistrict_match = candidates[0]
        source_code_matches = [
            value for value in reference_subdistricts
            if isinstance(value, dict)
            and str(value.get("subdistrictCode")) == source_subdistrict_code
            and str(value.get("provinceCode")) == source_province_code
            and value.get("subdistrictNameTh") == subdistrict.get("name_th")
        ]
        if source_subdistrict_code and not source_code_matches:
            conflicts.append("source subdistrict code/name does not validate together")
    status = "unresolved_geography" if not resolved.get("province_code") else ("source_hierarchy_conflict" if conflicts else ("province_only_source" if not district else "source_hierarchy_match"))
    coordinates = location.get("coordinates") if isinstance(location.get("coordinates"), dict) else {}
    return {
        "province_raw": province.get("name_th"), "district_raw": district_name,
        "subdistrict_raw": subdistrict.get("name_th") if isinstance(subdistrict, dict) else None,
        "province_normalized": resolved.get("province_normalized", province.get("name_th")),
        "province_code": str(resolved.get("province_code") or ""),
        "district_normalized": resolved.get("district_normalized", district_name or ""),
        "district_code": str(resolved.get("district_code") or ""),
        "subdistrict_normalized": subdistrict_match["subdistrictNameTh"] if subdistrict_match else resolved.get("subdistrict_normalized", ""),
        "subdistrict_code": str(subdistrict_match["subdistrictCode"]) if subdistrict_match else str(resolved.get("subdistrict_code") or ""),
        "source_mapping_methods_json": {"province": province.get("mapping_method"), "district": district.get("mapping_method") if isinstance(district, dict) else None, "subdistrict": subdistrict.get("mapping_method") if isinstance(subdistrict, dict) else None},
        "latitude": coordinates.get("latitude"), "longitude": coordinates.get("longitude"),
        "postal_code_raw": location.get("postal_code"), "status": status, "conflicts_json": conflicts,
        "correction_reason": resolved.get("correction_reason", ""), "reference_version": getattr(geography, "reference_version", ""),
        "source_admin_json": admin, "address_raw": location.get("address_raw"),
    }


def _category_rows(record: dict[str, Any], subject_id: str, observation_id: str, key: str) -> list[dict[str, Any]]:
    data = record.get("data")
    classification = data.get("classification") if isinstance(data, dict) else None
    primary = classification.get("primary_category") if isinstance(classification, dict) else None
    if not isinstance(primary, dict) or not primary.get("code"):
        _fail(f"map listing {record.get('external_id')!r} lacks primary category")
    categories = [("primary", primary, "data/classification/primary_category")]
    additional = classification.get("additional_categories") or []
    if not isinstance(additional, list):
        _fail(f"map listing {record.get('external_id')!r} has invalid additional categories")
    categories.extend(("additional", value, f"data/classification/additional_categories/{index}") for index, value in enumerate(additional))
    result = []
    for ordinal, (kind, category, locator) in enumerate(categories):
        if not isinstance(category, dict) or not category.get("code"):
            _fail(f"map listing {record.get('external_id')!r} has category without code")
        result.append({"category_assertion_id": stable_id("cultural_map_category", key, kind, ordinal), "subject_id": subject_id, "observation_id": observation_id, "source_key": key, "category_kind": kind, "category_code": str(category["code"]), "category_name_en": category.get("name_en"), "category_name_th": category.get("name_th"), "source_locator": locator})
    return result


def build_tables(datasets: dict[str, dict], reviews: dict, geography: ThaiGeography, input_metadata: dict[str, dict]) -> dict[str, list[dict]]:
    """Build relational Cultural Map tables without reading files or mutable globals.

    Only map-inspiration records create K12 subjects; every record in all five
    captures creates a source observation so ignored domains remain auditable.
    """
    if set(datasets) != set(DATASET_KEYS):
        _fail(f"datasets must be exactly {', '.join(DATASET_KEYS)}")
    if not isinstance(reviews, dict):
        _fail("reviews must be an object")
    tables: dict[str, list[dict]] = {name: [] for name in ("source_files", "source_observations", "mapped_subjects", "mapped_listing_observations", "category_assertions", "mapped_locations", "mapped_narrative_evidence", "mapped_media", "date_assertions", "identity_decisions", "review_cases")}
    records_by_dataset = {dataset: _records(datasets[dataset], dataset) for dataset in DATASET_KEYS}
    observations: dict[str, str] = {}
    map_by_key: dict[str, dict[str, Any]] = {}
    for dataset in DATASET_KEYS:
        metadata = _metadata(input_metadata, dataset)
        records = records_by_dataset[dataset]
        seen: set[str] = set()
        tables["source_files"].append({"dataset": dataset, "file": metadata["file"], "json_sha256": metadata["sha256"], "record_count": len(records), "source_id": metadata["source_id"], "run_id": metadata["run_id"], "captured_at": metadata["captured_at"]})
        for index, record in enumerate(records):
            if "external_id" not in record or record["external_id"] in (None, ""):
                _fail(f"{dataset} record {index} lacks external_id")
            external_id = str(record["external_id"])
            if external_id in seen:
                _fail(f"duplicate source ID in {dataset}: {external_id}")
            seen.add(external_id)
            if dataset == "map_inspiration" and not normalize(record.get("title")):
                _fail(f"map listing {external_id!r} lacks title")
            key = _source_key(dataset, external_id)
            observation_id = stable_id("cultural_map_obs", metadata["source_id"], dataset, external_id)
            observations[key] = observation_id
            tables["source_observations"].append({"observation_id": observation_id, "canonical_source_id": metadata["source_id"], "originating_system": metadata.get("originating_system", metadata["source_id"]), "dataset": dataset, "source_id": external_id, "source_key": key, "raw_file": metadata["file"], "row_locator": f"data/records/{index}", "file_sha256": metadata["sha256"], "captured_at": metadata["captured_at"], "run_id": metadata["run_id"], "validation_warnings_json": record.get("validation_warnings", []), "disposition": "retained_with_lineage" if dataset == "map_inspiration" else "provenance_only_in_k12_slice"})
            if dataset == "map_inspiration":
                map_by_key[key] = record
    review_source = reviews.get("source")
    if review_source is not None:
        if not isinstance(review_source, dict) or not isinstance(review_source.get("validation"), dict):
            _fail("review source pin must contain validation metadata")
        pinned = review_source["validation"]
        map_metadata = input_metadata["map_inspiration"]
        if review_source.get("source_id") != map_metadata["source_id"] or review_source.get("run_id") != map_metadata["run_id"]:
            _fail("review source pin does not match map_inspiration source or run")
        if pinned.get("capture_sha256") != map_metadata["sha256"] or pinned.get("record_count") != len(records_by_dataset["map_inspiration"]):
            _fail("review source pin does not match map_inspiration capture")
    location_decisions = reviews.get("location_decisions")
    if location_decisions is not None:
        if not isinstance(location_decisions, dict) or not isinstance(location_decisions.get("overrides", []), list):
            _fail("location_decisions must contain an overrides list")
        if location_decisions["overrides"]:
            _fail("K12 source mapping does not permit location overrides")
    identity = _identity_config(reviews)
    map_keys = sorted(map_by_key)
    map_ids = {key.rsplit(":", 1)[1] for key in map_keys}
    merges = _review_groups(identity, "reviewed_merges", "reviewed_subject_merges")
    cannot_groups = _review_groups(identity, "cannot_links", "subject_cannot_links")
    unresolved = _review_groups(identity, "unresolved_candidates", "reviewed_unresolved_subject_candidates")
    separations = _review_groups(identity, "separations", "reviewed_subject_separations")
    def keys_for(group: list[str], label: str) -> list[str]:
        unknown = set(group) - map_ids
        if unknown:
            _fail(f"{label} references unknown map source IDs: {sorted(unknown)}")
        return [_source_key("map_inspiration", value) for value in group]
    candidate_reviews = identity.get("candidate_reviews", [])
    if not isinstance(candidate_reviews, list):
        _fail("candidate_reviews must be a list")
    merge_sets = {frozenset(group) for group in merges}
    separation_sets = {frozenset(group) for group in separations}
    unresolved_sets = {frozenset(group) for group in unresolved}
    cannot_sets = {frozenset(group) for group in cannot_groups}
    for index, candidate in enumerate(candidate_reviews):
        if not isinstance(candidate, dict) or not isinstance(candidate.get("source_ids"), list):
            _fail(f"candidate_reviews[{index}] lacks source_ids")
        source_ids = [str(value) for value in candidate["source_ids"]]
        if len(source_ids) < 2 or len(set(source_ids)) != len(source_ids):
            _fail(f"candidate_reviews[{index}] has invalid source_ids")
        keys_for(source_ids, f"candidate_reviews[{index}]")
        if not isinstance(candidate.get("reason"), str) or not candidate["reason"].strip():
            _fail(f"candidate_reviews[{index}] lacks reason")
        disposition, source_set = candidate.get("disposition"), frozenset(source_ids)
        if disposition == "merge" and source_set not in merge_sets:
            _fail(f"candidate_reviews[{index}] merge is not materialized in reviewed_merges")
        if disposition == "separate" and source_set not in separation_sets:
            _fail(f"candidate_reviews[{index}] separation is not materialized in separations")
        if disposition == "unresolved" and source_set not in unresolved_sets:
            _fail(f"candidate_reviews[{index}] unresolved group is not materialized")
        if disposition == "partial_merge":
            partial_merges = _groups(candidate.get("partial_merges"), f"candidate_reviews[{index}].partial_merges")
            raw_partitions = candidate.get("separate_components")
            if not isinstance(raw_partitions, list) or not all(isinstance(group, list) and group for group in raw_partitions):
                _fail(f"candidate_reviews[{index}].separate_components must be non-empty groups")
            partitions = [[str(value) for value in group] for group in raw_partitions]
            if {value for group in partitions for value in group} != set(source_ids):
                _fail(f"candidate_reviews[{index}] partial merge does not partition source_ids")
            if not all(frozenset(group) in merge_sets for group in partial_merges):
                _fail(f"candidate_reviews[{index}] partial merge is not materialized in reviewed_merges")
            for offset, left_group in enumerate(partitions):
                for right_group in partitions[offset + 1:]:
                    for left in left_group:
                        for right in right_group:
                            if frozenset((left, right)) not in cannot_sets:
                                _fail(f"candidate_reviews[{index}] lacks partial-merge cannot-link")
        elif disposition not in {"merge", "separate", "unresolved"}:
            _fail(f"candidate_reviews[{index}] has unknown disposition")
    cannot: set[frozenset[str]] = set()
    for pair in cannot_groups:
        if len(pair) != 2:
            _fail("cannot_links entries must have exactly two source IDs")
        cannot.add(frozenset(keys_for(pair, "cannot_links")))
    for label, groups in (("separations", separations), ("unresolved_candidates", unresolved)):
        for group in groups:
            keys = keys_for(group, label)
            cannot.update(frozenset((left, right)) for offset, left in enumerate(keys) for right in keys[offset + 1:])
    unresolved_keys = {key for group in unresolved for key in keys_for(group, "unresolved_candidates")}
    components = _Components(map_keys, cannot)
    for group in merges:
        keys = keys_for(group, "reviewed_merges")
        for left, right in zip(keys, keys[1:]):
            outcome = components.merge(left, right)
            if outcome != "merged":
                _fail(f"reviewed merge {group} is {outcome}; cannot-links prevent unsafe transitive merging")
        tables["identity_decisions"].append({"decision_id": stable_id("cultural_map_decision", "merge", keys), "namespace": "mapped_subject", "candidate_group_id": "reviewed_merge", "source_keys_json": keys, "left_source_key": keys[0], "right_source_key": keys[1], "rule": "reviewed_source_subject_identity", "outcome": "supported_merge", "status": "resolved_by_review", "title_or_name": " / ".join(str(map_by_key[key].get("title", "")) for key in keys), "review_evidence_json": {"decision_source": "review input"}, "evidence_observation_ids_json": [observations[key] for key in keys]})
    for label, groups, outcome, status in (("cannot_link", cannot_groups + separations, "cannot_link", "resolved_separate"), ("unresolved", unresolved, "retained_unresolved_candidate", "unresolved")):
        for group in groups:
            keys = keys_for(group, label)
            tables["identity_decisions"].append({"decision_id": stable_id("cultural_map_decision", label, keys), "namespace": "mapped_subject", "candidate_group_id": label, "source_keys_json": keys, "left_source_key": keys[0], "right_source_key": keys[1], "rule": "reviewed_cannot_link" if label == "cannot_link" else "reviewed_insufficient_identity_evidence", "outcome": outcome, "status": status, "title_or_name": " / ".join(str(map_by_key[key].get("title", "")) for key in keys), "review_evidence_json": {"decision_source": "review input"}, "evidence_observation_ids_json": [observations[key] for key in keys]})
    subject_for_key: dict[str, str] = {}
    for root, members in sorted(components.members.items()):
        subject_id = stable_id("cultural_map_subject", root)
        for key in members:
            subject_for_key[key] = subject_id
        rows = [map_by_key[key] for key in sorted(members)]
        primary_codes = sorted({str(row["data"]["classification"]["primary_category"]["code"]) for row in rows if isinstance(row.get("data"), dict) and isinstance(row["data"].get("classification"), dict) and isinstance(row["data"]["classification"].get("primary_category"), dict) and row["data"]["classification"]["primary_category"].get("code")})
        tables["mapped_subjects"].append({"subject_id": subject_id, "source_keys_json": sorted(members), "source_ids_json": sorted(key.rsplit(":", 1)[1] for key in members), "display_title": sorted(normalize(row.get("title")) for row in rows)[0], "aliases_json": sorted({normalize(row.get("title")) for row in rows}), "identity_status": "unresolved_possible_duplicate" if members & unresolved_keys else ("supported_reviewed_merge" if len(members) > 1 else "source_listing_identity"), "k12_eligible": True, "cultural_area_eligible": "CS" in primary_codes, "primary_category_codes_json": primary_codes, "province_codes_json": [], "coordinate_conflict_status": "preserved_per_listing"})
    locations_by_subject: dict[str, set[str]] = defaultdict(set)
    for key, record in sorted(map_by_key.items()):
        subject_id, observation_id = subject_for_key[key], observations[key]
        data = record.get("data")
        if not isinstance(data, dict):
            _fail(f"map listing {record.get('external_id')!r} lacks data object")
        categories = _category_rows(record, subject_id, observation_id, key)
        tables["category_assertions"].extend(categories)
        classification = data["classification"]
        primary = classification["primary_category"]
        tables["mapped_listing_observations"].append({"listing_id": stable_id("cultural_map_listing", key), "subject_id": subject_id, "observation_id": observation_id, "source_key": key, "external_id": str(record["external_id"]), "title_raw": record.get("title"), "title_normalized": normalize(record.get("title")), "name_th_raw": (data.get("names") or {}).get("th"), "name_en_raw": (data.get("names") or {}).get("en"), "primary_category_code": str(primary["code"]), "additional_category_codes_json": [str(value["code"]) for value in classification.get("additional_categories") or []], "cultural_type_code": (classification.get("cultural_type") or {}).get("code"), "page_roles_json": data.get("page_roles", []), "record_code_raw": (data.get("identifiers") or {}).get("record_code"), "legacy_record_code_raw": (data.get("identifiers") or {}).get("legacy_record_code"), "dates_json": data.get("dates"), "description_json": data.get("description"), "funding_json": data.get("funding"), "assessment_json": data.get("assessment"), "people_summary_json": data.get("people"), "location_source_json": data.get("location"), "metrics_json": data.get("metrics"), "validation_warnings_json": record.get("validation_warnings", []), "source_url": record.get("source_url"), "discovered_from_json": record.get("discovered_from", [])})
        location = _location(record, geography)
        locations_by_subject[subject_id].add(location["province_code"])
        tables["mapped_locations"].append({"location_id": stable_id("cultural_map_location", key), "subject_id": subject_id, "observation_id": observation_id, "source_key": key, "location_role": "mapped_subject_location", **location})
        description = data.get("description") or {}
        if not isinstance(description, dict):
            _fail(f"map listing {record.get('external_id')!r} has invalid description")
        for field_name, value in description.items():
            if value is not None:
                tables["mapped_narrative_evidence"].append({"evidence_id": stable_id("cultural_map_narrative", key, field_name), "subject_id": subject_id, "observation_id": observation_id, "source_key": key, "field_name": field_name, "text": normalize(value), "source_locator": f"data/description/{field_name}", "status": "source_text_preserved"})
        dates = data.get("dates") or {}
        if not isinstance(dates, dict):
            _fail(f"map listing {record.get('external_id')!r} has invalid dates")
        for date_role, raw_value in dates.items():
            tables["date_assertions"].append({"date_assertion_id": stable_id("cultural_map_date", key, date_role), "subject_id": subject_id, "observation_id": observation_id, "source_key": key, "date_role": date_role, "raw_value": raw_value, "parsed_iso": "", "parse_status": "source_value_preserved", "source_locator": f"data/dates/{date_role}"})
        media = data.get("media") or {}
        if not isinstance(media, dict):
            _fail(f"map listing {record.get('external_id')!r} has invalid media")
        for kind in ("images", "clips", "documents", "links", "narration_links"):
            values = media.get(kind, [])
            if not isinstance(values, list):
                _fail(f"map listing {record.get('external_id')!r} has non-list media {kind}")
            for ordinal, value in enumerate(values):
                tables["mapped_media"].append({"media_id": stable_id("cultural_map_media", key, kind, ordinal), "subject_id": subject_id, "observation_id": observation_id, "source_key": key, "media_kind": kind[:-1], "ordinal": ordinal, "url_or_value": value.get("url") if isinstance(value, dict) else value, "caption": value.get("caption") if isinstance(value, dict) else None, "fetched_raw": value.get("fetched") if isinstance(value, dict) else None, "status": "reference_only_content_not_inspected", "source_locator": f"data/media/{kind}/{ordinal}"})
        unparsed = media.get("unparsed_values", {})
        if not isinstance(unparsed, dict):
            _fail(f"map listing {record.get('external_id')!r} has invalid unparsed media")
        for kind, value in sorted(unparsed.items()):
            tables["mapped_media"].append({"media_id": stable_id("cultural_map_media", key, "unparsed", kind), "subject_id": subject_id, "observation_id": observation_id, "source_key": key, "media_kind": f"unparsed_{kind}", "ordinal": 0, "url_or_value": value, "caption": None, "fetched_raw": None, "status": "raw_unparsed_value", "source_locator": f"data/media/unparsed_values/{kind}"})
    for subject in tables["mapped_subjects"]:
        subject["province_codes_json"] = sorted(code for code in locations_by_subject[subject["subject_id"]] if code)
    return {name: rows for name, rows in tables.items()}

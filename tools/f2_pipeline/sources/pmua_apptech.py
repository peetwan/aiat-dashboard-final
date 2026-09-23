"""Build the source-local PMUA AppTech pilot.

The cleaner keeps product-detail rows, map memberships, directory assertions,
station links, and dashboard aggregates at their source grains. It applies only
the reviewed within-PMUA identity decisions in the PMUA configuration. No
cross-source identity merge or final KPI consolidation is performed here.
Markdown documentation is maintained separately and is never overwritten by a build.
"""

import difflib
import json
import re
from collections import Counter, defaultdict

from ..common import (
    Components,
    matching_name,
    normalize,
    readable,
    safe_text,
    stable_id,
)

DATASET_KEYS = (
    "family_2025",
    "family_2026",
    "family_all",
    "innovation_map_all",
    "innovators_2025",
    "innovators_2026",
    "innovators_all",
    "products",
    "researchers",
    "stations",
    "universities",
)

RAW_FILES = [
    "dashboards/family_2025.json",
    "dashboards/family_2026.json",
    "dashboards/family_all.json",
    "dashboards/innovation_map_all.json",
    "dashboards/innovators_2025.json",
    "dashboards/innovators_2026.json",
    "dashboards/innovators_all.json",
    "products.json",
    "researchers.json",
    "stations.json",
    "universities.json",
]

TABLE_COLUMNS = {
    "source_files": [
        "dataset",
        "file",
        "sha256",
        "row_count",
        "declared_record_count",
        "record_type",
        "captured_at",
        "run_id",
        "year_filter",
        "source_url",
        "envelope_json",
    ],
    "source_observations": [
        "observation_id",
        "dataset",
        "source_id",
        "source_key",
        "row_locator",
        "raw_file",
        "file_sha256",
        "captured_at",
        "run_id",
        "record_type",
        "scope_json",
        "disposition",
    ],
    "innovations": [
        "innovation_id",
        "display_name",
        "aliases_json",
        "source_ids_json",
        "source_observation_ids_json",
        "innovation_kind",
        "has_detail_record",
        "identity_status",
        "candidate_status",
        "readiness_conflict",
    ],
    "innovation_details": [
        "innovation_id",
        "observation_id",
        "source_key",
        "source_id",
        "title_raw",
        "title_normalized",
        "category_raw",
        "technology_type_raw",
        "trl_level",
        "trl_label_raw",
        "trl_explanation_raw",
        "researcher_source_id",
        "researcher_name_raw",
        "university_source_id",
        "university_name_raw",
        "detail_url",
        "price_raw",
        "price_thb",
        "production_capacity_raw",
        "tags_json",
        "target_groups_json",
    ],
    "description_sections": [
        "section_id",
        "innovation_id",
        "observation_id",
        "source_key",
        "section_index",
        "label_raw",
        "text_readable",
        "items_json",
    ],
    "narrative_evidence": [
        "evidence_id",
        "innovation_id",
        "observation_id",
        "source_key",
        "kind",
        "indicator_raw",
        "quantity_raw",
        "value_raw",
        "text_readable",
    ],
    "ip_assertions": [
        "ip_assertion_id",
        "innovation_id",
        "observation_id",
        "source_key",
        "ip_index",
        "label_raw",
        "value_raw",
        "identifier_status",
    ],
    "funding_assertions": [
        "funding_assertion_id",
        "innovation_id",
        "observation_id",
        "source_key",
        "funding_index",
        "source_raw",
        "type_raw",
        "year_raw",
    ],
    "researchers": [
        "researcher_id",
        "display_name",
        "name_normalized",
        "source_ids_json",
        "source_observation_ids_json",
        "identity_status",
    ],
    "researcher_profiles": [
        "researcher_id",
        "source_id",
        "observation_id",
        "name_raw",
        "name_normalized",
        "university_raw",
        "expertise_raw",
        "innovation_count",
        "profile_url",
        "identity_status",
    ],
    "researcher_assertions": [
        "assertion_id",
        "innovation_id",
        "observation_id",
        "source_key",
        "source_researcher_id",
        "embedded_name_raw",
        "researcher_id",
        "profile_name_raw",
        "profile_status",
    ],
    "researcher_identity_reviews": [
        "review_group_id",
        "source_ids_json",
        "names_json",
        "status",
        "reason",
        "affected_measure",
        "evidence_observation_ids_json",
    ],
    "person_identity_decisions": [
        "decision_id",
        "left_source_id",
        "left_source_key",
        "right_source_key",
        "left_name_raw",
        "left_role_evidence",
        "left_university_raw",
        "left_expertise_raw",
        "right_name_raw",
        "decision",
        "status",
        "reason",
        "evidence_observation_ids_json",
    ],
    "universities": [
        "university_id",
        "source_id",
        "observation_id",
        "name_raw",
        "stats_json",
        "profile_url",
        "identity_status",
    ],
    "university_assertions": [
        "assertion_id",
        "innovation_id",
        "observation_id",
        "source_key",
        "source_university_id",
        "name_raw",
        "university_id",
        "reference_status",
    ],
    "stations": [
        "station_id",
        "source_id",
        "observation_id",
        "title_raw",
        "organization_raw",
        "director_raw",
        "location_note_raw",
        "mission_raw",
        "goals_raw",
        "start_year_raw",
        "product_ids_json",
        "contact_field_names_json",
        "contact_present",
        "detail_url",
        "identity_status",
    ],
    "station_links": [
        "station_link_id",
        "station_id",
        "station_source_id",
        "station_observation_id",
        "product_source_id",
        "innovation_id",
        "source_locator",
        "link_status",
        "relationship",
    ],
    "map_area_items": [
        "map_item_id",
        "map_observation_id",
        "source_key",
        "source_id",
        "source_locator",
        "map_province_raw",
        "title_raw",
        "university_raw",
        "trl_raw",
        "trl_level",
        "areas_json",
        "innovation_id",
        "detail_join_status",
    ],
    "innovation_area_assertions": [
        "assertion_id",
        "innovation_id",
        "observation_id",
        "source_key",
        "source_kind",
        "source_locator",
        "area_index",
        "raw_area_json",
        "area_text_raw",
        "province_raw",
        "province_id_raw",
        "province_normalized",
        "province_code",
        "district_raw_json",
        "district_id_raw_json",
        "district_normalized_json",
        "district_code_json",
        "subdistrict_raw_json",
        "subdistrict_id_raw_json",
        "subdistrict_normalized_json",
        "subdistrict_code_json",
        "hierarchy_pairs_json",
        "resolution_status",
        "correction_reason",
    ],
    "readiness_assessments": [
        "assessment_id",
        "innovation_id",
        "observation_id",
        "source_key",
        "source_kind",
        "source_locator",
        "source_id",
        "scale",
        "assessment_context",
        "raw_level",
        "level",
        "label_raw",
        "qualifies",
        "basis",
    ],
    "readiness_conflicts": [
        "conflict_id",
        "innovation_id",
        "source_id",
        "province_raw",
        "detail_level",
        "map_level",
        "map_source_locator",
        "status",
    ],
    "identity_decisions": [
        "decision_id",
        "entity_type",
        "left_source_id",
        "right_source_id",
        "left_source_key",
        "right_source_key",
        "rule",
        "outcome",
        "status",
        "reason",
        "evidence_observation_ids_json",
    ],
    "review_cases": [
        "review_id",
        "case_type",
        "entity_type",
        "source_ids_json",
        "source_names_json",
        "external_source_ids_json",
        "status",
        "decision",
        "reason",
        "possible_impact",
        "affected_measures_json",
        "evidence_observation_ids_json",
    ],
    "innovation_identity_candidates": [
        "candidate_id",
        "source_ids_json",
        "titles_json",
        "discovery_signals_json",
        "review_state",
        "disposition",
        "matching_evidence",
        "meaningful_differences",
        "recommendation",
        "count_impact",
        "evidence_locators_json",
    ],
    "review_coverage": [
        "coverage_id",
        "task",
        "source_record_id",
        "source_ids_json",
        "review_state",
        "disposition",
        "evidence_locators_json",
        "reason",
        "affected_measures_json",
    ],
    "pending_cross_source_decisions": [
        "pending_id",
        "left_source",
        "left_source_id",
        "left_source_key",
        "left_innovation_id",
        "left_observation_id",
        "right_source",
        "right_source_key",
        "decision",
        "status",
        "reason",
    ],
    "aggregate_summaries": [
        "aggregate_id",
        "observation_id",
        "source_file",
        "dashboard",
        "entity_type",
        "scope_json",
        "year_filter",
        "reported_count_raw",
        "reported_count",
        "unit",
        "retrieved_at",
        "status",
    ],
    "aggregate_components": [
        "component_id",
        "aggregate_id",
        "observation_id",
        "row_index",
        "province_raw",
        "province_normalized",
        "province_code",
        "component_kind",
        "total_hh",
        "total_inno",
        "total_members",
        "total_gen",
        "gen_users",
        "districts_json",
        "business_types_json",
        "levels_json",
    ],
    "aggregate_metrics": [
        "metric_id",
        "aggregate_id",
        "observation_id",
        "metric",
        "value_raw",
        "value_thb",
        "unit",
        "interpretation",
        "eligible_for_k10",
    ],
    "measure_results": [
        "measure",
        "value",
        "unit",
        "scope",
        "status",
        "basis",
        "source_population",
        "note",
        "source_observation_ids_json",
    ],
    "measure_contributions": [
        "measure",
        "entity_id",
        "entity_type",
        "scope",
        "status",
        "evidence_observation_ids_json",
    ],
    "entity_observations": [
        "entity_id",
        "entity_type",
        "observation_id",
        "source_id",
        "source_locator",
        "relationship",
    ],
}

TABLE_GRAINS = {
    "source_files": "one row per in-scope raw JSON file",
    "source_observations": "one row per raw top-level record; nested map rows are children of the map dashboard observation",
    "innovations": "one source-local innovation identity after the reviewed within-PMUA component decisions",
    "innovation_details": "one products.json detail listing",
    "description_sections": "one ordered description section within one detail listing",
    "narrative_evidence": "one retained impact, outcome, ROI or SROI assertion within one detail listing",
    "ip_assertions": "one IP array item within one detail listing",
    "funding_assertions": "one funding-history item within one detail listing",
    "researchers": "one source-local researcher identity after reviewed profile merges",
    "researcher_profiles": "one original researcher profile with its own affiliation, expertise and reported counter",
    "researcher_assertions": "one product-to-researcher source assertion",
    "researcher_identity_reviews": "one reviewed researcher identity group and its recorded decision",
    "person_identity_decisions": "one historical cross-source person must-link, retained without merging the external person record",
    "universities": "one university profile; university 0 is not present here",
    "university_assertions": "one product-to-university source assertion",
    "stations": "one AppTech station profile",
    "station_links": "one station product_ids association",
    "map_area_items": "one nested innovation_map_all item",
    "innovation_area_assertions": "one declared detail area object or one map area string",
    "readiness_assessments": "one source-specific TRL assessment from a detail listing or map item",
    "readiness_conflicts": "one preserved map/detail TRL conflict assertion",
    "identity_decisions": "one reviewed merge or cannot-link enforcement record",
    "review_cases": "one candidate, unresolved reference, accepted treatment or quality case",
    "innovation_identity_candidates": "one connected source-local innovation candidate component discovered from deterministic title, technical-text or map-only signals",
    "review_coverage": "one required source record, reference, aggregate component or identity-candidate review task",
    "pending_cross_source_decisions": "one exported historical cross-source link pending a later source-merge stage",
    "aggregate_summaries": "one family or innovator dashboard snapshot",
    "aggregate_components": "one source-reported province component within an aggregate snapshot",
    "aggregate_metrics": "one source-reported economic metric or derived formula component",
    "measure_results": "one source-local measure result with its own scope and limitation",
    "measure_contributions": "one contributor entity for one source-local measure",
    "entity_observations": "one link from an entity or directory assertion to a source observation",
}


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def text(value):
    return normalize(value) if value is not None else ""


def int_or_none(value):
    if value is None or value == "":
        return None
    match = re.search(r"-?\d+", str(value))
    return int(match.group()) if match else None


def canonical_province(value):
    value = text(value)
    return {
        "Bangkok": "กรุงเทพมหานคร",
        "กรุงเทพฯ": "กรุงเทพมหานคร",
        "กรุงเทพ": "กรุงเทพมหานคร",
    }.get(value, value)


def canonical_identity_text(value):
    """Normalize harmless presentation differences for candidate discovery only."""
    return "".join(
        character for character in text(value).casefold() if character.isalnum()
    )


def _export_tables(tables):
    """Apply legacy CSV JSON-cell encoding without mutating source-local facts."""
    exported = dict(tables)
    if "innovation_area_assertions" in tables:
        exported["innovation_area_assertions"] = [
            dict(row) for row in tables["innovation_area_assertions"]
        ]
    for row in exported.get("innovation_area_assertions", []):
        if "raw_area_json" in row:
            row["raw_area_json"] = dump(row["raw_area_json"])
    return exported


class PMUAPilot:
    def __init__(self, datasets, reviews, geography, input_metadata):
        if set(datasets) != set(DATASET_KEYS):
            raise ValueError(
                f"PMUA AppTech input contract: datasets must be exactly {', '.join(DATASET_KEYS)}"
            )
        self.inputs = datasets
        self.config = reviews.get("reviewed_cases.json", reviews)
        self.geography = geography
        self.input_metadata = input_metadata
        self.tables = defaultdict(list)
        self.data = {}
        self.source_meta = {}
        self.observations = {}
        self.product_rows = {}
        self.product_obs = {}
        self.product_index_by_source = {}
        self.map_items = []
        self.innovation_ids = {}
        self.innovation_names = {}
        self.innovation_obs = defaultdict(list)
        self.entity_labels = {}
        self.validation_checks = []
        self.expected_findings = []
        self.unexpected_failures = []
        self.province_entities = set()
        self.aggregate_ids_by_file = {}
        self.province_by_code = {str(r["provinceCode"]): r for r in geography.provinces}
        self.district_by_code = {str(r["districtCode"]): r for r in geography.districts}
        self.subdistrict_by_code = {
            str(r["subdistrictCode"]): r for r in geography.subdistricts
        }

    def add(self, table, **row):
        self.tables[table].append(row)

    def source_observation(self, relative, index):
        return self.observations[relative, index]

    def source_key(self, dataset, source_id):
        return f"pmua_apptech/{dataset}:{source_id}"

    def ingest(self):
        for relative in RAW_FILES:
            dataset = relative[:-5].replace("dashboards/", "").removesuffix(".json")
            payload = self.inputs[dataset]
            metadata = self.input_metadata.get(dataset)
            if not isinstance(payload, dict) or not isinstance(metadata, dict):
                raise ValueError(
                    f"PMUA AppTech input contract: missing capture or metadata for {dataset}"
                )
            for key in (
                "source_id",
                "run_id",
                "file",
                "sha256",
                "size",
                "captured_at",
                "originating_system",
            ):
                if not metadata.get(key):
                    raise ValueError(
                        f"PMUA AppTech input contract: incomplete metadata for {dataset}"
                    )
            rows = payload.get("data")
            declared = payload.get("record_count")
            if isinstance(rows, list):
                if declared is not None and declared != len(rows):
                    raise ValueError(f"Declared count mismatch: {relative}")
            else:
                rows, declared = [payload], None
            self.data[relative] = rows
            self.source_meta[relative] = payload
            self.add(
                "source_files",
                dataset=dataset,
                file=metadata["file"],
                sha256=metadata["sha256"],
                row_count=len(rows),
                declared_record_count=declared,
                record_type=payload.get("record_type") or payload.get("dataset"),
                captured_at=metadata["captured_at"],
                run_id=metadata["run_id"],
                year_filter=payload.get("year_filter"),
                source_url=payload.get("source_url") or payload.get("source_base_url"),
                envelope_json={k: v for k, v in payload.items() if k != "data"},
            )
            for index, row in enumerate(rows):
                source_id = str(
                    row.get("record_id")
                    or row.get("source_key")
                    or row.get("dataset")
                    or f"row:{index}"
                )
                observation_id = stable_id(
                    "pmua_observation",
                    metadata["source_id"],
                    metadata["run_id"],
                    relative,
                    source_id,
                )
                self.observations[relative, index] = observation_id
                self.add(
                    "source_observations",
                    observation_id=observation_id,
                    dataset=dataset,
                    source_id=source_id,
                    source_key=self.source_key(dataset, source_id),
                    row_locator=f"evidence://{metadata['source_id']}/{metadata['run_id']}/{metadata['file']}#data/{index}"
                    if declared is not None
                    else f"evidence://{metadata['source_id']}/{metadata['run_id']}/{metadata['file']}#",
                    raw_file=metadata["file"],
                    file_sha256=metadata["sha256"],
                    captured_at=metadata["captured_at"],
                    run_id=metadata["run_id"],
                    record_type=row.get("record_type")
                    or payload.get("record_type")
                    or payload.get("dataset"),
                    scope_json={
                        "year_filter": payload.get("year_filter"),
                        "dashboard": payload.get("dashboard"),
                        "title": payload.get("title"),
                    },
                    disposition="retained_with_lineage",
                )
        self.product_rows = {str(r["record_id"]): r for r in self.data["products.json"]}
        self.product_obs = {
            source_id: self.source_observation("products.json", index)
            for index, source_id in enumerate(self.product_rows)
        }
        self.product_index_by_source = {
            str(row["record_id"]): index
            for index, row in enumerate(self.data["products.json"])
        }

    def add_review(
        self,
        case_type,
        source_ids,
        source_names,
        reason,
        impact,
        status="unresolved",
        decision="",
        external_source_ids=None,
        evidence_observation_ids=None,
        entity_type="innovation",
        affected_measures=None,
    ):
        source_ids = sorted({str(x) for x in source_ids})
        self.add(
            "review_cases",
            review_id=stable_id("pmua_review", case_type, source_ids),
            case_type=case_type,
            entity_type=entity_type,
            source_ids_json=source_ids,
            source_names_json=source_names,
            external_source_ids_json=sorted(
                {str(x) for x in (external_source_ids or [])}
            ),
            status=status,
            decision=decision,
            reason=reason,
            possible_impact=impact,
            affected_measures_json=affected_measures
            or ["K04", "broader_listed_innovations"],
            evidence_observation_ids_json=evidence_observation_ids or [],
        )

    def detail_identity(self):
        product_ids = sorted(self.product_rows)
        protected_cases = [
            *self.config["innovation_cannot_links"],
            *self.config["innovation_unresolved_links"],
        ]
        cannot = [(str(c["left"]), str(c["right"])) for c in protected_cases]
        if any(
            left not in self.product_rows or right not in self.product_rows
            for left, right in cannot
        ):
            raise AssertionError(
                "Reviewed PMUA cannot-link endpoint is absent from current products"
            )
        components = Components(product_ids, cannot)
        supported_by_id = {}
        for group in self.config["reviewed_merge_groups"]:
            ids = [str(x) for x in group["source_ids"]]
            if any(source_id not in self.product_rows for source_id in ids):
                raise AssertionError(f"Reviewed merge endpoint missing: {ids}")
            self.validate_merge_evidence(ids, group)
            for left, right in zip(ids, ids[1:]):
                outcome = components.merge(left, right)
                if outcome == "blocked_cannot_link":
                    raise AssertionError(f"Reviewed merge crosses cannot-link: {ids}")
                self.add(
                    "identity_decisions",
                    decision_id=stable_id("pmua_identity", left, right, group["rule"]),
                    entity_type="innovation",
                    left_source_id=left,
                    right_source_id=right,
                    left_source_key=self.source_key("products", left),
                    right_source_key=self.source_key("products", right),
                    rule=group["rule"],
                    outcome=outcome,
                    status="accepted_within_source_merge",
                    reason=group["reason"],
                    evidence_observation_ids_json=[
                        self.product_obs[left],
                        self.product_obs[right],
                    ],
                )
            for source_id in ids:
                supported_by_id[source_id] = group["rule"]

        map_payload = self.source_meta["dashboards/innovation_map_all.json"]
        map_only_rows = {}
        for province_rows in map_payload["prov_data"].values():
            for row in province_rows:
                source_id = str(row["prod_id"])
                if source_id not in self.product_rows:
                    map_only_rows.setdefault(source_id, row)
        map_observation_id = self.source_observation(
            "dashboards/innovation_map_all.json", 0
        )
        linked_map_ids = defaultdict(list)
        for link in self.config["map_only_identity_links"]:
            map_source_id = str(link["map_source_id"])
            detail_source_id = str(link["detail_source_id"])
            if (
                map_source_id not in map_only_rows
                or detail_source_id not in self.product_rows
            ):
                raise AssertionError(
                    f"Reviewed map-only identity endpoint missing: {link}"
                )
            expected_title = canonical_identity_text(
                self.product_rows[detail_source_id]["title"]
            )
            actual_title = canonical_identity_text(
                map_only_rows[map_source_id]["prod_name"]
            )
            if expected_title != actual_title:
                raise AssertionError(
                    f"Map-only title evidence differs for reviewed link {map_source_id}/{detail_source_id}"
                )
            linked_map_ids[components.find(detail_source_id)].append(map_source_id)
            self.add(
                "identity_decisions",
                decision_id=stable_id(
                    "pmua_identity_map", map_source_id, detail_source_id, link["rule"]
                ),
                entity_type="innovation",
                left_source_id=detail_source_id,
                right_source_id=map_source_id,
                left_source_key=self.source_key("products", detail_source_id),
                right_source_key=self.source_key("innovation_map_all", map_source_id),
                rule=link["rule"],
                outcome="linked_map_only_listing_to_detail_identity",
                status="accepted_within_source_merge",
                reason=link["reason"],
                evidence_observation_ids_json=[
                    self.product_obs[detail_source_id],
                    map_observation_id,
                ],
            )

        for case in self.config["innovation_cannot_links"]:
            left, right = str(case["left"]), str(case["right"])
            if components.find(left) == components.find(right):
                raise AssertionError(
                    f"Cannot-link was bridged by a supported component: {left}/{right}"
                )
            self.add(
                "identity_decisions",
                decision_id=stable_id("pmua_identity_cannot", left, right),
                entity_type="innovation",
                left_source_id=left,
                right_source_id=right,
                left_source_key=self.source_key("products", left),
                right_source_key=self.source_key("products", right),
                rule="reviewed_cannot_link",
                outcome="cannot_link_preserved",
                status="accepted_separation",
                reason=case["reason"],
                evidence_observation_ids_json=[
                    self.product_obs[left],
                    self.product_obs[right],
                ],
            )

        for case in self.config["innovation_unresolved_links"]:
            left, right = str(case["left"]), str(case["right"])
            if components.find(left) == components.find(right):
                raise AssertionError(
                    f"Reviewed uncertainty was bridged by a supported component: {left}/{right}"
                )
            self.add(
                "identity_decisions",
                decision_id=stable_id("pmua_identity_unresolved", left, right),
                entity_type="innovation",
                left_source_id=left,
                right_source_id=right,
                left_source_key=self.source_key("products", left),
                right_source_key=self.source_key("products", right),
                rule="reviewed_unresolved_identity_boundary",
                outcome="separate_pending_new_evidence",
                status="reviewed_unresolved",
                reason=case["reason"],
                evidence_observation_ids_json=[
                    self.product_obs[left],
                    self.product_obs[right],
                ],
            )

        self.detail_components = components
        self.supported_by_id = supported_by_id
        self.innovation_ids = {
            source_id: stable_id(
                "pmua_innovation", "detail", components.find(source_id)
            )
            for source_id in product_ids
        }
        for root, members in sorted(components.members.items()):
            detail_source_ids = sorted(members)
            map_source_ids = sorted(linked_map_ids.get(root, []))
            source_ids = sorted(detail_source_ids + map_source_ids)
            names = sorted(
                {
                    self.product_rows[source_id]["title"]
                    for source_id in detail_source_ids
                }
                | {
                    map_only_rows[source_id]["prod_name"]
                    for source_id in map_source_ids
                }
            )
            entity_id = self.innovation_ids[detail_source_ids[0]]
            for source_id in map_source_ids:
                self.innovation_ids[source_id] = entity_id
            self.innovation_names[entity_id] = names[0]
            self.innovation_obs[entity_id].extend(
                self.product_obs[source_id] for source_id in detail_source_ids
            )
            if map_source_ids:
                self.innovation_obs[entity_id].append(map_observation_id)
            self.entity_labels[entity_id] = names[0]
            self.add(
                "innovations",
                innovation_id=entity_id,
                display_name=normalize(names[0]),
                aliases_json=names,
                source_ids_json=source_ids,
                source_observation_ids_json=sorted(
                    {self.product_obs[source_id] for source_id in detail_source_ids}
                    | ({map_observation_id} if map_source_ids else set())
                ),
                innovation_kind="detail_listing",
                has_detail_record=True,
                identity_status="supported_source_local"
                if len(source_ids) > 1
                else "source_listing_provisional",
                candidate_status=(
                    "reviewed_supported_group"
                    if any(source_id in supported_by_id for source_id in source_ids)
                    else "single_detail_identity"
                ),
                readiness_conflict=False,
            )
        self.review_identity_candidates(map_only_rows)

    def validate_merge_evidence(self, ids, group):
        rule = group["rule"]
        rows = [self.product_rows[source_id] for source_id in ids]
        validators = {
            "reviewed_small_biomass_stove_mould_pair": self.validate_biomass_merge,
            "reviewed_small_finished_biomass_stove_pair": self.validate_biomass_merge,
            "reviewed_large_biomass_stove_mould_pair": self.validate_biomass_merge,
            "reviewed_large_finished_biomass_stove_pair": self.validate_biomass_merge,
            "prior_reviewed_atri_1_must_link": self.validate_atri_merge,
            "supported_pef_fish_processing_version_group": self.validate_pef_merge,
            "reviewed_technical_output_match": self.validate_reviewed_technical_output,
        }
        if rule not in validators:
            raise AssertionError(
                f"No evidence validator is configured for reviewed merge rule: {rule}"
            )
        if rule == "reviewed_technical_output_match":
            validators[rule](ids, rows, group)
        else:
            validators[rule](ids, rows)

    @staticmethod
    def member_description(row):
        return " ".join(
            text(section.get("text")) for section in row.get("description_sections", [])
        )

    @staticmethod
    def require_same_member_field(ids, rows, field_name, values):
        if len(set(values)) != 1:
            raise AssertionError(
                f"{field_name} evidence differs for reviewed group {ids}"
            )

    def validate_biomass_merge(self, ids, rows):
        self.require_same_member_field(
            ids, rows, "title", [normalize(row["title"]) for row in rows]
        )
        for source_id, row in zip(ids, rows):
            evidence = f"{row['title']} {self.member_description(row)}"
            missing = [
                marker for marker in ["ชีวมวล", "แก๊สซิฟิเคชัน"] if marker not in evidence
            ]
            if missing:
                raise AssertionError(
                    f"Biomass-stove evidence missing for member {source_id}: {missing}"
                )

    def validate_atri_merge(self, ids, rows):
        required_markers = ["ATRI#1", "แรงดันต่ำ", "100 ลิตร"]
        for source_id, row in zip(ids, rows):
            evidence = f"{row['title']} {self.member_description(row)}"
            missing = [marker for marker in required_markers if marker not in evidence]
            if missing:
                raise AssertionError(
                    f"ATRI required evidence missing for member {source_id}: {missing}"
                )

    def validate_pef_merge(self, ids, rows):
        self.require_same_member_field(
            ids, rows, "PEF title", [normalize(row["title"]) for row in rows]
        )
        required_markers = ["PEF chamber", "อิเล็กโตรโพเรชั่น", "ลดระยะเวลาหมัก"]
        for source_id, row in zip(ids, rows):
            if "PEF" not in row["title"]:
                raise AssertionError(
                    f"PEF title evidence missing for member {source_id}"
                )
            description = self.member_description(row)
            missing = [
                marker for marker in required_markers if marker not in description
            ]
            if missing:
                raise AssertionError(
                    f"PEF required evidence missing for member {source_id}: {missing}"
                )

    def validate_reviewed_technical_output(self, ids, rows, group):
        title_markers = group.get("required_title_markers", [])
        description_markers = group.get("required_description_markers", [])
        if not title_markers or not description_markers:
            raise AssertionError(
                f"Reviewed technical rule lacks required evidence: {ids}"
            )
        if (
            not group.get("allow_title_variants")
            and len({canonical_identity_text(row["title"]) for row in rows}) != 1
        ):
            raise AssertionError(
                f"Contradictory title/version evidence for reviewed technical group {ids}"
            )
        for source_id, row in zip(ids, rows):
            title_evidence = canonical_identity_text(row["title"])
            missing_titles = [
                marker
                for marker in title_markers
                if canonical_identity_text(marker) not in title_evidence
            ]
            description = canonical_identity_text(self.member_description(row))
            missing_descriptions = [
                marker
                for marker in description_markers
                if canonical_identity_text(marker) not in description
            ]
            if missing_titles or missing_descriptions:
                raise AssertionError(
                    "Reviewed technical evidence missing for member "
                    f"{source_id}: title={missing_titles}, description={missing_descriptions}"
                )

    def discover_identity_candidates(self, map_only_rows):
        """Discover a deterministic review queue; never infer a merge from a signal alone."""
        edges = defaultdict(set)

        def add_group(source_ids, signal):
            source_ids = sorted(source_ids)
            for index, left in enumerate(source_ids):
                for right in source_ids[index + 1 :]:
                    edges[left, right].add(signal)

        normalized_titles = defaultdict(list)
        canonical_titles = defaultdict(list)
        technical_texts = defaultdict(list)
        technical_prefixes = defaultdict(list)
        title_model_tokens = defaultdict(list)
        for source_id, row in self.product_rows.items():
            normalized_titles[normalize(row["title"])].append(source_id)
            canonical_titles[canonical_identity_text(row["title"])].append(source_id)
            technical_text = canonical_identity_text(self.member_description(row))
            if len(technical_text) >= 180:
                technical_texts[technical_text].append(source_id)
            if len(technical_text) >= 300:
                technical_prefixes[technical_text[:180]].append(source_id)
            for token in re.findall(
                r"[a-z]+[-_#]?[a-z0-9]*\d+[a-z0-9_-]*", row["title"].casefold()
            ):
                if len(token) >= 5:
                    title_model_tokens[token].append(source_id)
        for source_ids in normalized_titles.values():
            if len(source_ids) > 1:
                add_group(source_ids, "exact_normalized_title")
        for source_ids in canonical_titles.values():
            if len(source_ids) > 1:
                add_group(source_ids, "title_format_or_case_variant")
        for source_ids in technical_texts.values():
            if len(source_ids) > 1:
                add_group(source_ids, "exact_full_technical_text")
        for source_ids in technical_prefixes.values():
            if not 1 < len(source_ids) <= 4:
                continue
            for index, left in enumerate(sorted(source_ids)):
                left_row = self.product_rows[left]
                for right in sorted(source_ids)[index + 1 :]:
                    right_row = self.product_rows[right]
                    left_university = left_row["university"]["university_id"]
                    shared_context = left_row["researcher"]["agent_id"] == right_row[
                        "researcher"
                    ]["agent_id"] or (
                        left_university != "0"
                        and left_university == right_row["university"]["university_id"]
                    )
                    title_similarity = difflib.SequenceMatcher(
                        None,
                        canonical_identity_text(left_row["title"]),
                        canonical_identity_text(right_row["title"]),
                        autojunk=False,
                    ).ratio()
                    if shared_context and title_similarity >= 0.35:
                        edges[left, right].add(
                            "matching_technical_opening_with_shared_context"
                        )
        for source_ids in title_model_tokens.values():
            if len(set(source_ids)) > 1:
                add_group(sorted(set(source_ids)), "shared_title_model_token")

        product_ids = sorted(self.product_rows)
        titles_by_id = {
            source_id: canonical_identity_text(row["title"])
            for source_id, row in self.product_rows.items()
        }
        for index, left in enumerate(product_ids):
            left_row = self.product_rows[left]
            left_title = titles_by_id[left]
            for right in product_ids[index + 1 :]:
                right_row = self.product_rows[right]
                right_title = titles_by_id[right]
                if (
                    left_title == right_title
                    or min(len(left_title), len(right_title)) < 12
                    or not (left_title in right_title or right_title in left_title)
                ):
                    continue
                same_researcher = (
                    left_row["researcher"]["agent_id"]
                    == right_row["researcher"]["agent_id"]
                )
                left_university = left_row["university"]["university_id"]
                same_known_university = (
                    left_university != "0"
                    and left_university == right_row["university"]["university_id"]
                )
                if same_researcher or same_known_university:
                    edges[left, right].add("expanded_title_with_shared_context")

        for map_source_id, map_row in map_only_rows.items():
            map_title = canonical_identity_text(map_row["prod_name"])
            matching_details = canonical_titles.get(map_title, [])
            if matching_details:
                add_group([map_source_id, *matching_details], "map_only_title_match")

        for group in self.config["reviewed_merge_groups"]:
            add_group(
                [str(source_id) for source_id in group["source_ids"]],
                "prior_reviewed_technical_candidate",
            )
        for link in self.config["map_only_identity_links"]:
            add_group(
                [str(link["map_source_id"]), str(link["detail_source_id"])],
                "prior_reviewed_map_identity_candidate",
            )
        for group in self.config["manual_candidate_groups"]:
            add_group(
                [str(source_id) for source_id in group["source_ids"]],
                "full_audit_manual_technical_candidate",
            )

        return edges

    def review_identity_candidates(self, map_only_rows):
        """Apply reviewed dispositions and export their evidence without changing membership."""
        edges = self.discover_identity_candidates(map_only_rows)
        components = Components(
            sorted({source_id for pair in edges for source_id in pair}), []
        )
        for left, right in edges:
            components.merge(left, right)

        configured = {
            tuple(sorted(str(source_id) for source_id in review["source_ids"])): review
            for review in self.config["candidate_component_reviews"]
        }
        if len(configured) != len(self.config["candidate_component_reviews"]):
            raise AssertionError("Duplicate PMUA candidate component review")
        innovation_rows = {
            row["innovation_id"]: row for row in self.tables["innovations"]
        }
        observed_components = sorted(
            (tuple(sorted(members)) for members in components.members.values()),
            key=lambda members: (int(members[0]), members),
        )
        configured_needed = set()
        map_observation_id = self.source_observation(
            "dashboards/innovation_map_all.json", 0
        )

        merge_reasons = []
        for group in self.config["reviewed_merge_groups"]:
            merge_reasons.append(
                (set(str(x) for x in group["source_ids"]), group["reason"])
            )
        for link in self.config["map_only_identity_links"]:
            merge_reasons.append(
                (
                    {str(link["map_source_id"]), str(link["detail_source_id"])},
                    link["reason"],
                )
            )

        for source_ids in observed_components:
            innovation_ids = {
                self.innovation_ids.get(source_id) for source_id in source_ids
            }
            fully_merged = None not in innovation_ids and len(innovation_ids) == 1
            review = configured.get(source_ids)
            if fully_merged:
                matching = " ".join(
                    reason
                    for members, reason in merge_reasons
                    if members.issubset(set(source_ids))
                )
                review_state = "reviewed_decided"
                disposition = "merge_supported_within_pmua"
                differences = self.candidate_context_differences(
                    source_ids, map_only_rows
                )
                recommendation = "Count the reviewed component once and retain every source assertion."
                count_impact = (
                    f"{len(source_ids)} source listings -> 1 innovation; "
                    f"reduces the source-local identity count by {len(source_ids) - 1}."
                )
            else:
                if review is None:
                    raise AssertionError(
                        f"Discovered PMUA candidate component lacks reviewed disposition: {source_ids}"
                    )
                configured_needed.add(source_ids)
                matching = review["matching_evidence"]
                review_state = review["review_state"]
                disposition = review["disposition"]
                differences = review["meaningful_differences"]
                recommendation = review["recommendation"]
                count_impact = review["count_impact"]

            # Candidate review state must be visible on the inventory, not only
            # in a separate review table. Identity membership itself is unchanged.
            if review_state == "reviewed_unresolved":
                candidate_status = "reviewed_unresolved"
            elif fully_merged:
                candidate_status = "reviewed_supported_group"
            elif len(innovation_ids) < len(source_ids):
                candidate_status = "reviewed_partial_merge"
            else:
                candidate_status = "reviewed_separate"
            for innovation_id in innovation_ids:
                if innovation_id in innovation_rows:
                    innovation_rows[innovation_id]["candidate_status"] = (
                        candidate_status
                    )

            signals = sorted(
                {
                    signal
                    for (left, right), pair_signals in edges.items()
                    if left in source_ids and right in source_ids
                    for signal in pair_signals
                }
            )
            titles = []
            evidence_locators = []
            evidence_observations = []
            for source_id in source_ids:
                if source_id in self.product_rows:
                    titles.append(self.product_rows[source_id]["title"])
                    index = self.product_index_by_source[source_id]
                    evidence_locators.extend(
                        [
                            f"data/pmua_apptech/products.json#data/{index}/title",
                            f"data/pmua_apptech/products.json#data/{index}/description_sections",
                            f"data/pmua_apptech/products.json#data/{index}/researcher",
                            f"data/pmua_apptech/products.json#data/{index}/university",
                            f"data/pmua_apptech/products.json#data/{index}/trl",
                            f"data/pmua_apptech/products.json#data/{index}/areas",
                            f"data/pmua_apptech/products.json#data/{index}/funding_history",
                        ]
                    )
                    evidence_observations.append(self.product_obs[source_id])
                else:
                    titles.append(map_only_rows[source_id]["prod_name"])
                    for province_raw, province_rows in sorted(
                        self.source_meta["dashboards/innovation_map_all.json"][
                            "prov_data"
                        ].items()
                    ):
                        for row_index, map_row in enumerate(province_rows):
                            if str(map_row["prod_id"]) == source_id:
                                evidence_locators.extend(
                                    [
                                        "data/pmua_apptech/dashboards/innovation_map_all.json"
                                        f"#prov_data/{province_raw}/{row_index}/prod_name",
                                        "data/pmua_apptech/dashboards/innovation_map_all.json"
                                        f"#prov_data/{province_raw}/{row_index}/areas",
                                    ]
                                )
                    evidence_observations.append(map_observation_id)

            candidate_id = stable_id("pmua_innovation_candidate", source_ids)
            self.add(
                "innovation_identity_candidates",
                candidate_id=candidate_id,
                source_ids_json=list(source_ids),
                titles_json=titles,
                discovery_signals_json=signals,
                review_state=review_state,
                disposition=disposition,
                matching_evidence=matching,
                meaningful_differences=differences,
                recommendation=recommendation,
                count_impact=count_impact,
                evidence_locators_json=evidence_locators,
            )
            self.add_review(
                "innovation_identity_candidate_component",
                source_ids,
                titles,
                f"Matching evidence: {matching} Meaningful differences: {differences}",
                count_impact,
                status=review_state,
                decision=disposition,
                evidence_observation_ids=sorted(set(evidence_observations)),
            )

        unused = set(configured) - configured_needed
        if unused:
            raise AssertionError(
                f"Configured candidate reviews are no longer discovered: {sorted(unused)}"
            )

    def candidate_context_differences(self, source_ids, map_only_rows):
        fields = {
            "titles": set(),
            "researchers": set(),
            "universities": set(),
            "TRL assessments": set(),
            "prices": set(),
            "deployments": set(),
        }
        for source_id in source_ids:
            if source_id not in self.product_rows:
                fields["titles"].add(normalize(map_only_rows[source_id]["prod_name"]))
                fields["deployments"].update(map_only_rows[source_id].get("areas", []))
                continue
            row = self.product_rows[source_id]
            fields["titles"].add(normalize(row["title"]))
            fields["researchers"].add(str(row["researcher"]["agent_id"]))
            fields["universities"].add(str(row["university"]["university_id"]))
            fields["TRL assessments"].add(str(row["trl"]["level"]))
            fields["prices"].add(str(row.get("price_thb")))
            fields["deployments"].update(
                area.get("province", "") for area in row.get("areas", [])
            )
        varied = [name for name, values in fields.items() if len(values - {""}) > 1]
        if not varied:
            return "No material source-field difference; duplicate catalogue evidence is retained."
        return (
            "The source varies "
            + ", ".join(varied)
            + "; these are retained relationship or assessment assertions, not identity boundaries."
        )

    def build_detail_facts(self):
        for source_id in sorted(self.product_rows):
            row = self.product_rows[source_id]
            entity_id = self.innovation_ids[source_id]
            observation_id = self.product_obs[source_id]
            source_key = self.source_key("products", source_id)
            self.add(
                "entity_observations",
                entity_id=entity_id,
                entity_type="innovation",
                observation_id=observation_id,
                source_id=source_id,
                source_locator=f"data/{self.product_index_by_source[source_id]}",
                relationship="detail_listing_observation",
            )
            self.add(
                "innovation_details",
                innovation_id=entity_id,
                observation_id=observation_id,
                source_key=source_key,
                source_id=source_id,
                title_raw=row["title"],
                title_normalized=normalize(row["title"]),
                category_raw=row.get("category"),
                technology_type_raw=row.get("technology_type"),
                trl_level=row["trl"].get("level"),
                trl_label_raw=row["trl"].get("label_raw"),
                trl_explanation_raw=row["trl"].get("explanation_raw"),
                researcher_source_id=str(row["researcher"].get("agent_id") or ""),
                researcher_name_raw=row["researcher"].get("name_raw"),
                university_source_id=str(row["university"].get("university_id") or ""),
                university_name_raw=row["university"].get("name_raw"),
                detail_url=row.get("detail_url"),
                price_raw=row.get("price_raw"),
                price_thb=row.get("price_thb"),
                production_capacity_raw=row.get("production_capacity_raw"),
                tags_json=row.get("tags", []),
                target_groups_json=row.get("target_groups", []),
            )
            for section_index, section in enumerate(
                row.get("description_sections", [])
            ):
                self.add(
                    "description_sections",
                    section_id=stable_id("pmua_description", source_id, section_index),
                    innovation_id=entity_id,
                    observation_id=observation_id,
                    source_key=source_key,
                    section_index=section_index,
                    label_raw=section.get("label"),
                    text_readable=safe_text(readable(section.get("text") or "")),
                    items_json=section.get("items", []),
                )
            for kind, value in [
                ("impact", row.get("impacts", [])),
                ("outcome", row.get("outcomes", [])),
            ]:
                for index, item in enumerate(value):
                    self.add(
                        "narrative_evidence",
                        evidence_id=stable_id("pmua_narrative", source_id, kind, index),
                        innovation_id=entity_id,
                        observation_id=observation_id,
                        source_key=source_key,
                        kind=kind,
                        indicator_raw="",
                        quantity_raw="",
                        value_raw=item,
                        text_readable=safe_text(text(item)),
                    )
            for kind, value in [
                ("roi", row.get("roi", {})),
                ("sroi", row.get("sroi", {})),
            ]:
                if value.get("indicator_raw") or value.get("quantity_raw"):
                    self.add(
                        "narrative_evidence",
                        evidence_id=stable_id("pmua_narrative", source_id, kind),
                        innovation_id=entity_id,
                        observation_id=observation_id,
                        source_key=source_key,
                        kind=kind,
                        indicator_raw=value.get("indicator_raw"),
                        quantity_raw=value.get("quantity_raw"),
                        value_raw="",
                        text_readable=safe_text(
                            " ".join(
                                text(value.get(field))
                                for field in ["indicator_raw", "quantity_raw"]
                            )
                        ),
                    )
            for ip_index, ip in enumerate(row.get("ip") or []):
                label = ip.get("label_raw")
                value = ip.get("value_raw")
                expects_identifier = "เลขที่" in text(label)
                if value in (None, ""):
                    identifier_status = "unknown_or_not_supplied"
                elif expects_identifier and not re.search(r"\d", str(value)):
                    identifier_status = "invalid_identifier_content"
                else:
                    identifier_status = "source_reported_identifier_or_text"
                self.add(
                    "ip_assertions",
                    ip_assertion_id=stable_id("pmua_ip", source_id, ip_index),
                    innovation_id=entity_id,
                    observation_id=observation_id,
                    source_key=source_key,
                    ip_index=ip_index,
                    label_raw=label,
                    value_raw=value,
                    identifier_status=identifier_status,
                )
            for funding_index, funding in enumerate(row.get("funding_history", [])):
                self.add(
                    "funding_assertions",
                    funding_assertion_id=stable_id(
                        "pmua_funding", source_id, funding_index
                    ),
                    innovation_id=entity_id,
                    observation_id=observation_id,
                    source_key=source_key,
                    funding_index=funding_index,
                    source_raw=funding.get("source_raw"),
                    type_raw=funding.get("type_raw"),
                    year_raw=funding.get("year_raw"),
                )
            self.add(
                "researcher_assertions",
                assertion_id=stable_id("pmua_researcher_assertion", source_id),
                innovation_id=entity_id,
                observation_id=observation_id,
                source_key=source_key,
                source_researcher_id=str(row["researcher"].get("agent_id") or ""),
                embedded_name_raw=row["researcher"].get("name_raw"),
                researcher_id=self.researcher_entity_by_source.get(
                    str(row["researcher"].get("agent_id") or ""), ""
                ),
                profile_name_raw=self.researcher_by_source.get(
                    str(row["researcher"].get("agent_id") or ""), {}
                ).get("title", ""),
                profile_status=(
                    "resolved_profile"
                    if str(row["researcher"].get("agent_id") or "")
                    in self.researcher_by_source
                    else "unresolved_external_profile"
                ),
            )
            university_source_id = str(row["university"].get("university_id") or "")
            self.add(
                "university_assertions",
                assertion_id=stable_id("pmua_university_assertion", source_id),
                innovation_id=entity_id,
                observation_id=observation_id,
                source_key=source_key,
                source_university_id=university_source_id,
                name_raw=row["university"].get("name_raw"),
                university_id=self.university_entity_by_source.get(
                    university_source_id, ""
                ),
                reference_status=(
                    "sentinel_university_reference"
                    if university_source_id == "0"
                    else "resolved_profile"
                    if university_source_id in self.university_by_source
                    else "unresolved_external_profile"
                ),
            )
            self.add_detail_readiness(
                row, source_id, entity_id, observation_id, source_key
            )
            for area_index, area in enumerate(row.get("areas", [])):
                self.add_detail_area(
                    row,
                    source_id,
                    entity_id,
                    observation_id,
                    source_key,
                    area_index,
                    area,
                )

    def add_detail_readiness(
        self, row, source_id, entity_id, observation_id, source_key
    ):
        level = row["trl"].get("level")
        self.add(
            "readiness_assessments",
            assessment_id=stable_id("pmua_readiness", "detail", source_id),
            innovation_id=entity_id,
            observation_id=observation_id,
            source_key=source_key,
            source_kind="detail",
            source_locator=f"data/{self.product_index_by_source[source_id]}/trl/level",
            source_id=source_id,
            scale="TRL",
            assessment_context="detail_listing",
            raw_level=level,
            level=level,
            label_raw=row["trl"].get("label_raw"),
            qualifies=level in {8, 9},
            basis="numeric_detail_trl_8_9",
        )

    def _detail_area_resolution(self, area):
        province_raw = area.get("province")
        province_id_raw = str(area.get("province_id") or "")
        province_record = self.province_by_code.get(province_id_raw)
        first_district = (area.get("districts") or [""])[0]
        helper = self.geography.resolve(province_raw, first_district)
        province_normalized = (
            province_record["provinceNameTh"]
            if province_record
            else canonical_province(province_raw)
        )
        province_code = province_id_raw if province_record else helper["province_code"]
        district_ids = [str(x) for x in area.get("district_ids", [])]
        tambon_ids = [str(x) for x in area.get("tambon_ids", [])]
        district_records = [
            self.district_by_code[x] for x in district_ids if x in self.district_by_code
        ]
        subdistrict_records = [
            self.subdistrict_by_code[x]
            for x in tambon_ids
            if x in self.subdistrict_by_code
        ]
        district_names = [r["districtNameTh"] for r in district_records]
        district_codes = [str(r["districtCode"]) for r in district_records]
        subdistrict_names = [r["subdistrictNameTh"] for r in subdistrict_records]
        subdistrict_codes = [str(r["subdistrictCode"]) for r in subdistrict_records]
        hierarchy_pairs = []
        for sub in subdistrict_records:
            if str(sub["provinceCode"]) != province_code:
                continue
            if district_codes and str(sub["districtCode"]) not in district_codes:
                continue
            parent = self.district_by_code.get(str(sub["districtCode"]))
            if parent:
                hierarchy_pairs.append(
                    {
                        "district_code": str(parent["districtCode"]),
                        "district_name": parent["districtNameTh"],
                        "subdistrict_code": str(sub["subdistrictCode"]),
                        "subdistrict_name": sub["subdistrictNameTh"],
                    }
                )
        if not hierarchy_pairs:
            hierarchy_pairs = [
                {
                    "district_code": str(r["districtCode"]),
                    "district_name": r["districtNameTh"],
                }
                for r in district_records
                if str(r["provinceCode"]) == province_code
            ]
        supplied_ids = district_ids + tambon_ids
        resolved_ids = [str(r["districtCode"]) for r in district_records] + [
            str(r["subdistrictCode"]) for r in subdistrict_records
        ]
        unknown_ids = set(supplied_ids) - set(resolved_ids)
        province_conflict = bool(
            province_record
            and canonical_province(province_raw)
            and canonical_province(province_raw) != province_record["provinceNameTh"]
        )
        unequal_arrays = len(area.get("districts", [])) != len(
            area.get("tambons", [])
        ) or len(area.get("district_ids", [])) != len(area.get("tambon_ids", []))
        if (
            unknown_ids
            or (tambon_ids and not subdistrict_records)
            or (district_ids and not district_records)
        ):
            status = "hierarchy_unresolved"
        elif unequal_arrays:
            status = "hierarchy_arrays_preserved_without_zip"
        elif province_conflict:
            status = "province_code_conflict_with_raw_label"
        elif hierarchy_pairs:
            status = "hierarchy_match_by_source_codes"
        else:
            status = helper["status"]
        return {
            "province_raw": province_raw,
            "province_id_raw": province_id_raw,
            "province_normalized": province_normalized,
            "province_code": province_code,
            "district_raw": area.get("districts", []),
            "district_id_raw": district_ids,
            "district_normalized": district_names,
            "district_code": district_codes,
            "subdistrict_raw": area.get("tambons", []),
            "subdistrict_id_raw": tambon_ids,
            "subdistrict_normalized": subdistrict_names,
            "subdistrict_code": subdistrict_codes,
            "hierarchy_pairs": hierarchy_pairs,
            "status": status,
            "correction_reason": (
                "Source province retained; hierarchy was checked from supplied administrative codes"
                if province_conflict
                else "Independent district/tambon arrays retained; no positional zip used"
                if unequal_arrays
                else ""
            ),
        }

    def add_detail_area(
        self, row, source_id, entity_id, observation_id, source_key, area_index, area
    ):
        resolved = self._detail_area_resolution(area)
        self.add(
            "innovation_area_assertions",
            assertion_id=stable_id("pmua_area", "detail", source_id, area_index),
            innovation_id=entity_id,
            observation_id=observation_id,
            source_key=source_key,
            source_kind="detail",
            source_locator=f"data/{self.product_index_by_source[source_id]}/areas/{area_index}",
            area_index=area_index,
            raw_area_json=area,
            area_text_raw="",
            province_raw=resolved["province_raw"],
            province_id_raw=resolved["province_id_raw"],
            province_normalized=resolved["province_normalized"],
            province_code=resolved["province_code"],
            district_raw_json=resolved["district_raw"],
            district_id_raw_json=resolved["district_id_raw"],
            district_normalized_json=resolved["district_normalized"],
            district_code_json=resolved["district_code"],
            subdistrict_raw_json=resolved["subdistrict_raw"],
            subdistrict_id_raw_json=resolved["subdistrict_id_raw"],
            subdistrict_normalized_json=resolved["subdistrict_normalized"],
            subdistrict_code_json=resolved["subdistrict_code"],
            hierarchy_pairs_json=resolved["hierarchy_pairs"],
            resolution_status=resolved["status"],
            correction_reason=resolved["correction_reason"],
        )

    def build_directories(self):
        self.researcher_by_source = {
            str(r["record_id"]): r for r in self.data["researchers.json"]
        }
        self.researcher_name_corrections = {
            str(correction["source_id"]): correction
            for correction in self.config.get("researcher_name_corrections", [])
        }
        for source_id, correction in self.researcher_name_corrections.items():
            profile = self.researcher_by_source.get(source_id)
            if not profile:
                raise AssertionError(
                    f"Researcher name-correction profile is absent: {source_id}"
                )
            if profile["title"] != correction["raw_name"]:
                raise AssertionError(
                    f"Researcher name-correction raw text changed: {source_id}"
                )
            if not correction.get("display_name") or not correction.get(
                "matching_name"
            ):
                raise AssertionError(
                    f"Researcher name correction is incomplete: {source_id}"
                )
        self.researcher_obs_by_source = {}
        components = Components(sorted(self.researcher_by_source), [])
        for group in self.config["researcher_alias_groups"]:
            if group["status"] != "user_confirmed_same_person":
                continue
            ids = [str(value) for value in group["source_ids"]]
            if not ids or not set(ids).issubset(self.researcher_by_source):
                raise AssertionError("Researcher merge endpoint is absent")
            if (
                len(
                    {
                        matching_name(self.researcher_by_source[value]["title"])
                        for value in ids
                    }
                )
                != 1
            ):
                raise AssertionError("Reviewed researcher name evidence changed")
            for left, right in zip(ids, ids[1:]):
                components.merge(left, right)
        self.researcher_entity_by_source = {}
        for index, row in enumerate(self.data["researchers.json"]):
            source_id = str(row["record_id"])
            correction = self.researcher_name_corrections.get(source_id, {})
            display_name = correction.get("display_name", row["title"])
            matching_display_name = correction.get("matching_name", display_name)
            entity_id = stable_id("pmua_researcher", components.find(source_id))
            self.researcher_entity_by_source[source_id] = entity_id
            observation_id = self.source_observation("researchers.json", index)
            self.researcher_obs_by_source[source_id] = observation_id
            self.entity_labels[entity_id] = row["title"]
            self.add(
                "researcher_profiles",
                researcher_id=entity_id,
                source_id=source_id,
                observation_id=observation_id,
                name_raw=row["title"],
                name_normalized=matching_name(matching_display_name),
                university_raw=row.get("university_raw"),
                expertise_raw=row.get("expertise_raw"),
                innovation_count=row.get("innovation_count"),
                profile_url=row.get("profile_url"),
                identity_status=(correction.get("status", "source_profile_directory")),
            )
            self.add(
                "entity_observations",
                entity_id=entity_id,
                entity_type="researcher",
                observation_id=observation_id,
                source_id=source_id,
                source_locator=f"data/{index}",
                relationship="researcher_profile",
            )
        for root, members in sorted(components.members.items()):
            source_ids = sorted(members)
            first = self.researcher_by_source[source_ids[0]]
            correction = self.researcher_name_corrections.get(source_ids[0], {})
            display_name = correction.get("display_name", first["title"])
            matching_display_name = correction.get("matching_name", display_name)
            self.add(
                "researchers",
                researcher_id=stable_id("pmua_researcher", root),
                display_name=normalize(display_name),
                name_normalized=matching_name(matching_display_name),
                source_ids_json=source_ids,
                source_observation_ids_json=[
                    self.researcher_obs_by_source[value] for value in source_ids
                ],
                identity_status="user_confirmed_profile_merge"
                if len(source_ids) > 1
                else "source_profile_identity",
            )
        self.university_by_source = {
            str(r["record_id"]): r for r in self.data["universities.json"]
        }
        self.university_entity_by_source = {}
        for index, row in enumerate(self.data["universities.json"]):
            source_id = str(row["record_id"])
            entity_id = stable_id("pmua_university", source_id)
            self.university_entity_by_source[source_id] = entity_id
            observation_id = self.source_observation("universities.json", index)
            self.entity_labels[entity_id] = row["title"]
            self.add(
                "universities",
                university_id=entity_id,
                source_id=source_id,
                observation_id=observation_id,
                name_raw=row["title"],
                stats_json=row.get("stats", {}),
                profile_url=row.get("profile_url"),
                identity_status="source_profile_directory",
            )
            self.add(
                "entity_observations",
                entity_id=entity_id,
                entity_type="university",
                observation_id=observation_id,
                source_id=source_id,
                source_locator=f"data/{index}",
                relationship="university_profile",
            )
        for group in self.config["researcher_alias_groups"]:
            source_ids = [str(x) for x in group["source_ids"]]
            rows = [self.researcher_by_source[source_id] for source_id in source_ids]
            self.add(
                "researcher_identity_reviews",
                review_group_id=stable_id("pmua_researcher_review", source_ids),
                source_ids_json=source_ids,
                names_json=[row["title"] for row in rows],
                status=group["status"],
                reason=group["reason"],
                affected_measure="researcher identity inventory only; K02 aggregate unchanged",
                evidence_observation_ids_json=[
                    self.researcher_obs_by_source[source_id] for source_id in source_ids
                ],
            )
        for source_id, correction in self.researcher_name_corrections.items():
            self.add(
                "researcher_identity_reviews",
                review_group_id=stable_id("pmua_researcher_name_correction", source_id),
                source_ids_json=[source_id],
                names_json=[correction["raw_name"]],
                status=correction["status"],
                reason=correction["reason"],
                affected_measure="researcher identity inventory only; K02 aggregate unchanged",
                evidence_observation_ids_json=[
                    self.researcher_obs_by_source[source_id]
                ],
            )
        self.build_person_identity_decisions()

    def build_person_identity_decisions(self):
        for decision in self.config["person_must_links"]:
            source_id = str(decision["left_source_id"])
            row = self.researcher_by_source.get(source_id)
            if not row:
                raise AssertionError(
                    f"Person must-link PMUA researcher is absent: {source_id}"
                )
            current_name = normalize(row["title"])
            if "ชญานนท์ แสงมณี" not in current_name:
                raise AssertionError(
                    f"Person must-link name changed for PMUA researcher {source_id}"
                )
            self.add(
                "person_identity_decisions",
                decision_id=decision["candidate_id"],
                left_source_id=source_id,
                left_source_key=decision["left_source_key"],
                right_source_key=decision["right_source_key"],
                left_name_raw=row["title"],
                left_role_evidence="record_type=researcher; source profile role is researcher",
                left_university_raw=row.get("university_raw"),
                left_expertise_raw=row.get("expertise_raw"),
                right_name_raw="ชญานนท์ แสงมณี",
                decision="must_link",
                status="accepted_cross_source_link_preserved",
                reason=decision["reason"],
                evidence_observation_ids_json=[
                    self.researcher_obs_by_source[source_id]
                ],
            )

    def build_stations(self):
        product_index = {
            str(source_id): index for index, source_id in enumerate(self.product_rows)
        }
        for index, row in enumerate(self.data["stations.json"]):
            source_id = str(row["record_id"])
            entity_id = stable_id("pmua_station", source_id)
            observation_id = self.source_observation("stations.json", index)
            contact = row.get("contact") or {}
            contact_names = sorted(
                str(k) for k, value in contact.items() if value not in (None, "")
            )
            self.entity_labels[entity_id] = row["title"]
            self.add(
                "stations",
                station_id=entity_id,
                source_id=source_id,
                observation_id=observation_id,
                title_raw=row.get("title"),
                organization_raw=row.get("organization_raw"),
                director_raw=row.get("director_raw"),
                location_note_raw=row.get("location_note_raw"),
                mission_raw=safe_text(row.get("mission_raw")),
                goals_raw=safe_text(row.get("goals_raw")),
                start_year_raw=row.get("start_year_raw"),
                product_ids_json=[str(x) for x in row.get("product_ids", [])],
                contact_field_names_json=contact_names,
                contact_present=bool(contact_names),
                detail_url=row.get("detail_url"),
                identity_status="source_profile_station",
            )
            self.add(
                "entity_observations",
                entity_id=entity_id,
                entity_type="station",
                observation_id=observation_id,
                source_id=source_id,
                source_locator=f"data/{index}",
                relationship="station_profile",
            )
            for link_index, product_source_id in enumerate(row.get("product_ids", [])):
                product_source_id = str(product_source_id)
                innovation_id = self.innovation_ids.get(product_source_id, "")
                status = (
                    "resolved_to_detail"
                    if product_source_id in product_index
                    else "unresolved_external_detail"
                )
                self.add(
                    "station_links",
                    station_link_id=stable_id(
                        "pmua_station_link", source_id, link_index
                    ),
                    station_id=entity_id,
                    station_source_id=source_id,
                    station_observation_id=observation_id,
                    product_source_id=product_source_id,
                    innovation_id=innovation_id,
                    source_locator=f"data/{index}/product_ids/{link_index}",
                    link_status=status,
                    relationship="source_reported_station_product_association",
                )

    def map_area_resolution(self, province_raw, area_text):
        area_text = text(area_text)
        district_match = re.search(
            r"(?:อำเภอ|อ\.)\s*(.*?)(?=\s*(?:ตำบล|ต\.)|$)", area_text
        )
        tambon_match = re.search(r"(?:ตำบล|ต\.)\s*(.*)$", area_text)
        district_raw = district_match.group(1).strip() if district_match else ""
        tambon_raw = tambon_match.group(1).strip() if tambon_match else ""
        is_bangkok = canonical_province(province_raw) == "กรุงเทพมหานคร"
        district_lookup = (
            re.sub(r"^เขต\s*", "", district_raw) if is_bangkok else district_raw
        )
        tambon_lookup = (
            re.sub(r"^แขวง\s*", "", tambon_raw) if is_bangkok else tambon_raw
        )
        resolved = self.geography.resolve(
            canonical_province(province_raw), district_lookup
        )
        subdistricts = [
            r
            for r in self.geography.subdistricts
            if str(r["provinceCode"]) == resolved["province_code"]
            and str(r["districtCode"]) == resolved["district_code"]
            and normalize(r["subdistrictNameTh"]) == normalize(tambon_lookup)
        ]
        subdistrict = subdistricts[0] if len(subdistricts) == 1 else None
        status = resolved["status"]
        if tambon_raw and not subdistrict:
            status = "subdistrict_unresolved"
        correction_reasons = (
            [resolved["correction_reason"]] if resolved["correction_reason"] else []
        )
        if is_bangkok and (
            district_lookup != district_raw or tambon_lookup != tambon_raw
        ):
            correction_reasons.append(
                "Bangkok เขต/แขวง administrative prefixes removed for reference lookup; raw names retained"
            )
        pairs = []
        if resolved["district_code"]:
            pairs.append(
                {
                    "district_code": resolved["district_code"],
                    "district_name": resolved["district_normalized"],
                    "subdistrict_code": str(subdistrict["subdistrictCode"])
                    if subdistrict
                    else "",
                    "subdistrict_name": subdistrict["subdistrictNameTh"]
                    if subdistrict
                    else tambon_lookup,
                }
            )
        return {
            "province_raw": province_raw,
            "province_id_raw": "",
            "province_normalized": canonical_province(resolved["province_normalized"]),
            "province_code": resolved["province_code"],
            "district_raw": [district_raw] if district_raw else [],
            "district_id_raw": [],
            "district_normalized": [resolved["district_normalized"]]
            if resolved["district_normalized"]
            else [],
            "district_code": [resolved["district_code"]]
            if resolved["district_code"]
            else [],
            "subdistrict_raw": [tambon_raw] if tambon_raw else [],
            "subdistrict_id_raw": [],
            "subdistrict_normalized": [
                subdistrict["subdistrictNameTh"] if subdistrict else tambon_lookup
            ]
            if tambon_raw
            else [],
            "subdistrict_code": [str(subdistrict["subdistrictCode"])]
            if subdistrict
            else [],
            "hierarchy_pairs": pairs,
            "status": status,
            "correction_reason": "; ".join(correction_reasons),
        }

    def build_map(self):
        relative = "dashboards/innovation_map_all.json"
        payload = self.source_meta[relative]
        map_observation_id = self.source_observation(relative, 0)
        for province_raw, rows in sorted(payload["prov_data"].items()):
            for row_index, row in enumerate(rows):
                source_id = str(row["prod_id"])
                map_item_id = stable_id(
                    "pmua_map_item", map_observation_id, province_raw, row_index
                )
                source_key = (
                    f"pmua_apptech/innovation_map_all:{province_raw}:{row_index}"
                )
                innovation_id = self.innovation_ids.get(source_id)
                if not innovation_id:
                    innovation_id = stable_id("pmua_innovation", "map_only", source_id)
                    self.innovation_ids[source_id] = innovation_id
                    self.innovation_names[innovation_id] = row["prod_name"]
                    self.entity_labels[innovation_id] = row["prod_name"]
                    self.add(
                        "innovations",
                        innovation_id=innovation_id,
                        display_name=normalize(row["prod_name"]),
                        aliases_json=[row["prod_name"]],
                        source_ids_json=[source_id],
                        source_observation_ids_json=[map_observation_id],
                        innovation_kind="map_only_limited_listing",
                        has_detail_record=False,
                        identity_status="source_map_limited_listing",
                        candidate_status="accepted_map_only_missing_detail",
                        readiness_conflict=False,
                    )
                self.map_items.append(
                    {
                        "map_item_id": map_item_id,
                        "map_observation_id": map_observation_id,
                        "source_key": source_key,
                        "source_id": source_id,
                        "source_locator": f"prov_data/{province_raw}/{row_index}",
                        "province_raw": province_raw,
                        "row": row,
                        "innovation_id": innovation_id,
                    }
                )
                self.innovation_obs[innovation_id].append(map_observation_id)
                self.add(
                    "entity_observations",
                    entity_id=innovation_id,
                    entity_type="innovation",
                    observation_id=map_observation_id,
                    source_id=source_id,
                    source_locator=f"prov_data/{province_raw}/{row_index}",
                    relationship="map_area_item_observation",
                )
                self.add(
                    "map_area_items",
                    map_item_id=map_item_id,
                    map_observation_id=map_observation_id,
                    source_key=source_key,
                    source_id=source_id,
                    source_locator=f"prov_data/{province_raw}/{row_index}",
                    map_province_raw=province_raw,
                    title_raw=row.get("prod_name"),
                    university_raw=row.get("univ"),
                    trl_raw=row.get("trl"),
                    trl_level=int_or_none(row.get("trl")),
                    areas_json=row.get("areas", []),
                    innovation_id=innovation_id,
                    detail_join_status="resolved_detail"
                    if source_id in self.product_rows
                    else (
                        "resolved_identity_without_detail"
                        if source_id in self.innovation_ids
                        and any(
                            source_id in row["source_ids_json"]
                            and row["has_detail_record"]
                            for row in self.tables["innovations"]
                        )
                        else "map_only_missing_detail"
                    ),
                )
                self.add(
                    "readiness_assessments",
                    assessment_id=stable_id("pmua_readiness", "map", map_item_id),
                    innovation_id=innovation_id,
                    observation_id=map_observation_id,
                    source_key=source_key,
                    source_kind="map",
                    source_locator=f"prov_data/{province_raw}/{row_index}/trl",
                    source_id=source_id,
                    scale="TRL",
                    assessment_context="innovation_map_area_item",
                    raw_level=row.get("trl"),
                    level=int_or_none(row.get("trl")),
                    label_raw="",
                    qualifies=int_or_none(row.get("trl")) in {8, 9},
                    basis="numeric_map_trl_8_9",
                )
                for area_index, area_text in enumerate(row.get("areas", [])):
                    self.add_map_area(
                        province_raw,
                        area_text,
                        area_index,
                        map_item_id,
                        map_observation_id,
                        source_key,
                        source_id,
                        innovation_id,
                        row_index,
                    )
        self.map_only_ids = sorted(
            {
                item["source_id"]
                for item in self.map_items
                if item["source_id"] not in self.product_rows
            }
        )

    def add_map_area(
        self,
        province_raw,
        area_text,
        area_index,
        map_item_id,
        observation_id,
        source_key,
        source_id,
        innovation_id,
        row_index,
    ):
        resolved = self.map_area_resolution(province_raw, area_text)
        self.add(
            "innovation_area_assertions",
            assertion_id=stable_id("pmua_area", "map", map_item_id, area_index),
            innovation_id=innovation_id,
            observation_id=observation_id,
            source_key=source_key,
            source_kind="map",
            source_locator=f"prov_data/{province_raw}/{row_index}/areas/{area_index}",
            area_index=area_index,
            raw_area_json=area_text,
            area_text_raw=area_text,
            province_raw=resolved["province_raw"],
            province_id_raw=resolved["province_id_raw"],
            province_normalized=resolved["province_normalized"],
            province_code=resolved["province_code"],
            district_raw_json=resolved["district_raw"],
            district_id_raw_json=resolved["district_id_raw"],
            district_normalized_json=resolved["district_normalized"],
            district_code_json=resolved["district_code"],
            subdistrict_raw_json=resolved["subdistrict_raw"],
            subdistrict_id_raw_json=resolved["subdistrict_id_raw"],
            subdistrict_normalized_json=resolved["subdistrict_normalized"],
            subdistrict_code_json=resolved["subdistrict_code"],
            hierarchy_pairs_json=resolved["hierarchy_pairs"],
            resolution_status=resolved["status"],
            correction_reason=resolved["correction_reason"],
        )

    def build_aggregates(self):
        for relative in [
            "dashboards/family_2025.json",
            "dashboards/family_2026.json",
            "dashboards/family_all.json",
            "dashboards/innovators_2025.json",
            "dashboards/innovators_2026.json",
            "dashboards/innovators_all.json",
        ]:
            payload = self.source_meta[relative]
            observation_id = self.source_observation(relative, 0)
            aggregate_id = stable_id("pmua_aggregate", relative)
            is_family = payload["dashboard"] == "family"
            entity_type = "family_aggregate" if is_family else "innovator_aggregate"
            unit = "households" if is_family else "innovators"
            self.aggregate_ids_by_file[relative] = aggregate_id
            self.add(
                "aggregate_summaries",
                aggregate_id=aggregate_id,
                observation_id=observation_id,
                source_file=f"data/pmua_apptech/{relative}",
                dashboard=payload["dashboard"],
                entity_type=entity_type,
                scope_json={
                    "year_filter": payload.get("year_filter"),
                    "dataset": payload.get("dataset"),
                },
                year_filter=payload.get("year_filter"),
                reported_count_raw=payload.get("headline"),
                reported_count=payload.get("headline"),
                unit=unit,
                retrieved_at=payload.get("scraped_at"),
                status="source_reported_nonadditive",
            )
            for row_index, (province_raw, component) in enumerate(
                sorted(payload["prov_data"].items())
            ):
                province = canonical_province(province_raw)
                geo = self.geography.resolve(province, "")
                province_code = geo["province_code"]
                self.add(
                    "aggregate_components",
                    component_id=stable_id(
                        "pmua_aggregate_component", aggregate_id, row_index
                    ),
                    aggregate_id=aggregate_id,
                    observation_id=observation_id,
                    row_index=row_index,
                    province_raw=province_raw,
                    province_normalized=province,
                    province_code=province_code,
                    component_kind="family_province"
                    if is_family
                    else "innovator_province",
                    total_hh=component.get("total_hh"),
                    total_inno=component.get("total_inno"),
                    total_members=component.get("total_members"),
                    total_gen=component.get("total_gen"),
                    gen_users=component.get("gen_users"),
                    districts_json=component.get("districts", {}),
                    business_types_json=component.get("business_types", {}),
                    levels_json=component.get("levels", {}),
                )
            if is_family:
                economic = payload["economic_metrics"]
                metrics = [
                    ("cost_reduction", economic["cost_reduction"], True),
                    ("income_increase", economic["income_increase"], True),
                    ("net_income_increase", economic["net_income_increase"], True),
                    (
                        "net_component_sum",
                        {
                            "raw": "",
                            "thb": economic["net_formula"]["component_sum_thb"],
                        },
                        True,
                    ),
                    (
                        "net_displayed",
                        {
                            "raw": economic["net_income_increase"]["raw"],
                            "thb": economic["net_formula"]["displayed_net_thb"],
                        },
                        True,
                    ),
                    (
                        "net_difference",
                        {"raw": "", "thb": economic["net_formula"]["difference_thb"]},
                        False,
                    ),
                ]
                for metric, value, eligible in metrics:
                    self.add(
                        "aggregate_metrics",
                        metric_id=stable_id(
                            "pmua_aggregate_metric", aggregate_id, metric
                        ),
                        aggregate_id=aggregate_id,
                        observation_id=observation_id,
                        metric=metric,
                        value_raw=value.get("raw"),
                        value_thb=value.get("thb"),
                        unit="THB",
                        interpretation=(
                            "source economic display; no established monthly K10 period"
                            if eligible
                            else "reported component discrepancy; one baht difference preserved"
                        ),
                        eligible_for_k10=False,
                    )

    def build_pending_links(self):
        for pending in self.config["pending_cross_source_links"]:
            left_source_id = str(pending.get("left_source_id") or "")
            left_innovation_id = self.innovation_ids.get(left_source_id, "")
            left_observation_id = self.product_obs.get(left_source_id, "")
            self.add(
                "pending_cross_source_decisions",
                pending_id=stable_id(
                    "pmua_pending_cross_source",
                    pending.get("left_source_key", left_source_id),
                    pending["right_source_key"],
                ),
                left_source=pending["left_source"],
                left_source_id=left_source_id,
                left_source_key=pending.get("left_source_key")
                or self.source_key("products", left_source_id),
                left_innovation_id=left_innovation_id,
                left_observation_id=left_observation_id,
                right_source=pending["right_source"],
                right_source_key=pending["right_source_key"],
                decision=pending["decision"],
                status=pending["status"],
                reason=pending["reason"],
            )

    def add_quality_reviews(self):
        for note in self.config.get("source_quality_notes", []):
            source_id = str(note["source_id"])
            self.add_review(
                note["case_type"],
                [source_id],
                [self.product_rows[source_id]["title"]],
                note["reason"],
                "No identity or KPI count change; raw field interpretation remains flagged.",
                status="accepted_treatment",
                decision=note["decision"],
                evidence_observation_ids=[self.product_obs[source_id]],
            )
        missing_researcher_rows = defaultdict(list)
        for source_id, row in self.product_rows.items():
            researcher_id = str(row["researcher"].get("agent_id") or "")
            if researcher_id not in self.researcher_by_source:
                missing_researcher_rows[researcher_id].append(source_id)
        for researcher_id, source_ids in sorted(missing_researcher_rows.items()):
            self.add_review(
                "missing_researcher_profile",
                source_ids,
                [self.product_rows[source_id]["title"] for source_id in source_ids],
                "Embedded researcher name and source ID are retained, but no matching researchers.json profile exists.",
                "Researcher relationship remains unresolved; no named person or innovator eligibility is inferred.",
                status="unresolved_external_reference",
                external_source_ids=[researcher_id],
                entity_type="researcher",
                affected_measures=[
                    "researcher_directory",
                    "K02_named_people_companion",
                ],
                evidence_observation_ids=[
                    self.product_obs[source_id] for source_id in source_ids
                ],
            )
        sentinel_products = [
            source_id
            for source_id, row in self.product_rows.items()
            if str(row["university"].get("university_id")) == "0"
        ]
        self.add_review(
            "sentinel_university_reference",
            sentinel_products,
            [self.product_rows[source_id]["title"] for source_id in sentinel_products],
            "University source ID 0 is a sentinel/unresolved reference, not a 67th university.",
            "University assertion is retained without creating an institution entity or a programme province.",
            status="accepted_treatment",
            decision="Retain source ID 0 as sentinel",
            external_source_ids=["0"],
            entity_type="university",
            affected_measures=["university_directory", "K01A"],
            evidence_observation_ids=[
                self.product_obs[source_id] for source_id in sentinel_products
            ],
        )
        unresolved_station = [
            row
            for row in self.tables["station_links"]
            if row["link_status"] == "unresolved_external_detail"
        ]
        self.add_review(
            "missing_station_detail_reference",
            [row["product_source_id"] for row in unresolved_station],
            [row["product_source_id"] for row in unresolved_station],
            "Station associations are retained even when a bare product ID has no captured detail record; no innovation is fabricated.",
            "Station relationship coverage remains separate from K04 identity counts.",
            status="accepted_treatment",
            decision="Retain unresolved station association",
            entity_type="station_link",
            affected_measures=["station_product_associations", "K04"],
            evidence_observation_ids=[
                row["station_observation_id"] for row in unresolved_station
            ],
        )
        for source_id in self.map_only_ids:
            items = [item for item in self.map_items if item["source_id"] == source_id]
            linked_identity = any(
                item["detail_join_status"] == "resolved_identity_without_detail"
                for item in self.tables["map_area_items"]
                if item["source_id"] == source_id
            )
            self.add_review(
                "map_only_identity_link"
                if linked_identity
                else "map_only_limited_listing",
                [source_id],
                [item["row"]["prod_name"] for item in items],
                (
                    "The map-only listing lacks a detail page but its distinctive title and reviewed technical identity link it to a detail component."
                    if linked_identity
                    else "Map-only listing has title, map province/area and TRL evidence but no product detail page in the supplied catalogue."
                ),
                (
                    "The deployment remains a separate map relationship and does not add another innovation identity."
                    if linked_identity
                    else "Retained in the broader listed inventory; TRL 7 does not qualify for the readiness-supported K04 measure."
                ),
                status="accepted_treatment",
                decision=(
                    "Link map deployment to reviewed detail identity without inventing detail facts"
                    if linked_identity
                    else "Retain limited map listing without invented detail facts"
                ),
                entity_type="innovation",
                affected_measures=["K04", "broader_listed_innovations"],
                evidence_observation_ids=[
                    self.source_observation("dashboards/innovation_map_all.json", 0)
                ],
            )

    def finalize_readiness(self):
        by_entity = defaultdict(list)
        for row in self.tables["readiness_assessments"]:
            by_entity[row["innovation_id"]].append(row)
        for innovation in self.tables["innovations"]:
            assessments = by_entity[innovation["innovation_id"]]
            levels = sorted(
                {row["level"] for row in assessments if row["level"] is not None}
            )
            conflict = len(levels) > 1
            innovation["readiness_conflict"] = conflict
        detail_level_by_source = {
            source_id: row["trl"]["level"]
            for source_id, row in self.product_rows.items()
        }
        map_conflict_count = 0
        conflict_ids = set()
        for item in self.map_items:
            source_id = item["source_id"]
            if source_id not in detail_level_by_source:
                continue
            map_level = int_or_none(item["row"].get("trl"))
            detail_level = detail_level_by_source[source_id]
            if map_level != detail_level:
                map_conflict_count += 1
                conflict_ids.add(source_id)
                self.add(
                    "readiness_conflicts",
                    conflict_id=stable_id(
                        "pmua_readiness_conflict", item["map_item_id"]
                    ),
                    innovation_id=item["innovation_id"],
                    source_id=source_id,
                    province_raw=item["province_raw"],
                    detail_level=detail_level,
                    map_level=map_level,
                    map_source_locator=item["source_locator"],
                    status="preserved_same_source_map_detail_conflict",
                )
        self.readiness_conflict_count = map_conflict_count
        self.readiness_conflict_ids = conflict_ids
        if map_conflict_count != 15 or len(conflict_ids) != 8:
            raise AssertionError(
                f"Expected 15 map/detail readiness conflicts over 8 IDs, got {map_conflict_count}/{len(conflict_ids)}"
            )
        for source_id in sorted(conflict_ids):
            self.add_review(
                "map_detail_readiness_conflict",
                [source_id],
                [self.product_rows[source_id]["title"]],
                "Map and detail TRL assertions differ; both source assessments remain available and no latest/canonical value is selected.",
                "K04 includes the identity if any retained assessment qualifies; the readiness conflict remains visible.",
                status="accepted_treatment",
                decision="Preserve both assessments and use any qualifying supported assessment",
                affected_measures=["K04", "broader_listed_innovations"],
                evidence_observation_ids=[
                    self.product_obs[source_id],
                    self.source_observation("dashboards/innovation_map_all.json", 0),
                ],
            )

    def measures(self):
        ready_ids = sorted(
            {
                row["innovation_id"]
                for row in self.tables["readiness_assessments"]
                if row["qualifies"]
            }
        )
        listed_ids = sorted(
            {row["innovation_id"] for row in self.tables["innovations"]}
        )
        detail_qualifying = sum(
            row["trl"]["level"] in {8, 9} for row in self.product_rows.values()
        )
        area_rows = [
            row
            for row in self.tables["innovation_area_assertions"]
            if row["province_code"]
        ]
        provinces = sorted({row["province_code"] for row in area_rows})
        self.province_entities = set(provinces)
        all_innovator = self.source_meta["dashboards/innovators_all.json"]
        family_all = self.source_meta["dashboards/family_all.json"]
        all_innovator_obs = self.source_observation("dashboards/innovators_all.json", 0)
        family_obs = self.source_observation("dashboards/family_all.json", 0)

        def result(measure, value, unit, scope, status, basis, population, note, obs):
            self.add(
                "measure_results",
                measure=measure,
                value=value,
                unit=unit,
                scope=scope,
                status=status,
                basis=basis,
                source_population=population,
                note=note,
                source_observation_ids_json=obs,
            )

        def contributions(measure, ids, entity_type, scope, status, evidence=None):
            for entity_id in ids:
                self.add(
                    "measure_contributions",
                    measure=measure,
                    entity_id=entity_id,
                    entity_type=entity_type,
                    scope=scope,
                    status=status,
                    evidence_observation_ids_json=sorted(
                        set((evidence or {}).get(entity_id, []))
                    ),
                )

        ready_evidence = defaultdict(list)
        for row in self.tables["readiness_assessments"]:
            if row["qualifies"]:
                ready_evidence[row["innovation_id"]].append(row["observation_id"])
        listed_evidence = defaultdict(list)
        for row in self.tables["innovations"]:
            listed_evidence[row["innovation_id"]] = self.innovation_obs[
                row["innovation_id"]
            ]
        province_evidence = defaultdict(list)
        for row in area_rows:
            province_evidence[row["province_code"]].append(row["observation_id"])

        contributions(
            "K04_ready_innovations",
            ready_ids,
            "innovation",
            "pmua_only",
            "provisional_source_local",
            ready_evidence,
        )
        result(
            "K04_ready_innovations",
            len(ready_ids),
            "innovations",
            "pmua_only",
            "provisional_source_local",
            "distinct source-local identities with at least one retained TRL 8-9 assessment",
            "1,172 detail listings plus 1,510 map items reconciled by namespaced innovation source ID",
            "Not a final cross-source KPI; conflicts and unresolved candidate groups remain visible.",
            sorted(
                {
                    row["observation_id"]
                    for row in self.tables["readiness_assessments"]
                    if row["qualifies"]
                }
            ),
        )
        contributions(
            "broader_listed_innovations",
            listed_ids,
            "innovation",
            "pmua_only",
            "provisional_source_local",
            listed_evidence,
        )
        result(
            "broader_listed_innovations",
            len(listed_ids),
            "innovations",
            "pmua_only",
            "provisional_source_local",
            "distinct retained detail and map-only listing identities",
            "1,172 detail listings and map source IDs",
            "Map-only 9390 remains a limited identity; map-only 10095 is retained as a deployment of the reviewed Super Dr Ball detail identity. Reviewed uncertainty is not collapsed.",
            sorted(
                {
                    row["observation_id"]
                    for row in self.tables["entity_observations"]
                    if row["entity_type"] == "innovation"
                }
            ),
        )
        contributions(
            "K01A_innovation_use_provinces",
            provinces,
            "province",
            "pmua_only",
            "provisional_source_local",
            province_evidence,
        )
        result(
            "K01A_innovation_use_provinces",
            len(provinces),
            "provinces",
            "pmua_only",
            "provisional_source_local",
            "distinct province codes from declared detail areas and map memberships",
            "1,506 detail area objects plus 2,654 map area strings",
            "This is a PMUA programme-use coverage contributor only. Researcher, university and station locations do not qualify it.",
            sorted({row["observation_id"] for row in area_rows}),
        )
        result(
            "K02_headline",
            all_innovator["headline"],
            "innovators",
            "pmua_aggregate_all",
            "source_reported_aggregate_substitute",
            "supplied innovators_all headline and province/level breakdown",
            "PMUA all-scope innovator aggregate",
            "Accepted aggregate basis with limited drilldown. It does not establish named people, community-role equivalence or overlap with directories.",
            [all_innovator_obs],
        )
        self.add(
            "measure_contributions",
            measure="K02_headline",
            entity_id=self.aggregate_ids_by_file["dashboards/innovators_all.json"],
            entity_type="aggregate",
            scope="pmua_aggregate_all",
            status="source_reported_aggregate_substitute",
            evidence_observation_ids_json=[all_innovator_obs],
        )
        result(
            "pmua_researcher_profiles",
            len(self.tables["researcher_profiles"]),
            "profiles",
            "pmua_only",
            "supporting_directory_count_not_innovator_measure",
            "researchers.json profile rows",
            "539 researcher profiles",
            "Researcher-only records do not qualify either innovator population.",
            [row["observation_id"] for row in self.tables["researcher_profiles"]],
        )
        result(
            "pmua_record_based_innovator_companion",
            None,
            "people",
            "pmua_only",
            "unavailable",
            "No explicit inventor/community-innovator person evidence in the supplied PMUA directories",
            "Researcher and embedded researcher assertions",
            "Researcher profiles and product associations are retained, but researcher-only status cannot construct a named innovator population.",
            [
                row["observation_id"]
                for row in self.tables["source_observations"]
                if row["dataset"] in {"products", "researchers"}
            ],
        )
        result(
            "pmua_detail_rows_trl_8_9",
            detail_qualifying,
            "listing_rows",
            "pmua_only",
            "diagnostic_not_identity_count",
            "detail listing rows with numeric TRL 8 or 9",
            "1,172 detail listings",
            "Diagnostic baseline only. Do not use as a final ready-innovation total.",
            [self.source_observation("products.json", 0)],
        )
        result(
            "pmua_map_nested_items",
            len(self.map_items),
            "map_items",
            "pmua_only",
            "diagnostic_source_reconciliation",
            "nested innovation_map_all rows",
            "one current map dashboard snapshot",
            "Map rows are retained separately from detail observations.",
            [self.source_observation("dashboards/innovation_map_all.json", 0)],
        )
        result(
            "pmua_station_product_associations",
            len(self.tables["station_links"]),
            "associations",
            "pmua_only",
            "supporting_relationship_count",
            "station product_ids arrays",
            "31 station profiles",
            "Includes unresolved bare product references; no innovation is fabricated from a missing detail record.",
            [row["observation_id"] for row in self.tables["stations"]],
        )
        for metric, value, note in [
            (
                "pmua_family_households",
                family_all["headline"],
                "Source-reported all-family aggregate; not named households or K08 businesses.",
            ),
            (
                "pmua_family_cost_reduction_thb",
                family_all["economic_metrics"]["cost_reduction"]["thb"],
                "Source economic context; no established monthly K10 period.",
            ),
            (
                "pmua_family_income_increase_thb",
                family_all["economic_metrics"]["income_increase"]["thb"],
                "Source economic context; no established monthly K10 period.",
            ),
            (
                "pmua_family_net_displayed_thb",
                family_all["economic_metrics"]["net_formula"]["displayed_net_thb"],
                "Displayed net retained as source context, not a K10 result.",
            ),
            (
                "pmua_family_net_component_sum_thb",
                family_all["economic_metrics"]["net_formula"]["component_sum_thb"],
                "Component sum retained; it differs from displayed net by one baht.",
            ),
            (
                "pmua_family_net_discrepancy_thb",
                family_all["economic_metrics"]["net_formula"]["difference_thb"],
                "Known one-baht family aggregate discrepancy.",
            ),
        ]:
            result(
                metric,
                value,
                "THB" if metric.endswith("thb") else "households",
                "pmua_aggregate_all",
                "source_reported_supporting_context",
                "family_all dashboard",
                "PMUA family aggregate",
                note,
                [family_obs],
            )

    def validate(self):
        def check(name, expected, observed, note=""):
            status = "passed" if expected == observed else "failed"
            item = {
                "name": name,
                "status": status,
                "expected": expected,
                "observed": observed,
            }
            if note:
                item["note"] = note
            self.validation_checks.append(item)
            if status == "failed":
                self.unexpected_failures.append(item)

        check("raw file inventory", 11, len(self.tables["source_files"]))
        check("detail listing rows", 1172, len(self.product_rows))
        check("researcher profile rows", 539, len(self.tables["researcher_profiles"]))
        check(
            "researcher identities after user decisions",
            537,
            len(self.tables["researchers"]),
        )
        check("university profile rows", 66, len(self.tables["universities"]))
        check("station profile rows", 31, len(self.tables["stations"]))
        check("map nested items", 1510, len(self.map_items))
        check(
            "map unique source IDs",
            1174,
            len({item["source_id"] for item in self.map_items}),
        )
        check("map-only IDs", ["10095", "9390"], sorted(self.map_only_ids))
        check(
            "detail IDs absent from map",
            [],
            sorted(
                set(self.product_rows) - {item["source_id"] for item in self.map_items}
            ),
        )
        check(
            "detail area objects",
            1506,
            sum(len(row.get("areas", [])) for row in self.product_rows.values()),
        )
        check(
            "map area strings",
            2654,
            sum(len(item["row"].get("areas", [])) for item in self.map_items),
        )
        check("station associations", 504, len(self.tables["station_links"]))
        check(
            "unresolved station associations",
            24,
            sum(
                row["link_status"] == "unresolved_external_detail"
                for row in self.tables["station_links"]
            ),
        )
        check(
            "missing researcher rows",
            55,
            sum(
                row["profile_status"] == "unresolved_external_profile"
                for row in self.tables["researcher_assertions"]
            ),
        )
        check(
            "missing researcher IDs",
            18,
            len(
                {
                    row["source_researcher_id"]
                    for row in self.tables["researcher_assertions"]
                    if row["profile_status"] == "unresolved_external_profile"
                }
            ),
        )
        check(
            "university sentinel rows",
            26,
            sum(
                row["reference_status"] == "sentinel_university_reference"
                for row in self.tables["university_assertions"]
            ),
        )
        candidate_count = len(self.tables["innovation_identity_candidates"])
        check("identity candidate components", 76, candidate_count)
        check(
            "identity candidate components fully reviewed",
            candidate_count,
            sum(
                row["review_state"] in {"reviewed_decided", "reviewed_unresolved"}
                for row in self.tables["innovation_identity_candidates"]
            ),
        )
        check(
            "reviewed unresolved identity components",
            len(self.config["innovation_unresolved_links"]),
            sum(
                row["review_state"] == "reviewed_unresolved"
                for row in self.tables["innovation_identity_candidates"]
            ),
        )
        check(
            "coverage ledger unfinished rows",
            0,
            sum(
                row["review_state"] == "not_reviewed"
                for row in self.tables["review_coverage"]
            ),
        )
        coverage_counts = Counter(row["task"] for row in self.tables["review_coverage"])
        for task, expected in [
            ("detail_identity_readiness_location", 1172),
            ("map_item_identity_readiness_location", 1510),
            ("innovation_identity_candidate_review", candidate_count),
            ("researcher_reference", 1172),
            ("university_reference", 1172),
            ("station_product_reference", 504),
            ("aggregate_scope", 6),
            ("aggregate_component", len(self.tables["aggregate_components"])),
        ]:
            check(f"coverage task {task}", expected, coverage_counts[task])
        check(
            "reviewed cannot-links",
            len(self.config["innovation_cannot_links"]),
            sum(
                row["rule"] == "reviewed_cannot_link"
                for row in self.tables["identity_decisions"]
            ),
        )
        check(
            "map/detail readiness conflicts",
            15,
            len(self.tables["readiness_conflicts"]),
        )
        check("map/detail conflict IDs", 8, len(self.readiness_conflict_ids))
        all_family = self.source_meta["dashboards/family_all.json"]
        all_innovator = self.source_meta["dashboards/innovators_all.json"]
        family_sum = sum(
            row.get("total_hh", 0) or 0
            for row in self.tables["aggregate_components"]
            if row["component_kind"] == "family_province"
            and row["aggregate_id"]
            == self.aggregate_ids_by_file["dashboards/family_all.json"]
        )
        innovator_sum = sum(
            row.get("total_inno", 0) or 0
            for row in self.tables["aggregate_components"]
            if row["component_kind"] == "innovator_province"
            and row["aggregate_id"]
            == self.aggregate_ids_by_file["dashboards/innovators_all.json"]
        )
        check("family all province sum", all_family["headline"], family_sum)
        check("innovator all province sum", all_innovator["headline"], innovator_sum)
        check(
            "family economic component sum",
            1005872564,
            all_family["economic_metrics"]["net_formula"]["component_sum_thb"],
        )
        check(
            "family economic display discrepancy",
            1,
            all_family["economic_metrics"]["net_formula"]["difference_thb"],
        )
        hierarchy_errors = []
        bangkok_map_areas = []
        for area in self.tables["innovation_area_assertions"]:
            if (
                area["source_kind"] == "map"
                and area["province_normalized"] == "กรุงเทพมหานคร"
            ):
                bangkok_map_areas.append(area)
            for pair in area["hierarchy_pairs_json"]:
                district = self.district_by_code.get(str(pair["district_code"]))
                if not district or str(district["provinceCode"]) != str(
                    area["province_code"]
                ):
                    hierarchy_errors.append(area["assertion_id"])
                    continue
                subdistrict_code = str(pair.get("subdistrict_code") or "")
                if subdistrict_code:
                    subdistrict = self.subdistrict_by_code.get(subdistrict_code)
                    if (
                        not subdistrict
                        or str(subdistrict["districtCode"])
                        != str(pair["district_code"])
                        or str(subdistrict["provinceCode"])
                        != str(area["province_code"])
                    ):
                        hierarchy_errors.append(area["assertion_id"])
        check("area hierarchy code errors", 0, len(set(hierarchy_errors)))
        check("Bangkok map area assertions", 12, len(bangkok_map_areas))
        check(
            "Bangkok map areas with full hierarchy match",
            12,
            sum(
                area["resolution_status"] == "hierarchy_match"
                and bool(area["district_code_json"])
                and bool(area["subdistrict_code_json"])
                for area in bangkok_map_areas
            ),
        )
        self.expected_findings.extend(
            [
                {
                    "finding": "University 0 is a sentinel",
                    "observed": 26,
                    "status": "documented",
                },
                {
                    "finding": "Map-only IDs retained without detail",
                    "observed": sorted(self.map_only_ids),
                    "status": "documented",
                },
                {
                    "finding": "Researcher profile gaps retained",
                    "observed": {"ids": 18, "rows": 55},
                    "status": "documented",
                },
                {
                    "finding": "Map/detail TRL conflicts retained",
                    "observed": {"assertions": 15, "source_ids": 8},
                    "status": "documented",
                },
                {
                    "finding": "Family aggregate one-baht discrepancy retained",
                    "observed": 1,
                    "status": "documented",
                },
                {
                    "finding": "Cross-source coffee links remain pending",
                    "observed": len(self.tables["pending_cross_source_decisions"]),
                    "status": "documented",
                },
            ]
        )
        self.validation = {
            "source": "pmua_apptech",
            "validation_version": "pmua-apptech-v1",
            "checks": self.validation_checks,
            "expected_findings": self.expected_findings,
            "unexpected_failures": self.unexpected_failures,
            "foreign_key_policy": "Internal entity and observation links are validated; unresolved external source IDs are explicit and are not treated as broken internal links.",
        }

    def add_coverage(
        self,
        task,
        source_record_id,
        source_ids,
        disposition,
        evidence_locators,
        reason,
        affected_measures,
        review_state="reviewed_decided",
    ):
        self.add(
            "review_coverage",
            coverage_id=stable_id("pmua_coverage", task, source_record_id),
            task=task,
            source_record_id=source_record_id,
            source_ids_json=[str(source_id) for source_id in source_ids],
            review_state=review_state,
            disposition=disposition,
            evidence_locators_json=evidence_locators,
            reason=reason,
            affected_measures_json=affected_measures,
        )

    def build_review_coverage(self):
        for source_id in sorted(self.product_rows):
            index = self.product_index_by_source[source_id]
            self.add_coverage(
                "detail_identity_readiness_location",
                source_id,
                [source_id],
                "retained_detail_listing_with_separate_assertions",
                [
                    f"data/pmua_apptech/products.json#data/{index}/title",
                    f"data/pmua_apptech/products.json#data/{index}/trl",
                    f"data/pmua_apptech/products.json#data/{index}/areas",
                ],
                "The detail listing is retained at source grain; identity, every TRL assessment and every declared area remain traceable without positional geography inference.",
                ["K01A", "K04", "broader_listed_innovations"],
            )

        for row in self.tables["map_area_items"]:
            self.add_coverage(
                "map_item_identity_readiness_location",
                row["map_item_id"],
                [row["source_id"]],
                row["detail_join_status"],
                [
                    f"data/pmua_apptech/dashboards/innovation_map_all.json#{row['source_locator']}/prod_id",
                    f"data/pmua_apptech/dashboards/innovation_map_all.json#{row['source_locator']}/trl",
                    f"data/pmua_apptech/dashboards/innovation_map_all.json#{row['source_locator']}/areas",
                ],
                "The nested map item is retained independently; its detail join, TRL and all area strings are assessed at map-item grain.",
                ["K01A", "K04", "broader_listed_innovations"],
            )

        for review in self.tables["innovation_identity_candidates"]:
            source_ids = review["source_ids_json"]
            self.add_coverage(
                "innovation_identity_candidate_review",
                ",".join(source_ids),
                source_ids,
                review["disposition"],
                review["evidence_locators_json"],
                (
                    f"Matching evidence: {review['matching_evidence']} "
                    f"Meaningful differences: {review['meaningful_differences']}"
                ),
                ["K04", "broader_listed_innovations"],
                review_state=review["review_state"],
            )

        for row in self.tables["researcher_assertions"]:
            source_id = row["source_key"].rsplit(":", 1)[-1]
            index = self.product_index_by_source[source_id]
            self.add_coverage(
                "researcher_reference",
                row["assertion_id"],
                [source_id, row["source_researcher_id"]],
                row["profile_status"],
                [f"data/pmua_apptech/products.json#data/{index}/researcher"],
                "The embedded researcher assertion is retained and linked only when its captured directory profile exists; missing profiles remain explicit external references.",
                ["K02"],
            )

        for row in self.tables["university_assertions"]:
            source_id = row["source_key"].rsplit(":", 1)[-1]
            index = self.product_index_by_source[source_id]
            self.add_coverage(
                "university_reference",
                row["assertion_id"],
                [source_id, row["source_university_id"]],
                row["reference_status"],
                [f"data/pmua_apptech/products.json#data/{index}/university"],
                "The product affiliation is retained; university 0 remains a sentinel and no institution address is converted into programme coverage.",
                ["K01A"],
            )

        for row in self.tables["station_links"]:
            self.add_coverage(
                "station_product_reference",
                row["station_link_id"],
                [row["station_source_id"], row["product_source_id"]],
                row["link_status"],
                [f"data/pmua_apptech/stations.json#{row['source_locator']}"],
                "The station association is retained; an absent product detail remains an unresolved endpoint and never creates an innovation.",
                ["broader_listed_innovations"],
            )

        aggregate_by_id = {
            row["aggregate_id"]: row for row in self.tables["aggregate_summaries"]
        }
        for row in self.tables["aggregate_summaries"]:
            self.add_coverage(
                "aggregate_scope",
                row["aggregate_id"],
                [row["aggregate_id"]],
                row["status"],
                [f"{row['source_file']}#."],
                "The dashboard scope and reported headline are retained as a separate snapshot; overlapping year and all-time scopes are not added together.",
                ["K02", "pmua_family_households", "K10"],
            )
        for row in self.tables["aggregate_components"]:
            summary = aggregate_by_id[row["aggregate_id"]]
            self.add_coverage(
                "aggregate_component",
                row["component_id"],
                [row["aggregate_id"]],
                "retained_source_reported_component",
                [f"{summary['source_file']}#prov_data/{row['province_raw']}"],
                "The dashboard component is retained at its supplied province row and nested maps are not expanded into unsupported cross-products.",
                ["K02", "pmua_family_households"],
            )

    def validate_foreign_keys(self):
        source_observation_ids = {
            row["observation_id"] for row in self.tables["source_observations"]
        }
        innovations = {row["innovation_id"] for row in self.tables["innovations"]}
        researchers = {row["researcher_id"] for row in self.tables["researchers"]}
        universities = {row["university_id"] for row in self.tables["universities"]}
        stations = {row["station_id"] for row in self.tables["stations"]}
        aggregates = {row["aggregate_id"] for row in self.tables["aggregate_summaries"]}
        map_source_ids = {row["source_id"] for row in self.tables["map_area_items"]}
        innovation_source_ids = set(self.product_rows) | map_source_ids
        for table in [
            "innovation_details",
            "description_sections",
            "narrative_evidence",
            "ip_assertions",
            "funding_assertions",
            "readiness_assessments",
            "readiness_conflicts",
            "map_area_items",
            "innovation_area_assertions",
        ]:
            assert all(
                row["innovation_id"] in innovations for row in self.tables[table]
            ), table
        assert all(
            row["observation_id"] in source_observation_ids
            for table in self.tables.values()
            for row in table
            if row.get("observation_id")
        ), "observation links"
        assert all(
            row["researcher_id"] in researchers
            for row in self.tables["researcher_profiles"]
        ), "researcher profiles"
        assert len(researchers) == len(self.tables["researchers"]), (
            "unique researcher identities"
        )
        assert all(
            row["researcher_id"] in researchers or not row["researcher_id"]
            for row in self.tables["researcher_assertions"]
        ), "researcher assertions"
        assert all(
            row["university_id"] in universities or not row["university_id"]
            for row in self.tables["university_assertions"]
        ), "university assertions"
        assert all(
            row["station_id"] in stations for row in self.tables["station_links"]
        ), "station links"
        assert all(
            row["innovation_id"] in innovations or not row["innovation_id"]
            for row in self.tables["station_links"]
        ), "station innovation links"
        assert all(
            row["aggregate_id"] in aggregates
            for table in ["aggregate_components", "aggregate_metrics"]
            for row in self.tables[table]
        ), "aggregate links"
        assert all(
            set(row["source_ids_json"]).issubset(innovation_source_ids)
            for row in self.tables["innovation_identity_candidates"]
        ), "identity candidate source links"
        assert all(
            row["left_source_id"] in innovation_source_ids
            and row["right_source_id"] in innovation_source_ids
            for row in self.tables["identity_decisions"]
        ), "innovation identity decision source links"
        known_entity_ids = innovations | researchers | universities | stations
        for row in self.tables["entity_observations"]:
            assert row["entity_id"] in known_entity_ids
        for row in self.tables["measure_contributions"]:
            if row["entity_type"] == "innovation":
                assert row["entity_id"] in innovations
            elif row["entity_type"] == "researcher":
                assert row["entity_id"] in researchers
            elif row["entity_type"] == "aggregate":
                assert row["entity_id"] in aggregates
            elif row["entity_type"] == "province":
                assert row["entity_id"] in self.province_entities
            else:
                raise AssertionError(
                    f"Unknown contributor entity type: {row['entity_type']}"
                )

    def run(self):
        self.ingest()
        self.build_directories()
        self.detail_identity()
        self.build_detail_facts()
        self.build_stations()
        self.build_map()
        self.build_aggregates()
        self.build_pending_links()
        self.add_quality_reviews()
        self.finalize_readiness()
        self.measures()
        self.build_review_coverage()
        self.validate_foreign_keys()
        self.validate()
        if self.unexpected_failures:
            raise ValueError(f"PMUA validation failed: {self.unexpected_failures}")
        return _export_tables(self.tables)


def build_tables(datasets, reviews, geography, input_metadata):
    """Build all PMUA source-local legacy tables from declared in-memory captures."""
    return PMUAPilot(datasets, reviews, geography, input_metadata).run()

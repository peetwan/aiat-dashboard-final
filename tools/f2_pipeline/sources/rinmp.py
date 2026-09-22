"""Build the source-local RINMP pilot from the supplied snapshot.

The cleaner preserves catalogue profiles, collector owner groups, title and name
claims, technical sections, readiness assertions, locations, and aggregates at
their source grains. Only reviewed within-RINMP innovation matches are applied.
Markdown review guides are maintained separately and are never overwritten here.
"""

import json
import re
from collections import Counter, defaultdict

from ..common import normalize, readable, safe_text, stable_id

DATASET_KEYS = ("app_tech", "owner_profiles", "statistics")

TABLE_COLUMNS = {
    "source_files": [
        "dataset",
        "file",
        "sha256",
        "declared_sha256",
        "integrity_status",
        "row_count",
        "declared_record_count",
        "record_type",
        "captured_at",
        "run_id",
        "source_url",
        "warnings_json",
        "envelope_json",
    ],
    "source_observations": [
        "observation_id",
        "dataset",
        "source_id",
        "source_key",
        "raw_file",
        "row_locator",
        "file_sha256",
        "captured_at",
        "run_id",
        "record_type",
        "disposition",
    ],
    "innovations": [
        "innovation_id",
        "display_name",
        "aliases_json",
        "source_ids_json",
        "source_observation_ids_json",
        "identity_status",
        "candidate_status",
        "readiness_conflict",
        "ready_qualification",
    ],
    "innovation_profiles": [
        "innovation_id",
        "observation_id",
        "source_key",
        "source_id",
        "title_raw",
        "title_normalized",
        "owner_display_name_raw",
        "institute_source_id",
        "institute_name_raw",
        "category_raw",
        "sub_category_raw",
        "industrial_type_raw",
        "status_raw",
        "is_recommend_raw",
        "detail_url",
        "tags_json",
        "target_segments_json",
        "province_resolved_raw",
        "source_created_at",
        "source_last_update_at",
    ],
    "description_sections": [
        "section_id",
        "innovation_id",
        "observation_id",
        "source_key",
        "section_index",
        "label_raw",
        "text_readable",
        "source_locator",
    ],
    "readiness_assertions": [
        "assertion_id",
        "innovation_id",
        "observation_id",
        "source_key",
        "source_id",
        "scale",
        "value_raw",
        "numeric_level",
        "validity",
        "qualifies_k04",
        "assessment_context",
        "source_locator",
    ],
    "matrix_scores": [
        "matrix_score_id",
        "innovation_id",
        "observation_id",
        "source_key",
        "ease_cost_score",
        "impact_3e_score",
        "local_tech_score",
        "average_score",
        "tech_efficiency_score",
        "interpretation",
        "source_locator",
    ],
    "commercial_assertions": [
        "assertion_id",
        "innovation_id",
        "observation_id",
        "source_key",
        "budget_thb",
        "cost_per_unit_thb",
        "life_time_year_count",
        "interpretation",
        "source_locator",
    ],
    "ip_assertions": [
        "assertion_id",
        "innovation_id",
        "observation_id",
        "source_key",
        "category_raw",
        "number_raw",
        "identifier_status",
        "source_locator",
    ],
    "certificate_assertions": [
        "assertion_id",
        "innovation_id",
        "observation_id",
        "source_key",
        "level_raw",
        "expired_datetime_raw",
        "interpretation",
        "source_locator",
    ],
    "media_references": [
        "media_reference_id",
        "innovation_id",
        "observation_id",
        "source_key",
        "media_role",
        "media_index",
        "file_id",
        "inspection_status",
        "source_locator",
    ],
    "institutes": [
        "institute_id",
        "source_institute_id",
        "name_raw",
        "catalogue_profile_count",
        "statistics_reported_count",
        "reconciliation_status",
    ],
    "institute_assertions": [
        "assertion_id",
        "innovation_id",
        "observation_id",
        "source_key",
        "institute_id",
        "source_institute_id",
        "name_raw",
        "role",
        "coverage_eligibility",
        "source_locator",
    ],
    "location_assertions": [
        "location_id",
        "innovation_id",
        "observation_id",
        "source_key",
        "assertion_kind",
        "address_index",
        "location_role",
        "party_name_raw",
        "province_raw",
        "district_raw",
        "subdistrict_raw",
        "province_normalized",
        "province_code",
        "district_normalized",
        "district_code",
        "subdistrict_normalized",
        "subdistrict_code",
        "resolution_status",
        "correction_reason",
        "coverage_eligibility",
        "evidence_section_id",
        "source_locator",
    ],
    "owner_groups": [
        "owner_group_id",
        "observation_id",
        "owner_key",
        "fullname_raw",
        "name_normalized",
        "institute_raw",
        "linked_app_count",
        "title_claim_count",
        "underlying_identity_status",
        "person_id",
    ],
    "owner_technology_links": [
        "owner_link_id",
        "owner_group_id",
        "owner_observation_id",
        "owner_key",
        "innovation_id",
        "app_observation_id",
        "app_source_id",
        "link_index",
        "endpoint_status",
        "source_locator",
    ],
    "owner_title_claims": [
        "title_claim_id",
        "owner_group_id",
        "owner_observation_id",
        "owner_key",
        "title_index",
        "title_raw",
        "title_normalized",
        "matched_app_source_ids_json",
        "reconciliation_status",
        "source_locator",
    ],
    "owner_name_claims": [
        "name_claim_id",
        "owner_link_id",
        "owner_group_id",
        "app_source_id",
        "claim_origin",
        "name_raw",
        "name_normalized",
        "role",
        "natural_person_status",
        "source_locator",
    ],
    "owner_name_disagreements": [
        "disagreement_id",
        "owner_link_id",
        "owner_group_id",
        "owner_key",
        "app_source_id",
        "group_name_raw",
        "app_name_raw",
        "group_name_normalized",
        "app_name_normalized",
        "treatment",
        "evidence_locators_json",
    ],
    "people": [
        "person_id",
        "display_name",
        "aliases_json",
        "identity_status",
        "community_innovator_eligibility",
        "broader_innovator_eligibility",
    ],
    "person_role_assertions": [
        "role_assertion_id",
        "person_id",
        "innovation_id",
        "observation_id",
        "source_key",
        "role",
        "confidence",
        "evidence_text",
        "source_locator",
    ],
    "narrative_role_mentions": [
        "mention_id",
        "innovation_id",
        "observation_id",
        "source_key",
        "section_id",
        "role",
        "matched_terms_json",
        "named_person_id",
        "eligibility_treatment",
        "evidence_text",
        "source_locator",
    ],
    "identity_decisions": [
        "decision_id",
        "source_ids_json",
        "title_raw",
        "decision",
        "review_state",
        "rule",
        "reason",
        "evidence_observation_ids_json",
        "evidence_locators_json",
        "possible_broader_count_reduction",
        "possible_k04_count_reduction",
    ],
    "pending_cross_source_decisions": [
        "decision_id",
        "rinmp_source_id",
        "rinmp_innovation_id",
        "rinmp_observation_id",
        "other_source",
        "other_source_id",
        "decision",
        "union_status",
        "evidence_locator",
    ],
    "aggregate_metrics": [
        "aggregate_metric_id",
        "observation_id",
        "metric",
        "population_label",
        "value",
        "unit",
        "recomputable",
        "recomputed_value",
        "reconciliation_status",
        "interpretation",
        "source_locator",
    ],
    "aggregate_components": [
        "component_id",
        "observation_id",
        "metric",
        "component_index",
        "institute_raw",
        "reported_count",
        "recomputed_count",
        "reconciliation_status",
        "source_locator",
    ],
    "review_cases": [
        "review_id",
        "case_type",
        "source_ids_json",
        "names_json",
        "status",
        "review_state",
        "treatment",
        "reason",
        "affected_measures_json",
        "evidence_locators_json",
    ],
    "review_coverage": [
        "coverage_id",
        "task",
        "source_record_or_group",
        "source_ids_json",
        "review_state",
        "disposition",
        "evidence_locators_json",
        "reason",
        "affected_measures_json",
    ],
    "measure_results": [
        "measure",
        "definition_version",
        "snapshot_scope",
        "value",
        "basis",
        "unit",
        "assumption",
        "status",
        "source_population",
        "supported_drilldown",
        "supported_filters",
        "supported_filters_json",
        "unsupported_filters_json",
        "unsupported_filter_policy",
        "aggregation",
        "limitations",
    ],
    "measure_contributions": [
        "contribution_id",
        "measure",
        "entity_id",
        "entity_type",
        "status",
        "evidence_observation_ids_json",
        "evidence_location_ids_json",
    ],
}

TABLE_GRAINS = {
    "source_files": "One supplied RINMP JSON file.",
    "source_observations": "One raw profile, owner group, or statistics snapshot.",
    "innovations": "One provisional source-local innovation after reviewed matches.",
    "innovation_profiles": "One original app_tech profile.",
    "description_sections": "One retained source description section.",
    "readiness_assertions": "One TRL or ATL assertion from one app_tech profile.",
    "matrix_scores": "One optional matrix-score object from one profile.",
    "commercial_assertions": "One commercial field group from one profile.",
    "ip_assertions": "One IP claim from one profile.",
    "certificate_assertions": "One certificate claim from one profile.",
    "media_references": "One profile or gallery file-ID reference.",
    "institutes": "One source institute reconciled to the statistics graph.",
    "institute_assertions": "One profile-to-institute affiliation claim.",
    "location_assertions": "One structured, passage-derived, or collector-resolved location claim.",
    "owner_groups": "One collector-created owner_key group, not a verified person.",
    "owner_technology_links": "One explicit owner-group-to-app_tech-ID relationship.",
    "owner_title_claims": "One independent title entry in an owner group title array.",
    "owner_name_claims": "One group-name or profile-display-name claim for an owner link.",
    "owner_name_disagreements": "One normalized name disagreement on an owner link.",
    "people": "One natural person explicitly named with a non-owner narrative role.",
    "person_role_assertions": "One explicit named-person role passage.",
    "narrative_role_mentions": "One role class mentioned in one description section.",
    "identity_decisions": "One reviewed exact-title candidate group.",
    "pending_cross_source_decisions": "One accepted external must-link pending later union.",
    "aggregate_metrics": "One statistics headline retained at aggregate grain.",
    "aggregate_components": "One institute component in the statistics graph.",
    "review_cases": "One reviewed issue or accepted uncertainty.",
    "review_coverage": "One completed review task for one record, assertion, or group.",
    "measure_results": "One source-local result or explicit unavailable measure.",
    "measure_contributions": "One distinct entity contribution to one source-local measure.",
}

ROLE_TERMS = {
    "researcher": ["นักวิจัย", "ทีมวิจัย", "ผู้วิจัย", "คณะผู้วิจัย"],
    "community_innovator": ["นวัตกรชุมชน"],
    "creator_or_inventor": ["ผู้สร้างงาน", "ผู้คิดค้น", "ผู้ประดิษฐ์"],
    "developer": ["ผู้พัฒนา", "พัฒนาโดย"],
    "operator": ["ผู้ประกอบการ", "เจ้าของธุรกิจ", "เจ้าของกิจการ"],
    "user": ["ผู้ใช้งาน", "ผู้ใช้ประโยชน์", "กลุ่มผู้ใช้"],
    "community_enterprise": ["วิสาหกิจชุมชน"],
}

NEGATIVE_COVERAGE_PHRASES = [
    "ยังไม่มีกลุ่มนำไปใช้ประโยชน์",
    "ยังไม่มีการนำนวัตกรรมไปใช้งาน",
    "ยังไม่มีการนำนวัตกรรมไปใช้",
]

STRONG_USE_PHRASES = [
    "พื้นที่ที่นำไปใช้ประโยชน์",
    "ที่นำนวัตกรรมไปใช้ประโยชน์",
    "ติดตั้งอุปกรณ์ดังกล่าวในพื้นที่",
    "ถูกนำไปใช้",
    "ชุมชนนำผลงานออกแบบไปใช้ประโยชน์",
    "นำไปใช้การใน",
]


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def scalar(value):
    return "" if value is None else value


def strip_admin_prefix(value, prefixes):
    result = normalize(value)
    for prefix in prefixes:
        if result.startswith(prefix):
            return result[len(prefix) :].strip()
    return result


class RINMPPilot:
    def __init__(self, datasets, reviews, geography, input_metadata):
        if set(datasets) != set(DATASET_KEYS):
            raise ValueError(
                "RINMP input contract: datasets must be app_tech, owner_profiles, statistics"
            )
        self.config = reviews["reviewed_cases.json"]
        self.datasets, self.input_metadata, self.geo = (
            datasets,
            input_metadata,
            geography,
        )
        self.tables = {name: [] for name in TABLE_COLUMNS}
        self.payloads = {}
        self.file_hashes = {}
        self.apps = []
        self.owners = []
        self.statistics = {}
        self.app_by_id = {}
        self.app_index_by_id = {}
        self.owner_index_by_key = {}
        self.observation_by_app_id = {}
        self.observation_by_owner_key = {}
        self.innovation_by_source_id = {}
        self.section_id_by_app_label = defaultdict(list)

    def add(self, table, **row):
        expected = TABLE_COLUMNS[table]
        unknown = set(row) - set(expected)
        if unknown:
            raise AssertionError(f"Unexpected {table} columns: {sorted(unknown)}")
        self.tables[table].append({column: row.get(column, "") for column in expected})

    def source_key(self, dataset, source_id):
        return f"rinmp/{dataset}:{source_id}"

    def raw_locator(self, file_name, fragment):
        dataset = {
            "app_tech.json": "app_tech",
            "owner_profiles.json": "owner_profiles",
            "statistics.json": "statistics",
        }[file_name]
        metadata = self.input_metadata[dataset]
        return f"evidence://{metadata['source_id']}/{metadata['run_id']}/{metadata['file']}#{fragment}"

    def ingest(self):
        names = (
            ("app_tech", "app_tech.json", "app_tech"),
            ("owner_profiles", "owner_profiles.json", "owner_profile"),
            ("statistics", "statistics.json", "statistics_snapshot"),
        )
        for dataset, file_name, record_type in names:
            payload, metadata = self.datasets[dataset], self.input_metadata.get(dataset)
            if not isinstance(payload, dict) or not isinstance(
                payload.get("data"), dict
            ):
                raise ValueError(
                    f"RINMP input contract: {dataset} must be an envelope with data"
                )
            if not isinstance(metadata, dict) or any(
                not metadata.get(key)
                for key in (
                    "source_id",
                    "run_id",
                    "file",
                    "sha256",
                    "size",
                    "captured_at",
                    "originating_system",
                )
            ):
                raise ValueError(
                    f"RINMP input contract: missing locked metadata for {dataset}"
                )
            rows = (
                [payload["data"]]
                if dataset == "statistics"
                else payload["data"].get("records")
            )
            if not isinstance(rows, list) or not all(
                isinstance(row, dict) for row in rows
            ):
                raise ValueError(f"RINMP input contract: invalid {dataset} rows")
            if dataset != "statistics":
                declared_count = payload.get("record_count")
                if type(declared_count) is not int or declared_count != len(rows):
                    raise ValueError(
                        f"RINMP input contract: invalid {dataset} row accounting"
                    )
            self.payloads[file_name], self.file_hashes[file_name] = (
                payload,
                metadata["sha256"],
            )
            envelope = {
                key: value
                for key, value in payload.items()
                if key not in {"data", "warnings"}
            }
            self.add(
                "source_files",
                dataset=payload.get("dataset", dataset),
                file=metadata["file"],
                sha256=metadata["sha256"],
                declared_sha256=metadata["sha256"],
                integrity_status="locked_capture",
                row_count=len(rows),
                declared_record_count=scalar(payload.get("record_count")),
                record_type=record_type,
                captured_at=metadata["captured_at"],
                run_id=metadata["run_id"],
                source_url=payload.get("source_base_url"),
                warnings_json=dump(payload.get("warnings", [])),
                envelope_json=dump(envelope),
            )
            seen = set()
            for index, row in enumerate(rows):
                raw_source_id = (
                    row.get("id")
                    if dataset == "app_tech"
                    else row.get("owner_key")
                    if dataset == "owner_profiles"
                    else metadata["run_id"]
                )
                if (
                    isinstance(raw_source_id, bool)
                    or not isinstance(raw_source_id, (str, int))
                    or not str(raw_source_id).strip()
                ):
                    raise ValueError(
                        f"RINMP input contract: missing or invalid {dataset} source ID"
                    )
                source_id = str(raw_source_id)
                if source_id in seen:
                    raise ValueError(
                        f"RINMP input contract: reused or missing {dataset} source ID"
                    )
                seen.add(source_id)
                locator = f"data/records/{index}" if dataset != "statistics" else "data"
                observation_id = stable_id(
                    "obs", "rinmp", dataset, source_id, metadata["sha256"]
                )
                self.add(
                    "source_observations",
                    observation_id=observation_id,
                    dataset=dataset,
                    source_id=source_id,
                    source_key=self.source_key(dataset, source_id),
                    raw_file=metadata["file"],
                    row_locator=locator,
                    file_sha256=metadata["sha256"],
                    captured_at=metadata["captured_at"],
                    run_id=metadata["run_id"],
                    record_type=row.get("record_type", record_type),
                    disposition="retained_once_at_source_grain",
                )
                if dataset == "app_tech":
                    self.observation_by_app_id[int(source_id)] = observation_id
                elif dataset == "owner_profiles":
                    self.observation_by_owner_key[source_id] = observation_id
                else:
                    self.statistics_observation_id = observation_id
        self.apps = self.payloads["app_tech.json"]["data"]["records"]
        self.owners = self.payloads["owner_profiles.json"]["data"]["records"]
        self.statistics = self.payloads["statistics.json"]["data"]
        self.app_by_id = {row["id"]: row for row in self.apps}
        self.app_index_by_id = {row["id"]: index for index, row in enumerate(self.apps)}
        self.owner_index_by_key = {row["owner_key"]: index for row in self.owners}

    def build_innovation_identities(self):
        # Each reviewed candidate partitions its members into complete identities.
        # Different groups in one partition are protected separation boundaries.
        component_by_source = {row["id"]: [row["id"]] for row in self.apps}
        reviewed_sources = set()
        for case in self.config["title_candidate_groups"]:
            ids = case["source_ids"]
            if case["decision"] == "must_link":
                groups = [ids]
            elif case["decision"] == "partition":
                groups = case["identity_groups"]
            elif case["decision"] in {"cannot_link", "unresolved"}:
                groups = [[source_id] for source_id in ids]
            else:
                raise AssertionError(f"Unknown identity decision: {case['decision']}")
            flattened = [source_id for group in groups for source_id in group]
            if (
                not all(groups)
                or sorted(flattened) != sorted(ids)
                or len(set(flattened)) != len(flattened)
                or reviewed_sources.intersection(ids)
            ):
                raise AssertionError(
                    f"Invalid or overlapping identity partition: {ids}"
                )
            reviewed_sources.update(ids)
            for group in groups:
                for source_id in group:
                    component_by_source[source_id] = sorted(group)

        case_by_source = {}
        for case in self.config["title_candidate_groups"]:
            for source_id in case["source_ids"]:
                case_by_source[source_id] = case

        emitted = set()
        for row in self.apps:
            members = component_by_source[row["id"]]
            member_key = tuple(members)
            innovation_id = stable_id("innovation", "rinmp", *members)
            for source_id in members:
                self.innovation_by_source_id[source_id] = innovation_id
            if member_key in emitted:
                continue
            emitted.add(member_key)
            member_rows = [self.app_by_id[source_id] for source_id in members]
            titles = list(
                dict.fromkeys(normalize(item["title"]) for item in member_rows)
            )
            observations = [
                self.observation_by_app_id[source_id] for source_id in members
            ]
            readiness_values = [item["trl"]["level"] for item in member_rows]
            case = case_by_source.get(members[0])
            if case is None:
                candidate_status = "no_exact_title_candidate"
            elif case["decision"] == "must_link" or (
                case["decision"] == "partition" and len(members) > 1
            ):
                candidate_status = "reviewed_supported_group"
            elif case["decision"] in {"cannot_link", "partition"}:
                candidate_status = "reviewed_separate"
            else:
                candidate_status = "reviewed_unresolved"
            self.add(
                "innovations",
                innovation_id=innovation_id,
                display_name=titles[0],
                aliases_json=dump(titles),
                source_ids_json=dump(members),
                source_observation_ids_json=dump(observations),
                identity_status=(
                    "supported_multi_profile_identity"
                    if len(members) > 1
                    else "provisional_listing"
                ),
                candidate_status=candidate_status,
                readiness_conflict=(
                    "True"
                    if len({value for value in readiness_values if value is not None})
                    > 1
                    else "False"
                ),
                ready_qualification=(
                    "qualifies_from_at_least_one_numeric_trl_8_9"
                    if any(value in {8, 9} for value in readiness_values)
                    else "does_not_qualify_from_numeric_trl"
                ),
            )

        for case in self.config["title_candidate_groups"]:
            ids = case["source_ids"]
            rows = [self.app_by_id[source_id] for source_id in ids]
            title = normalize(rows[0]["title"])
            if any(normalize(row["title"]) != title for row in rows):
                raise AssertionError(
                    f"Configured title group has differing titles: {ids}"
                )
            descriptions = {
                source_id: " ".join(
                    normalize(section["text"])
                    for section in self.app_by_id[source_id]["description_sections"]
                )
                for source_id in ids
            }
            for marker in case.get("required_shared_markers", []):
                missing = [
                    source_id
                    for source_id in ids
                    if marker not in descriptions[source_id]
                ]
                if missing:
                    raise AssertionError(
                        f"Candidate rule {case['rule']} missing marker {marker!r} in {missing}"
                    )
            observations = [self.observation_by_app_id[source_id] for source_id in ids]
            locators = [
                self.raw_locator(
                    "app_tech.json", f"data/records/{self.app_index_by_id[i]}"
                )
                for i in ids
            ]
            potential_broader = len(ids) - 1 if case["decision"] == "unresolved" else 0
            qualifying = sum(self.app_by_id[i]["trl"]["level"] in {8, 9} for i in ids)
            potential_k04 = (
                max(0, qualifying - 1) if case["decision"] == "unresolved" else 0
            )
            self.add(
                "identity_decisions",
                decision_id=stable_id("decision", "rinmp_title", *ids),
                source_ids_json=dump(ids),
                title_raw=rows[0]["title"],
                decision=case["decision"],
                review_state=case["review_state"],
                rule=case["rule"],
                reason=case["reason"],
                evidence_observation_ids_json=dump(observations),
                evidence_locators_json=dump(locators),
                possible_broader_count_reduction=potential_broader,
                possible_k04_count_reduction=potential_k04,
            )
            self.add_review_case(
                "innovation_identity_candidate",
                ids,
                [rows[0]["title"]],
                case["decision"],
                case["review_state"],
                case["rule"],
                case["reason"],
                ["K04_ready_innovations", "broader_listed_innovations"],
                locators,
            )

    def build_profile_facts(self):
        explicit_people = {
            (item["source_id"], item["section_index"]): item
            for item in self.config["explicit_named_people"]
        }
        people_emitted = set()
        for index, row in enumerate(self.apps):
            source_id = row["id"]
            innovation_id = self.innovation_by_source_id[source_id]
            observation_id = self.observation_by_app_id[source_id]
            source_key = self.source_key("app_tech", source_id)
            base = f"data/records/{index}"
            self.add(
                "innovation_profiles",
                innovation_id=innovation_id,
                observation_id=observation_id,
                source_key=source_key,
                source_id=source_id,
                title_raw=row["title"],
                title_normalized=normalize(row["title"]),
                owner_display_name_raw=row["owner_display_name"],
                institute_source_id=row["institute"]["id"],
                institute_name_raw=row["institute"]["name"],
                category_raw=row["category"],
                sub_category_raw=row["sub_category"],
                industrial_type_raw=scalar(row["industrial_type_raw"]),
                status_raw=row["status"],
                is_recommend_raw=str(row["is_recommend"]),
                detail_url=row["detail_url"],
                tags_json=dump(row["tags"]),
                target_segments_json=dump(row["target_segments"]),
                province_resolved_raw=scalar(row["province_resolved"]),
                source_created_at=row["source_created_at"],
                source_last_update_at=row["source_last_update_at"],
            )

            for section_index, section in enumerate(row["description_sections"]):
                section_id = stable_id("section", observation_id, section_index)
                locator = self.raw_locator(
                    "app_tech.json", f"{base}/description_sections/{section_index}"
                )
                self.section_id_by_app_label[(source_id, section["label"])].append(
                    section_id
                )
                evidence_text = safe_text(readable(section["text"]))
                self.add(
                    "description_sections",
                    section_id=section_id,
                    innovation_id=innovation_id,
                    observation_id=observation_id,
                    source_key=source_key,
                    section_index=section_index,
                    label_raw=section["label"],
                    text_readable=evidence_text,
                    source_locator=locator,
                )
                for role, terms in ROLE_TERMS.items():
                    found = sorted({term for term in terms if term in section["text"]})
                    if not found:
                        continue
                    person_item = explicit_people.get((source_id, section_index))
                    person_id = ""
                    if person_item and role in {"creator_or_inventor", "developer"}:
                        person_id = stable_id(
                            "person", "rinmp", normalize(person_item["name"])
                        )
                    self.add(
                        "narrative_role_mentions",
                        mention_id=stable_id("mention", section_id, role),
                        innovation_id=innovation_id,
                        observation_id=observation_id,
                        source_key=source_key,
                        section_id=section_id,
                        role=role,
                        matched_terms_json=dump(found),
                        named_person_id=person_id,
                        eligibility_treatment=(
                            "named_role_evidence_retained"
                            if person_id
                            else "unnamed_role_context_no_person_created"
                        ),
                        evidence_text=evidence_text,
                        source_locator=locator,
                    )

                person_item = explicit_people.get((source_id, section_index))
                if person_item:
                    person_id = stable_id(
                        "person", "rinmp", normalize(person_item["name"])
                    )
                    if person_id not in people_emitted:
                        people_emitted.add(person_id)
                        broader = (
                            "eligible_explicit_inventor"
                            if person_item["role"] == "inventor_and_developer"
                            else "not_eligible_creator_role_only"
                        )
                        self.add(
                            "people",
                            person_id=person_id,
                            display_name=person_item["name"],
                            aliases_json=dump([person_item["name"]]),
                            identity_status="explicitly_named_in_narrative",
                            community_innovator_eligibility="not_eligible_no_community_role",
                            broader_innovator_eligibility=broader,
                        )
                    self.add(
                        "person_role_assertions",
                        role_assertion_id=stable_id(
                            "person_role", person_id, observation_id
                        ),
                        person_id=person_id,
                        innovation_id=innovation_id,
                        observation_id=observation_id,
                        source_key=source_key,
                        role=person_item["role"],
                        confidence="explicit_name_and_role_in_passage",
                        evidence_text=evidence_text,
                        source_locator=locator,
                    )

            trl = row["trl"]
            trl_level = trl["level"]
            self.add(
                "readiness_assertions",
                assertion_id=stable_id("readiness", observation_id, "trl"),
                innovation_id=innovation_id,
                observation_id=observation_id,
                source_key=source_key,
                source_id=source_id,
                scale="TRL",
                value_raw=scalar(trl["raw"]),
                numeric_level=scalar(trl_level),
                validity="valid_numeric" if trl_level in range(1, 10) else "unknown",
                qualifies_k04=str(trl_level in {8, 9}),
                assessment_context="source_profile_reported_technology_readiness",
                source_locator=self.raw_locator("app_tech.json", f"{base}/trl"),
            )
            self.add(
                "readiness_assertions",
                assertion_id=stable_id("readiness", observation_id, "atl"),
                innovation_id=innovation_id,
                observation_id=observation_id,
                source_key=source_key,
                source_id=source_id,
                scale="ATL",
                value_raw=row["atl_level"],
                numeric_level="",
                validity="retained_unmapped_letter",
                qualifies_k04="False",
                assessment_context="source_profile_reported_atl_no_trl_crosswalk",
                source_locator=self.raw_locator("app_tech.json", f"{base}/atl_level"),
            )

            if row["matrix_scores"] is not None:
                scores = row["matrix_scores"]
                self.add(
                    "matrix_scores",
                    matrix_score_id=stable_id("matrix", observation_id),
                    innovation_id=innovation_id,
                    observation_id=observation_id,
                    source_key=source_key,
                    ease_cost_score=scores["easeCostMatrixScore"],
                    impact_3e_score=scores["impact3EMatrixScore"],
                    local_tech_score=scalar(scores["localTechMatrixScore"]),
                    average_score=scores["matrixScoreAverage"],
                    tech_efficiency_score=scores["techEfficiencyMatrixScore"],
                    interpretation="source_reported_matrix_not_readiness_fallback",
                    source_locator=self.raw_locator(
                        "app_tech.json", f"{base}/matrix_scores"
                    ),
                )

            commercial = row["commercial"]
            self.add(
                "commercial_assertions",
                assertion_id=stable_id("commercial", observation_id),
                innovation_id=innovation_id,
                observation_id=observation_id,
                source_key=source_key,
                budget_thb=scalar(commercial["budget_thb"]),
                cost_per_unit_thb=scalar(commercial["cost_per_unit_thb"]),
                life_time_year_count=scalar(commercial["life_time_year_count"]),
                interpretation="separate_source_claims_not_additive",
                source_locator=self.raw_locator("app_tech.json", f"{base}/commercial"),
            )
            ip = row["ip"]
            number = ip["number_raw"]
            if number is None:
                identifier_status = "missing"
            elif re.search(r"\d", str(number)):
                identifier_status = "reported_text_contains_digits_unverified"
            else:
                identifier_status = "reported_pending_or_non_numeric_text"
            self.add(
                "ip_assertions",
                assertion_id=stable_id("ip", observation_id),
                innovation_id=innovation_id,
                observation_id=observation_id,
                source_key=source_key,
                category_raw=ip["category"],
                number_raw=scalar(number),
                identifier_status=identifier_status,
                source_locator=self.raw_locator("app_tech.json", f"{base}/ip"),
            )
            certificate = row["certificate"]
            self.add(
                "certificate_assertions",
                assertion_id=stable_id("certificate", observation_id),
                innovation_id=innovation_id,
                observation_id=observation_id,
                source_key=source_key,
                level_raw=scalar(certificate["level_raw"]),
                expired_datetime_raw=scalar(certificate["expired_datetime"]),
                interpretation="source_claim_not_independently_validated_or_readiness",
                source_locator=self.raw_locator("app_tech.json", f"{base}/certificate"),
            )

            media = row["media"]
            if media["profile_picture_file_id"] is not None:
                self.add(
                    "media_references",
                    media_reference_id=stable_id("media", observation_id, "profile"),
                    innovation_id=innovation_id,
                    observation_id=observation_id,
                    source_key=source_key,
                    media_role="profile_picture",
                    media_index="",
                    file_id=media["profile_picture_file_id"],
                    inspection_status="reference_retained_content_not_inspected",
                    source_locator=self.raw_locator(
                        "app_tech.json", f"{base}/media/profile_picture_file_id"
                    ),
                )
            for media_index, file_id in enumerate(media["gallery_file_ids"]):
                self.add(
                    "media_references",
                    media_reference_id=stable_id(
                        "media", observation_id, "gallery", media_index
                    ),
                    innovation_id=innovation_id,
                    observation_id=observation_id,
                    source_key=source_key,
                    media_role="gallery",
                    media_index=media_index,
                    file_id=file_id,
                    inspection_status="reference_retained_content_not_inspected",
                    source_locator=self.raw_locator(
                        "app_tech.json", f"{base}/media/gallery_file_ids/{media_index}"
                    ),
                )

    def build_institutes(self):
        catalogue_counts = Counter(row["institute"]["name"] for row in self.apps)
        reported_counts = {
            row["institute"]: row["count"] for row in self.statistics["institute_graph"]
        }
        source_ids = {}
        for row in self.apps:
            source_ids.setdefault(row["institute"]["name"], row["institute"]["id"])
        institute_id_by_name = {}
        for name in sorted(set(catalogue_counts) | set(reported_counts)):
            institute_id = stable_id("institute", "rinmp", name)
            institute_id_by_name[name] = institute_id
            catalogue = catalogue_counts.get(name, 0)
            reported = reported_counts.get(name, 0)
            self.add(
                "institutes",
                institute_id=institute_id,
                source_institute_id=scalar(source_ids.get(name)),
                name_raw=name,
                catalogue_profile_count=catalogue,
                statistics_reported_count=reported,
                reconciliation_status=(
                    "matched" if catalogue == reported else "mismatch"
                ),
            )
        for index, row in enumerate(self.apps):
            source_id = row["id"]
            observation_id = self.observation_by_app_id[source_id]
            self.add(
                "institute_assertions",
                assertion_id=stable_id("institute_assertion", observation_id),
                innovation_id=self.innovation_by_source_id[source_id],
                observation_id=observation_id,
                source_key=self.source_key("app_tech", source_id),
                institute_id=institute_id_by_name[row["institute"]["name"]],
                source_institute_id=row["institute"]["id"],
                name_raw=row["institute"]["name"],
                role="profile_affiliated_institute",
                coverage_eligibility="not_eligible_from_institution_affiliation_alone",
                source_locator=self.raw_locator(
                    "app_tech.json", f"data/records/{index}/institute"
                ),
            )

    def resolve_address(self, address):
        resolved = self.geo.resolve(address.get("province"), address.get("district"))
        subdistrict_raw = address.get("sub_district") or ""
        subdistrict = strip_admin_prefix(subdistrict_raw, ["ตำบล", "ต.", "แขวง"])
        district_raw = address.get("district") or ""
        if resolved["district_code"] and subdistrict:
            matches = [
                item
                for item in self.geo.subdistricts
                if str(item["districtCode"]) == resolved["district_code"]
                and item["subdistrictNameTh"] == subdistrict
            ]
            if len(matches) == 1:
                resolved["subdistrict_normalized"] = subdistrict
                resolved["subdistrict_code"] = str(matches[0]["subdistrictCode"])
            elif resolved["status"] in {
                "hierarchy_match",
                "province_corrected_from_unique_district",
            }:
                resolved["status"] = "unresolved_subdistrict"
                resolved["correction_reason"] = (
                    "District retained; subdistrict does not match that district in the pinned reference"
                )
        elif not district_raw and subdistrict and resolved["province_code"]:
            matches = [
                item
                for item in self.geo.subdistricts
                if str(item["provinceCode"]) == resolved["province_code"]
                and item["subdistrictNameTh"] == subdistrict
            ]
            if len(matches) == 1:
                match = matches[0]
                parent = next(
                    item
                    for item in self.geo.districts
                    if str(item["districtCode"]) == str(match["districtCode"])
                )
                resolved["district_normalized"] = parent["districtNameTh"]
                resolved["district_code"] = str(parent["districtCode"])
                resolved["subdistrict_normalized"] = subdistrict
                resolved["subdistrict_code"] = str(match["subdistrictCode"])
                resolved["status"] = (
                    "district_filled_from_unique_subdistrict_within_province"
                )
                resolved["correction_reason"] = (
                    "District was absent; subdistrict is unique within the stated province"
                )
        return resolved

    def coverage_passages(self, row):
        passages = []
        for section_index, section in enumerate(row["description_sections"]):
            text = normalize(section["text"])
            is_target = section["label"] == "targetUserAddressDetail"
            is_use = any(phrase in text for phrase in STRONG_USE_PHRASES)
            if not is_target and not is_use:
                continue
            negative = any(phrase in text for phrase in NEGATIVE_COVERAGE_PHRASES)
            substantive = bool(text and text != "-")
            passages.append(
                {
                    "section_index": section_index,
                    "section": section,
                    "negative": negative,
                    "substantive": substantive,
                    "passage_role": (
                        "target_user_address_passage"
                        if is_target
                        else "explicit_use_passage"
                    ),
                }
            )
        return passages

    def marked_admin_names(self, text, prefixes):
        matches = []
        for prefix in prefixes:
            start = 0
            while True:
                position = text.find(prefix, start)
                if position < 0:
                    break
                remainder = text[position + len(prefix) :].lstrip()
                name = re.split(
                    r"[\s,;:()/]|จังหวัด|อำเภอ|ตำบล|จ\.|อ\.|ต\.|เขต|แขวง",
                    remainder,
                    maxsplit=1,
                )[0].rstrip(".ๆฯ")
                if name:
                    matches.append((position, name))
                start = position + len(prefix)
        return [name for _, name in sorted(matches)]

    def extract_passage_locations(self, passage):
        claims = []
        for line_index, line in enumerate(passage["section"]["text"].splitlines()):
            text = normalize(line)
            if not text:
                continue
            province_names = self.marked_admin_names(text, ["จังหวัด", "จ."])
            district_names = self.marked_admin_names(text, ["อำเภอ", "อ.", "เขต"])
            subdistrict_names = self.marked_admin_names(text, ["ตำบล", "ต.", "แขวง"])
            resolved_provinces = []
            for province_name in province_names:
                resolved = self.geo.resolve(province_name, None)
                resolved_provinces.append((province_name, resolved))

            if len(resolved_provinces) == 1 and district_names:
                province_raw = resolved_provinces[0][0]
                for district_name in district_names:
                    resolved = self.geo.resolve(province_raw, district_name)
                    claims.append(
                        self.passage_location_claim(
                            line_index,
                            province_raw,
                            district_name,
                            subdistrict_names,
                            resolved,
                        )
                    )
            elif resolved_provinces:
                for province_raw, resolved in resolved_provinces:
                    claims.append(
                        self.passage_location_claim(
                            line_index, province_raw, "", [], resolved
                        )
                    )
                for district_name in district_names:
                    claims.append(
                        self.passage_location_claim(
                            line_index,
                            "",
                            district_name,
                            subdistrict_names,
                            self.geo.resolve("", district_name),
                        )
                    )
            else:
                for district_name in district_names:
                    normalized_district = strip_admin_prefix(
                        district_name, ["อำเภอ", "อ.", "เขต"]
                    )
                    matches = [
                        item
                        for item in self.geo.districts
                        if item["districtNameTh"] == normalized_district
                    ]
                    if len(matches) == 1:
                        match = matches[0]
                        province_raw = next(
                            item["provinceNameTh"]
                            for item in self.geo.provinces
                            if item["provinceCode"] == match["provinceCode"]
                        )
                        resolved = self.geo.resolve(province_raw, district_name)
                    else:
                        province_raw = ""
                        resolved = self.geo.resolve("", district_name)
                    claims.append(
                        self.passage_location_claim(
                            line_index,
                            province_raw,
                            district_name,
                            subdistrict_names,
                            resolved,
                        )
                    )
                if not district_names:
                    for subdistrict_name in subdistrict_names:
                        normalized_subdistrict = strip_admin_prefix(
                            subdistrict_name, ["ตำบล", "ต.", "แขวง"]
                        )
                        matches = [
                            item
                            for item in self.geo.subdistricts
                            if item["subdistrictNameTh"] == normalized_subdistrict
                        ]
                        if len(matches) == 1:
                            subdistrict = matches[0]
                            district = next(
                                item
                                for item in self.geo.districts
                                if item["districtCode"] == subdistrict["districtCode"]
                            )
                            province_raw = next(
                                item["provinceNameTh"]
                                for item in self.geo.provinces
                                if item["provinceCode"] == subdistrict["provinceCode"]
                            )
                            resolved = self.resolve_address(
                                {
                                    "province": province_raw,
                                    "district": district["districtNameTh"],
                                    "sub_district": subdistrict_name,
                                }
                            )
                            district_raw = district["districtNameTh"]
                        else:
                            province_raw = ""
                            district_raw = ""
                            resolved = self.geo.resolve("", "")
                        claims.append(
                            {
                                "line_index": line_index,
                                "province_raw": province_raw,
                                "district_raw": district_raw,
                                "subdistrict_raw": subdistrict_name,
                                "resolved": resolved,
                            }
                        )

        unique_claims = {}
        for claim in claims:
            key = (
                claim["line_index"],
                claim["province_raw"],
                claim["district_raw"],
                claim["subdistrict_raw"],
            )
            unique_claims[key] = claim
        return list(unique_claims.values())

    def passage_location_claim(
        self, line_index, province_raw, district_raw, subdistrict_names, resolved
    ):
        subdistrict_raw = subdistrict_names[0] if len(subdistrict_names) == 1 else ""
        if subdistrict_raw:
            resolved = self.resolve_address(
                {
                    "province": province_raw,
                    "district": district_raw,
                    "sub_district": subdistrict_raw,
                }
            )
        return {
            "line_index": line_index,
            "province_raw": province_raw,
            "district_raw": district_raw,
            "subdistrict_raw": subdistrict_raw,
            "resolved": resolved,
        }

    def address_passage_match(self, address, passages):
        party = normalize(address.get("name"))
        province = strip_admin_prefix(address.get("province"), ["จังหวัด", "จ."])
        district = strip_admin_prefix(address.get("district"), ["อำเภอ", "อ.", "เขต"])
        subdistrict = strip_admin_prefix(
            address.get("sub_district"), ["ตำบล", "ต.", "แขวง"]
        )
        for passage in passages:
            if passage["negative"] or not passage["substantive"]:
                continue
            text = normalize(passage["section"]["text"])
            party_match = bool(party and len(party) >= 6 and party in text)
            province_match = bool(province and province in text)
            district_match = bool(district and len(district) >= 3 and district in text)
            subdistrict_match = bool(
                subdistrict and len(subdistrict) >= 3 and subdistrict in text
            )
            hierarchy_match = (
                province_match and (district_match or subdistrict_match)
            ) or (district_match and subdistrict_match)
            if party_match or hierarchy_match:
                return (
                    passage,
                    "party_name_match"
                    if party_match
                    else "administrative_hierarchy_match",
                )
        return None, ""

    def build_locations(self):
        for index, row in enumerate(self.apps):
            source_id = row["id"]
            observation_id = self.observation_by_app_id[source_id]
            innovation_id = self.innovation_by_source_id[source_id]
            source_key = self.source_key("app_tech", source_id)
            passages = self.coverage_passages(row)
            negative = any(passage["negative"] for passage in passages)

            for address_index, address in enumerate(row["addresses"]):
                resolved = self.resolve_address(address)
                matching_passage, match_basis = self.address_passage_match(
                    address, passages
                )
                evidence_section_id = ""
                if matching_passage:
                    evidence_section_id = stable_id(
                        "section", observation_id, matching_passage["section_index"]
                    )
                if negative:
                    address_role = "address_conflicts_with_explicit_no_use_passage"
                    coverage = "excluded_explicit_no_use"
                elif matching_passage:
                    address_role = f"target_or_use_address_{match_basis}"
                    coverage = "eligible_programme_target_or_use_coverage"
                else:
                    address_role = "unclassified_profile_address"
                    coverage = "context_only_role_not_supported"
                locator = self.raw_locator(
                    "app_tech.json", f"data/records/{index}/addresses/{address_index}"
                )
                self.add(
                    "location_assertions",
                    location_id=stable_id(
                        "location", observation_id, "address", address_index
                    ),
                    innovation_id=innovation_id,
                    observation_id=observation_id,
                    source_key=source_key,
                    assertion_kind="structured_address",
                    address_index=address_index,
                    location_role=address_role,
                    party_name_raw=scalar(address.get("name")),
                    province_raw=address["province"],
                    district_raw=scalar(address.get("district")),
                    subdistrict_raw=scalar(address.get("sub_district")),
                    province_normalized=resolved["province_normalized"],
                    province_code=resolved["province_code"],
                    district_normalized=resolved["district_normalized"],
                    district_code=resolved["district_code"],
                    subdistrict_normalized=resolved["subdistrict_normalized"],
                    subdistrict_code=resolved["subdistrict_code"],
                    resolution_status=resolved["status"],
                    correction_reason=resolved["correction_reason"],
                    coverage_eligibility=coverage,
                    evidence_section_id=evidence_section_id,
                    source_locator=locator,
                )

            for passage in passages:
                if passage["negative"] or not passage["substantive"]:
                    continue
                section_index = passage["section_index"]
                section_id = stable_id("section", observation_id, section_index)
                locator = self.raw_locator(
                    "app_tech.json",
                    f"data/records/{index}/description_sections/{section_index}",
                )
                for claim_index, claim in enumerate(
                    self.extract_passage_locations(passage)
                ):
                    resolved = claim["resolved"]
                    self.add(
                        "location_assertions",
                        location_id=stable_id(
                            "location",
                            observation_id,
                            "passage",
                            section_index,
                            claim["line_index"],
                            claim_index,
                        ),
                        innovation_id=innovation_id,
                        observation_id=observation_id,
                        source_key=source_key,
                        assertion_kind="narrative_target_or_use_place",
                        address_index="",
                        location_role=passage["passage_role"],
                        party_name_raw="",
                        province_raw=claim["province_raw"],
                        district_raw=claim["district_raw"],
                        subdistrict_raw=claim["subdistrict_raw"],
                        province_normalized=resolved["province_normalized"],
                        province_code=resolved["province_code"],
                        district_normalized=resolved["district_normalized"],
                        district_code=resolved["district_code"],
                        subdistrict_normalized=resolved["subdistrict_normalized"],
                        subdistrict_code=resolved["subdistrict_code"],
                        resolution_status=resolved["status"],
                        correction_reason=resolved["correction_reason"],
                        coverage_eligibility="eligible_programme_target_or_use_coverage",
                        evidence_section_id=section_id,
                        source_locator=locator,
                    )

            province = row["province_resolved"]
            province_resolved = (
                self.geo.resolve(province, None)
                if province
                else {
                    "province_normalized": "",
                    "province_code": "",
                    "district_normalized": "",
                    "district_code": "",
                    "subdistrict_normalized": "",
                    "subdistrict_code": "",
                    "status": "unknown_province",
                    "correction_reason": "",
                }
            )
            if negative:
                province_coverage = "excluded_explicit_no_use"
            elif row["addresses"]:
                province_coverage = "supporting_duplicate_not_separate_contribution"
            else:
                province_coverage = "context_only_collector_resolution"
            self.add(
                "location_assertions",
                location_id=stable_id("location", observation_id, "province_resolved"),
                innovation_id=innovation_id,
                observation_id=observation_id,
                source_key=source_key,
                assertion_kind="collector_resolved_province",
                address_index="",
                location_role="collector_derived_profile_province",
                party_name_raw="",
                province_raw=scalar(province),
                district_raw="",
                subdistrict_raw="",
                province_normalized=province_resolved["province_normalized"],
                province_code=province_resolved["province_code"],
                district_normalized="",
                district_code="",
                subdistrict_normalized="",
                subdistrict_code="",
                resolution_status=province_resolved["status"],
                correction_reason=province_resolved["correction_reason"],
                coverage_eligibility=province_coverage,
                evidence_section_id="",
                source_locator=self.raw_locator(
                    "app_tech.json", f"data/records/{index}/province_resolved"
                ),
            )

    def build_owner_groups(self):
        accepted = self.config["accepted_owner_uncertainty"]
        for owner_index, owner in enumerate(self.owners):
            observation_id = self.observation_by_owner_key[owner["owner_key"]]
            owner_group_id = stable_id("owner_group", "rinmp", owner["owner_key"])
            identity_status = (
                "accepted_underlying_identity_unresolved"
                if owner["owner_key"] == accepted["owner_key"]
                else "collector_group_not_verified_person"
            )
            self.add(
                "owner_groups",
                owner_group_id=owner_group_id,
                observation_id=observation_id,
                owner_key=owner["owner_key"],
                fullname_raw=owner["fullname"],
                name_normalized=normalize(owner["fullname"]),
                institute_raw=owner["institute"],
                linked_app_count=len(owner["app_tech_ids"]),
                title_claim_count=len(owner["app_tech_titles"]),
                underlying_identity_status=identity_status,
                person_id="",
            )
            for link_index, app_source_id in enumerate(owner["app_tech_ids"]):
                app = self.app_by_id.get(app_source_id)
                app_observation_id = self.observation_by_app_id.get(app_source_id, "")
                owner_link_id = stable_id(
                    "owner_link", owner["owner_key"], app_source_id, link_index
                )
                locator = self.raw_locator(
                    "owner_profiles.json",
                    f"data/records/{owner_index}/app_tech_ids/{link_index}",
                )
                self.add(
                    "owner_technology_links",
                    owner_link_id=owner_link_id,
                    owner_group_id=owner_group_id,
                    owner_observation_id=observation_id,
                    owner_key=owner["owner_key"],
                    innovation_id=(
                        self.innovation_by_source_id[app_source_id] if app else ""
                    ),
                    app_observation_id=app_observation_id,
                    app_source_id=app_source_id,
                    link_index=link_index,
                    endpoint_status="resolved_internal_app_profile"
                    if app
                    else "unresolved_external_app_id",
                    source_locator=locator,
                )
                if not app:
                    continue
                group_locator = self.raw_locator(
                    "owner_profiles.json", f"data/records/{owner_index}/fullname"
                )
                app_index = self.app_index_by_id[app_source_id]
                app_locator = self.raw_locator(
                    "app_tech.json", f"data/records/{app_index}/owner_display_name"
                )
                claims = [
                    ("collector_owner_group", owner["fullname"], group_locator),
                    (
                        "app_profile_owner_display",
                        app["owner_display_name"],
                        app_locator,
                    ),
                ]
                for origin, name, name_locator in claims:
                    self.add(
                        "owner_name_claims",
                        name_claim_id=stable_id(
                            "owner_name_claim", owner_link_id, origin
                        ),
                        owner_link_id=owner_link_id,
                        owner_group_id=owner_group_id,
                        app_source_id=app_source_id,
                        claim_origin=origin,
                        name_raw=name,
                        name_normalized=normalize(name),
                        role="owner_or_rights_holder_label",
                        natural_person_status="unconfirmed_from_owner_evidence",
                        source_locator=name_locator,
                    )
                if normalize(owner["fullname"]) != normalize(app["owner_display_name"]):
                    self.add(
                        "owner_name_disagreements",
                        disagreement_id=stable_id(
                            "owner_name_disagreement", owner_link_id
                        ),
                        owner_link_id=owner_link_id,
                        owner_group_id=owner_group_id,
                        owner_key=owner["owner_key"],
                        app_source_id=app_source_id,
                        group_name_raw=owner["fullname"],
                        app_name_raw=app["owner_display_name"],
                        group_name_normalized=normalize(owner["fullname"]),
                        app_name_normalized=normalize(app["owner_display_name"]),
                        treatment="independent_claims_retained_no_person_merge",
                        evidence_locators_json=dump([group_locator, app_locator]),
                    )

            for title_index, title in enumerate(owner["app_tech_titles"]):
                matches = [
                    app_id
                    for app_id in owner["app_tech_ids"]
                    if normalize(self.app_by_id[app_id]["title"]) == normalize(title)
                ]
                status = (
                    "unique_exact_title_reconciliation"
                    if len(matches) == 1
                    else "ambiguous_repeated_title_claim"
                    if len(matches) > 1
                    else "unresolved_title_claim"
                )
                self.add(
                    "owner_title_claims",
                    title_claim_id=stable_id(
                        "owner_title_claim", owner["owner_key"], title_index
                    ),
                    owner_group_id=owner_group_id,
                    owner_observation_id=observation_id,
                    owner_key=owner["owner_key"],
                    title_index=title_index,
                    title_raw=title,
                    title_normalized=normalize(title),
                    matched_app_source_ids_json=dump(matches),
                    reconciliation_status=status,
                    source_locator=self.raw_locator(
                        "owner_profiles.json",
                        f"data/records/{owner_index}/app_tech_titles/{title_index}",
                    ),
                )

        owner = next(
            item for item in self.owners if item["owner_key"] == accepted["owner_key"]
        )
        owner_index = self.owner_index_by_key[owner["owner_key"]]
        self.add_review_case(
            "owner_underlying_identity",
            accepted["app_tech_ids"],
            [accepted["fullname"]],
            accepted["decision"],
            "reviewed_unresolved",
            "user_confirmed_incomplete_name_across_institutes",
            accepted["reason"],
            ["K02_community_innovators", "broader_innovators"],
            [self.raw_locator("owner_profiles.json", f"data/records/{owner_index}")],
        )

    def add_review_case(
        self,
        case_type,
        source_ids,
        names,
        status,
        review_state,
        treatment,
        reason,
        affected_measures,
        evidence_locators,
    ):
        self.add(
            "review_cases",
            review_id=stable_id("review", "rinmp", case_type, *source_ids),
            case_type=case_type,
            source_ids_json=dump(source_ids),
            names_json=dump(names),
            status=status,
            review_state=review_state,
            treatment=treatment,
            reason=reason,
            affected_measures_json=dump(affected_measures),
            evidence_locators_json=dump(evidence_locators),
        )

    def build_aggregates(self):
        metric_specs = [
            (
                "total_app_tech_count",
                "technologies",
                "catalogue profiles",
                True,
                len(self.apps),
            ),
            (
                "institute_count",
                "institutes",
                "institutes",
                True,
                len(self.tables["institutes"]),
            ),
            (
                "innovator_count",
                "labelled innovators",
                "collector owner groups",
                True,
                len(self.owners),
            ),
            ("normal_user_count", "normal users", "people", False, None),
            ("requirement_count", "requirements", "requirements", False, None),
            ("match_requirement_count", "matched requirements", "matches", False, None),
        ]
        for metric, label, unit, recomputable, recomputed in metric_specs:
            value = self.statistics[metric]
            status = (
                "matched_recomputed_source_grain"
                if recomputable and value == recomputed
                else "mismatch"
                if recomputable
                else "source_reported_not_recomputable_from_supplied_rows"
            )
            interpretation = (
                "The innovator label numerically matches collector owner groups but does not establish people or eligible innovator roles."
                if metric == "innovator_count"
                else "Retained as a source-reported aggregate; no row-level population is fabricated."
            )
            self.add(
                "aggregate_metrics",
                aggregate_metric_id=stable_id("aggregate_metric", "rinmp", metric),
                observation_id=self.statistics_observation_id,
                metric=metric,
                population_label=label,
                value=value,
                unit=unit,
                recomputable=str(recomputable),
                recomputed_value=scalar(recomputed),
                reconciliation_status=status,
                interpretation=interpretation,
                source_locator=self.raw_locator("statistics.json", f"data/{metric}"),
            )
        catalogue_counts = Counter(row["institute"]["name"] for row in self.apps)
        for index, component in enumerate(self.statistics["institute_graph"]):
            recomputed = catalogue_counts[component["institute"]]
            self.add(
                "aggregate_components",
                component_id=stable_id("aggregate_component", "rinmp", index),
                observation_id=self.statistics_observation_id,
                metric="total_app_tech_count_by_institute",
                component_index=index,
                institute_raw=component["institute"],
                reported_count=component["count"],
                recomputed_count=recomputed,
                reconciliation_status=(
                    "matched" if component["count"] == recomputed else "mismatch"
                ),
                source_locator=self.raw_locator(
                    "statistics.json", f"data/institute_graph/{index}"
                ),
            )

    def build_pending_links(self):
        source_id = 636
        for item in self.config["pending_cross_source_links"]:
            observation_id = self.observation_by_app_id[source_id]
            self.add(
                "pending_cross_source_decisions",
                decision_id=stable_id(
                    "pending",
                    "rinmp",
                    source_id,
                    item["other_source"],
                    item["other_source_id"],
                ),
                rinmp_source_id=source_id,
                rinmp_innovation_id=self.innovation_by_source_id[source_id],
                rinmp_observation_id=observation_id,
                other_source=item["other_source"],
                other_source_id=item["other_source_id"],
                decision=item["decision"],
                union_status="pending_external_reference_not_applied",
                evidence_locator=self.raw_locator(
                    "app_tech.json", f"data/records/{self.app_index_by_id[source_id]}"
                ),
            )

    def add_quality_reviews(self):
        for source_id in [63, 594]:
            row = self.app_by_id[source_id]
            index = self.app_index_by_id[source_id]
            self.add_review_case(
                "unknown_numeric_trl",
                [source_id],
                [row["title"]],
                "retained_unknown",
                "reviewed_decided",
                "atl_not_used_as_trl_fallback",
                f"Numeric TRL is absent and ATL {row['atl_level']} has no accepted TRL crosswalk.",
                ["K04_ready_innovations"],
                [self.raw_locator("app_tech.json", f"data/records/{index}/trl")],
            )
        disagreement_locators = [
            locator
            for row in self.tables["owner_name_disagreements"]
            for locator in json.loads(row["evidence_locators_json"])
        ]
        self.add_review_case(
            "owner_display_name_disagreements",
            [row["app_source_id"] for row in self.tables["owner_name_disagreements"]],
            ["64 link-level group/display disagreements"],
            "independent_claims_retained",
            "reviewed_decided",
            "no_blanket_owner_person_consolidation",
            "Whitespace, honorific and substantive name differences remain separate claims; six compact-name differences show why punctuation removal cannot be a universal person merge rule.",
            ["K02_community_innovators", "broader_innovators"],
            disagreement_locators,
        )
        ambiguous_title_claims = [
            row
            for row in self.tables["owner_title_claims"]
            if row["reconciliation_status"] != "unique_exact_title_reconciliation"
        ]
        self.add_review_case(
            "owner_parallel_title_array",
            [row["owner_key"] for row in ambiguous_title_claims],
            [f"{len(ambiguous_title_claims)} ambiguous title claims"],
            "retained_without_positional_join",
            "reviewed_decided",
            "exact_unique_title_only",
            "The title arrays contain 620 claims for 636 ID links. Unique exact titles are reconciled; repeated titles remain attached only to the owner group instead of being zipped to IDs.",
            ["broader_listed_innovations"],
            [row["source_locator"] for row in ambiguous_title_claims],
        )
        negative_ids = self.config["coverage_negative_source_ids"]
        self.add_review_case(
            "explicit_no_use_locations",
            negative_ids,
            [self.app_by_id[source_id]["title"] for source_id in negative_ids],
            "excluded_from_programme_coverage",
            "reviewed_decided",
            "explicit_no_use_passage",
            "The source states that no group or implementation exists; province context remains retained without K01 contribution.",
            ["K01A_target_provinces"],
            [
                self.raw_locator(
                    "app_tech.json",
                    f"data/records/{self.app_index_by_id[source_id]}/description_sections",
                )
                for source_id in negative_ids
            ],
        )

    def build_measures(self):
        innovations = self.tables["innovations"]
        ready = [
            row
            for row in innovations
            if row["ready_qualification"]
            == "qualifies_from_at_least_one_numeric_trl_8_9"
        ]
        unresolved_decisions = [
            row
            for row in self.tables["identity_decisions"]
            if row["decision"] == "unresolved"
        ]
        broader_reduction = sum(
            int(row["possible_broader_count_reduction"]) for row in unresolved_decisions
        )
        ready_reduction = sum(
            int(row["possible_k04_count_reduction"]) for row in unresolved_decisions
        )

        eligible_locations = [
            row
            for row in self.tables["location_assertions"]
            if row["coverage_eligibility"]
            == "eligible_programme_target_or_use_coverage"
            and row["province_code"]
        ]
        locations_by_province = defaultdict(list)
        for row in eligible_locations:
            locations_by_province[row["province_code"]].append(row)

        supported_merge_count = sum(
            row["identity_status"] == "supported_multi_profile_identity"
            for row in innovations
        )
        unresolved_count = len(unresolved_decisions)

        self.add(
            "measure_results",
            measure="broader_listed_innovations",
            value=len(innovations),
            basis=f"Distinct source-local innovation components after {supported_merge_count} supported within-RINMP matches.",
            unit="innovations",
            assumption="Eligible unresolved candidate profiles count separately under ADR 0015.",
            status="provisional_reviewed_uncertainty",
            source_population=f"{len(self.apps)} app_tech profiles",
            supported_drilldown="innovation profiles, sections, readiness, owner groups, institutes and locations",
            supported_filters="source taxonomy, institute, reported readiness and supported location roles",
            limitations=f"{unresolved_count} unresolved candidate groups could reduce this value by up to {broader_reduction}; no cross-source union is applied.",
        )
        self.add(
            "measure_results",
            measure="K04_ready_innovations",
            value=len(ready),
            basis="Distinct source-local innovations with at least one valid numeric TRL 8 or 9 assertion.",
            unit="innovations",
            assumption="Competing same-source readiness assertions remain eligible unless supersession is established.",
            status="provisional_reviewed_uncertainty",
            source_population=f"{len(innovations)} provisional innovation components",
            supported_drilldown="readiness_assertions to innovation_profiles and source_observations",
            supported_filters="institute, TRL, source taxonomy and supported location roles",
            limitations=f"Reviewed unresolved groups could reduce this value by up to {ready_reduction}; ATL letters, status and certificates never qualify records.",
        )
        self.add(
            "measure_results",
            measure="rinmp_profile_rows_trl_8_9",
            value=sum(row["trl"]["level"] in {8, 9} for row in self.apps),
            basis="Raw app_tech profile diagnostic before identity resolution.",
            unit="profiles",
            assumption="None.",
            status="diagnostic_not_final_entity_count",
            source_population="630 app_tech profiles",
            supported_drilldown="readiness_assertions",
            supported_filters="institute, TRL and source taxonomy",
            limitations="Profiles are not distinct real-world innovation identities.",
        )
        self.add(
            "measure_results",
            measure="K01A_target_provinces",
            value=len(locations_by_province),
            basis="Distinct resolved Thai provinces from declared target/use passages or explicit use evidence.",
            unit="provinces",
            assumption="The targetUserAddressDetail field supports declared programme target coverage when it contains a non-negative passage.",
            status="provisional_source_local",
            source_population="RINMP profile target/use location assertions",
            supported_drilldown="location_assertions to innovation profiles and exact source passages",
            supported_filters="province and contributing innovation",
            limitations="Unclassified addresses, institute affiliations and collector-only province context do not contribute; unresolved province spellings remain unknown.",
        )
        self.add(
            "measure_results",
            measure="K02_community_innovators",
            value="",
            basis="Unavailable from owner groups and unnamed role mentions.",
            unit="people",
            assumption="Owner labels and the statistics innovator label do not establish community-role evidence for named people.",
            status="unavailable_unsupported_population",
            source_population="308 collector owner groups plus narrative role mentions",
            supported_drilldown="owner groups, name claims and narrative role mentions",
            supported_filters="none for a person count",
            limitations="No confirmed named community innovator population can be calculated from this folder.",
        )
        broader_people = [
            row
            for row in self.tables["people"]
            if row["broader_innovator_eligibility"] == "eligible_explicit_inventor"
        ]
        self.add(
            "measure_results",
            measure="broader_innovators",
            value=len(broader_people),
            basis="Distinct explicitly named natural people with inventor or innovator role evidence.",
            unit="people",
            assumption="Creator-only and researcher-only roles remain excluded.",
            status="partial_named_evidence_only",
            source_population="Narrative passages in 630 app_tech profiles",
            supported_drilldown="person_role_assertions to description_sections",
            supported_filters="role and linked innovation",
            limitations="Unnamed researchers and community innovators cannot create people; owner groups are excluded.",
        )

        filter_contracts = {
            "broader_listed_innovations": {
                "supported": [
                    "institute",
                    "category",
                    "sub_category",
                    "reported_trl",
                    "eligible_target_province",
                ],
                "unsupported": ["year", "named_person", "community_innovator"],
                "aggregation": "distinct innovation_id after reviewed within-source identity decisions",
            },
            "K04_ready_innovations": {
                "supported": [
                    "institute",
                    "category",
                    "sub_category",
                    "reported_trl",
                    "eligible_target_province",
                ],
                "unsupported": ["year", "named_person", "community_innovator"],
                "aggregation": "distinct innovation_id with at least one numeric TRL 8 or 9 assertion",
            },
            "rinmp_profile_rows_trl_8_9": {
                "supported": ["institute", "category", "sub_category", "reported_trl"],
                "unsupported": ["year", "person", "community_role", "geography"],
                "aggregation": "distinct app_tech source profile rows before identity resolution",
            },
            "K01A_target_provinces": {
                "supported": ["province", "institute", "category", "sub_category"],
                "unsupported": ["year", "person", "community_role"],
                "aggregation": "distinct province_code from passage-supported target or use assertions",
            },
            "K02_community_innovators": {
                "supported": [],
                "unsupported": [
                    "year",
                    "person",
                    "community_role",
                    "institute",
                    "geography",
                ],
                "aggregation": "unavailable because no supported named community-innovator population exists",
            },
            "broader_innovators": {
                "supported": ["explicit_role", "institute"],
                "unsupported": ["year", "community_role", "geography"],
                "aggregation": "distinct person_id with explicit inventor or innovator role evidence",
            },
        }
        for result in self.tables["measure_results"]:
            contract = filter_contracts[result["measure"]]
            result["definition_version"] = "rinmp-source-local-v1"
            result["snapshot_scope"] = (
                "Supplied RINMP snapshot captured "
                f"{self.payloads['app_tech.json']['scraped_at']}; no cross-source identity union"
            )
            result["supported_filters_json"] = dump(contract["supported"])
            result["unsupported_filters_json"] = dump(contract["unsupported"])
            result["unsupported_filter_policy"] = (
                "Return unavailable for unsupported selections; never return zero or allocate an overall value."
            )
            result["aggregation"] = contract["aggregation"]

        for row in innovations:
            self.add(
                "measure_contributions",
                contribution_id=stable_id(
                    "contribution", "broader_listed_innovations", row["innovation_id"]
                ),
                measure="broader_listed_innovations",
                entity_id=row["innovation_id"],
                entity_type="innovation",
                status=row["candidate_status"],
                evidence_observation_ids_json=row["source_observation_ids_json"],
                evidence_location_ids_json=dump([]),
            )
        for row in ready:
            self.add(
                "measure_contributions",
                contribution_id=stable_id(
                    "contribution", "K04_ready_innovations", row["innovation_id"]
                ),
                measure="K04_ready_innovations",
                entity_id=row["innovation_id"],
                entity_type="innovation",
                status=row["candidate_status"],
                evidence_observation_ids_json=row["source_observation_ids_json"],
                evidence_location_ids_json=dump([]),
            )
        for province_code, locations in sorted(locations_by_province.items()):
            observation_ids = sorted({row["observation_id"] for row in locations})
            location_ids = sorted({row["location_id"] for row in locations})
            self.add(
                "measure_contributions",
                contribution_id=stable_id(
                    "contribution", "K01A_target_provinces", province_code
                ),
                measure="K01A_target_provinces",
                entity_id=f"th-province:{province_code}",
                entity_type="province",
                status="supported_target_or_use_evidence",
                evidence_observation_ids_json=dump(observation_ids),
                evidence_location_ids_json=dump(location_ids),
            )
        for row in broader_people:
            evidence = [
                role["observation_id"]
                for role in self.tables["person_role_assertions"]
                if role["person_id"] == row["person_id"]
            ]
            self.add(
                "measure_contributions",
                contribution_id=stable_id(
                    "contribution", "broader_innovators", row["person_id"]
                ),
                measure="broader_innovators",
                entity_id=row["person_id"],
                entity_type="person",
                status="explicit_inventor_evidence",
                evidence_observation_ids_json=dump(sorted(set(evidence))),
                evidence_location_ids_json=dump([]),
            )

    def add_coverage(
        self, task, record, source_ids, state, disposition, locators, reason, measures
    ):
        self.add(
            "review_coverage",
            coverage_id=stable_id("coverage", "rinmp", task, str(record)),
            task=task,
            source_record_or_group=str(record),
            source_ids_json=dump(source_ids),
            review_state=state,
            disposition=disposition,
            evidence_locators_json=dump(locators),
            reason=reason,
            affected_measures_json=dump(measures),
        )

    def build_review_coverage(self):
        decision_by_source = {
            source_id: case
            for case in self.config["title_candidate_groups"]
            for source_id in case["source_ids"]
        }
        named_people_by_source = defaultdict(list)
        for item in self.config["explicit_named_people"]:
            named_people_by_source[item["source_id"]].append(item["name"])
        role_mentions_by_source = defaultdict(list)
        for row in self.tables["narrative_role_mentions"]:
            source_id = int(row["source_key"].rsplit(":", 1)[1])
            role_mentions_by_source[source_id].append(row["role"])
        locations_by_section = defaultdict(list)
        for location in self.tables["location_assertions"]:
            if location["evidence_section_id"]:
                locations_by_section[location["evidence_section_id"]].append(location)

        for index, row in enumerate(self.apps):
            source_id = row["id"]
            locator = self.raw_locator("app_tech.json", f"data/records/{index}")
            case = decision_by_source.get(source_id)
            disposition = (
                f"candidate_{case['decision']}"
                if case
                else "retained_as_single_profile_component"
            )
            self.add_coverage(
                "app_profile_identity_and_fact_extraction",
                source_id,
                [source_id],
                case["review_state"] if case else "reviewed_decided",
                disposition,
                [locator],
                "Profile identity, technical sections, commercial/IP/certificate fields and all source metadata were retained.",
                ["K04_ready_innovations", "broader_listed_innovations"],
            )
            self.add_coverage(
                "readiness_review",
                source_id,
                [source_id],
                "reviewed_decided",
                "numeric_trl_used_at_8_9_or_retained_unknown;_atl_unmapped",
                [
                    self.raw_locator("app_tech.json", f"data/records/{index}/trl"),
                    self.raw_locator(
                        "app_tech.json", f"data/records/{index}/atl_level"
                    ),
                ],
                "TRL and ATL were inspected independently. Numeric TRL alone determines RINMP K04 qualification.",
                ["K04_ready_innovations"],
            )
            roles = sorted(set(role_mentions_by_source[source_id]))
            names = named_people_by_source[source_id]
            self.add_coverage(
                "narrative_role_review",
                source_id,
                [source_id],
                "reviewed_decided",
                "explicit_named_person_retained"
                if names
                else "role_context_retained_no_person_invented",
                [locator],
                (
                    f"Explicit named role evidence retained for {', '.join(names)}."
                    if names
                    else f"All sections were screened; role mentions {roles or ['none']} do not name an eligible person."
                ),
                ["K02_community_innovators", "broader_innovators"],
            )
            passages = {
                passage["section_index"]: passage
                for passage in self.coverage_passages(row)
            }
            for section_index, section in enumerate(row["description_sections"]):
                section_id = stable_id(
                    "section", self.observation_by_app_id[source_id], section_index
                )
                linked_locations = locations_by_section[section_id]
                passage = passages.get(section_index)
                if linked_locations:
                    disposition = "passage_supported_location_assertions_retained"
                    reason = (
                        f"Passage-specific review linked {len(linked_locations)} structured or narrative "
                        "location assertions; only resolved eligible assertions may contribute to K01."
                    )
                elif passage and passage["negative"]:
                    disposition = "explicit_no_use_passage_excluded"
                    reason = "The passage explicitly reports no implementation group or use location."
                elif passage and passage["substantive"]:
                    disposition = (
                        "target_or_use_passage_retained_without_supported_place"
                    )
                    reason = (
                        "The passage was retained but contains no independently resolved administrative "
                        "place and does not promote collector province context."
                    )
                elif passage:
                    disposition = "empty_target_passage_no_location_claim"
                    reason = "The target-address field is empty or a dash and supports no location."
                else:
                    disposition = "screened_no_target_or_use_location_claim"
                    reason = "The section contains no target-address label or configured explicit-use phrase."
                self.add_coverage(
                    "description_location_passage_review",
                    section_id,
                    [source_id],
                    "reviewed_decided",
                    disposition,
                    [
                        self.raw_locator(
                            "app_tech.json",
                            f"data/records/{index}/description_sections/{section_index}",
                        )
                    ],
                    reason,
                    ["K01A_target_provinces"],
                )

        for owner_index, owner in enumerate(self.owners):
            state = (
                "reviewed_unresolved"
                if owner["owner_key"]
                == self.config["accepted_owner_uncertainty"]["owner_key"]
                else "reviewed_decided"
            )
            self.add_coverage(
                "owner_group_review",
                owner["owner_key"],
                [owner["owner_key"]],
                state,
                "collector_group_retained_not_person",
                [
                    self.raw_locator(
                        "owner_profiles.json", f"data/records/{owner_index}"
                    )
                ],
                "The owner_key is retained as grouping provenance. It creates no confirmed person or innovator contribution.",
                ["K02_community_innovators", "broader_innovators"],
            )
        for row in self.tables["owner_technology_links"]:
            self.add_coverage(
                "owner_technology_link_review",
                row["owner_link_id"],
                [row["owner_key"], row["app_source_id"]],
                "reviewed_decided",
                row["endpoint_status"],
                [row["source_locator"]],
                "Explicit app_tech ID link retained; owner role does not establish person identity or innovation eligibility.",
                ["broader_listed_innovations"],
            )
        for row in self.tables["owner_title_claims"]:
            state = (
                "reviewed_unresolved"
                if row["reconciliation_status"] == "ambiguous_repeated_title_claim"
                else "reviewed_decided"
            )
            self.add_coverage(
                "owner_title_claim_review",
                row["title_claim_id"],
                [row["owner_key"]],
                state,
                row["reconciliation_status"],
                [row["source_locator"]],
                "A title claim links to an app profile only when the normalized title is unique within that owner group's ID set.",
                ["broader_listed_innovations"],
            )
        for row in self.tables["identity_decisions"]:
            self.add_coverage(
                "innovation_identity_candidate_review",
                row["decision_id"],
                json.loads(row["source_ids_json"]),
                row["review_state"],
                row["decision"],
                json.loads(row["evidence_locators_json"]),
                row["reason"],
                ["K04_ready_innovations", "broader_listed_innovations"],
            )
        section_locator_by_id = {
            row["section_id"]: row["source_locator"]
            for row in self.tables["description_sections"]
        }
        for row in self.tables["location_assertions"]:
            locators = [row["source_locator"]]
            if row["evidence_section_id"]:
                locators.append(section_locator_by_id[row["evidence_section_id"]])
            self.add_coverage(
                "location_assertion_review",
                row["location_id"],
                [row["source_key"].rsplit(":", 1)[1]],
                "reviewed_decided",
                row["coverage_eligibility"],
                list(dict.fromkeys(locators)),
                "Location role, passage provenance, raw hierarchy and pinned-reference resolution are retained separately.",
                ["K01A_target_provinces"],
            )
        for row in self.tables["aggregate_metrics"]:
            self.add_coverage(
                "aggregate_metric_review",
                row["metric"],
                [row["metric"]],
                "reviewed_decided",
                row["reconciliation_status"],
                [row["source_locator"]],
                row["interpretation"],
                ["source_reported_aggregates"],
            )
        for row in self.tables["aggregate_components"]:
            self.add_coverage(
                "aggregate_institute_component_review",
                row["component_id"],
                [row["institute_raw"]],
                "reviewed_decided",
                row["reconciliation_status"],
                [row["source_locator"]],
                "Institute component compared directly with the catalogue profile count.",
                ["source_reported_technologies"],
            )




    def run(self):
        self.ingest()
        self.build_innovation_identities()
        self.build_profile_facts()
        self.build_institutes()
        self.build_locations()
        self.build_owner_groups()
        self.build_aggregates()
        self.build_pending_links()
        self.add_quality_reviews()
        self.build_measures()
        self.build_review_coverage()
        return self.tables


def build_tables(datasets, reviews, geography, input_metadata):
    """Build full legacy-compatible RINMP tables from injected immutable captures."""
    return RINMPPilot(datasets, reviews, geography, input_metadata).run()

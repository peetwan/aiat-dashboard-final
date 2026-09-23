"""Build the source-local AppTech MRU pilot.

The cleaner retains every innovation and requirement page, separates role
claims, corrects only reviewed inventor parsing cases, and applies reviewed
within-source innovation identity decisions. It does not merge across sources
or generate the maintained Markdown review guides.
"""

import copy
import itertools
import json
import re
from collections import defaultdict

from ..common import Components, matching_name, normalize, safe_text, stable_id

DATASET_KEYS = ("innovations", "requirements")

PLACEHOLDERS = {"", "-", "ไม่ระบุ", "none", "null"}
ORGANISATION_PREFIXES = (
    "มหาวิทยาลัย",
    "วิทยาลัย",
    "สถาบัน",
    "โรงเรียน",
    "บริษัท",
    "ห้างหุ้นส่วน",
    "มูลนิธิ",
    "ศูนย์",
    "ชุมชน",
    "สำนักงาน",
)

TABLE_COLUMNS = {
    "source_files": [
        "dataset",
        "raw_file",
        "sha256",
        "row_count",
        "declared_record_count",
        "schema_version",
        "captured_at",
        "run_id",
        "source_base_url",
        "warnings_json",
    ],
    "source_observations": [
        "observation_id",
        "dataset",
        "source_id",
        "nested_source_id",
        "source_key",
        "raw_file",
        "row_locator",
        "file_sha256",
        "record_type",
        "detail_url",
        "captured_at",
        "run_id",
        "disposition",
    ],
    "innovations": [
        "innovation_id",
        "display_name",
        "alternative_display_name",
        "aliases_json",
        "source_ids_json",
        "source_observation_ids_json",
        "identity_status",
        "candidate_group_ids_json",
        "candidate_status",
        "qualifies_k04",
    ],
    "innovation_observations": [
        "innovation_id",
        "observation_id",
        "source_id",
        "source_key",
        "title_raw",
        "title_normalized",
        "category_raw",
        "innovation_type_raw",
        "innovation_value_raw",
        "inventors_raw",
        "original_inventors_json",
        "rights_holder_raw",
        "account_owner_name_raw",
        "account_owner_user_id",
        "account_affiliation_raw",
        "video_url",
        "view_count",
        "validation_warnings_json",
        "missing_narrative",
        "detail_url",
    ],
    "description_sections": [
        "section_id",
        "innovation_id",
        "observation_id",
        "source_id",
        "section_index",
        "label_raw",
        "text_readable",
        "source_locator",
    ],
    "highlights": [
        "highlight_id",
        "innovation_id",
        "observation_id",
        "source_id",
        "highlight_index",
        "text_readable",
        "source_locator",
    ],
    "target_groups": [
        "target_group_id",
        "innovation_id",
        "observation_id",
        "source_id",
        "target_index",
        "target_group_raw",
        "interpretation",
        "source_locator",
    ],
    "funding_assertions": [
        "funding_id",
        "record_type",
        "innovation_id",
        "requirement_id",
        "observation_id",
        "source_id",
        "funding_index",
        "source_raw",
        "amount_raw",
        "amount_thb",
        "details_raw",
        "source_locator",
    ],
    "readiness_assessments": [
        "assessment_id",
        "innovation_id",
        "observation_id",
        "source_id",
        "trl_level",
        "trl_image_url",
        "trl_valid",
        "trl_image_agrees",
        "srl_level",
        "srl_label_raw",
        "qualifies_k04_assertion",
        "source_locator",
    ],
    "ip_assertions": [
        "ip_assertion_id",
        "innovation_id",
        "observation_id",
        "source_id",
        "ip_type",
        "ip_type_raw",
        "property_name_raw",
        "request_no_raw",
        "patent_no_raw",
        "request_identifier_status",
        "source_locator",
    ],
    "economic_claims": [
        "claim_id",
        "innovation_id",
        "observation_id",
        "source_id",
        "claim_type",
        "indicator_raw",
        "value_raw",
        "interpretation",
        "source_locator",
    ],
    "people": [
        "person_id",
        "display_name",
        "name_normalized",
        "roles_json",
        "source_observation_ids_json",
        "identity_status",
        "broader_innovator_eligible",
        "community_innovator_eligible",
    ],
    "organisations": [
        "organisation_id",
        "display_name",
        "name_normalized",
        "roles_json",
        "source_observation_ids_json",
        "identity_status",
    ],
    "role_assertions": [
        "assertion_id",
        "record_type",
        "innovation_id",
        "requirement_id",
        "observation_id",
        "source_id",
        "role",
        "role_index",
        "subject_type",
        "person_id",
        "organisation_id",
        "name_raw",
        "subject_name",
        "name_normalized",
        "placeholder",
        "team_unspecified",
        "role_raw",
        "faculty_raw",
        "university_raw",
        "field_semantic_flag",
        "account_user_id",
        "affiliation_raw",
        "parsing_basis",
        "source_locator",
    ],
    "inventor_parsing": [
        "parse_id",
        "innovation_id",
        "observation_id",
        "source_id",
        "inventors_raw",
        "original_inventors_json",
        "corrected_people_json",
        "organisation_mentions_json",
        "has_unspecified_team",
        "invalid_non_person_text",
        "parsing_basis",
        "review_state",
        "source_locator",
    ],
    "requirements": [
        "requirement_id",
        "observation_id",
        "source_id",
        "title_raw",
        "category_raw",
        "type_raw",
        "description_raw",
        "short_description_raw",
        "need_statement_raw",
        "required_expertise_raw",
        "hired_external_expert_raw",
        "video_url",
        "view_count",
        "tags_raw",
        "detail_url",
        "innovation_link_status",
    ],
    "requirement_expertise": [
        "expertise_id",
        "requirement_id",
        "observation_id",
        "source_id",
        "expertise_index",
        "expertise_raw",
        "relationship_status",
        "source_locator",
    ],
    "requirement_impacts": [
        "impact_id",
        "requirement_id",
        "observation_id",
        "source_id",
        "impact_type",
        "value_raw",
        "source_locator",
    ],
    "requirement_tags": [
        "tag_id",
        "requirement_id",
        "observation_id",
        "source_id",
        "tag_index",
        "tag_raw",
        "source_locator",
    ],
    "innovation_identity_candidates": [
        "candidate_group_id",
        "source_ids_json",
        "innovation_ids_json",
        "titles_json",
        "basis",
        "disposition",
        "review_state",
        "reason",
        "possible_count_reduction",
        "evidence_locators_json",
    ],
    "identity_decisions": [
        "decision_id",
        "candidate_group_id",
        "source_ids_json",
        "decision",
        "status",
        "reason",
        "evidence_observation_ids_json",
    ],
    "person_identity_decisions": [
        "decision_id",
        "prior_candidate_id",
        "left_parent_source_id",
        "right_parent_source_id",
        "left_name_raw",
        "right_name_raw",
        "left_current_person_id",
        "right_current_person_id",
        "decision",
        "status",
        "decision_origin",
        "evidence_observation_ids_json",
    ],
    "person_identity_reviews": [
        "review_id",
        "name_normalized",
        "source_ids_json",
        "roles_json",
        "account_user_ids_json",
        "institution_families_json",
        "disposition",
        "review_state",
        "reason",
        "evidence_observation_ids_json",
    ],
    "pending_cross_source_decisions": [
        "pending_id",
        "prior_candidate_id",
        "entity_type",
        "mru_source_id",
        "mru_name_raw",
        "mru_person_id",
        "external_source_key",
        "decision",
        "status",
        "reason",
    ],
    "entity_observations": [
        "entity_type",
        "entity_id",
        "observation_id",
        "source_id",
        "relationship",
    ],
    "review_cases": [
        "review_id",
        "case_type",
        "source_ids_json",
        "names_json",
        "status",
        "reason",
        "affected_measures_json",
        "possible_count_reduction",
        "evidence_locators_json",
    ],
    "review_coverage": [
        "coverage_id",
        "task",
        "subject_key",
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
        "value",
        "unit",
        "status",
        "definition",
        "snapshot_scope",
        "supported_filters_json",
        "unsupported_filters_json",
        "filter_policy_json",
        "provisional",
        "contribution_table",
        "limitation",
    ],
    "measure_contributions": [
        "measure",
        "entity_type",
        "entity_id",
        "source_observation_ids_json",
        "contribution",
        "eligibility_reason",
    ],
}

TABLE_GRAINS = {
    "source_files": "one input JSON file",
    "source_observations": "one raw innovation or requirement page",
    "innovations": "one reviewed source-local innovation identity",
    "innovation_observations": "one raw innovation page attached to an innovation identity",
    "description_sections": "one source description section",
    "highlights": "one source highlight",
    "target_groups": "one stated target group, not an observed beneficiary",
    "funding_assertions": "one source funding entry",
    "readiness_assessments": "one source innovation page's TRL and SRL assertions",
    "ip_assertions": "one source innovation page's IP claim",
    "economic_claims": "one source ROI, SROI, or innovation-value claim",
    "people": "one exact-name source-local natural-person identity after reviewed remapping",
    "organisations": "one exact-name source-local organisation mention identity",
    "role_assertions": "one observation-specific person, organisation, non-person text, placeholder, or team role claim",
    "inventor_parsing": "one innovation page's reviewed inventor segmentation",
    "requirements": "one retained need identity",
    "requirement_expertise": "one required-expertise entry, not an engagement",
    "requirement_impacts": "one source-stated requirement impact field",
    "requirement_tags": "one requirement tag",
    "innovation_identity_candidates": "one reviewed within-source candidate component",
    "identity_decisions": "one reviewed candidate-group disposition",
    "person_identity_decisions": "one historical MRU person edge remapped to current evidence",
    "person_identity_reviews": "one repeated exact normalized person name audited for conflicting source context",
    "pending_cross_source_decisions": "one historical edge that crosses the MRU source boundary",
    "entity_observations": "one entity-to-source-observation relationship",
    "review_cases": "one accepted uncertainty or source-quality case",
    "review_coverage": "one required raw-record or identity-review task",
    "measure_results": "one source-local result or explicitly unavailable KPI",
    "measure_contributions": "one distinct entity contribution to one source-local result",
}


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def placeholder(value):
    return normalize(value).casefold() in PLACEHOLDERS


def person_key(value):
    value = re.sub(r"^\s*\d+\s*[.)]?\s*", "", normalize(value))
    previous = None
    while value != previous:
        previous = value
        value = re.sub(
            r"^(?:ผู้ช่วยศาสตราจารย์|รองศาสตราจารย์|ศาสตราจารย์|"
            r"ผศ\.ดร\.|รศ\.ดร\.|ศ\.ดร\.|ผศ\.|รศ\.|ศ\.|ดร\.|"
            r"อาจารย์|อ\.|นาย|นางสาว|นาง)\s*",
            "",
            value,
        )
    return normalize(value).casefold()


def is_organisation(value):
    name = normalize(value)
    return name.startswith(("มรภ.", "มรภ ")) or any(
        name.startswith(prefix) for prefix in ORGANISATION_PREFIXES
    )


def institution_family(value):
    """Normalize only explicit institution labels for same-name conflict review."""
    name = normalize(value)
    if placeholder(name) or not is_organisation(name):
        return ""
    replacements = {
        "มหาวิทยาลัยราชภัฎ": "มหาวิทยาลัยราชภัฏ",
        "มหาวิทยาลัยราชถัฏ": "มหาวิทยาลัยราชภัฏ",
        "มหาวิทาลัยราชภัฏ": "มหาวิทยาลัยราชภัฏ",
        "มหาวิทยาลราชภัฏ": "มหาวิทยาลัยราชภัฏ",
        "มรภ.": "มหาวิทยาลัยราชภัฏ",
        "มรภ ": "มหาวิทยาลัยราชภัฏ",
        "มหาวิทยาลัยราชภัฏบ้าสมเด็จ": "มหาวิทยาลัยราชภัฏบ้านสมเด็จ",
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    name = name.replace("ในพระบรมราชูปถัมภ์", "").rstrip("ฯ ")
    name = name.split(" จังหวัด", 1)[0]
    if name.endswith(" แม่สอด"):
        name = name.removesuffix(" แม่สอด")
    return normalize(name).casefold()


def source_key(dataset, source_id):
    return f"apptech_mru:{dataset}:{source_id}"


def split_researcher_names(value):
    """Split the two observed multi-person researcher fields, preserving source text."""
    name = normalize(value)
    if "," not in name:
        return [name]
    parts = [normalize(part) for part in name.split(",") if normalize(part)]
    return parts if len(parts) > 1 else [name]


def split_rights_holder_names(value):
    """Split explicit co-holder lists without inferring unnamed members."""
    name = normalize(value)
    if is_organisation(name):
        return [name]
    return [
        normalize(part)
        for part in re.split(
            r"\s*,\s*|\s+และ\s+|และ(?=(?:คุณ|นาย|นาง|ผศ|รศ|ศ\.|ดร|อาจารย์|ผู้ช่วย|รอง))",
            name,
        )
        if normalize(part)
    ]


class AppTechMRUPilot:
    def __init__(self, datasets, reviews, geography, input_metadata):
        if set(datasets) != set(DATASET_KEYS):
            raise ValueError(
                "AppTech MRU input contract: datasets must be innovations and requirements"
            )
        self.reviews = reviews
        self.config = reviews["reviewed_cases.json"]
        self.datasets, self.input_metadata, self.geography = (
            datasets,
            input_metadata,
            geography,
        )
        self.tables = defaultdict(list)
        self.data = {}
        self.envelopes = {}
        self.observations = {}
        self.rows_by_id = {}
        self.innovation_ids = {}
        self.person_mentions = defaultdict(
            lambda: {"roles": set(), "observations": set()}
        )
        self.organisation_mentions = defaultdict(
            lambda: {"roles": set(), "observations": set()}
        )
        self.person_ids = {}
        self.organisation_ids = {}
        self.person_correction_by_key = {}
        self.person_correction_group_by_key = {}
        self.load_person_identity_corrections()

    def load_person_identity_corrections(self):
        """Load only the reviewed source-local alias corrections for this pilot."""
        audit = self.config["source_identity_correction_audit"]
        corrections = self.config["person_identity_corrections"]
        assert len(corrections) == audit["expected_group_count"]
        for correction in corrections:
            canonical_key = person_key(correction["canonical_name"])
            assert canonical_key and len(correction["aliases"]) >= 2
            for alias in correction["aliases"]:
                alias_key = person_key(alias)
                existing = self.person_correction_by_key.setdefault(
                    alias_key, canonical_key
                )
                assert existing == canonical_key, f"Conflicting correction for {alias}"
                group = self.person_correction_group_by_key.setdefault(
                    alias_key, correction["group_id"]
                )
                assert group == correction["group_id"], f"Conflicting group for {alias}"

    def canonical_person_key(self, value):
        key = person_key(value)
        return self.person_correction_by_key.get(key, key)

    def correction_group_for(self, value):
        return self.person_correction_group_by_key.get(person_key(value), "")

    def configured_non_person_subject(self, value):
        return self.config["non_person_subjects"].get(normalize(value), {})

    def add(self, table, **row):
        self.tables[table].append(row)


    def ingest(self):
        for dataset, nested_id in (
            ("innovations", "innovationid"),
            ("requirements", "requirementid"),
        ):
            envelope = self.datasets[dataset]
            metadata = self.input_metadata.get(dataset)
            if not isinstance(envelope, dict) or not isinstance(
                envelope.get("data"), list
            ):
                raise ValueError(
                    f"AppTech MRU input contract: {dataset} must be an envelope with data"
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
                    f"AppTech MRU input contract: missing locked metadata for {dataset}"
                )
            rows = envelope["data"]
            if len(rows) != envelope.get("record_count") or len(
                {str(row.get("record_id")) for row in rows}
            ) != len(rows):
                raise ValueError(
                    f"AppTech MRU input contract: invalid {dataset} row accounting"
                )
            self.data[dataset], self.envelopes[dataset] = rows, envelope
            self.add(
                "source_files",
                dataset=dataset,
                raw_file=metadata["file"],
                sha256=metadata["sha256"],
                row_count=len(rows),
                declared_record_count=envelope["record_count"],
                schema_version=envelope.get("schema_version"),
                captured_at=metadata["captured_at"],
                run_id=metadata["run_id"],
                source_base_url=envelope.get("source_base_url"),
                warnings_json=envelope.get("warnings", []),
            )
            for index, row in enumerate(rows):
                sid = str(row.get("record_id") or "")
                if (
                    not sid
                    or not isinstance(row.get("data"), dict)
                    or str(row["data"].get(nested_id)) != sid
                ):
                    raise ValueError(
                        f"AppTech MRU input contract: invalid {dataset} record identity"
                    )
                oid = stable_id("mru_obs", metadata["source_id"], dataset, sid)
                self.observations[dataset, sid] = oid
                self.add(
                    "source_observations",
                    observation_id=oid,
                    dataset=dataset,
                    source_id=sid,
                    nested_source_id=sid,
                    source_key=source_key(dataset, sid),
                    raw_file=metadata["file"],
                    row_locator=f"data/{index}",
                    file_sha256=metadata["sha256"],
                    record_type=row.get("record_type"),
                    detail_url=row.get("detail_url"),
                    captured_at=metadata["captured_at"],
                    run_id=metadata["run_id"],
                    disposition="retained_with_lineage",
                )
                self.add(
                    "review_coverage",
                    coverage_id=stable_id("mru_coverage", "raw_record", dataset, sid),
                    task="raw_record_accounting",
                    subject_key=source_key(dataset, sid),
                    source_ids_json=[sid],
                    review_state="reviewed_decided",
                    disposition="retained_with_lineage",
                    evidence_locators_json=[self.raw_locator(dataset, sid)],
                    reason="The primary page is retained exactly once at its source grain.",
                    affected_measures_json=["K04", "broader_listed_innovations"]
                    if dataset == "innovations"
                    else [],
                )
        self.rows_by_id = {
            str(row["record_id"]): row for row in self.data["innovations"]
        }

    def build_innovation_identities(self):
        all_ids = sorted(self.rows_by_id)
        cannot = []
        for group in self.config["innovation_candidate_groups"]:
            if group["disposition"] in {"separate", "unresolved"}:
                cannot.extend(itertools.combinations(group["source_ids"], 2))
        components = Components(all_ids, cannot)
        for group in self.config["innovation_candidate_groups"]:
            ids = group["source_ids"]
            assert all(sid in self.rows_by_id for sid in ids), group["group_id"]
            if group["disposition"] == "merge":
                for sid in ids[1:]:
                    assert components.merge(ids[0], sid) in {"merged", "already_linked"}

        group_by_source = defaultdict(list)
        for group in self.config["innovation_candidate_groups"]:
            for sid in group["source_ids"]:
                group_by_source[sid].append(group)

        for root, members in sorted(components.members.items()):
            entity_id = stable_id("mru_innovation", sorted(members))
            for sid in members:
                self.innovation_ids[sid] = entity_id
            rows = [self.rows_by_id[sid] for sid in sorted(members)]
            titles = sorted({normalize(row["title"]) for row in rows})
            subjects = sorted(
                {
                    normalize(row["data"]["ip"].get("property_name"))
                    for row in rows
                    if not placeholder(row["data"]["ip"].get("property_name"))
                }
            )
            related_groups = {
                group["group_id"]: group
                for sid in members
                for group in group_by_source[sid]
            }
            dispositions = {group["disposition"] for group in related_groups.values()}
            if "unresolved" in dispositions:
                candidate_status = "reviewed_unresolved_possible_duplicate"
            elif related_groups:
                candidate_status = "reviewed_decided"
            else:
                candidate_status = "no_candidate_signal"
            qualifies = any(row["data"]["trl"]["level"] in {8, 9} for row in rows)
            self.add(
                "innovations",
                innovation_id=entity_id,
                display_name=titles[0],
                alternative_display_name=subjects[0]
                if len(titles) == 1 and subjects
                else "",
                aliases_json=titles,
                source_ids_json=sorted(members),
                source_observation_ids_json=sorted(
                    self.observations["innovations", sid] for sid in members
                ),
                identity_status="supported_source_local_merge"
                if len(members) > 1
                else "provisional_source_local",
                candidate_group_ids_json=sorted(related_groups),
                candidate_status=candidate_status,
                qualifies_k04=qualifies,
            )
            for sid in sorted(members):
                self.add(
                    "entity_observations",
                    entity_type="innovation",
                    entity_id=entity_id,
                    observation_id=self.observations["innovations", sid],
                    source_id=sid,
                    relationship="described_by",
                )

        for group in self.config["innovation_candidate_groups"]:
            ids = group["source_ids"]
            entity_ids = sorted({self.innovation_ids[sid] for sid in ids})
            state = (
                "reviewed_unresolved"
                if group["disposition"] == "unresolved"
                else "reviewed_decided"
            )
            locators = [self.raw_locator("innovations", sid) for sid in ids]
            self.add(
                "innovation_identity_candidates",
                candidate_group_id=group["group_id"],
                source_ids_json=ids,
                innovation_ids_json=entity_ids,
                titles_json=sorted({self.rows_by_id[sid]["title"] for sid in ids}),
                basis=group["basis"],
                disposition=group["disposition"],
                review_state=state,
                reason=group["reason"],
                possible_count_reduction=len(entity_ids) - 1
                if state == "reviewed_unresolved"
                else 0,
                evidence_locators_json=locators,
            )
            self.add(
                "identity_decisions",
                decision_id=stable_id("mru_innovation_decision", group["group_id"]),
                candidate_group_id=group["group_id"],
                source_ids_json=ids,
                decision=group["disposition"],
                status=state,
                reason=group["reason"],
                evidence_observation_ids_json=[
                    self.observations["innovations", sid] for sid in ids
                ],
            )
            self.add(
                "review_coverage",
                coverage_id=stable_id(
                    "mru_coverage", "innovation_candidate", group["group_id"]
                ),
                task="innovation_identity_candidate",
                subject_key=group["group_id"],
                source_ids_json=ids,
                review_state=state,
                disposition=group["disposition"],
                evidence_locators_json=locators,
                reason=group["reason"],
                affected_measures_json=["K04", "broader_listed_innovations"],
            )
            if group["disposition"] == "unresolved":
                self.add(
                    "review_cases",
                    review_id=stable_id("mru_review", group["group_id"]),
                    case_type="innovation_identity_uncertainty",
                    source_ids_json=ids,
                    names_json=sorted({self.rows_by_id[sid]["title"] for sid in ids}),
                    status="reviewed_unresolved",
                    reason=group["reason"],
                    affected_measures_json=["K04", "broader_listed_innovations"],
                    possible_count_reduction=len(entity_ids) - 1,
                    evidence_locators_json=locators,
                )

    def raw_locator(self, dataset, source_id, suffix=""):
        observation = next(
            row
            for row in self.tables["source_observations"]
            if row["dataset"] == dataset and row["source_id"] == source_id
        )
        metadata = self.input_metadata[dataset]
        locator = f"evidence://{metadata['source_id']}/{metadata['run_id']}/{metadata['file']}#{observation['row_locator']}"
        return locator + (f"/{suffix}" if suffix else "")


    def register_subject(self, name, role, observation_id, subject_type=None):
        name = normalize(name)
        if placeholder(name):
            return "placeholder", "", ""
        if subject_type == "non_person_text":
            return subject_type, "", ""
        subject_type = subject_type or (
            "organisation" if is_organisation(name) else "person"
        )
        if subject_type == "organisation":
            key = normalize(name).casefold()
            self.organisation_mentions[key]["display_names"] = (
                self.organisation_mentions[key].get("display_names", set()) | {name}
            )
            self.organisation_mentions[key]["roles"].add(role)
            self.organisation_mentions[key]["observations"].add(observation_id)
            return subject_type, "", key
        key = self.canonical_person_key(name)
        if not key or key in PLACEHOLDERS:
            return "placeholder", "", ""
        self.person_mentions[key]["display_names"] = self.person_mentions[key].get(
            "display_names", set()
        ) | {name}
        self.person_mentions[key]["roles"].add(role)
        self.person_mentions[key]["observations"].add(observation_id)
        return "person", key, ""

    def add_role(
        self,
        *,
        record_type,
        source_id,
        observation_id,
        role,
        role_index,
        name,
        source_locator,
        subject_type=None,
        placeholder_flag=False,
        team=False,
        role_raw="",
        faculty="",
        university="",
        field_flag="",
        account_user_id="",
        affiliation="",
        parsing_basis="source_field",
        source_name_raw=None,
    ):
        non_person_subject = self.configured_non_person_subject(name)
        if non_person_subject:
            subject_type = non_person_subject["subject_type"]
            parsing_basis = "reviewed_non_person_subject"
        if placeholder_flag:
            actual_type, person_name_key, organisation_name_key = "placeholder", "", ""
        elif team:
            actual_type, person_name_key, organisation_name_key = "team", "", ""
        else:
            actual_type, person_name_key, organisation_name_key = self.register_subject(
                name, role, observation_id, subject_type
            )
        self.add(
            "role_assertions",
            assertion_id=stable_id(
                "mru_role", record_type, source_id, role, role_index
            ),
            record_type=record_type,
            innovation_id=(
                ""
                if record_type == "requirement"
                else self.innovation_ids.get(source_id, "")
            ),
            requirement_id=stable_id("mru_requirement", source_id)
            if record_type == "requirement"
            else "",
            observation_id=observation_id,
            source_id=source_id,
            role=role,
            role_index=role_index,
            subject_type=actual_type,
            person_id=person_name_key,
            organisation_id=organisation_name_key,
            name_raw=normalize(
                source_name_raw if source_name_raw is not None else name
            ),
            subject_name=normalize(name),
            name_normalized=person_name_key or organisation_name_key,
            placeholder=placeholder_flag,
            team_unspecified=team,
            role_raw=role_raw,
            faculty_raw=normalize(faculty),
            university_raw=normalize(university),
            field_semantic_flag=field_flag,
            account_user_id=account_user_id,
            affiliation_raw=normalize(affiliation),
            parsing_basis=parsing_basis,
            source_locator=source_locator,
        )

    def parse_inventors(self, row, index):
        sid = str(row["record_id"])
        data = row["data"]
        raw = normalize(data.get("inventors_raw"))
        oid = self.observations["innovations", sid]
        people = []
        organisations = []
        has_team = "และคณะ" in raw or "คณะผู้วิจัย" in raw
        invalid_non_person = False
        basis = "researcher_name_corroborated_in_raw_inventor_text"

        if placeholder(raw):
            basis = "source_placeholder"
        elif sid in self.config["organisation_inventor_ids"]:
            organisations = [raw]
            basis = "reviewed_organisation_led_inventor_string"
            has_team = "คณะ" in raw or "ชุมชน" in raw
        elif sid in self.config["juthamas_person_plus_team_ids"]:
            people = ["จุฑามาศ ศุภพันธ์"]
            has_team = True
            basis = "reviewed_juthamas_person_plus_unspecified_team_correction"
        elif sid in self.config["inventor_overrides"]:
            override = self.config["inventor_overrides"][sid]
            people = override.get("people", [])
            has_team = override.get("has_unspecified_team", has_team)
            invalid_non_person = override.get("invalid_non_person_text", False)
            basis = "reviewed_full_population_override"
        else:
            raw_key = person_key(raw)
            matched = []
            for researcher in data["researchers"]:
                candidate = person_key(researcher.get("name"))
                if (
                    candidate
                    and candidate not in PLACEHOLDERS
                    and len(candidate.split()) >= 2
                    and candidate in raw_key
                ):
                    matched.append((candidate, matching_name(researcher["name"])))
            # A full researcher name and a redundant given-name-only entry can
            # both occur on the same page (10268). Keep the longest supported
            # name so the short entry cannot become a phantom person.
            matched = [
                item
                for item in matched
                if not any(
                    item[0] != other[0] and item[0] in other[0] for other in matched
                )
            ]
            people = sorted(
                {name for _, name in matched if normalize(name)}, key=person_key
            )
            assert people, f"Unreviewed inventor parse for {sid}: {raw}"

        for person_index, name in enumerate(people):
            self.add_role(
                record_type="innovation",
                source_id=sid,
                observation_id=oid,
                role="inventor",
                role_index=person_index,
                name=name,
                source_locator=f"data/apptech_mru/innovations.json#data/{index}/data/inventors_raw",
                subject_type="person",
                parsing_basis=basis,
            )
        for organisation_index, name in enumerate(organisations):
            self.add_role(
                record_type="innovation",
                source_id=sid,
                observation_id=oid,
                role="inventor",
                role_index=organisation_index,
                name=name,
                source_locator=f"data/apptech_mru/innovations.json#data/{index}/data/inventors_raw",
                subject_type="organisation",
                parsing_basis=basis,
            )
        if has_team:
            self.add_role(
                record_type="innovation",
                source_id=sid,
                observation_id=oid,
                role="inventor",
                role_index="team",
                name="unspecified team",
                source_locator=f"data/apptech_mru/innovations.json#data/{index}/data/inventors_raw",
                team=True,
                parsing_basis=basis,
            )
        if placeholder(raw):
            self.add_role(
                record_type="innovation",
                source_id=sid,
                observation_id=oid,
                role="inventor",
                role_index="placeholder",
                name=raw or "",
                source_locator=f"data/apptech_mru/innovations.json#data/{index}/data/inventors_raw",
                placeholder_flag=True,
                parsing_basis=basis,
            )

        state = "reviewed_decided"
        disposition = (
            "excluded_invalid_non_person_text"
            if invalid_non_person
            else (
                "retained_placeholder"
                if placeholder(raw)
                else "corrected_or_retained_role_claim"
            )
        )
        self.add(
            "inventor_parsing",
            parse_id=stable_id("mru_inventor_parse", sid),
            innovation_id=self.innovation_ids[sid],
            observation_id=oid,
            source_id=sid,
            inventors_raw=data.get("inventors_raw"),
            original_inventors_json=data["inventors"],
            corrected_people_json=people,
            organisation_mentions_json=organisations,
            has_unspecified_team=has_team,
            invalid_non_person_text=invalid_non_person,
            parsing_basis=basis,
            review_state=state,
            source_locator=f"data/apptech_mru/innovations.json#data/{index}/data/inventors_raw",
        )
        return disposition

    @staticmethod
    def researcher_field_flag(researcher):
        university = normalize(researcher.get("university"))
        faculty = normalize(researcher.get("faculty"))
        if (
            university
            and not placeholder(university)
            and not faculty
            and not is_organisation(university)
        ):
            return "faculty_like_value_in_university_field"
        return ""

    def build_innovation_facts_and_roles(self):
        for index, row in enumerate(self.data["innovations"]):
            sid = str(row["record_id"])
            data = row["data"]
            oid = self.observations["innovations", sid]
            entity_id = self.innovation_ids[sid]
            self.add(
                "innovation_observations",
                innovation_id=entity_id,
                observation_id=oid,
                source_id=sid,
                source_key=source_key("innovations", sid),
                title_raw=row["title"],
                title_normalized=normalize(row["title"]),
                category_raw=data["category"],
                innovation_type_raw=data["innovation_type"],
                innovation_value_raw=data["innovation_value_raw"],
                inventors_raw=data.get("inventors_raw"),
                original_inventors_json=data["inventors"],
                rights_holder_raw=data.get("rights_holder"),
                account_owner_name_raw=data["listing"]["owner_name"],
                account_owner_user_id=str(data["listing"]["owner_user_id"]),
                account_affiliation_raw=data["listing"]["affiliation"],
                video_url=data.get("video_url"),
                view_count=data["view_count"],
                validation_warnings_json=row["validation_warnings"],
                missing_narrative=not data["description_sections"],
                detail_url=row["detail_url"],
            )
            inventor_disposition = self.parse_inventors(row, index)

            for researcher_index, researcher in enumerate(data["researchers"]):
                source_name = researcher.get("name")
                if sid == "10572" and researcher_index == 0:
                    names = ["ผู้ช่วยศาสตราจารย์ ดร.ราเชณ คณะนา"]
                else:
                    names = split_researcher_names(source_name)
                for name_index, name in enumerate(names):
                    is_placeholder = placeholder(name)
                    field_flag = self.researcher_field_flag(researcher)
                    if sid == "10572" and researcher_index == 0:
                        field_flag = "surname_spilled_into_faculty_field"
                    self.add_role(
                        record_type="innovation",
                        source_id=sid,
                        observation_id=oid,
                        role="researcher",
                        role_index=f"{researcher_index}.{name_index}",
                        name=name,
                        source_locator=(
                            f"data/apptech_mru/innovations.json#data/{index}/data/researchers/{researcher_index}"
                        ),
                        placeholder_flag=is_placeholder,
                        role_raw=researcher.get("role", ""),
                        faculty=researcher.get("faculty"),
                        university=researcher.get("university"),
                        field_flag=field_flag,
                        source_name_raw=source_name,
                        parsing_basis="source_researcher_entry"
                        if len(names) == 1
                        else "split_multi_person_researcher_entry",
                    )
            rights_holder = data.get("rights_holder")
            if placeholder(rights_holder):
                self.add_role(
                    record_type="innovation",
                    source_id=sid,
                    observation_id=oid,
                    role="rights_holder",
                    role_index=0,
                    name=rights_holder,
                    source_locator=f"data/apptech_mru/innovations.json#data/{index}/data/rights_holder",
                    placeholder_flag=True,
                )
            else:
                holder_names = split_rights_holder_names(rights_holder)
                if sid in self.config["juthamas_person_plus_team_ids"]:
                    holder_names = ["จุฑามาศ ศุภพันธ์"]
                elif sid == "10572":
                    holder_names = ["ราเชณ คณะนา"]
                for holder_index, holder_name in enumerate(holder_names):
                    self.add_role(
                        record_type="innovation",
                        source_id=sid,
                        observation_id=oid,
                        role="rights_holder",
                        role_index=holder_index,
                        name=holder_name,
                        source_locator=f"data/apptech_mru/innovations.json#data/{index}/data/rights_holder",
                        source_name_raw=rights_holder,
                        parsing_basis="split_explicit_co_holder_list"
                        if len(holder_names) > 1
                        else "source_rights_holder_field",
                    )
                if (
                    sid in self.config["juthamas_person_plus_team_ids"]
                    or sid == "10572"
                ):
                    self.add_role(
                        record_type="innovation",
                        source_id=sid,
                        observation_id=oid,
                        role="rights_holder",
                        role_index="team",
                        name="unspecified team",
                        source_locator=f"data/apptech_mru/innovations.json#data/{index}/data/rights_holder",
                        team=True,
                        source_name_raw=rights_holder,
                        parsing_basis="named_person_plus_unspecified_team",
                    )
            listing = data["listing"]
            self.add_role(
                record_type="innovation",
                source_id=sid,
                observation_id=oid,
                role="listing_account_owner",
                role_index=0,
                name=listing["owner_name"],
                source_locator=f"data/apptech_mru/innovations.json#data/{index}/data/listing",
                account_user_id=str(listing["owner_user_id"]),
                affiliation=listing["affiliation"],
            )

            for section_index, section in enumerate(data["description_sections"]):
                self.add(
                    "description_sections",
                    section_id=stable_id("mru_section", sid, section_index),
                    innovation_id=entity_id,
                    observation_id=oid,
                    source_id=sid,
                    section_index=section_index,
                    label_raw=section["label"],
                    text_readable=safe_text(section["text"]),
                    source_locator=self.raw_locator(
                        "innovations", sid, f"data/description_sections/{section_index}"
                    ),
                )
            for highlight_index, text in enumerate(data["highlights"]):
                self.add(
                    "highlights",
                    highlight_id=stable_id("mru_highlight", sid, highlight_index),
                    innovation_id=entity_id,
                    observation_id=oid,
                    source_id=sid,
                    highlight_index=highlight_index,
                    text_readable=safe_text(text),
                    source_locator=self.raw_locator(
                        "innovations", sid, f"data/highlights/{highlight_index}"
                    ),
                )
            for target_index, target in enumerate(data["target_groups"]):
                self.add(
                    "target_groups",
                    target_group_id=stable_id("mru_target", sid, target_index),
                    innovation_id=entity_id,
                    observation_id=oid,
                    source_id=sid,
                    target_index=target_index,
                    target_group_raw=target,
                    interpretation="stated_target_not_observed_beneficiary",
                    source_locator=self.raw_locator(
                        "innovations", sid, f"data/target_groups/{target_index}"
                    ),
                )
            self.add_funding(
                "innovation", sid, entity_id, "", oid, index, data["funding"]
            )
            self.add_readiness(row, index)
            ip = data["ip"]
            request = normalize(ip.get("request_no_raw"))
            identifier_status = (
                "missing"
                if not request
                else (
                    "placeholder_or_pending"
                    if request.casefold() in PLACEHOLDERS
                    or "ระหว่าง" in request
                    or set(request) <= {"*"}
                    else "source_reported_identifier"
                )
            )
            self.add(
                "ip_assertions",
                ip_assertion_id=stable_id("mru_ip", sid),
                innovation_id=entity_id,
                observation_id=oid,
                source_id=sid,
                ip_type=ip.get("type"),
                ip_type_raw=ip.get("type_raw"),
                property_name_raw=ip.get("property_name"),
                request_no_raw=ip.get("request_no_raw"),
                patent_no_raw=ip.get("patent_no_raw"),
                request_identifier_status=identifier_status,
                source_locator=self.raw_locator("innovations", sid, "data/ip"),
            )
            for claim_type, claim in [("roi", data["roi"]), ("sroi", data["sroi"])]:
                self.add(
                    "economic_claims",
                    claim_id=stable_id("mru_economic", sid, claim_type),
                    innovation_id=entity_id,
                    observation_id=oid,
                    source_id=sid,
                    claim_type=claim_type,
                    indicator_raw=claim.get("indicator_raw"),
                    value_raw=claim.get("value_raw"),
                    interpretation="source_claim_not_monthly_income",
                    source_locator=self.raw_locator(
                        "innovations", sid, f"data/{claim_type}"
                    ),
                )
            self.add(
                "economic_claims",
                claim_id=stable_id("mru_economic", sid, "innovation_value"),
                innovation_id=entity_id,
                observation_id=oid,
                source_id=sid,
                claim_type="innovation_value",
                indicator_raw="",
                value_raw=data["innovation_value_raw"],
                interpretation="source_value_not_monthly_income",
                source_locator=self.raw_locator(
                    "innovations", sid, "data/innovation_value_raw"
                ),
            )
            role_count = sum(
                role["source_id"] == sid and role["record_type"] == "innovation"
                for role in self.tables["role_assertions"]
            )
            self.add(
                "review_coverage",
                coverage_id=stable_id("mru_coverage", "roles", sid),
                task="innovation_role_population",
                subject_key=source_key("innovations", sid),
                source_ids_json=[sid],
                review_state="reviewed_decided",
                disposition=inventor_disposition,
                evidence_locators_json=[
                    f"data/apptech_mru/innovations.json#data/{index}/data/inventors_raw",
                    f"data/apptech_mru/innovations.json#data/{index}/data/researchers",
                    f"data/apptech_mru/innovations.json#data/{index}/data/rights_holder",
                    f"data/apptech_mru/innovations.json#data/{index}/data/listing",
                ],
                reason=f"Reviewed inventor, researcher, rights-holder and account claims; emitted {role_count} role assertions.",
                affected_measures_json=["broader_inventor_people", "K02"],
            )

    def add_funding(
        self, record_type, sid, innovation_id, requirement_id, oid, row_index, entries
    ):
        filename = (
            "innovations.json" if record_type == "innovation" else "requirements.json"
        )
        for funding_index, funding in enumerate(entries):
            self.add(
                "funding_assertions",
                funding_id=stable_id("mru_funding", record_type, sid, funding_index),
                record_type=record_type,
                innovation_id=innovation_id,
                requirement_id=requirement_id,
                observation_id=oid,
                source_id=sid,
                funding_index=funding_index,
                source_raw=funding.get("source"),
                amount_raw=funding.get("amount_raw"),
                amount_thb=funding.get("amount_thb"),
                details_raw=funding.get("details_raw"),
                source_locator=f"data/apptech_mru/{filename}#data/{row_index}/data/funding/{funding_index}",
            )

    def add_readiness(self, row, index):
        sid = str(row["record_id"])
        data = row["data"]
        trl = data["trl"]
        match = re.search(r"TRL-(\d)\.png", trl["image_url"])
        image_level = int(match.group(1)) if match else None
        self.add(
            "readiness_assessments",
            assessment_id=stable_id("mru_readiness", sid),
            innovation_id=self.innovation_ids[sid],
            observation_id=self.observations["innovations", sid],
            source_id=sid,
            trl_level=trl["level"],
            trl_image_url=trl["image_url"],
            trl_valid=trl["level"] in range(1, 10),
            trl_image_agrees=image_level == trl["level"],
            srl_level=data["srl"]["level"],
            srl_label_raw=data["srl"]["label_raw"],
            qualifies_k04_assertion=trl["level"] in {8, 9},
            source_locator=self.raw_locator("innovations", sid, "data/trl"),
        )

    def build_requirements(self):
        for index, row in enumerate(self.data["requirements"]):
            sid = str(row["record_id"])
            data = row["data"]
            oid = self.observations["requirements", sid]
            requirement_id = stable_id("mru_requirement", sid)
            self.add(
                "requirements",
                requirement_id=requirement_id,
                observation_id=oid,
                source_id=sid,
                title_raw=row["title"],
                category_raw=data["category"],
                type_raw=data["type_raw"],
                description_raw=safe_text(data["description"]),
                short_description_raw=safe_text(data["short_description"]),
                need_statement_raw=safe_text(data["need_statement"]),
                required_expertise_raw=safe_text(data["required_expertise_raw"]),
                hired_external_expert_raw=data["hired_external_expert_raw"],
                video_url=data.get("video_url"),
                view_count=data["view_count"],
                tags_raw=data["tags_raw"],
                detail_url=row["detail_url"],
                innovation_link_status="no_source_supported_link",
            )
            self.add(
                "entity_observations",
                entity_type="requirement",
                entity_id=requirement_id,
                observation_id=oid,
                source_id=sid,
                relationship="described_by",
            )
            for expertise_index, expertise in enumerate(data["required_expertise"]):
                self.add(
                    "requirement_expertise",
                    expertise_id=stable_id("mru_expertise", sid, expertise_index),
                    requirement_id=requirement_id,
                    observation_id=oid,
                    source_id=sid,
                    expertise_index=expertise_index,
                    expertise_raw=safe_text(expertise),
                    relationship_status="required_not_delivered_engagement",
                    source_locator=self.raw_locator(
                        "requirements",
                        sid,
                        f"data/required_expertise/{expertise_index}",
                    ),
                )
            for impact_type, value in sorted(data["impact"].items()):
                self.add(
                    "requirement_impacts",
                    impact_id=stable_id("mru_requirement_impact", sid, impact_type),
                    requirement_id=requirement_id,
                    observation_id=oid,
                    source_id=sid,
                    impact_type=impact_type.removesuffix("_raw"),
                    value_raw=safe_text(value),
                    source_locator=self.raw_locator(
                        "requirements", sid, f"data/impact/{impact_type}"
                    ),
                )
            for tag_index, tag in enumerate(data["tags"]):
                self.add(
                    "requirement_tags",
                    tag_id=stable_id("mru_requirement_tag", sid, tag_index),
                    requirement_id=requirement_id,
                    observation_id=oid,
                    source_id=sid,
                    tag_index=tag_index,
                    tag_raw=tag,
                    source_locator=self.raw_locator(
                        "requirements", sid, f"data/tags/{tag_index}"
                    ),
                )
            listing = data["listing"]
            self.add_role(
                record_type="requirement",
                source_id=sid,
                observation_id=oid,
                role="listing_account_owner",
                role_index=0,
                name=listing["owner_name"],
                source_locator=f"data/apptech_mru/requirements.json#data/{index}/data/listing",
                account_user_id=str(listing["owner_user_id"]),
                affiliation=listing["affiliation"],
            )
            self.add_funding(
                "requirement", sid, "", requirement_id, oid, index, data["funding"]
            )
            self.add(
                "review_coverage",
                coverage_id=stable_id("mru_coverage", "requirement", sid),
                task="requirement_relationship_review",
                subject_key=source_key("requirements", sid),
                source_ids_json=[sid],
                review_state="reviewed_decided",
                disposition="retained_need_without_innovation_or_expert_link",
                evidence_locators_json=[
                    f"data/apptech_mru/requirements.json#data/{index}/data"
                ],
                reason="Need, expertise, impact, funding and account context are retained; no supplied key proves a match or delivered engagement.",
                affected_measures_json=[],
            )

    def finalize_role_entities(self):
        roles_by_source = defaultdict(list)
        for role in self.tables["role_assertions"]:
            roles_by_source[role["source_id"]].append(role)
        for key, mention in sorted(self.person_mentions.items()):
            source_roles = [
                row for row in self.tables["role_assertions"] if row["person_id"] == key
            ]
            source_ids = sorted({row["source_id"] for row in source_roles})
            account_ids = sorted(
                {
                    row["account_user_id"]
                    for row in source_roles
                    if row["account_user_id"]
                }
            )
            institutions = sorted(
                {
                    family
                    for row in source_roles
                    for family in [
                        institution_family(row["affiliation_raw"]),
                        institution_family(row["university_raw"]),
                    ]
                    if family
                }
            )
            conflicts = []
            if len(account_ids) > 1:
                conflicts.append("different listing-account user IDs")
            if len(institutions) > 1:
                conflicts.append("different explicit institutions")
            if conflicts:
                raise AssertionError(
                    f"Same-name person requires a reviewed split or merge: {key}: "
                    + "; ".join(conflicts)
                )
            repeated = len(source_ids) > 1
            corroboration = []
            if account_ids:
                corroboration.append("one listing-account user ID")
            if institutions:
                corroboration.append("one compatible institution family")
            if any(
                len({row["role"] for row in source_roles if row["source_id"] == sid})
                > 1
                for sid in source_ids
            ):
                corroboration.append("cross-role evidence on the same page")
            page_account_sets = [
                {
                    row["account_user_id"]
                    for row in roles_by_source[source_id]
                    if row["account_user_id"]
                }
                for source_id in source_ids
            ]
            shared_page_accounts = (
                set.intersection(*page_account_sets)
                if page_account_sets and all(page_account_sets)
                else set()
            )
            if shared_page_accounts:
                corroboration.append(
                    "the same page-account ID "
                    + ", ".join(sorted(shared_page_accounts))
                )
            page_institution_sets = [
                {
                    family
                    for row in roles_by_source[source_id]
                    for family in [institution_family(row["affiliation_raw"])]
                    if family
                }
                for source_id in source_ids
            ]
            shared_page_institutions = (
                set.intersection(*page_institution_sets)
                if page_institution_sets and all(page_institution_sets)
                else set()
            )
            if shared_page_institutions:
                corroboration.append(
                    "the same page affiliation context "
                    + ", ".join(sorted(shared_page_institutions))
                )
            participant_sets = [
                {
                    row["name_normalized"]
                    for row in roles_by_source[source_id]
                    if row["person_id"] and row["name_normalized"] != key
                }
                for source_id in source_ids
            ]
            shared_participants = (
                set.intersection(*participant_sets)
                if participant_sets and all(participant_sets)
                else set()
            )
            if shared_participants:
                names = sorted(shared_participants)[:3]
                corroboration.append(
                    "recurring named team context with " + ", ".join(names)
                )
            linked_innovation_ids = {
                self.innovation_ids.get(source_id, source_id)
                for source_id in source_ids
            }
            if len(linked_innovation_ids) < len(source_ids):
                corroboration.append("observations of one reviewed innovation identity")
            correction_group = self.correction_group_for(key)
            pid = stable_id("mru_person", key)
            self.person_ids[key] = pid
            roles = sorted(mention["roles"])
            self.add(
                "people",
                person_id=pid,
                display_name=sorted(
                    mention["display_names"], key=lambda value: (len(value), value)
                )[0],
                name_normalized=key,
                roles_json=roles,
                source_observation_ids_json=sorted(mention["observations"]),
                identity_status=(
                    "reviewed_source_identity_correction"
                    if correction_group
                    else "reviewed_exact_name_with_compatible_context_source_local"
                    if repeated
                    else "single_name_observation_source_local"
                ),
                broader_innovator_eligible="inventor" in roles,
                community_innovator_eligible=False,
            )
            if repeated or correction_group:
                reason = "Exact normalized name has no contradictory account or institution context"
                if correction_group:
                    reason = (
                        f"Reviewed source identity correction {correction_group} remaps only its "
                        "supported local aliases; raw names and role assertions remain source-specific"
                    )
                reason += (
                    f"; corroborated by {', '.join(corroboration)}."
                    if corroboration
                    else "."
                )
                self.add(
                    "person_identity_reviews",
                    review_id=stable_id("mru_person_name_review", key),
                    name_normalized=key,
                    source_ids_json=source_ids,
                    roles_json=roles,
                    account_user_ids_json=account_ids,
                    institution_families_json=institutions,
                    disposition=(
                        "merge_reviewed_source_identity_correction"
                        if correction_group
                        else "merge_source_local_name_mentions"
                    ),
                    review_state="reviewed_decided",
                    reason=reason,
                    evidence_observation_ids_json=sorted(mention["observations"]),
                )
        for key, mention in sorted(self.organisation_mentions.items()):
            oid = stable_id("mru_organisation", key)
            self.organisation_ids[key] = oid
            self.add(
                "organisations",
                organisation_id=oid,
                display_name=sorted(
                    mention["display_names"], key=lambda value: (len(value), value)
                )[0],
                name_normalized=key,
                roles_json=sorted(mention["roles"]),
                source_observation_ids_json=sorted(mention["observations"]),
                identity_status="supported_exact_normalized_name_source_local",
            )
        for row in self.tables["role_assertions"]:
            if row["person_id"]:
                row["person_id"] = self.person_ids[row["person_id"]]
            if row["organisation_id"]:
                row["organisation_id"] = self.organisation_ids[row["organisation_id"]]

    @staticmethod
    def prior_key_parts(value):
        parts = value.split("|")
        if len(parts) < 5:
            raise AssertionError(f"Unexpected prior observation key: {value}")
        dataset = parts[0].split("@", 1)[0]
        return dataset, parts[1], parts[4]

    def remap_prior_person_decisions(self):
        audit = self.reviews.get("prior_person_decisions.json")
        if (
            not isinstance(audit, dict)
            or audit.get("origin_sha256")
            != self.config["prior_decision_audit"]["sha256"]
        ):
            raise ValueError(
                "AppTech MRU input contract: missing or changed prior person decisions"
            )
        decisions = [
            decision
            for decision in audit.get("prior_reviewed_decisions", {}).get(
                "decisions", []
            )
            if decision.get("entity_type") == "person"
            and "apptech_mru"
            in decision.get("left_observation_key", "")
            + decision.get("right_observation_key", "")
        ]
        if (
            len(decisions)
            != self.config["prior_decision_audit"]["expected_mru_person_must_links"]
        ):
            raise ValueError(
                "AppTech MRU input contract: incomplete prior person decisions"
            )
        role_index = defaultdict(list)
        for role in self.tables["role_assertions"]:
            if role["record_type"] == "innovation" and role["person_id"]:
                role_index[role["source_id"], role["name_normalized"]].append(role)
        for decision in decisions:
            left_dataset, left_sid, left_name = self.prior_key_parts(
                decision["left_observation_key"]
            )
            right_dataset, right_sid, right_name = self.prior_key_parts(
                decision["right_observation_key"]
            )
            left_key = self.canonical_person_key(left_name)
            right_key = self.canonical_person_key(right_name)
            assert left_key == right_key
            current_pid = self.person_ids.get(left_key, "")
            mru_sides = [
                (dataset, sid, name)
                for dataset, sid, name in [
                    (left_dataset, left_sid, left_name),
                    (right_dataset, right_sid, right_name),
                ]
                if dataset.startswith("apptech_mru/")
            ]
            evidence = []
            for _, sid, name in mru_sides:
                matches = role_index[sid, self.canonical_person_key(name)]
                assert matches, f"Prior person side did not remap: {sid} {name}"
                evidence.extend(role["observation_id"] for role in matches)
            cross_source = not (
                left_dataset.startswith("apptech_mru/")
                and right_dataset.startswith("apptech_mru/")
            )
            self.add(
                "person_identity_decisions",
                decision_id=stable_id("mru_person_decision", decision["candidate_id"]),
                prior_candidate_id=decision["candidate_id"],
                left_parent_source_id=left_sid,
                right_parent_source_id=right_sid,
                left_name_raw=left_name,
                right_name_raw=right_name,
                left_current_person_id=current_pid
                if left_dataset.startswith("apptech_mru/")
                else "",
                right_current_person_id=current_pid
                if right_dataset.startswith("apptech_mru/")
                else "",
                decision=decision["decision"],
                status="remapped_pending_cross_source"
                if cross_source
                else "remapped_applied_source_local",
                decision_origin=f"{decision['reviewer']} {decision['decided_at']}",
                evidence_observation_ids_json=sorted(set(evidence)),
            )
            if cross_source:
                mru_dataset, mru_sid, mru_name = mru_sides[0]
                external_key = (
                    decision["right_observation_key"]
                    if left_dataset.startswith("apptech_mru/")
                    else decision["left_observation_key"]
                )
                self.add(
                    "pending_cross_source_decisions",
                    pending_id=stable_id(
                        "mru_pending_cross_source", decision["candidate_id"]
                    ),
                    prior_candidate_id=decision["candidate_id"],
                    entity_type="person",
                    mru_source_id=mru_sid,
                    mru_name_raw=mru_name,
                    mru_person_id=current_pid,
                    external_source_key=external_key,
                    decision=decision["decision"],
                    status="pending_cross_source_resolution",
                    reason="Historical identity evidence is remapped, but this source-local cleaner does not merge across source boundaries.",
                )

    def add_quality_cases(self):
        quality_cases = [
            (
                "10398_university_field_semantics",
                ["10398"],
                "Faculty-like text วิทยาศาสตร์และเทคโนโลยี appears in a university field while faculty is null; retained without inventing an institution.",
            ),
            (
                "reused_unrelated_ip_identifier",
                ["10464", "10469"],
                "Application 0901003963 appears on unrelated insect-repellent equipment and fibre dye records; both claims remain visible and identities stay separate.",
            ),
            (
                "invalid_inventor_text",
                ["10611"],
                "The inventor field repeats the innovation title and does not support a natural person or organisation.",
            ),
        ]
        for case_type, ids, reason in quality_cases:
            self.add(
                "review_cases",
                review_id=stable_id("mru_review", case_type),
                case_type=case_type,
                source_ids_json=ids,
                names_json=[self.rows_by_id[sid]["title"] for sid in ids],
                status="reviewed_decided",
                reason=reason,
                affected_measures_json=["broader_inventor_people"]
                if ids == ["10611"]
                else [],
                possible_count_reduction=0,
                evidence_locators_json=[
                    self.raw_locator("innovations", sid) for sid in ids
                ],
            )

    def build_measures(self):
        innovations = self.tables["innovations"]
        people = self.tables["people"]
        unresolved = [
            row
            for row in self.tables["innovation_identity_candidates"]
            if row["review_state"] == "reviewed_unresolved"
        ]
        definition_version = "apptech-mru-v1"
        snapshot_scope = (
            "501 innovation pages and 2 requirement pages captured 2026-08-23; "
            "observation year unavailable"
        )
        results = [
            (
                "broader_listed_innovations",
                len(innovations),
                "distinct innovations",
                "calculated_source_local",
                "Distinct reviewed MRU innovation identities in the snapshot.",
                bool(unresolved),
                "Eligible unresolved candidates count separately until resolved.",
                ["category_raw", "innovation_type_raw", "trl_level"],
                ["year", "province", "district", "subdistrict", "institution"],
            ),
            (
                "K04",
                sum(bool(row["qualifies_k04"]) for row in innovations),
                "readiness-supported innovations",
                "calculated_working_definition",
                "Distinct MRU innovations with at least one TRL 8 or 9 assertion.",
                any(
                    row["review_state"] == "reviewed_unresolved"
                    and any(
                        self.rows_by_id[sid]["data"]["trl"]["level"] in {8, 9}
                        for sid in row["source_ids_json"]
                    )
                    for row in unresolved
                ),
                "Source-reported TRL is preserved as evidence, not independently validated readiness.",
                ["category_raw", "innovation_type_raw", "trl_level"],
                [
                    "year",
                    "province",
                    "district",
                    "subdistrict",
                    "institution",
                    "independently_validated_readiness",
                ],
            ),
            (
                "broader_inventor_people",
                sum(bool(row["broader_innovator_eligible"]) for row in people),
                "distinct named people",
                "calculated_source_local",
                "Distinct natural people explicitly supported as inventors in MRU.",
                False,
                "Reviewed source-local person identities count once; unnamed teams add no headcount.",
                ["innovation_id", "category_raw", "innovation_type_raw"],
                [
                    "year",
                    "province",
                    "district",
                    "subdistrict",
                    "institution",
                    "community_role",
                ],
            ),
            (
                "K02",
                None,
                "community innovators",
                "unavailable",
                "MRU inventor evidence alone does not establish community-innovator status.",
                False,
                "No MRU person contributes to K02 without separate community-role evidence.",
                [],
                [
                    "year",
                    "province",
                    "district",
                    "subdistrict",
                    "institution",
                    "community_role",
                    "innovation_id",
                    "category_raw",
                    "innovation_type_raw",
                ],
            ),
        ]
        for (
            measure,
            value,
            unit,
            status,
            definition,
            provisional,
            limitation,
            supported_filters,
            unsupported_filters,
        ) in results:
            self.add(
                "measure_results",
                measure=measure,
                definition_version=definition_version,
                value=value,
                unit=unit,
                status=status,
                definition=definition,
                snapshot_scope=snapshot_scope,
                supported_filters_json=supported_filters,
                unsupported_filters_json=unsupported_filters,
                filter_policy_json={
                    "allocation_policy": "do_not_allocate_overall_value",
                    "unsupported_value": "unavailable",
                    "year_filter": "unsupported",
                },
                provisional=provisional,
                contribution_table="measure_contributions.csv"
                if value is not None
                else "",
                limitation=limitation,
            )
        for innovation in innovations:
            observation_ids = innovation["source_observation_ids_json"]
            self.add(
                "measure_contributions",
                measure="broader_listed_innovations",
                entity_type="innovation",
                entity_id=innovation["innovation_id"],
                source_observation_ids_json=observation_ids,
                contribution=1,
                eligibility_reason="retained source-listed innovation identity",
            )
            if innovation["qualifies_k04"]:
                self.add(
                    "measure_contributions",
                    measure="K04",
                    entity_type="innovation",
                    entity_id=innovation["innovation_id"],
                    source_observation_ids_json=observation_ids,
                    contribution=1,
                    eligibility_reason="at least one source TRL assessment is 8 or 9",
                )
        inventor_observations = defaultdict(set)
        for role in self.tables["role_assertions"]:
            if role["role"] == "inventor" and role["person_id"]:
                inventor_observations[role["person_id"]].add(role["observation_id"])
        for person in people:
            if person["broader_innovator_eligible"]:
                self.add(
                    "measure_contributions",
                    measure="broader_inventor_people",
                    entity_type="person",
                    entity_id=person["person_id"],
                    source_observation_ids_json=sorted(
                        inventor_observations[person["person_id"]]
                    ),
                    contribution=1,
                    eligibility_reason="explicit named natural-person inventor role",
                )




    def run(self):
        self.ingest()
        self.build_innovation_identities()
        self.build_innovation_facts_and_roles()
        self.build_requirements()
        self.finalize_role_entities()
        self.remap_prior_person_decisions()
        self.add_quality_cases()
        self.build_measures()
        return self.tables


def validate_tables(tables):
    """Reject broken requirement ownership before source tables are released."""
    requirements_by_id = {}
    for index, row in enumerate(tables["requirements"]):
        requirement_id = row.get("requirement_id")
        if not isinstance(requirement_id, str) or not requirement_id.strip():
            raise ValueError(f"requirements[{index}] has missing requirement_id")
        if requirement_id in requirements_by_id:
            raise ValueError(f"duplicate requirement_id: {requirement_id}")
        for field in ("observation_id", "source_id"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f"requirements[{index}] has missing {field}")
        requirements_by_id[requirement_id] = row

    for table, identity_field in (
        ("requirement_expertise", "expertise_id"),
        ("requirement_impacts", "impact_id"),
        ("requirement_tags", "tag_id"),
    ):
        identities = set()
        for index, row in enumerate(tables[table]):
            identity = row.get(identity_field)
            if not isinstance(identity, str) or not identity.strip():
                raise ValueError(f"{table}[{index}] has missing {identity_field}")
            if identity in identities:
                raise ValueError(f"duplicate {identity_field}: {identity}")
            identities.add(identity)

            requirement_id = row.get("requirement_id")
            if (
                not isinstance(requirement_id, str)
                or not requirement_id.strip()
                or requirement_id not in requirements_by_id
            ):
                raise ValueError(
                    f"{table}[{index}] references missing requirement_id: {requirement_id!r}"
                )
            requirement = requirements_by_id[requirement_id]
            for field in ("observation_id", "source_id"):
                value = row.get(field)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{table}[{index}] has missing {field}")
                if value != requirement[field]:
                    raise ValueError(
                        f"{table}[{index}] {field} does not belong to requirement_id: "
                        f"{requirement_id}"
                    )


def _canonicalize_locators(value, metadata):
    if isinstance(value, str):
        for dataset, filename in (
            ("innovations", "innovations.json"),
            ("requirements", "requirements.json"),
        ):
            prefix = f"data/apptech_mru/{filename}#"
            if value.startswith(prefix):
                item = metadata[dataset]
                return f"evidence://{item['source_id']}/{item['run_id']}/{item['file']}#{value[len(prefix) :]}"
        return value
    if isinstance(value, list):
        return [_canonicalize_locators(item, metadata) for item in value]
    if isinstance(value, dict):
        return {
            key: _canonicalize_locators(item, metadata) for key, item in value.items()
        }
    return value


def build_tables(datasets, reviews, geography, input_metadata):
    """Build full legacy-compatible MRU tables from injected immutable captures."""
    pilot = AppTechMRUPilot(datasets, reviews, geography, input_metadata)
    tables = pilot.run()
    canonical_tables = {
        name: [_canonicalize_locators(row, input_metadata) for row in tables[name]]
        for name in TABLE_COLUMNS
    }
    validate_tables(canonical_tables)
    return canonical_tables

"""Pure Learning area-based normalization preserving the accepted legacy semantics."""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from typing import Any

from ..common import Components, normalize, stable_id as common_stable_id

DATASET_KEYS = (
    "area_based_response",
    "area_based_rows",
    "area_based_stats",
    "refresh_summary",
    "capture_manifest",
)
TABLE_GRAINS = {
    "source_files": "one input file or copied representation in the supplied capture",
    "source_observations": "one area_based.json.data listing observation",
    "businesses": "one supported source-local business or provisional participating unit",
    "business_observation_links": "one listing assigned to one source-local identity",
    "participations": "one source-listed business/project/research-unit participation",
    "project_assertions": "one raw project-name assertion from a listing",
    "research_unit_assertions": "one raw research-unit assertion from a listing",
    "locations": "one raw programme business-location assertion and its derived hierarchy treatment",
    "identity_decisions": "one exact-name, near-name, or protected cannot-link decision",
    "review_cases": "one inspected geography review case from the 95-row audit baseline",
    "review_coverage": "one required source listing, candidate group/pair, or statistic review task",
    "source_statistics": "one raw source aggregate member, never back-assigned to a business",
    "measure_results": "one source-local supported or unavailable measure result",
    "measure_contributions": "one business/unit contribution to a source-local measure",
}
TABLE_COLUMNS = {
    "source_files": [
        "file_id",
        "file",
        "role",
        "sha256",
        "manifest_sha256",
        "declared_hash_status",
        "source_id",
        "run_id",
        "captured_at",
    ],
    "source_observations": [
        "observation_id",
        "source_id",
        "source_key",
        "sequence",
        "row_locator",
        "raw_file",
        "raw_file_sha256",
        "business_name_raw",
        "business_name_normalized",
        "malformed_name",
        "fiscal_year_be",
        "fiscal_year_ce",
        "created_at_raw",
        "updated_at_raw",
        "disposition",
    ],
    "businesses": [
        "business_id",
        "display_name",
        "aliases_json",
        "source_ids_json",
        "identity_status",
        "name_quality",
        "eligible_k08",
        "identity_review_status",
    ],
    "business_observation_links": [
        "business_id",
        "observation_id",
        "source_id",
        "link_basis",
    ],
    "participations": [
        "participation_id",
        "business_id",
        "observation_id",
        "project_assertion_id",
        "research_unit_assertion_id",
        "fiscal_year_be",
        "source_batch_timestamp",
    ],
    "project_assertions": [
        "assertion_id",
        "observation_id",
        "project_name_raw",
        "fiscal_year_be",
        "official_project_id",
    ],
    "research_unit_assertions": ["assertion_id", "observation_id", "research_unit_raw"],
    "locations": [
        "location_id",
        "observation_id",
        "business_id",
        "location_role",
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
        "resolution_method",
        "reference_version",
        "region_raw",
        "resolution_reason",
    ],
    "identity_decisions": [
        "decision_id",
        "candidate_kind",
        "candidate_number",
        "source_ids_json",
        "names_json",
        "treatment",
        "review_state",
        "evidence",
        "count_impact",
    ],
    "review_cases": [
        "review_id",
        "case_kind",
        "source_id",
        "sequence",
        "business_name_raw",
        "raw_province",
        "raw_district",
        "raw_subdistrict",
        "baseline_status",
        "current_status",
        "review_state",
        "treatment",
        "reason",
        "evidence_locator",
        "affected_measures",
    ],
    "review_coverage": [
        "coverage_id",
        "task",
        "source_ids_json",
        "review_state",
        "disposition",
        "evidence_locator",
        "reason",
        "affected_measures",
    ],
    "source_statistics": [
        "statistic_id",
        "dimension",
        "label",
        "value",
        "grain",
        "row_attribute_available",
        "source_path_json",
    ],
    "measure_results": [
        "measure",
        "value",
        "unit",
        "status",
        "basis",
        "limitations",
        "measure_version",
        "scope",
        "supported_filters_json",
        "unsupported_filters_json",
        "drilldown",
        "aggregation",
    ],
    "measure_contributions": [
        "measure",
        "business_id",
        "province_code",
        "contribution_status",
        "evidence_observation_ids_json",
        "location_role",
    ],
}


def json_cell(value):
    return value


def declared_hash_status(actual_hash, declared_hash):
    if not declared_hash:
        return "not_declared"
    return "passed" if actual_hash == declared_hash else "failed"


def _fail(message):
    raise ValueError(f"Learning area-based input contract: {message}")


class LearningAreaPilot:
    def __init__(self, datasets, reviews, geography, input_metadata):
        if set(datasets) != set(DATASET_KEYS):
            _fail(f"datasets must be exactly {', '.join(DATASET_KEYS)}")
        config = (
            reviews.get("reviewed_cases.json", reviews.get("reviewed_cases"))
            if isinstance(reviews, dict)
            else None
        )
        audit = (
            reviews.get("geography_review.json") if isinstance(reviews, dict) else None
        )
        if not isinstance(config, dict):
            _fail("reviewed_cases.json must be supplied")
        if not isinstance(audit, dict) or not isinstance(
            audit.get("area", {}).get("full_hierarchy_review"), list
        ):
            _fail("geography_review.json must contain area.full_hierarchy_review")
        self.raw = datasets["area_based_response"]
        if (
            not isinstance(self.raw, dict)
            or not isinstance(self.raw.get("data"), list)
            or not isinstance(self.raw.get("stats"), dict)
        ):
            _fail("area_based_response must contain data and stats")
        self.config, self.audit = config, audit
        self.datasets, self.input_metadata, self.geography = (
            datasets,
            input_metadata,
            geography,
        )
        self.rows = self.raw["data"]
        if self.raw["stats"].get("totalRecords") != len(self.rows):
            _fail("stats.totalRecords differs from data length")
        if not all(
            isinstance(row, dict) and row.get("id") is not None for row in self.rows
        ):
            _fail("every area-based record must have an id")
        if len({str(row["id"]) for row in self.rows}) != len(self.rows):
            _fail("area-based ids must be unique")
        self.by_id = {str(row["id"]): row for row in self.rows}
        self.files = []
        self.tables = {name: [] for name in TABLE_COLUMNS}

    def metadata(self, dataset):
        value = self.input_metadata.get(dataset)
        required = (
            "source_id",
            "run_id",
            "file",
            "sha256",
            "size",
            "captured_at",
            "originating_system",
        )
        if not isinstance(value, dict) or any(
            key not in value or value[key] in (None, "") for key in required
        ):
            _fail(f"metadata for {dataset} must include {', '.join(required)}")
        return value

    def stable_id(self, kind, *parts):
        metadata = self.metadata("area_based_response")
        return common_stable_id(
            f"learning_area_based_{kind}", metadata["run_id"], *parts
        )

    def raw_locator(self, index):
        metadata = self.metadata("area_based_response")
        return f"evidence://{metadata['source_id']}/{metadata['run_id']}/{metadata['file']}#/data/{index}"

    def raw_stats_locator(self, dimension):
        metadata = self.metadata("area_based_response")
        return f"evidence://{metadata['source_id']}/{metadata['run_id']}/{metadata['file']}#/stats/{dimension}"

    def load_reference(self):
        self.reference_version = getattr(self.geography, "reference_version", "")
        self.provinces = self.geography.provinces
        self.districts = self.geography.districts
        self.subdistricts = self.geography.subdistricts
        self.province_by_name = {
            item["provinceNameTh"]: item for item in self.provinces
        }

    def register_source_files(self):
        roles = {
            "area_based_response": "authoritative_response",
            "area_based_rows": "expanded_copy",
            "area_based_stats": "repeated_statistics",
            "refresh_summary": "collection_metadata_and_repeated_statistics",
            "capture_manifest": "collector_provenance_and_declared_hashes",
        }
        manifest = self.datasets["capture_manifest"]
        if not isinstance(manifest, dict):
            _fail("capture_manifest must be an object")
        declared = {
            item.get("file"): item.get("sha256", "")
            for item in [
                *manifest.get("datasets", []),
                *manifest.get("extra_files", []),
            ]
            if isinstance(item, dict)
        }
        source_meta = self.metadata("area_based_response")
        if (
            manifest.get("source_id") != source_meta["source_id"]
            or manifest.get("run_id") != source_meta["run_id"]
        ):
            _fail(
                "capture manifest source/run identity differs from authoritative metadata"
            )
        if (
            not isinstance(self.audit.get("origin_sha256"), str)
            or not self.audit["origin_sha256"]
        ):
            _fail("geography review must declare its audited origin")
        for dataset, role in roles.items():
            metadata = self.metadata(dataset)
            expected = declared.get(
                metadata["file"], metadata.get("declared_sha256", "")
            )
            self.files.append(
                {
                    "file_id": self.stable_id("file", metadata["file"]),
                    "file": metadata["file"],
                    "role": role,
                    "sha256": metadata["sha256"],
                    "manifest_sha256": expected,
                    "declared_hash_status": declared_hash_status(
                        metadata["sha256"], expected
                    ),
                    "source_id": metadata["source_id"],
                    "run_id": metadata["run_id"],
                    "captured_at": metadata["captured_at"],
                }
            )
        rows_meta = self.metadata("area_based_rows")
        canonical_path = rows_meta.get("canonical_evidence_path")
        if canonical_path:
            expected = declared.get(canonical_path, "")
            if not expected:
                _fail("canonical area-based row inventory lacks a manifest hash")
            self.files.append(
                {
                    "file_id": self.stable_id("file", canonical_path),
                    "file": canonical_path,
                    "role": "compressed_expanded_copy",
                    "sha256": expected,
                    "manifest_sha256": expected,
                    "declared_hash_status": "passed",
                    "source_id": rows_meta["source_id"],
                    "run_id": rows_meta["run_id"],
                    "captured_at": rows_meta["captured_at"],
                }
            )
        if self.datasets["area_based_rows"] != self.rows:
            _fail("area_based_rows differs from authoritative data")
        if self.datasets["area_based_stats"] != self.raw["stats"]:
            _fail("area_based_stats differs from authoritative stats")
        refresh = self.datasets["refresh_summary"]
        if (
            not isinstance(refresh, dict)
            or refresh.get("row_count") != len(self.rows)
            or refresh.get("stats") != self.raw["stats"]
        ):
            _fail("refresh_summary differs from authoritative response")

    def location_values(self, row):
        raw_values = (row["province"], row["district"], row["subDistrict"])
        province, district, subdistrict = raw_values
        override = self.config["location_overrides"]
        if row["id"] in override["swaps"]:
            district, subdistrict = subdistrict, district
            method = "reviewed_district_subdistrict_swap"
        else:
            method = "raw_fields_preserved"
        return raw_values, (province, district, subdistrict), method

    def clean_label(self, value, level):
        value = normalize(value)
        prefixes = {
            "province": ("จังหวัด", "จ."),
            "district": ("อำเภอ", "อ.", "เขต"),
            "subdistrict": ("ตำบล", "ต.", "แขวง"),
        }
        for prefix in prefixes[level]:
            if value.startswith(prefix):
                value = value[len(prefix) :].strip()
        if level == "province":
            value = {"กรุงเทพฯ": "กรุงเทพมหานคร", "กรุงเทพ": "กรุงเทพมหานคร"}.get(
                value, value
            )
        return value

    def resolve_location(self, row):
        raw_values, lookup_values, correction = self.location_values(row)
        province_raw, district_raw, subdistrict_raw = raw_values
        lookup_province, lookup_district, lookup_subdistrict = lookup_values
        province = self.clean_label(lookup_province, "province")
        district = self.clean_label(lookup_district, "district")
        subdistrict = self.clean_label(lookup_subdistrict, "subdistrict")
        district = self.config["location_overrides"]["district_aliases"].get(
            district, district
        )
        province_item = self.province_by_name.get(province)
        province_code = str(province_item["provinceCode"]) if province_item else ""
        district_name = (
            "เมือง" + province if district == "เมือง" and province else district
        )
        for alias in self.config["location_overrides"].get("subdistrict_aliases", []):
            if (province, district_name, subdistrict) == (
                alias["province"],
                alias["district"],
                alias["raw"],
            ):
                subdistrict = alias["normalized"]
                correction = "reviewed_spelling_alias"
        if (province, district_name, subdistrict) != (
            lookup_province,
            lookup_district,
            lookup_subdistrict,
        ) and correction == "raw_fields_preserved":
            correction = "normalized_prefix_or_reviewed_alias"
        district_matches = [
            item for item in self.districts if item["districtNameTh"] == district_name
        ]
        local_district = [
            item
            for item in district_matches
            if str(item["provinceCode"]) == province_code
        ]
        district_item = local_district[0] if len(local_district) == 1 else None
        local_subdistrict = [
            item
            for item in self.subdistricts
            if item["subdistrictNameTh"] == subdistrict
            and str(item["provinceCode"]) == province_code
        ]
        matching_subdistrict = None
        if district_item:
            matching = [
                item
                for item in local_subdistrict
                if str(item["districtCode"]) == str(district_item["districtCode"])
            ]
            matching_subdistrict = matching[0] if len(matching) == 1 else None

        # Match both lower levels nationally. A bare city abbreviation or a
        # subdistrict alone cannot overrule a supplied province/district.
        national_pairs = (
            [
                (d, sub)
                for d in district_matches
                for sub in self.subdistricts
                if sub["districtCode"] == d["districtCode"]
                and sub["subdistrictNameTh"] == subdistrict
            ]
            if district and district != "เมือง" and subdistrict
            else []
        )
        if (
            len(national_pairs) == 1
            and str(national_pairs[0][0]["provinceCode"]) != province_code
        ):
            corrected_district, corrected_subdistrict = national_pairs[0]
            corrected_province = next(
                item
                for item in self.provinces
                if item["provinceCode"] == corrected_district["provinceCode"]
            )
            return self.location_row(
                row,
                province_raw,
                district_raw,
                subdistrict_raw,
                corrected_province["provinceNameTh"],
                corrected_province,
                corrected_district,
                corrected_subdistrict,
                "province_corrected_from_unique_district_subdistrict",
                "unique_district_subdistrict_pair",
            )
        if district_item and subdistrict and not matching_subdistrict:
            return self.location_row(
                row,
                province_raw,
                district_raw,
                subdistrict_raw,
                province,
                province_item,
                district_item,
                None,
                "district_subdistrict_conflict",
                correction,
            )
        if district_item and matching_subdistrict:
            return self.location_row(
                row,
                province_raw,
                district_raw,
                subdistrict_raw,
                province,
                province_item,
                district_item,
                matching_subdistrict,
                "hierarchy_match",
                correction,
            )
        if district_item:
            status = (
                "district_match_missing_subdistrict"
                if not subdistrict
                else "subdistrict_unresolved"
            )
            return self.location_row(
                row,
                province_raw,
                district_raw,
                subdistrict_raw,
                province,
                province_item,
                district_item,
                None,
                status,
                correction,
            )
        if province_item and not district:
            return self.location_row(
                row,
                province_raw,
                district_raw,
                subdistrict_raw,
                province,
                province_item,
                None,
                None,
                "province_only",
                correction,
            )
        if province_item:
            return self.location_row(
                row,
                province_raw,
                district_raw,
                subdistrict_raw,
                province,
                province_item,
                None,
                None,
                "unresolved_district",
                correction,
            )
        return self.location_row(
            row,
            province_raw,
            district_raw,
            subdistrict_raw,
            province,
            None,
            None,
            None,
            "unresolved_province",
            correction,
        )

    def location_row(
        self,
        row,
        province_raw,
        district_raw,
        subdistrict_raw,
        province,
        province_item,
        district_item,
        subdistrict_item,
        status,
        correction,
    ):
        return {
            "location_id": self.stable_id("location", row["id"]),
            "observation_id": self.stable_id("observation", row["id"]),
            "business_id": "",
            "location_role": "programme_business_location",
            "province_raw": province_raw,
            "district_raw": district_raw,
            "subdistrict_raw": subdistrict_raw,
            "province_normalized": province,
            "province_code": str(province_item["provinceCode"])
            if province_item
            else "",
            "district_normalized": district_item["districtNameTh"]
            if district_item
            else self.clean_label(district_raw, "district"),
            "district_code": str(district_item["districtCode"])
            if district_item
            else "",
            "subdistrict_normalized": subdistrict_item["subdistrictNameTh"]
            if subdistrict_item
            else self.clean_label(subdistrict_raw, "subdistrict"),
            "subdistrict_code": str(subdistrict_item["subdistrictCode"])
            if subdistrict_item
            else "",
            "resolution_status": status,
            "resolution_method": correction,
            "region_raw": row["region"],
            "resolution_reason": {
                "hierarchy_match": "District and subdistrict resolve together inside the stated province.",
                "district_subdistrict_conflict": "The supplied district is valid, but the subdistrict does not resolve within it; no parent is guessed.",
                "unresolved_district": "No exact district match in the stated province and no unique complete lower hierarchy supports correction.",
                "unresolved_province": "Province is absent or unrecognized and the remaining fields do not establish a complete unique hierarchy.",
                "province_only": "Province is supported; no district is supplied.",
                "district_match_missing_subdistrict": "Province and district are supported; subdistrict is missing.",
                "province_corrected_from_unique_district_subdistrict": "Exact district and subdistrict jointly identify one national hierarchy; raw province remains evidence only.",
            }.get(
                status,
                "Retain supplied address without an unsupported hierarchy assignment.",
            ),
            "reference_version": self.reference_version,
        }

    def create_observations_and_assertions(self):
        for index, row in enumerate(self.rows):
            observation_id = self.stable_id("observation", row["id"])
            name = row["businessName"]
            malformed = name == "[object Object]"
            self.tables["source_observations"].append(
                {
                    "observation_id": observation_id,
                    "source_id": row["id"],
                    "source_key": f"area_based:{row['id']}",
                    "sequence": row["sequence"],
                    "row_locator": self.raw_locator(index),
                    "raw_file": self.metadata("area_based_response")["file"],
                    "raw_file_sha256": self.metadata("area_based_response")["sha256"],
                    "business_name_raw": name,
                    "business_name_normalized": "" if malformed else normalize(name),
                    "malformed_name": str(malformed),
                    "fiscal_year_be": row["fiscalYear"],
                    "fiscal_year_ce": str(int(row["fiscalYear"]) - 543),
                    "created_at_raw": row["createdAt"],
                    "updated_at_raw": row["updatedAt"],
                    "disposition": "eligible_participation_observation",
                }
            )
            self.tables["project_assertions"].append(
                {
                    "assertion_id": self.stable_id("project", row["id"]),
                    "observation_id": observation_id,
                    "project_name_raw": row["projectName"],
                    "fiscal_year_be": row["fiscalYear"],
                    "official_project_id": "",
                }
            )
            self.tables["research_unit_assertions"].append(
                {
                    "assertion_id": self.stable_id("unit", row["id"]),
                    "observation_id": observation_id,
                    "research_unit_raw": row["researchUnit"],
                }
            )
            self.tables["locations"].append(self.resolve_location(row))

    def apply_identity_decisions(self):
        cannot = [tuple(item["source_ids"]) for item in self.config["cannot_links"]]
        for group in self.config["exact_name_groups"]:
            if group["treatment"] != "merge_supported":
                cannot.extend(combinations(group["source_ids"], 2))
        for pair in self.config["near_name_pairs"]:
            if pair["treatment"] != "supported_alias_after_contradiction_checks":
                cannot.extend(combinations(pair["source_ids"], 2))
        self.protected_pairs = sorted(set(tuple(sorted(pair)) for pair in cannot))
        components = Components(self.by_id, self.protected_pairs)
        merge_groups = [
            group
            for group in self.config["exact_name_groups"]
            if group["treatment"] == "merge_supported"
        ]
        merge_groups += [
            pair
            for pair in self.config["near_name_pairs"]
            if pair["treatment"] == "supported_alias_after_contradiction_checks"
        ]
        for group in merge_groups:
            identifiers = group["source_ids"]
            for source_id in identifiers[1:]:
                assert components.merge(identifiers[0], source_id) == "merged"
        for group in self.config["exact_name_groups"]:
            self.record_identity_decision(
                "exact",
                str(group["group"]),
                group["source_ids"],
                group["treatment"],
                "reviewed_decided"
                if group["treatment"] != "reviewed_unresolved"
                else "reviewed_unresolved",
                group["evidence"],
            )
        for pair in self.config["near_name_pairs"]:
            state = (
                "reviewed_unresolved"
                if pair["treatment"] == "unresolved_identity_or_subgroup"
                else "reviewed_decided"
            )
            self.record_identity_decision(
                "near",
                str(pair["pair"]),
                pair["source_ids"],
                pair["treatment"],
                state,
                pair["evidence"],
            )
        for item in self.config["cannot_links"]:
            self.record_identity_decision(
                "cannot_link",
                item["candidate_id"],
                item["source_ids"],
                "cannot_link_preserved",
                "reviewed_decided",
                item["evidence"],
            )
        return components

    def record_identity_decision(
        self, kind, number, source_ids, treatment, state, evidence
    ):
        self.tables["identity_decisions"].append(
            {
                "decision_id": self.stable_id("identity_decision", kind, number),
                "candidate_kind": kind,
                "candidate_number": number,
                "source_ids_json": json_cell(source_ids),
                "names_json": json_cell(
                    [self.by_id[key]["businessName"] for key in source_ids]
                ),
                "treatment": treatment,
                "review_state": state,
                "evidence": evidence,
                "count_impact": "separate provisional contributors remain"
                if state == "reviewed_unresolved"
                else "applied to source-local identity components",
            }
        )

    def create_businesses_and_relationships(self, components):
        unresolved_ids = set()
        for decision in self.tables["identity_decisions"]:
            if decision["review_state"] == "reviewed_unresolved":
                unresolved_ids.update(decision["source_ids_json"])
        member_ids = defaultdict(list)
        for source_id in self.by_id:
            member_ids[components.find(source_id)].append(source_id)
        for root, source_ids in sorted(member_ids.items()):
            members = [self.by_id[source_id] for source_id in sorted(source_ids)]
            malformed = all(
                item["businessName"] == "[object Object]" for item in members
            )
            business_id = self.stable_id("business", *sorted(source_ids))
            aliases = sorted({item["businessName"] for item in members})
            self.tables["businesses"].append(
                {
                    "business_id": business_id,
                    "display_name": "" if malformed else members[0]["businessName"],
                    "aliases_json": json_cell(aliases),
                    "source_ids_json": json_cell(sorted(source_ids)),
                    "identity_status": "provisional_malformed_name"
                    if malformed
                    else (
                        "supported_within_source_merge"
                        if len(source_ids) > 1
                        else "provisional_source_unit"
                    ),
                    "name_quality": "malformed_name"
                    if malformed
                    else "source_reported_name",
                    "eligible_k08": "True",
                    "identity_review_status": "reviewed_unresolved"
                    if unresolved_ids.intersection(source_ids)
                    else "retained_after_source_review",
                }
            )
            for row in members:
                observation_id = self.stable_id("observation", row["id"])
                self.tables["business_observation_links"].append(
                    {
                        "business_id": business_id,
                        "observation_id": observation_id,
                        "source_id": row["id"],
                        "link_basis": "reviewed_merge"
                        if len(source_ids) > 1
                        else "one_source_listing_one_provisional_unit",
                    }
                )
                self.tables["participations"].append(
                    {
                        "participation_id": self.stable_id("participation", row["id"]),
                        "business_id": business_id,
                        "observation_id": observation_id,
                        "project_assertion_id": self.stable_id("project", row["id"]),
                        "research_unit_assertion_id": self.stable_id("unit", row["id"]),
                        "fiscal_year_be": row["fiscalYear"],
                        "source_batch_timestamp": row["createdAt"],
                    }
                )
        location_by_observation = {
            row["observation_id"]: row for row in self.tables["locations"]
        }
        link_by_observation = {
            row["observation_id"]: row["business_id"]
            for row in self.tables["business_observation_links"]
        }
        for observation_id, location in location_by_observation.items():
            location["business_id"] = link_by_observation[observation_id]

        observations_by_business = defaultdict(list)
        locations_by_business = defaultdict(list)
        for link in self.tables["business_observation_links"]:
            observations_by_business[link["business_id"]].append(link["observation_id"])
        for location in self.tables["locations"]:
            locations_by_business[location["business_id"]].append(location)
        for business in self.tables["businesses"]:
            business_id = business["business_id"]
            self.tables["measure_contributions"].append(
                {
                    "measure": "K08_participating_businesses_provisional",
                    "business_id": business_id,
                    "province_code": "",
                    "contribution_status": "provisional_unit"
                    if len(observations_by_business[business_id]) == 1
                    else "supported_merged_business",
                    "evidence_observation_ids_json": json_cell(
                        sorted(observations_by_business[business_id])
                    ),
                    "location_role": "programme_business_location",
                }
            )
            by_province = defaultdict(list)
            for location in locations_by_business[business_id]:
                if (
                    location["province_code"]
                    and location["resolution_status"] != "unresolved_province"
                ):
                    by_province[location["province_code"]].append(
                        location["observation_id"]
                    )
            for province_code, observation_ids in sorted(by_province.items()):
                self.tables["measure_contributions"].append(
                    {
                        "measure": "K01_programme_coverage_provinces",
                        "business_id": business_id,
                        "province_code": province_code,
                        "contribution_status": "resolved_programme_business_location",
                        "evidence_observation_ids_json": json_cell(
                            sorted(observation_ids)
                        ),
                        "location_role": "programme_business_location",
                    }
                )

    def create_geography_review_cases(self):
        locations = {row["observation_id"]: row for row in self.tables["locations"]}
        unresolved = {
            "district_subdistrict_conflict",
            "unresolved_district",
            "unresolved_province",
            "subdistrict_unresolved",
        }
        seen = set()
        for item in self.audit["area"]["full_hierarchy_review"]:
            if (
                not isinstance(item, dict)
                or str(item.get("id", "")) not in self.by_id
                or "status" not in item
            ):
                _fail("geography review references an unknown record or lacks status")
            source_id = str(item["id"])
            if source_id in seen:
                _fail("geography review repeats a source id")
            seen.add(source_id)
            raw = self.by_id[source_id]
            location = locations[self.stable_id("observation", source_id)]
            state = (
                "reviewed_unresolved"
                if location["resolution_status"] in unresolved
                else "reviewed_decided"
            )
            self.tables["review_cases"].append(
                {
                    "review_id": self.stable_id("geography_review", source_id),
                    "case_kind": "audit_full_hierarchy_review",
                    "source_id": source_id,
                    "sequence": raw["sequence"],
                    "business_name_raw": raw["businessName"],
                    "raw_province": raw["province"],
                    "raw_district": raw["district"],
                    "raw_subdistrict": raw["subDistrict"],
                    "baseline_status": item["status"],
                    "current_status": location["resolution_status"],
                    "review_state": state,
                    "treatment": location["resolution_method"],
                    "reason": location["resolution_reason"],
                    "evidence_locator": self.raw_locator(
                        next(
                            index
                            for index, row in enumerate(self.rows)
                            if str(row["id"]) == source_id
                        )
                    ),
                    "affected_measures": "K01 geography filter; K08 eligibility remains retained",
                }
            )

    def create_statistics_and_coverage(self):
        for dimension, values in self.raw["stats"].items():
            if dimension == "totalRecords":
                self.tables["source_statistics"].append(
                    {
                        "statistic_id": self.stable_id("stat", dimension),
                        "dimension": dimension,
                        "label": "",
                        "value": str(values),
                        "source_path_json": json_cell(["stats", dimension]),
                        "grain": "source_listing_aggregate",
                        "row_attribute_available": "False",
                    }
                )
                continue
            for label, value in values.items():
                self.tables["source_statistics"].append(
                    {
                        "statistic_id": self.stable_id("stat", dimension, label),
                        "dimension": dimension,
                        "label": label,
                        "value": str(value),
                        "source_path_json": json_cell(["stats", dimension, label]),
                        "grain": "source_listing_aggregate",
                        "row_attribute_available": "False"
                        if dimension == "byBusinessType"
                        else "True",
                    }
                )
        for index, row in enumerate(self.rows):
            observation_id = self.stable_id("observation", row["id"])
            location = next(
                item
                for item in self.tables["locations"]
                if item["observation_id"] == observation_id
            )
            geography_unresolved = location["resolution_status"] in {
                "district_subdistrict_conflict",
                "unresolved_district",
                "unresolved_province",
                "subdistrict_unresolved",
            }
            self.tables["review_coverage"].append(
                {
                    "coverage_id": self.stable_id("coverage", "identity", row["id"]),
                    "task": "listing_identity",
                    "source_ids_json": json_cell([row["id"]]),
                    "review_state": "reviewed_decided",
                    "disposition": "eligible_provisional_unit_or_reviewed_component",
                    "evidence_locator": self.raw_locator(index),
                    "reason": "Every listing is retained once and has an explicit source-local identity treatment.",
                    "affected_measures": "K08",
                }
            )
            self.tables["review_coverage"].append(
                {
                    "coverage_id": self.stable_id("coverage", "geography", row["id"]),
                    "task": "listing_geography",
                    "source_ids_json": json_cell([row["id"]]),
                    "review_state": "reviewed_unresolved"
                    if geography_unresolved
                    else "reviewed_decided",
                    "disposition": location["resolution_status"],
                    "evidence_locator": self.raw_locator(index),
                    "reason": location["resolution_reason"],
                    "affected_measures": "K01",
                }
            )
        for decision in self.tables["identity_decisions"]:
            source_ids = decision["source_ids_json"]
            locators = [
                self.raw_locator(
                    next(
                        index
                        for index, row in enumerate(self.rows)
                        if row["id"] == source_id
                    )
                )
                for source_id in source_ids
            ]
            self.tables["review_coverage"].append(
                {
                    "coverage_id": self.stable_id(
                        "coverage", "candidate", decision["decision_id"]
                    ),
                    "task": f"{decision['candidate_kind']}_identity_candidate",
                    "source_ids_json": decision["source_ids_json"],
                    "review_state": decision["review_state"],
                    "disposition": decision["treatment"],
                    "evidence_locator": json_cell(locators),
                    "reason": "Complete registered candidate decision; source profile registers the evidence treatment.",
                    "affected_measures": "K08",
                }
            )
        for dimension in self.raw["stats"]:
            self.tables["review_coverage"].append(
                {
                    "coverage_id": self.stable_id("coverage", "stat", dimension),
                    "task": "raw_statistic_dimension",
                    "source_ids_json": [],
                    "review_state": "reviewed_decided",
                    "disposition": "retained_as_raw_listing_aggregate",
                    "evidence_locator": self.raw_stats_locator(dimension),
                    "reason": "Recomputed from raw listing fields."
                    if dimension != "byBusinessType"
                    else "Aggregate-only category; no row attribute exists.",
                    "affected_measures": "raw_reconciliation",
                }
            )

    def create_measure_results(self):
        businesses = self.tables["businesses"]
        resolved_provinces = {
            row["province_code"]
            for row in self.tables["locations"]
            if row["province_code"]
            and row["resolution_status"] != "unresolved_province"
        }
        self.tables["measure_results"].extend(
            [
                {
                    "measure": "K08_participating_businesses_provisional",
                    "value": str(len(businesses)),
                    "unit": "source-local business or provisional participating unit",
                    "status": "supported_provisional",
                    "basis": "distinct reviewed source-local identities with programme participation",
                    "limitations": "Participation is a K08 substitute, not measured capability growth. Cross-source identity remains out of scope.",
                },
                {
                    "measure": "K01_programme_coverage_provinces",
                    "value": str(len(resolved_provinces)),
                    "unit": "Thai provinces",
                    "status": "supported_source_local",
                    "basis": "distinct programme business-location province assertions where province is independently supported",
                    "limitations": "District/subdistrict conflicts do not erase a raw province claim. Unresolved province claims remain unknown; institution assertions do not contribute.",
                },
            ]
        )

    def add_measure_metadata(self):
        for result in self.tables["measure_results"]:
            result.update(
                measure_version="v1",
                scope="learning_area_based_snapshot",
                supported_filters_json=json_cell(
                    [
                        "province",
                        "district",
                        "subdistrict",
                        "project_name",
                        "research_unit",
                    ]
                ),
                unsupported_filters_json=json_cell(
                    [
                        "year",
                        "business_type",
                        "employment",
                        "income",
                        "person_development",
                    ]
                ),
                drilldown="business identities -> participations -> raw source and location assertions",
                aggregation="distinct business_id for K08; distinct province_code for K01; union entities across selected locations",
            )

    def validate(self):
        for table, rows in self.tables.items():
            expected = set(TABLE_COLUMNS[table])
            for row in rows:
                if set(row) != expected:
                    _fail(f"{table} row columns differ from the legacy schema")
        observation_ids = {
            row["observation_id"] for row in self.tables["source_observations"]
        }
        business_ids = {row["business_id"] for row in self.tables["businesses"]}
        if len(observation_ids) != len(self.rows):
            _fail("not every source record produced one observation")
        links = self.tables["business_observation_links"]
        if (
            len(links) != len(self.rows)
            or {row["observation_id"] for row in links} != observation_ids
        ):
            _fail(
                "not every source observation links exactly once to a business identity"
            )
        for table in ("business_observation_links", "participations", "locations"):
            if not all(
                row["business_id"] in business_ids
                and row["observation_id"] in observation_ids
                for row in self.tables[table]
            ):
                _fail(f"{table} contains an unresolved internal reference")
        project_ids = {row["assertion_id"] for row in self.tables["project_assertions"]}
        unit_ids = {
            row["assertion_id"] for row in self.tables["research_unit_assertions"]
        }
        if not all(
            row["project_assertion_id"] in project_ids
            and row["research_unit_assertion_id"] in unit_ids
            for row in self.tables["participations"]
        ):
            _fail("participation assertion link does not resolve")
        districts = {str(row["districtCode"]): row for row in self.districts}
        subdistricts = {str(row["subdistrictCode"]): row for row in self.subdistricts}
        for row in self.tables["locations"]:
            if row["district_code"] and (
                row["district_code"] not in districts
                or str(districts[row["district_code"]]["provinceCode"])
                != row["province_code"]
            ):
                _fail("emitted district does not belong to emitted province")
            if row["subdistrict_code"] and (
                row["subdistrict_code"] not in subdistricts
                or str(subdistricts[row["subdistrict_code"]]["districtCode"])
                != row["district_code"]
            ):
                _fail("emitted subdistrict does not belong to emitted district")
        linked = {row["source_id"]: row["business_id"] for row in links}
        if not all(
            linked[left] != linked[right] for left, right in self.protected_pairs
        ):
            _fail("a reviewed separate or unresolved identity boundary was bridged")
        for field in (
            "region",
            "province",
            "district",
            "subDistrict",
            "researchUnit",
            "fiscalYear",
        ):
            expected = self.raw["stats"].get("by" + field[0].upper() + field[1:])
            if (
                expected is not None
                and dict(Counter(row[field] for row in self.rows if row[field]))
                != expected
            ):
                _fail(f"raw statistic {field} does not reconcile")
        if len(self.tables["review_cases"]) != len(
            self.audit["area"]["full_hierarchy_review"]
        ):
            _fail("geography audit coverage is incomplete")

    def run(self):
        self.load_reference()
        self.register_source_files()
        self.tables["source_files"] = self.files
        self.create_observations_and_assertions()
        components = self.apply_identity_decisions()
        self.create_businesses_and_relationships(components)
        self.create_statistics_and_coverage()
        self.create_geography_review_cases()
        self.create_measure_results()
        self.add_measure_metadata()
        self.validate()
        return self.tables


def build_tables(
    datasets: dict[str, Any],
    reviews: dict,
    geography: Any,
    input_metadata: dict[str, dict],
) -> dict[str, list[dict]]:
    return LearningAreaPilot(datasets, reviews, geography, input_metadata).run()

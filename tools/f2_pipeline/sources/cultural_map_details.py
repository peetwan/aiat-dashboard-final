"""Full source-local Cultural Map details layered on the approved K12 identity core.

Only accepted injected decisions are consumed. This module performs no publication
or filesystem access; cross-source commerce remains a separate later stage.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlsplit

from ..common import (
    Components,
    PipelineError,
    normalize,
    readable,
    safe_text,
    stable_id,
)
from . import cultural_map as k12

DATASET_KEYS = k12.DATASET_KEYS

TABLE_GRAINS = {
    "source_files": "one input envelope and integrity record per dataset",
    "source_observations": "one retained raw record per source dataset row",
    "mapped_subjects": "one supported source-local mapped cultural subject",
    "mapped_listing_observations": "one original map/inspiration listing",
    "category_assertions": "one source category assertion for a mapped listing",
    "mapped_locations": "one source location assertion for a mapped listing",
    "mapped_narrative_evidence": "one narrative field assertion from a mapped listing",
    "mapped_person_role_evidence": "one mapped-listing person or role assertion",
    "mapped_media": "one media or unparsed media reference from a mapped listing",
    "date_assertions": "one source date-role assertion from a mapped listing",
    "identity_decisions": "one reviewed or screened candidate component decision",
    "offerings": "one supported source-local cultural product offering",
    "offering_listing_observations": "one original cultural product listing",
    "cultural_record_references": "one product listing relationship assertion",
    "offering_locations": "one product listing address assertion",
    "offering_prices": "one parsed price assertion per product listing",
    "offering_media": "one product media or external-link reference",
    "sellers": "one source-local seller or operator identity supported by explicit evidence",
    "seller_evidence": "one source passage supporting a seller or operator relationship",
    "people": "one source-local natural person supported by explicit cultural-business evidence",
    "person_role_evidence": "one source passage supporting a person role",
    "product_sellers": "one source-supported product/operator relationship",
    "activity_publications": "one original activity publication",
    "activity_occurrences": "one counted reported activity occurrence",
    "activity_sessions": "one session attached to a parent occurrence",
    "activity_narrative_evidence": "one activity publication description assertion",
    "activity_dates": "one activity source date or register date assertion",
    "activity_locations": "one location mentioned by an activity publication",
    "activity_media": "one activity media or external-link reference",
    "recreation_projects": "one source Re-creation project entry",
    "recreation_evidence": "one Re-creation narrative or team assertion",
    "recreation_team_members": "one supplied project team-member assertion",
    "recreation_media": "one Re-creation media reference",
    "team_profiles": "one source site-team profile",
    "target_province_evidence": "one qualifying or non-qualifying province evidence assertion",
    "target_provinces": "one distinct Thai province supported by source-local coverage",
    "category_counts": "one subject and listing count for a mapped category",
    "measure_results": "one source-local measure result",
    "measure_contributions": "one entity or province contribution to one measure",
    "review_cases": "one review case or accepted treatment",
}

TABLE_COLUMNS = {
    "source_files": [
        "dataset",
        "file",
        "json_sha256",
        "compressed_file",
        "compressed_sha256",
        "declared_compressed_sha256",
        "compressed_sha256_matches_manifest",
        "decompressed_bytes_equal_json",
        "integrity_status",
        "row_count_metadata",
        "record_count",
        "source_id",
        "run_id",
        "captured_at",
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
        "validation_warnings_json",
        "disposition",
    ],
    "mapped_subjects": [
        "subject_id",
        "source_keys_json",
        "source_ids_json",
        "display_title",
        "aliases_json",
        "identity_status",
        "k12_eligible",
        "cultural_area_eligible",
        "primary_category_codes_json",
        "province_codes_json",
        "coordinate_conflict_status",
    ],
    "mapped_listing_observations": [
        "listing_id",
        "subject_id",
        "observation_id",
        "source_key",
        "external_id",
        "title_raw",
        "title_normalized",
        "name_th_raw",
        "name_en_raw",
        "primary_category_code",
        "additional_category_codes_json",
        "cultural_type_code",
        "page_roles_json",
        "record_code_raw",
        "legacy_record_code_raw",
        "dates_json",
        "description_json",
        "funding_json",
        "assessment_json",
        "people_summary_json",
        "location_source_json",
        "metrics_json",
        "validation_warnings_json",
        "source_url",
        "discovered_from_json",
    ],
    "category_assertions": [
        "category_assertion_id",
        "subject_id",
        "observation_id",
        "source_key",
        "category_kind",
        "category_code",
        "category_name_en",
        "category_name_th",
        "source_locator",
    ],
    "mapped_locations": [
        "location_id",
        "subject_id",
        "observation_id",
        "source_key",
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
        "source_mapping_methods_json",
        "latitude",
        "longitude",
        "postal_code_raw",
        "status",
        "conflicts_json",
        "correction_reason",
        "reference_version",
        "source_admin_json",
        "address_raw",
    ],
    "mapped_narrative_evidence": [
        "evidence_id",
        "subject_id",
        "observation_id",
        "source_key",
        "field_name",
        "text",
        "source_locator",
        "status",
    ],
    "mapped_person_role_evidence": [
        "evidence_id",
        "subject_id",
        "observation_id",
        "source_key",
        "role",
        "person_or_institution_raw",
        "evidence",
        "eligibility",
        "source_locator",
    ],
    "mapped_media": [
        "media_id",
        "subject_id",
        "observation_id",
        "source_key",
        "media_kind",
        "ordinal",
        "url_or_value",
        "caption",
        "fetched_raw",
        "status",
        "source_locator",
    ],
    "date_assertions": [
        "date_assertion_id",
        "subject_id",
        "observation_id",
        "source_key",
        "date_role",
        "raw_value",
        "parsed_iso",
        "parse_status",
        "source_locator",
    ],
    "identity_decisions": [
        "decision_id",
        "namespace",
        "candidate_group_id",
        "source_keys_json",
        "left_source_key",
        "right_source_key",
        "rule",
        "outcome",
        "status",
        "title_or_name",
        "review_evidence_json",
        "evidence_observation_ids_json",
    ],
    "offerings": [
        "offering_id",
        "display_title",
        "aliases_json",
        "source_keys_json",
        "identity_status",
        "cultural_scope_eligibility",
        "generic_name_flag",
    ],
    "offering_listing_observations": [
        "listing_id",
        "offering_id",
        "observation_id",
        "source_key",
        "external_id",
        "title_raw",
        "title_normalized",
        "description",
        "product_category_raw",
        "address_text_raw",
        "related_cultural_record_raw",
        "related_record_status",
        "seller_id",
        "operator_review_status",
        "operator_review_reason",
        "price_text_raw",
        "sales_channels_raw",
        "external_links_json",
        "sales_accounts_json",
        "gallery_images_json",
        "view_count_raw",
        "validation_warnings_json",
        "source_url",
        "discovered_from_json",
    ],
    "cultural_record_references": [
        "reference_id",
        "offering_id",
        "observation_id",
        "source_key",
        "target_source_id_raw",
        "target_subject_id",
        "status",
        "relationship",
        "source_locator",
    ],
    "offering_locations": [
        "location_id",
        "offering_id",
        "observation_id",
        "source_key",
        "location_role",
        "address_raw",
        "province_raw",
        "district_raw",
        "subdistrict_raw",
        "province_normalized",
        "province_code",
        "district_normalized",
        "district_code",
        "subdistrict_normalized",
        "subdistrict_code",
        "status",
        "correction_reason",
        "reference_version",
    ],
    "offering_prices": [
        "price_id",
        "offering_id",
        "observation_id",
        "source_key",
        "price_text_raw",
        "price_kind",
        "amounts_json",
        "display_min_thb",
        "display_max_thb",
        "currency",
        "qualifier_raw",
        "parse_status",
        "source_locator",
    ],
    "offering_media": [
        "media_id",
        "offering_id",
        "observation_id",
        "source_key",
        "media_kind",
        "ordinal",
        "url_or_value",
        "label",
        "status",
        "source_locator",
    ],
    "sellers": [
        "seller_id",
        "name",
        "identity_status",
        "source_scope",
        "current_status",
    ],
    "seller_evidence": [
        "evidence_id",
        "seller_id",
        "offering_id",
        "observation_id",
        "source_key",
        "role",
        "evidence_passage",
        "basis",
    ],
    "people": [
        "person_id",
        "display_name",
        "aliases_json",
        "identity_status",
        "eligibility",
    ],
    "person_role_evidence": [
        "evidence_id",
        "person_id",
        "seller_id",
        "offering_id",
        "observation_id",
        "source_key",
        "role",
        "evidence_passage",
        "eligibility",
    ],
    "product_sellers": [
        "relationship_id",
        "offering_id",
        "seller_id",
        "person_id",
        "observation_id",
        "source_key",
        "relationship",
        "evidence_passage",
    ],
    "activity_publications": [
        "publication_id",
        "activity_id",
        "observation_id",
        "source_key",
        "external_id",
        "title",
        "description",
        "source_date_text",
        "disposition",
        "parent_key",
        "counted_as_occurrence",
        "source_url",
        "discovered_from_json",
    ],
    "activity_occurrences": [
        "activity_id",
        "publication_id",
        "observation_id",
        "source_key",
        "name",
        "start_date",
        "end_date",
        "date_evidence_json",
        "date_conflict",
        "status",
        "identity_status",
    ],
    "activity_sessions": [
        "session_id",
        "activity_id",
        "publication_id",
        "observation_id",
        "source_key",
        "session_label",
        "start_date",
        "end_date",
        "date_evidence_json",
        "status",
    ],
    "activity_narrative_evidence": [
        "evidence_id",
        "activity_id",
        "observation_id",
        "source_key",
        "field_name",
        "text",
        "source_locator",
    ],
    "activity_dates": [
        "date_assertion_id",
        "activity_id",
        "observation_id",
        "source_key",
        "date_role",
        "raw_value",
        "parsed_start_date",
        "parsed_end_date",
        "parse_status",
        "date_conflict",
        "evidence_json",
        "source_locator",
    ],
    "activity_locations": [
        "location_id",
        "activity_id",
        "observation_id",
        "source_key",
        "location_name_raw",
        "country",
        "province_normalized",
        "province_code",
        "location_role",
        "qualifies_target_province",
        "resolution_method",
        "status",
    ],
    "activity_media": [
        "media_id",
        "activity_id",
        "observation_id",
        "source_key",
        "media_kind",
        "ordinal",
        "url_or_value",
        "caption",
        "status",
        "source_locator",
    ],
    "recreation_projects": [
        "recreation_id",
        "observation_id",
        "source_key",
        "external_id",
        "title",
        "category_raw",
        "team_name_raw",
        "team_members_json",
        "description",
        "extension_text",
        "contact_present",
        "output_status",
        "identity_status",
        "source_url",
    ],
    "recreation_evidence": [
        "evidence_id",
        "recreation_id",
        "observation_id",
        "source_key",
        "field_name",
        "text",
        "source_locator",
        "interpretation",
    ],
    "recreation_team_members": [
        "member_id",
        "recreation_id",
        "observation_id",
        "source_key",
        "member_ordinal",
        "member_name_raw",
        "role",
        "kpi_eligibility",
    ],
    "recreation_media": [
        "media_id",
        "recreation_id",
        "observation_id",
        "source_key",
        "media_kind",
        "ordinal",
        "url_or_value",
        "caption",
        "status",
    ],
    "team_profiles": [
        "team_id",
        "observation_id",
        "source_key",
        "external_id",
        "profile_title",
        "group_raw",
        "profile_image_url",
        "status",
        "source_url",
    ],
    "target_province_evidence": [
        "evidence_id",
        "province_code",
        "province_name",
        "observation_id",
        "source_key",
        "evidence_entity_id",
        "location_role",
        "basis",
        "qualifies_target_province",
        "country",
    ],
    "target_provinces": [
        "province_code",
        "province_name",
        "source_keys_json",
        "observation_ids_json",
        "location_roles_json",
        "basis_json",
        "status",
    ],
    "category_counts": [
        "category_kind",
        "category_code",
        "listing_count",
        "subject_count",
        "counting_note",
    ],
    "measure_results": ["measure", "value", "scope", "status", "note"],
    "measure_contributions": [
        "measure",
        "entity_type",
        "entity_id",
        "scope",
        "status",
        "basis",
        "evidence_observation_ids_json",
    ],
    "review_cases": [
        "review_id",
        "kind",
        "source_keys_json",
        "names_json",
        "evidence_observation_ids_json",
        "reason",
        "treatment",
        "possible_impact",
        "affected_measures_json",
        "status",
    ],
}


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def matching_text(value):
    return normalize(value).casefold()


def source_key(dataset, source_id):
    return dataset + ":" + str(source_id)


def parse_source_date(raw_value, role):
    if raw_value in (None, ""):
        return "", "missing"
    raw = str(raw_value)
    if role == "recorded":
        try:
            parsed = date.fromisoformat(raw)
        except ValueError:
            return "", "invalid_source_date"
        if not 1800 <= parsed.year <= 2026:
            return parsed.isoformat(), "screening_anomaly_outside_1800_2026"
        return parsed.isoformat(), "valid_source_date"
    try:
        parsed_datetime = datetime.fromisoformat(raw)
    except ValueError:
        return "", "invalid_source_date"
    return parsed_datetime.isoformat(), "valid_source_timestamp"


def parse_price(price_text):
    raw = normalize(price_text)
    result = {
        "price_text_raw": price_text,
        "price_kind": "unknown",
        "amounts": [],
        "display_min_thb": None,
        "display_max_thb": None,
        "currency": "THB" if "บาท" in raw else "",
        "qualifier_raw": "",
        "parse_status": "unknown_price_text",
    }
    if not raw or not re.search(r"\d", raw):
        return result

    explicit_display_notation = bool(re.search(r"\d\.-", raw))
    normalized = raw.replace(".-", ".00")
    list_delimiter = bool(re.search(r",\s+|\s+(?:และ|หรือ)\s+", normalized))
    range_match = re.search(
        r"(?P<left>\d[\d,]*(?:\.\d+)?)\s*[-–]\s*(?P<right>\d[\d,]*(?:\.\d+)?)",
        normalized,
    )
    amounts = []
    if range_match and not list_delimiter:
        amounts = [range_match.group("left"), range_match.group("right")]
        result["price_kind"] = "explicit_range"
    elif list_delimiter:
        number_text = normalized.replace(",", " ")
        amounts = re.findall(r"\d+(?:\.\d+)?", number_text)
        result["price_kind"] = "discrete_list" if len(amounts) > 1 else "fixed"
    else:
        number_match = re.search(r"\d[\d,]*(?:\.\d+)?", normalized)
        if number_match:
            amounts = [number_match.group(0)]
            result["price_kind"] = "fixed"

    try:
        decimals = [Decimal(amount.replace(",", "")) for amount in amounts]
    except (InvalidOperation, ValueError):
        return result
    if not decimals:
        return result

    result["amounts"] = [str(amount) for amount in decimals]
    result["display_min_thb"] = str(min(decimals))
    result["display_max_thb"] = str(max(decimals))
    remainder = normalized
    for amount in amounts:
        remainder = remainder.replace(amount, " ", 1)
    remainder = remainder.replace("บาท", " ").replace(",", " ").replace("-", " ")
    remainder = normalize(remainder)
    result["qualifier_raw"] = remainder
    result["parse_status"] = (
        "parsed_explicit_display_notation"
        if explicit_display_notation
        else "parsed_with_qualifier"
        if remainder
        else "parsed"
    )
    return result


def comparable(value):
    return re.sub(r"\s+", "", normalize(value or ""))


def sales_accounts(record):
    """Parse account identifiers from saved links, without fetching or guessing owners."""
    links = [link.get("url", "") for link in record["data"].get("external_links", [])]
    links += re.findall(
        r"https?://[^\s<>]+", record["data"].get("sales_channels") or ""
    )
    accounts = {}
    for link in links:
        parsed = urlsplit(link)
        host = (parsed.hostname or "").lower().removeprefix("www.")
        parts = parsed.path.strip("/").split("/")
        platform = account = ""
        if (
            host == "shopee.co.th"
            and len(parts) == 3
            and parts[0] == "product"
            and all(part.isdigit() for part in parts[1:])
        ):
            platform, account = "shopee", parts[1]
        elif host == "facebook.com":
            if parts == ["profile.php"]:
                account = parse_qs(parsed.query).get("id", [""])[0]
            elif len(parts) == 1 and parts[0] not in {
                "",
                "share",
                "watch",
                "sharer.php",
            }:
                account = parts[0]
            if account:
                platform = "facebook"
        if platform:
            key = f"{platform}:{account}"
            accounts.setdefault(
                key,
                {
                    "account_key": key,
                    "platform": platform,
                    "account_id": account,
                    "source_urls": [],
                },
            )
            if link not in accounts[key]["source_urls"]:
                accounts[key]["source_urls"].append(link)
    return list(accounts.values())


def validate_role_evidence(record, case):
    """Require all configured field assertions, not a keyword anywhere in a row."""
    assertions = case.get("evidence_requirements", [])
    for assertion in assertions:
        field = assertion["field"]
        if field not in {
            "title",
            "description",
            "sales_channels",
            "price_text",
            "sales_account",
        }:
            raise ValueError(f"Unsupported role evidence field: {field}")
        value = record.get("title") if field == "title" else record["data"].get(field)
        if field == "sales_account":
            value = [account["account_key"] for account in sales_accounts(record)]
            if assertion["contains"] not in value:
                raise ValueError(f"Sales account missing for {record['external_id']}")
            continue
        phrase = assertion["contains"]
        if not comparable(phrase) or comparable(phrase) not in comparable(value):
            raise ValueError(
                f"Role evidence missing in {field} for {record['external_id']}"
            )
    if case.get("basis") == "named_sales_counterparty":
        # This supports a provisional K05 seller relationship only. Explicitly
        # following an artist is not an invitation to order their work.
        sales = record["data"].get("sales_channels") or ""
        if "ติดตามผลงาน" in sales or not assertions:
            raise ValueError(
                "A follow/contact profile does not establish a sales counterparty"
            )
    return safe_text(
        " | ".join(
            f"{assertion['field']}: {assertion['contains']}" for assertion in assertions
        )
    )


class CulturalMapDetails:
    def __init__(self, datasets, reviews, geography, input_metadata):
        self.config = reviews["details_reviewed_cases.json"]
        self.geography = geography
        self.geography_reference_version = geography.reference_version
        self.data = {key: datasets[key]["data"]["records"] for key in DATASET_KEYS}
        for key, records in self.data.items():
            metadata = input_metadata[key]
            if self.config["raw_json_sha256"][metadata["file"]] != metadata["sha256"]:
                raise PipelineError("Cultural Map detail review capture hash changed")
            if self.config["expected_record_counts"][key] != len(records):
                raise PipelineError("Cultural Map detail review row count changed")
        core = k12.build_tables(
            {key: datasets[key] for key in DATASET_KEYS},
            reviews["k12_review.json"],
            geography,
            {key: input_metadata[key] for key in DATASET_KEYS},
        )
        self.tables = defaultdict(list, core)
        self.records = {
            source_key(key, row["external_id"]): row
            for key, rows in self.data.items()
            for row in rows
        }
        self.observations = {
            row["source_key"]: row["observation_id"]
            for row in self.tables["source_observations"]
        }
        self.subject_for_source = {
            row["source_key"]: row["subject_id"]
            for row in self.tables["mapped_listing_observations"]
        }
        self.offering_for_source = {}
        self.activity_for_source = {}
        self.seller_for_source = {}
        self.person_for_source = {}
        for row in self.tables["source_observations"]:
            metadata = input_metadata[row["dataset"]]
            row["raw_file"] = (
                f"evidence://{metadata['source_id']}/{metadata['run_id']}/{metadata['file']}"
            )
            row["disposition"] = "retained_with_lineage"

    def add(self, table, **row):
        self.tables[table].append(row)

    def clean_mapped_people(self):
        for row in self.data["map_inspiration"]:
            key = source_key("map_inspiration", row["external_id"])
            data = row["data"]
            people = data.get("people") or {}
            recorder = people.get("recorder") or {}
            for role, value, label in [
                ("recorder", recorder.get("name"), "source recorder"),
                ("informant", people.get("informants_raw"), "source informant"),
                ("contact", people.get("contact_raw"), "source contact reference"),
            ]:
                if value:
                    self.add(
                        "mapped_person_role_evidence",
                        evidence_id=stable_id("cultural_map_person_role", key, role),
                        subject_id=self.subject_for_source[key],
                        observation_id=self.observations[key],
                        source_key=key,
                        role=role,
                        person_or_institution_raw=label if role == "contact" else value,
                        evidence=safe_text(str(value)),
                        eligibility="not_eligible_from_role_alone",
                        source_locator="data/people/" + role,
                    )

    def review(
        self,
        kind,
        keys,
        reason,
        treatment,
        impact,
        affected_measures,
        status="unresolved",
    ):
        keys = sorted(set(keys))
        names = []
        evidence = []
        for key in keys:
            names.append(self.records.get(key, {}).get("title", key))
            if key in self.observations:
                evidence.append(self.observations[key])
        self.add(
            "review_cases",
            review_id=stable_id("cultural_map_review", kind, keys),
            kind=kind,
            source_keys_json=keys,
            names_json=names,
            evidence_observation_ids_json=sorted(set(evidence)),
            reason=reason,
            treatment=treatment,
            possible_impact=impact,
            affected_measures_json=affected_measures,
            status=status,
        )

    def parse_product_address(self, address_text):
        raw = address_text or ""
        normalized = normalize(raw)
        province = ""
        province_match = re.search(
            r"(?:จังหวัด|จ\.)\s*([^\d]+?)(?=\s+\d{5}|$)", normalized
        )
        if province_match:
            province = normalize(province_match.group(1))
        boundary = r"(?=\s*(?:ตำบล|ต\.|อำเภอ|อ\.|เขต|จังหวัด|จ\.)|$)"
        district_values = [
            normalize(match.group(1))
            for match in re.finditer(
                rf"(?:อำเภอ|อ\.|เขต)\s*(.*?){boundary}", normalized
            )
            if normalize(match.group(1))
        ]
        subdistrict_values = [
            normalize(match.group(1))
            for match in re.finditer(rf"(?:ตำบล|ต\.)\s*(.*?){boundary}", normalized)
            if normalize(match.group(1))
        ]
        district = district_values[-1] if district_values else ""
        subdistrict = subdistrict_values[-1] if subdistrict_values else ""
        province = province.strip(" ,")
        district = district.strip(" ,")
        subdistrict = subdistrict.strip(" ,")
        resolved = self.geography.resolve(province, district or None)
        subdistrict_matches = []
        if subdistrict and resolved["district_code"]:
            subdistrict_matches = [
                value
                for value in self.geography.subdistricts
                if value["subdistrictNameTh"] == subdistrict
                and str(value["districtCode"]) == resolved["district_code"]
                and str(value["provinceCode"]) == resolved["province_code"]
            ]
        subdistrict_match = (
            subdistrict_matches[0] if len(subdistrict_matches) == 1 else None
        )
        if not province:
            status = "unresolved_address"
        elif resolved["status"] == "hierarchy_match" and subdistrict_match:
            status = "address_text_hierarchy_match"
        elif resolved["status"] == "hierarchy_match" and subdistrict:
            status = "address_text_subdistrict_unresolved"
        elif resolved["status"] == "hierarchy_match":
            status = "address_text_district_match"
        elif resolved["status"] == "province_only":
            status = "address_text_province_only"
        else:
            status = "address_text_hierarchy_unresolved"
        return {
            "address_raw": raw,
            "province_raw": province or None,
            "district_raw": district or None,
            "subdistrict_raw": subdistrict or None,
            "province_normalized": resolved["province_normalized"] if province else "",
            "province_code": resolved["province_code"],
            "district_normalized": resolved["district_normalized"] if district else "",
            "district_code": resolved["district_code"],
            "subdistrict_normalized": subdistrict_match["subdistrictNameTh"]
            if subdistrict_match
            else subdistrict,
            "subdistrict_code": str(subdistrict_match["subdistrictCode"])
            if subdistrict_match
            else "",
            "status": status,
            "correction_reason": resolved["correction_reason"],
            "reference_version": self.geography_reference_version,
        }

    def apply_offering_identity(self):
        product_keys = [
            source_key("products", r["external_id"]) for r in self.data["products"]
        ]
        components = Components(product_keys)
        for pair in self.config["reviewed_offering_merges"]:
            keys = [source_key("products", source_id) for source_id in pair]
            outcome = components.merge(*keys)
            if outcome != "merged":
                raise RuntimeError(f"Reviewed offering merge failed: {keys}: {outcome}")
            self.add(
                "identity_decisions",
                decision_id=stable_id("cultural_map_decision", "offering", keys),
                namespace="offering",
                candidate_group_id="reviewed_offering_merge",
                source_keys_json=keys,
                left_source_key=keys[0],
                right_source_key=keys[1],
                rule="reviewed_same_offering_listing",
                outcome="supported_merge",
                status="resolved_by_review",
                title_or_name=self.records[keys[0]]["title"],
                evidence_observation_ids_json=[self.observations[key] for key in keys],
            )
            self.review(
                "offering_supported_duplicate",
                keys,
                "Complete source listing evidence supports one offering with repeated publications",
                "Merge listing publications while preserving all listing, price and view assertions",
                "K07 counts one offering for this group",
                ["K07"],
                "resolved_by_review",
            )
        for root, members in sorted(components.members.items()):
            offering_id = stable_id("cultural_map_offering", root)
            for key in members:
                self.offering_for_source[key] = offering_id
            rows = [self.records[key] for key in sorted(members)]
            titles = sorted({normalize(row["title"]) for row in rows})
            self.add(
                "offerings",
                offering_id=offering_id,
                display_title=titles[0],
                aliases_json=titles,
                source_keys_json=sorted(members),
                identity_status="supported_reviewed_merge"
                if len(members) > 1
                else "source_listing_offering",
                cultural_scope_eligibility="accepted_cultural_product_listing_scope",
                generic_name_flag=matching_text(titles[0])
                in {"อาหาร", "ของใช้", "สินค้า"},
            )

    def add_offering_media(self, key, row, offering_id, observation_id):
        data = row["data"]
        for ordinal, value in enumerate(data.get("gallery_images") or []):
            url = value.get("url") if isinstance(value, dict) else value
            self.add(
                "offering_media",
                media_id=stable_id(
                    "cultural_map_offering_media", key, "gallery", ordinal
                ),
                offering_id=offering_id,
                observation_id=observation_id,
                source_key=key,
                media_kind="gallery_image",
                ordinal=ordinal,
                url_or_value=url,
                label=None,
                status="reference_only_content_not_inspected",
                source_locator=f"data/gallery_images/{ordinal}",
            )
        for ordinal, value in enumerate(data.get("external_links") or []):
            self.add(
                "offering_media",
                media_id=stable_id(
                    "cultural_map_offering_media", key, "external", ordinal
                ),
                offering_id=offering_id,
                observation_id=observation_id,
                source_key=key,
                media_kind="external_link",
                ordinal=ordinal,
                url_or_value=value.get("url") if isinstance(value, dict) else value,
                label=value.get("label") if isinstance(value, dict) else None,
                status="reference_only_content_not_inspected",
                source_locator=f"data/external_links/{ordinal}",
            )

    def clean_offerings(self):
        for row in self.data["products"]:
            key = source_key("products", row["external_id"])
            data = row["data"]
            offering_id = self.offering_for_source[key]
            observation_id = self.observations[key]
            relation = data.get("related_cultural_record")
            target_key = source_key("map_inspiration", relation) if relation else ""
            if not relation:
                relation_status = "missing_external_target"
                target_subject_id = ""
            elif target_key in self.subject_for_source:
                relation_status = "resolved_source_subject"
                target_subject_id = self.subject_for_source[target_key]
            else:
                relation_status = "unresolved_external_target"
                target_subject_id = ""
            parsed_address = self.parse_product_address(data.get("address_text"))
            self.add(
                "offering_listing_observations",
                listing_id=stable_id("cultural_map_offering_listing", key),
                offering_id=offering_id,
                observation_id=observation_id,
                source_key=key,
                external_id=row["external_id"],
                title_raw=row["title"],
                title_normalized=normalize(row["title"]),
                description=safe_text(data.get("description") or ""),
                product_category_raw=data.get("product_category"),
                address_text_raw=data.get("address_text"),
                related_cultural_record_raw=relation,
                related_record_status=relation_status,
                seller_id="",
                operator_review_status="not_reviewed",
                operator_review_reason="",
                price_text_raw=data.get("price_text"),
                sales_channels_raw=safe_text(data.get("sales_channels") or ""),
                external_links_json=data.get("external_links", []),
                sales_accounts_json=sales_accounts(row),
                gallery_images_json=data.get("gallery_images", []),
                view_count_raw=data.get("view_count"),
                validation_warnings_json=row.get("validation_warnings", []),
                source_url=row["source_url"],
                discovered_from_json=row.get("discovered_from", []),
            )
            self.add(
                "cultural_record_references",
                reference_id=stable_id("cultural_map_record_reference", key),
                offering_id=offering_id,
                observation_id=observation_id,
                source_key=key,
                target_source_id_raw=relation,
                target_subject_id=target_subject_id,
                status=relation_status,
                relationship="related_cultural_record",
                source_locator="data/related_cultural_record",
            )
            self.add(
                "offering_locations",
                location_id=stable_id("cultural_map_offering_location", key),
                offering_id=offering_id,
                observation_id=observation_id,
                source_key=key,
                location_role="offering_listing_address",
                **parsed_address,
            )
            parsed_price = parse_price(data.get("price_text"))
            self.add(
                "offering_prices",
                price_id=stable_id("cultural_map_offering_price", key),
                offering_id=offering_id,
                observation_id=observation_id,
                source_key=key,
                price_text_raw=parsed_price["price_text_raw"],
                price_kind=parsed_price["price_kind"],
                amounts_json=parsed_price["amounts"],
                display_min_thb=parsed_price["display_min_thb"],
                display_max_thb=parsed_price["display_max_thb"],
                currency=parsed_price["currency"],
                qualifier_raw=parsed_price["qualifier_raw"],
                parse_status=parsed_price["parse_status"],
                source_locator="data/price_text",
            )
            self.add_offering_media(key, row, offering_id, observation_id)

        unresolved = [
            key
            for key in self.offering_for_source
            if next(
                r
                for r in self.tables["offering_listing_observations"]
                if r["source_key"] == key
            )["related_record_status"]
            == "unresolved_external_target"
        ]
        missing = [
            key
            for key in self.offering_for_source
            if next(
                r
                for r in self.tables["offering_listing_observations"]
                if r["source_key"] == key
            )["related_record_status"]
            == "missing_external_target"
        ]
        self.review(
            "offering_external_targets_unresolved",
            unresolved,
            "Product relation target is non-empty but absent from the captured map_inspiration IDs",
            "Retain the product listing and raw target without inventing a subject join",
            "35 product-to-subject links remain unresolved",
            ["K07", "K01A"],
        )
        self.review(
            "offering_external_target_missing",
            missing,
            "Product listing has no related cultural record value",
            "Retain the product listing with no manufactured subject relationship",
            "One product has no source relationship to a captured map subject",
            ["K07", "K01A"],
        )
        for special_id, reason in [
            (
                "PD-88",
                "Discrete 69 and 49 price list retained in source order; no inverted range is inferred",
            ),
            (
                "PD-56",
                "Three size-labelled price values retained as a discrete price list",
            ),
            (
                "PD-155",
                "Three explicit package prices retained as a discrete price list",
            ),
            ("PD-27", "159.- retained through the explicit display-notation rule"),
        ]:
            self.review(
                "offering_price_parse",
                [source_key("products", special_id)],
                reason,
                "Keep raw price text and parsed Decimal amounts together",
                "Price evidence supports product detail only and never monthly income",
                ["K07"],
                "accepted_treatment",
            )

    def extract_explicit_roles(self):
        by_source_id = {row["external_id"]: row for row in self.data["products"]}
        listings = {
            row["external_id"]: row
            for row in self.tables["offering_listing_observations"]
        }
        sellers = {}
        people = {}
        supported_source_ids = {
            source_id
            for case in self.config["operator_cases"]
            for source_id in case["source_ids"]
        }
        ambiguous_source_ids = {
            source_id
            for case in self.config["ambiguous_operator_cases"]
            for source_id in case["source_ids"]
        }
        no_operator_source_ids = {
            source_id
            for case in self.config["no_supported_operator_cases"]
            for source_id in case["source_ids"]
        }
        configured_source_ids = (
            supported_source_ids | ambiguous_source_ids | no_operator_source_ids
        )
        configured_total = sum(
            len(case["source_ids"])
            for group in [
                "operator_cases",
                "ambiguous_operator_cases",
                "no_supported_operator_cases",
            ]
            for case in self.config[group]
        )
        if configured_source_ids != set(by_source_id) or configured_total != len(
            by_source_id
        ):
            raise RuntimeError(
                "Product operator dispositions are missing, duplicated, or reference unknown products"
            )
        for case in self.config["operator_cases"]:
            for source_id in case["source_ids"]:
                row = by_source_id[source_id]
                validated_evidence = validate_role_evidence(row, case)
                data = row["data"]
                evidence_text = " ".join(
                    [
                        row["title"],
                        data.get("description") or "",
                        data.get("sales_channels") or "",
                    ]
                )
                operator_name = (
                    row["title"]
                    if case.get("operator_name_from_title")
                    else case["operator_name"]
                )
                evidence_phrase = (
                    row["title"]
                    if case.get("evidence_phrase_from_title")
                    else case["evidence_phrase"]
                )
                if matching_text(evidence_phrase) not in matching_text(evidence_text):
                    raise RuntimeError(
                        f"Operator evidence changed for {source_id}: {evidence_phrase}"
                    )
                key = source_key("products", source_id)
                offering_id = self.offering_for_source[key]
                observation_id = self.observations[key]
                seller_id = stable_id("cultural_map_seller", operator_name)
                self.seller_for_source[key] = seller_id
                if seller_id not in sellers:
                    sellers[seller_id] = True
                    self.add(
                        "sellers",
                        seller_id=seller_id,
                        name=operator_name,
                        identity_status="source_reported_operator_provisional",
                        source_scope="cultural_map_only",
                        current_status=(
                            case.get("current_status", "source_reported_operator")
                        ),
                    )
                evidence = validated_evidence or safe_text(evidence_phrase)
                self.add(
                    "seller_evidence",
                    evidence_id=stable_id("cultural_map_seller_evidence", key),
                    seller_id=seller_id,
                    offering_id=offering_id,
                    observation_id=observation_id,
                    source_key=key,
                    role=case.get("relationship", "named_seller_or_operator"),
                    evidence_passage=evidence,
                    basis=case["basis"],
                )
                self.add(
                    "product_sellers",
                    relationship_id=stable_id("cultural_map_product_seller", key),
                    offering_id=offering_id,
                    seller_id=seller_id,
                    person_id="",
                    observation_id=observation_id,
                    source_key=key,
                    relationship=case.get(
                        "relationship", "explicit_named_seller_or_operator"
                    ),
                    evidence_passage=evidence,
                )
                listings[source_id]["seller_id"] = seller_id
                listings[source_id]["operator_review_status"] = "supported_operator"
                listings[source_id]["operator_review_reason"] = case["basis"]

        for case in self.config["person_role_cases"]:
            source_id = case["source_id"]
            row = by_source_id[source_id]
            validated_evidence = validate_role_evidence(row, case)
            data = row["data"]
            evidence_text = " ".join(
                [
                    row["title"],
                    data.get("description") or "",
                    data.get("sales_channels") or "",
                ]
            )
            if matching_text(case["evidence_phrase"]) not in matching_text(
                evidence_text
            ):
                raise RuntimeError(f"Person-role evidence changed for {source_id}")
            key = source_key("products", source_id)
            seller_id = self.seller_for_source[key]
            person_id = stable_id("cultural_map_person", case["person_name"])
            self.person_for_source[key] = person_id
            if person_id not in people:
                people[person_id] = True
                self.add(
                    "people",
                    person_id=person_id,
                    display_name=case["person_name"],
                    aliases_json=[case["person_name"]],
                    identity_status="source_reported_named_person",
                    eligibility="explicit_cultural_business_role",
                )
            self.add(
                "person_role_evidence",
                evidence_id=stable_id("cultural_map_person_evidence", key),
                person_id=person_id,
                seller_id=seller_id,
                offering_id=self.offering_for_source[key],
                observation_id=self.observations[key],
                source_key=key,
                role=case["role"],
                evidence_passage=validated_evidence
                or safe_text(case["evidence_phrase"]),
                eligibility=case["eligibility"],
            )
            relationship = next(
                value
                for value in self.tables["product_sellers"]
                if value["source_key"] == key
            )
            relationship["person_id"] = person_id

        for case in self.config["ambiguous_operator_cases"]:
            for source_id in case["source_ids"]:
                listings[source_id]["operator_review_status"] = (
                    "reviewed_ambiguous_role"
                )
                listings[source_id]["operator_review_reason"] = case["reason"]
                self.review(
                    "offering_operator_role_ambiguous",
                    [source_key("products", source_id)],
                    case["reason"],
                    "Keep the named evidence without creating a seller or entrepreneur identity",
                    "The case contributes to neither K05 nor K06 unless new role evidence is supplied",
                    ["K05", "K06"],
                    "reviewed_unresolved",
                )

        for case in self.config["no_supported_operator_cases"]:
            for source_id in case["source_ids"]:
                listings[source_id]["operator_review_status"] = (
                    "reviewed_no_supported_operator"
                )
                listings[source_id]["operator_review_reason"] = case["reason"]

        unfinished = [
            source_id
            for source_id, listing in listings.items()
            if listing["operator_review_status"] == "not_reviewed"
        ]
        if unfinished:
            raise RuntimeError(
                f"Products still lack explicit operator review: {unfinished}"
            )
        for case in self.config["non_qualifying_role_cases"]:
            key = source_key("products", case["source_id"])
            self.review(
                "offering_non_qualifying_role",
                [key],
                case["reason"],
                "Retain the product listing and narrative, but do not create a seller or person from this wording",
                "No seller or entrepreneur contribution from this case",
                ["K05", "K06"],
                "accepted_treatment",
            )

    def activity_config(self, source_id):
        try:
            return self.config["activity_dispositions"][source_id]
        except KeyError as exc:
            raise RuntimeError(f"Missing activity disposition for {source_id}") from exc

    def add_activity_media(self, key, row, activity_id, observation_id):
        data = row["data"]
        for media_kind, values in [
            ("gallery_image", data.get("gallery_images") or []),
            ("external_link", data.get("external_links") or []),
        ]:
            for ordinal, value in enumerate(values):
                self.add(
                    "activity_media",
                    media_id=stable_id(
                        "cultural_map_activity_media", key, media_kind, ordinal
                    ),
                    activity_id=activity_id,
                    observation_id=observation_id,
                    source_key=key,
                    media_kind=media_kind,
                    ordinal=ordinal,
                    url_or_value=value.get("url") if isinstance(value, dict) else value,
                    caption=value.get("caption") if isinstance(value, dict) else None,
                    status="reference_only_content_not_inspected",
                    source_locator=f"data/{'gallery_images' if media_kind == 'gallery_image' else 'external_links'}/{ordinal}",
                )

    def add_activity_locations(self, key, row, activity_id, observation_id, counted):
        text = normalize(row["title"] + " " + row["data"].get("description", ""))
        source_id = str(row["external_id"])
        assertions = [
            value
            for value in self.config["activity_location_assertions"]
            if value["source_id"] == source_id
        ]
        for assertion in assertions:
            if normalize(assertion["evidence_phrase"]) not in text:
                raise RuntimeError(
                    f"Activity location evidence changed for {source_id}: {assertion['evidence_phrase']}"
                )
            province = assertion["province"]
            resolved = (
                self.geography.resolve(province, None)
                if province
                else {
                    "province_normalized": "",
                    "province_code": "",
                }
            )
            self.add(
                "activity_locations",
                location_id=stable_id(
                    "cultural_map_activity_location",
                    key,
                    assertion["location_name"],
                    assertion["role"],
                ),
                activity_id=activity_id,
                observation_id=observation_id,
                source_key=key,
                location_name_raw=assertion["location_name"],
                country=assertion["country"],
                province_normalized=resolved["province_normalized"],
                province_code=resolved["province_code"],
                location_role=assertion["role"],
                qualifies_target_province=counted
                and assertion["country"] == "Thailand",
                resolution_method=assertion["resolution_method"],
                status=(
                    "resolved_thai_province"
                    if province
                    else "resolved_foreign_location"
                ),
            )

    def clean_activities(self):
        raw_ids = {str(row["external_id"]) for row in self.data["activities"]}
        config_ids = set(self.config["activity_dispositions"])
        if raw_ids != config_ids:
            raise RuntimeError(
                f"Activity register mismatch: raw={sorted(raw_ids - config_ids)} config={sorted(config_ids - raw_ids)}"
            )
        reviewed_location_ids = set(
            self.config["activity_location_reviewed_source_ids"]
        )
        if raw_ids != reviewed_location_ids:
            raise RuntimeError(
                "Activity location review coverage mismatch: "
                f"raw={sorted(raw_ids - reviewed_location_ids)} "
                f"review={sorted(reviewed_location_ids - raw_ids)}"
            )
        raw_date_ids = {
            str(row["external_id"])
            for row in self.data["activities"]
            if row["data"].get("date_text")
        }
        source_date_ids = set(self.config["activity_source_date_interpretations"])
        if raw_date_ids != source_date_ids:
            raise RuntimeError(
                "Activity source-date review coverage mismatch: "
                f"raw={sorted(raw_date_ids - source_date_ids)} "
                f"review={sorted(source_date_ids - raw_date_ids)}"
            )
        for row in self.data["activities"]:
            source_id = str(row["external_id"])
            key = source_key("activities", source_id)
            config = self.activity_config(source_id)
            observation_id = self.observations[key]
            counted = bool(config["counted"])
            activity_id = (
                stable_id("cultural_map_activity", config["parent_key"])
                if config["parent_key"]
                else ""
            )
            if counted:
                self.activity_for_source[key] = activity_id
            publication_id = stable_id("cultural_map_publication", key)
            self.add(
                "activity_publications",
                publication_id=publication_id,
                activity_id=activity_id,
                observation_id=observation_id,
                source_key=key,
                external_id=source_id,
                title=normalize(row["title"]),
                description=safe_text(readable(row["data"].get("description", ""))),
                source_date_text=row["data"].get("date_text"),
                disposition=config["disposition"],
                parent_key=config["parent_key"],
                counted_as_occurrence=counted,
                source_url=row["source_url"],
                discovered_from_json=row.get("discovered_from", []),
            )
            self.add(
                "activity_narrative_evidence",
                evidence_id=stable_id("cultural_map_activity_narrative", key),
                activity_id=activity_id,
                observation_id=observation_id,
                source_key=key,
                field_name="description",
                text=safe_text(readable(row["data"].get("description", ""))),
                source_locator="data/description",
            )
            if counted:
                date_conflict = config.get("date_conflict", "")
                self.add(
                    "activity_occurrences",
                    activity_id=activity_id,
                    publication_id=publication_id,
                    observation_id=observation_id,
                    source_key=key,
                    name=config.get("name", normalize(row["title"])),
                    start_date=config.get("start_date"),
                    end_date=config.get("end_date"),
                    date_evidence_json=config.get("date_evidence", []),
                    date_conflict=date_conflict,
                    status="reported_occurrence",
                    identity_status="provisional_reported_activity",
                )
                self.add_activity_locations(key, row, activity_id, observation_id, True)
            elif config["disposition"] == "session":
                self.add(
                    "activity_sessions",
                    session_id=stable_id("cultural_map_activity_session", key),
                    activity_id=stable_id(
                        "cultural_map_activity", config["parent_key"]
                    ),
                    publication_id=publication_id,
                    observation_id=observation_id,
                    source_key=key,
                    session_label=config["session_label"],
                    start_date=config.get("start_date"),
                    end_date=config.get("end_date"),
                    date_evidence_json=config.get("date_evidence", []),
                    status="session_detail_not_separate_occurrence",
                )
                self.add_activity_locations(
                    key,
                    row,
                    stable_id("cultural_map_activity", config["parent_key"]),
                    observation_id,
                    False,
                )
            else:
                self.add_activity_locations(key, row, "", observation_id, False)
            raw_date = row["data"].get("date_text")
            source_date = self.config["activity_source_date_interpretations"].get(
                source_id
            )
            if source_date and source_date["raw_value"] != raw_date:
                raise RuntimeError(f"Activity source date changed for {source_id}")
            self.add(
                "activity_dates",
                date_assertion_id=stable_id(
                    "cultural_map_activity_date", key, "source"
                ),
                activity_id=activity_id,
                observation_id=observation_id,
                source_key=key,
                date_role="source_date_text",
                raw_value=raw_date,
                parsed_start_date=source_date["start_date"] if source_date else "",
                parsed_end_date=source_date["end_date"] if source_date else "",
                parse_status=(
                    "reviewed_source_field_BE_conversion"
                    if source_date
                    else "missing_source_date_text"
                ),
                date_conflict=(config.get("date_conflict", "") if source_date else ""),
                evidence_json=[raw_date] if raw_date else [],
                source_locator="data/date_text",
            )
            if config.get("date_evidence") and config.get("start_date"):
                self.add(
                    "activity_dates",
                    date_assertion_id=stable_id(
                        "cultural_map_activity_date", key, "register"
                    ),
                    activity_id=activity_id,
                    observation_id=observation_id,
                    source_key=key,
                    date_role="accepted_activity_register",
                    raw_value="; ".join(config["date_evidence"]),
                    parsed_start_date=config.get("start_date"),
                    parsed_end_date=config.get("end_date"),
                    parse_status="accepted_explicit_date_evidence",
                    date_conflict=config.get("date_conflict", ""),
                    evidence_json=config["date_evidence"],
                    source_locator="config/cultural_map/reviewed_cases.json",
                )
            self.add_activity_media(key, row, activity_id, observation_id)

        self.review(
            "activity_workshop_sessions",
            [source_key("activities", f"G-{number}") for number in range(340, 347)],
            "G-340 through G-346 describe one Workshop 1 parent occurrence with room/day detail",
            "Count one parent occurrence and retain six session publications",
            "Six publications are not six additional K03 activities",
            ["K03", "K01A"],
            "accepted_treatment",
        )
        self.review(
            "activity_context_only_publications",
            [
                source_key("activities", f"G-{number}")
                for number in [364, 365, 366, 367, 368, 369, 374]
            ],
            "These publications do not identify a particular activity occurrence under the accepted register",
            "Retain source context and narrative without a counted activity contribution",
            "Seven publications remain outside K03",
            ["K03", "K01A"],
            "accepted_treatment",
        )
        for source_id in ["G-375", "G-381", "G-386"]:
            key = source_key("activities", source_id)
            config = self.activity_config(source_id)
            self.review(
                "activity_date_or_location_treatment",
                [key],
                "; ".join(config["date_evidence"]),
                "Retain the explicit source date roles and any conflict without a year filter or repair",
                "Activity remains a provisional reported occurrence; date/location detail is source evidence",
                ["K01A", "K03"],
                "accepted_treatment",
            )

    def clean_recreation_and_team(self):
        for row in self.data["recreation"]:
            key = source_key("recreation", row["external_id"])
            recreation_id = stable_id("cultural_map_recreation", key)
            observation_id = self.observations[key]
            data = row["data"]
            self.add(
                "recreation_projects",
                recreation_id=recreation_id,
                observation_id=observation_id,
                source_key=key,
                external_id=row["external_id"],
                title=row["title"],
                category_raw=data.get("recreation_category"),
                team_name_raw=data.get("team_name"),
                team_members_json=data.get("team_members", []),
                description=safe_text(data.get("description", "")),
                extension_text=safe_text(data.get("extension_text") or ""),
                contact_present=bool(data.get("contact_text")),
                output_status="source_described_proposal_not_a_KPI_entity",
                identity_status="source_project_retained_distinct",
                source_url=row["source_url"],
            )
            self.add(
                "recreation_evidence",
                evidence_id=stable_id(
                    "cultural_map_recreation_evidence", key, "description"
                ),
                recreation_id=recreation_id,
                observation_id=observation_id,
                source_key=key,
                field_name="description",
                text=safe_text(data.get("description", "")),
                source_locator="data/description",
                interpretation="cultural theme and project context, not an inferred product or event",
            )
            if data.get("extension_text"):
                self.add(
                    "recreation_evidence",
                    evidence_id=stable_id(
                        "cultural_map_recreation_evidence", key, "extension"
                    ),
                    recreation_id=recreation_id,
                    observation_id=observation_id,
                    source_key=key,
                    field_name="extension_text",
                    text=safe_text(data["extension_text"]),
                    source_locator="data/extension_text",
                    interpretation="proposed or described output, not an automatically counted offering",
                )
            for ordinal, member in enumerate(data.get("team_members", [])):
                self.add(
                    "recreation_team_members",
                    member_id=stable_id("cultural_map_recreation_member", key, ordinal),
                    recreation_id=recreation_id,
                    observation_id=observation_id,
                    source_key=key,
                    member_ordinal=ordinal,
                    member_name_raw=member,
                    role="supplied_project_team_member",
                    kpi_eligibility="not_inferred_from_membership",
                )
            for media_kind, values in [
                ("gallery_image", data.get("gallery_images") or []),
                (
                    "external_image_link",
                    [data["external_image_link"]]
                    if data.get("external_image_link")
                    else [],
                ),
                (
                    "external_video_link",
                    [data["external_video_link"]]
                    if data.get("external_video_link")
                    else [],
                ),
            ]:
                for ordinal, value in enumerate(values):
                    self.add(
                        "recreation_media",
                        media_id=stable_id(
                            "cultural_map_recreation_media", key, media_kind, ordinal
                        ),
                        recreation_id=recreation_id,
                        observation_id=observation_id,
                        source_key=key,
                        media_kind=media_kind,
                        ordinal=ordinal,
                        url_or_value=value.get("url")
                        if isinstance(value, dict)
                        else value,
                        caption=value.get("caption")
                        if isinstance(value, dict)
                        else None,
                        status="reference_only_content_not_inspected",
                    )
        repeated_groups = [
            ["REDetail-1", "REDetail-15"],
            ["REDetail-26", "REDetail-27"],
            ["REDetail-72", "REDetail-84", "REDetail-88"],
            ["REDetail-78", "REDetail-96"],
        ]
        for group in repeated_groups:
            keys = [source_key("recreation", value) for value in group]
            self.review(
                "recreation_theme_not_identity",
                keys,
                "Repeated theme/title is accompanied by different teams or project/output evidence",
                "Retain each Re-creation project separately and do not infer products, businesses or authors",
                "No automatic K05, K06, K07 or K12 contribution",
                ["K05", "K06", "K07", "K12"],
                "resolved_separate",
            )
        for row in self.data["team"]:
            key = source_key("team", row["external_id"])
            observation_id = self.observations[key]
            self.add(
                "team_profiles",
                team_id=stable_id("cultural_map_team", key),
                observation_id=observation_id,
                source_key=key,
                external_id=row["external_id"],
                profile_title=row["title"],
                group_raw=row["data"]["group"],
                profile_image_url=row["data"].get("profile_image_url"),
                status="site_team_provenance_only",
                source_url=row["source_url"],
            )

    def build_target_provinces(self):
        for row in self.tables["mapped_locations"]:
            if row["province_code"]:
                self.add(
                    "target_province_evidence",
                    evidence_id=stable_id(
                        "cultural_map_target_province", row["observation_id"], "map"
                    ),
                    province_code=row["province_code"],
                    province_name=row["province_normalized"],
                    observation_id=row["observation_id"],
                    source_key=row["source_key"],
                    evidence_entity_id=row["subject_id"],
                    location_role="mapped_subject_location",
                    basis="source-published cultural subject coverage",
                    qualifies_target_province=True,
                    country="Thailand",
                )
        for row in self.tables["offering_locations"]:
            if row["province_code"]:
                self.add(
                    "target_province_evidence",
                    evidence_id=stable_id(
                        "cultural_map_target_province",
                        row["observation_id"],
                        "offering",
                    ),
                    province_code=row["province_code"],
                    province_name=row["province_normalized"],
                    observation_id=row["observation_id"],
                    source_key=row["source_key"],
                    evidence_entity_id=row["offering_id"],
                    location_role="offering_listing_address",
                    basis="source-published cultural product location",
                    qualifies_target_province=True,
                    country="Thailand",
                )
        for row in self.tables["activity_locations"]:
            if row["country"] == "Thailand" and row["province_code"]:
                self.add(
                    "target_province_evidence",
                    evidence_id=stable_id(
                        "cultural_map_target_province",
                        row["observation_id"],
                        "activity",
                        row["province_code"],
                    ),
                    province_code=row["province_code"],
                    province_name=row["province_normalized"],
                    observation_id=row["observation_id"],
                    source_key=row["source_key"],
                    evidence_entity_id=row["activity_id"],
                    location_role="reported_activity_location",
                    basis="reported activity location",
                    qualifies_target_province=row["qualifies_target_province"],
                    country="Thailand",
                )
        grouped = defaultdict(list)
        for row in self.tables["target_province_evidence"]:
            if row["qualifies_target_province"]:
                grouped[row["province_code"]].append(row)
        for province_code, rows in sorted(grouped.items()):
            self.add(
                "target_provinces",
                province_code=province_code,
                province_name=rows[0]["province_name"],
                source_keys_json=sorted({row["source_key"] for row in rows}),
                observation_ids_json=sorted({row["observation_id"] for row in rows}),
                location_roles_json=sorted({row["location_role"] for row in rows}),
                basis_json=sorted({row["basis"] for row in rows}),
                status="provisional_source_local_target_province",
            )


def build_tables(datasets, reviews, geography, input_metadata):
    builder = CulturalMapDetails(datasets, reviews, geography, input_metadata)
    builder.clean_mapped_people()
    builder.apply_offering_identity()
    builder.clean_offerings()
    builder.extract_explicit_roles()
    builder.clean_activities()
    builder.clean_recreation_and_team()
    builder.build_target_provinces()
    known_observations = set(builder.observations.values())
    for name, rows in builder.tables.items():
        for row in rows:
            observation = row.get("observation_id")
            if observation and observation not in known_observations:
                raise PipelineError(
                    f"Cultural Map detail has an unknown observation: {name}"
                )
    # Keep declared empty detail tables so downstream adapters never infer absence.
    for name in TABLE_COLUMNS:
        builder.tables[name]
    return dict(builder.tables)

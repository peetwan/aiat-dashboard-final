"""Pure Learning dashboard aggregate normalization preserving legacy source semantics."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..common import stable_id as common_stable_id

DATASET_KEYS = (
    "learning_dashboard_response",
    "dashboard_keys",
    "refresh_summary",
    "capture_manifest",
)
COUNT_LABELS = {
    "provinces": "province",
    "entityTypes": "business_form",
    "categories": "business_category",
    "geography": "region",
}
IMPACT_METRICS = {
    "localEmployeeAmount": (
        "people/month",
        "totalEmplyeeAmount",
        "reported_monthly_employment",
    ),
    "localEmployeeExpense": ("THB/month", "totalEmployeeExpense", "worker_payments"),
    "localResourceConsumption": (
        "kg/month",
        "totalResourceConsumption",
        "resource_quantity",
    ),
    "localResourceExpense": ("THB/month", "totalResourceExpense", "resource_spending"),
}
TABLE_GRAINS = {
    "source_files": "one supplied capture file, including non-observation metadata",
    "source_observations": "one top-level response key, never an entity",
    "count_dimension_headers": "one display header retained from a count dimension",
    "count_members": "one header-excluded count member in one non-additive dimension",
    "regional_impacts": "one unlabeled raw regional impact object with guide-supported positional mapping",
    "impact_components": "one metric in one regional impact object",
    "impact_summary_metrics": "one raw impactSummary metric used only for reconciliation",
    "reconciliation_links": "one regional component linked to its matching summary metric",
    "excluded_amounts": "one separately reported excluded-resource amount",
    "coverage_assertions": "one positive province aggregate supporting source-reported coverage",
    "measure_results": "one source-local measure version or companion result",
    "measure_contributions": "one raw aggregate component contributing to one measure version",
    "review_coverage": "one inspected response family, aggregate member, metric, or special amount",
    "integrity_reviews": "one declared-hash discrepancy assessment",
}
TABLE_COLUMNS = {
    "source_files": [
        "file_id",
        "file",
        "role",
        "sha256",
        "manifest_sha256",
        "declared_hash_status",
        "integrity_status",
        "integrity_limitation",
    ],
    "source_observations": [
        "observation_id",
        "source_key",
        "source_kind",
        "raw_locator",
        "raw_file",
        "raw_file_sha256",
        "value_type",
        "entity_inventory",
        "disposition",
    ],
    "count_dimension_headers": [
        "header_id",
        "observation_id",
        "dimension",
        "label_header_raw",
        "count_header_raw",
        "raw_locator",
        "treatment",
    ],
    "count_members": [
        "count_member_id",
        "observation_id",
        "header_id",
        "dimension",
        "dimension_label",
        "position",
        "label_raw",
        "count",
        "unit",
        "raw_locator",
        "nonadditive_group",
        "filter_support",
    ],
    "regional_impacts": [
        "regional_impact_id",
        "observation_id",
        "position",
        "region_raw",
        "region_mapping_basis",
        "raw_locator",
        "mapping_limit",
    ],
    "impact_components": [
        "component_id",
        "regional_impact_id",
        "observation_id",
        "position",
        "region_raw",
        "raw_field",
        "metric_kind",
        "amount",
        "unit",
        "raw_locator",
    ],
    "impact_summary_metrics": [
        "summary_metric_id",
        "observation_id",
        "raw_field",
        "stable_metric_name",
        "amount",
        "unit",
        "raw_locator",
        "treatment",
    ],
    "reconciliation_links": [
        "reconciliation_link_id",
        "summary_metric_id",
        "component_id",
        "summary_raw_field",
        "relationship",
    ],
    "excluded_amounts": [
        "excluded_amount_id",
        "observation_id",
        "region_raw",
        "amount",
        "unit",
        "raw_locator",
        "meaning_status",
        "treatment",
    ],
    "coverage_assertions": [
        "coverage_assertion_id",
        "count_member_id",
        "province_raw",
        "province_normalized",
        "province_code",
        "reference_version",
        "reported_business_count",
        "coverage_role",
        "raw_locator",
        "limitation",
    ],
    "measure_results": [
        "measure",
        "definition_version",
        "value",
        "unit",
        "status",
        "basis",
        "reporting_period",
        "supported_drilldown",
        "supported_filters",
        "unsupported_filters",
        "filter_metadata_json",
        "nonadditive_group",
        "limitations",
    ],
    "measure_contributions": [
        "measure",
        "contributor_type",
        "contributor_id",
        "amount",
        "unit",
        "raw_locator",
        "contribution_role",
    ],
    "review_coverage": [
        "coverage_id",
        "task",
        "source_reference",
        "review_state",
        "disposition",
        "evidence_locator",
        "reason",
        "affected_measures",
    ],
    "integrity_reviews": [
        "integrity_review_id",
        "file_id",
        "actual_sha256",
        "declared_sha256",
        "status",
        "treatment",
        "reason",
    ],
}


def json_cell(value):
    return value


def decimal_text(value):
    try:
        return format(Decimal(str(value)), "f")
    except Exception as exc:
        raise ValueError(
            "Learning dashboard input contract: aggregate value is not decimal"
        ) from exc


def _fail(message):
    raise ValueError(f"Learning dashboard input contract: {message}")


class LearningDashboardPilot:
    def __init__(self, datasets, reviews, geography, input_metadata):
        if set(datasets) != set(DATASET_KEYS):
            _fail(f"datasets must be exactly {', '.join(DATASET_KEYS)}")
        config = (
            reviews.get("reviewed_cases.json", reviews.get("reviewed_cases"))
            if isinstance(reviews, dict)
            else None
        )
        if not isinstance(config, dict):
            _fail("reviewed_cases.json must be supplied")
        self.raw = datasets["learning_dashboard_response"]
        if not isinstance(self.raw, dict):
            _fail("learning_dashboard_response must be an object")
        expected = set(COUNT_LABELS) | {
            "geographyImpact",
            "impactSummary",
            "excludedResourceExpense",
        }
        if set(self.raw) != expected:
            _fail(
                "authoritative response key set differs from reviewed aggregate schema"
            )
        self.config, self.datasets = config, datasets
        self.geography, self.input_metadata = geography, input_metadata
        self.geography_version = getattr(geography, "reference_version", "")
        self.tables = {name: [] for name in TABLE_COLUMNS}
        self.files = []

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
        return common_stable_id(
            f"learning_dashboard_{kind}",
            self.metadata("learning_dashboard_response")["run_id"],
            *parts,
        )

    def raw_locator(self, suffix):
        metadata = self.metadata("learning_dashboard_response")
        return f"evidence://{metadata['source_id']}/{metadata['run_id']}/{metadata['file']}#/{suffix}"

    def register_source_files(self):
        manifest = self.datasets["capture_manifest"]
        if not isinstance(manifest, dict):
            _fail("capture_manifest must be an object")
        response_meta = self.metadata("learning_dashboard_response")
        if (
            manifest.get("source_id") != response_meta["source_id"]
            or manifest.get("run_id") != response_meta["run_id"]
        ):
            _fail(
                "capture manifest source/run identity differs from authoritative metadata"
            )
        reviewed_hash = self.config.get("source_files", {}).get(response_meta["file"])
        if reviewed_hash and reviewed_hash != response_meta["sha256"]:
            _fail("reviewed authoritative response hash changed")
        declared = {
            item.get("file"): item.get("sha256", "")
            for item in [
                *manifest.get("datasets", []),
                *manifest.get("extra_files", []),
            ]
            if isinstance(item, dict)
        }
        roles = {
            "dashboard_keys": "top_level_key_inventory",
            "learning_dashboard_response": "authoritative_aggregate_response",
            "refresh_summary": "collection_metadata_and_key_count_reconciliation",
            "capture_manifest": "collector_provenance_and_declared_hashes",
        }
        allowed = {
            (item["file"], item["actual_sha256"], item["declared_sha256"]): item
            for item in self.config.get("allowed_declared_hash_discrepancies", [])
        }
        for dataset, role in roles.items():
            metadata = self.metadata(dataset)
            actual, expected = (
                metadata["sha256"],
                declared.get(metadata["file"], metadata.get("declared_sha256", "")),
            )
            if not expected:
                declared_status, integrity_status, limitation = (
                    "not_declared",
                    "not_applicable",
                    "No collector declaration for this supplied file.",
                )
            elif actual == expected:
                declared_status, integrity_status, limitation = (
                    "passed",
                    "declared_hash_matches",
                    "",
                )
            elif (metadata["file"], actual, expected) in allowed:
                declared_status, integrity_status, limitation = (
                    "failed_allowed_discrepancy",
                    "known_declared_hash_discrepancy",
                    allowed[(metadata["file"], actual, expected)]["reason"],
                )
            else:
                _fail(f"unexpected declared hash discrepancy: {metadata['file']}")
            self.files.append(
                {
                    "file_id": self.stable_id("file", metadata["file"]),
                    "file": metadata["file"],
                    "role": role,
                    "sha256": actual,
                    "manifest_sha256": expected,
                    "declared_hash_status": declared_status,
                    "integrity_status": integrity_status,
                    "integrity_limitation": limitation,
                }
            )
        inventory = self.datasets["dashboard_keys"]
        if not isinstance(inventory, list) or [
            row.get("key") for row in inventory if isinstance(row, dict)
        ] != sorted(self.raw):
            _fail("dashboard_keys differs from authoritative response keys")
        refresh = self.datasets["refresh_summary"]
        if (
            not isinstance(refresh, dict)
            or refresh.get("province_rows") != len(self.raw["provinces"])
            or refresh.get("keys") != sorted(self.raw)
        ):
            _fail("refresh_summary differs from authoritative response")
        keys_meta = self.metadata("dashboard_keys")
        canonical_path = keys_meta.get("canonical_evidence_path")
        if canonical_path:
            expected = declared.get(canonical_path, "")
            if not expected:
                _fail("canonical dashboard key inventory lacks a manifest hash")
            self.files.append(
                {
                    "file_id": self.stable_id("file", canonical_path),
                    "file": canonical_path,
                    "role": "compressed_top_level_key_inventory_copy",
                    "sha256": expected,
                    "manifest_sha256": expected,
                    "declared_hash_status": "passed",
                    "integrity_status": "declared_hash_matches",
                    "integrity_limitation": "Canonical compressed bytes validated by the input lock; decoded rows equal dashboard_keys.",
                }
            )

    def add_source_observations(self):
        for key in sorted(self.raw):
            self.tables["source_observations"].append(
                {
                    "observation_id": self.stable_id("response_key", key),
                    "source_key": key,
                    "source_kind": "aggregate_response_key",
                    "raw_locator": self.raw_locator(key),
                    "raw_file": self.metadata("learning_dashboard_response")["file"],
                    "raw_file_sha256": self.metadata("learning_dashboard_response")[
                        "sha256"
                    ],
                    "value_type": type(self.raw[key]).__name__,
                    "entity_inventory": "False",
                    "disposition": "retained_as_aggregate_or_metadata",
                }
            )

    def add_count_dimensions(self):
        for source_key in self.config["count_dimensions"]:
            rows = self.raw[source_key]
            header = rows[0]
            header_id = self.stable_id("count_header", source_key)
            self.tables["count_dimension_headers"].append(
                {
                    "header_id": header_id,
                    "observation_id": self.stable_id("response_key", source_key),
                    "dimension": source_key,
                    "label_header_raw": header[0],
                    "count_header_raw": header[1],
                    "raw_locator": self.raw_locator(f"{source_key}/0"),
                    "treatment": "retained_as_display_header_excluded_from_facts",
                }
            )
            for position, row in enumerate(rows[1:], 1):
                assert len(row) == 2 and isinstance(row[1], int) and row[1] > 0
                self.tables["count_members"].append(
                    {
                        "count_member_id": self.stable_id(
                            "count_member", source_key, position
                        ),
                        "observation_id": self.stable_id("response_key", source_key),
                        "header_id": header_id,
                        "dimension": source_key,
                        "dimension_label": COUNT_LABELS[source_key],
                        "position": str(position),
                        "label_raw": row[0],
                        "count": str(row[1]),
                        "unit": "source-reported businesses",
                        "raw_locator": self.raw_locator(f"{source_key}/{position}"),
                        "nonadditive_group": "dashboard_reported_businesses_375",
                        "filter_support": "count_dimension_only",
                    }
                )

    def add_impact_facts(self):
        regions = self.config["regional_impact_position_order"]
        assert [row[0] for row in self.raw["geography"][1:]] == regions
        assert len(self.raw["geographyImpact"]) == len(regions) == 6
        for position, (region, impact) in enumerate(
            zip(regions, self.raw["geographyImpact"]), 1
        ):
            regional_id = self.stable_id("regional_impact", position)
            self.tables["regional_impacts"].append(
                {
                    "regional_impact_id": regional_id,
                    "observation_id": self.stable_id("response_key", "geographyImpact"),
                    "position": str(position),
                    "region_raw": region,
                    "region_mapping_basis": self.config[
                        "regional_impact_mapping_basis"
                    ],
                    "raw_locator": self.raw_locator(f"geographyImpact/{position - 1}"),
                    "mapping_limit": "Raw impact object has no region ID. Check this position order again for a changed capture.",
                }
            )
            assert set(impact) == set(IMPACT_METRICS)
            for raw_field, (unit, summary_field, metric_kind) in IMPACT_METRICS.items():
                component_id = self.stable_id("impact_component", position, raw_field)
                self.tables["impact_components"].append(
                    {
                        "component_id": component_id,
                        "regional_impact_id": regional_id,
                        "observation_id": self.stable_id(
                            "response_key", "geographyImpact"
                        ),
                        "position": str(position),
                        "region_raw": region,
                        "raw_field": raw_field,
                        "metric_kind": metric_kind,
                        "amount": decimal_text(impact[raw_field]),
                        "unit": unit,
                        "raw_locator": self.raw_locator(
                            f"geographyImpact/{position - 1}/{raw_field}"
                        ),
                    }
                )
                self.tables["reconciliation_links"].append(
                    {
                        "reconciliation_link_id": self.stable_id(
                            "reconciliation", component_id, summary_field
                        ),
                        "summary_metric_id": self.stable_id(
                            "impact_summary_metric", summary_field
                        ),
                        "component_id": component_id,
                        "summary_raw_field": summary_field,
                        "relationship": "component_of_summary_reconciliation_not_additional_contribution",
                    }
                )
        for raw_field, value in self.raw["impactSummary"].items():
            unit = next(
                unit
                for unit, summary, _ in IMPACT_METRICS.values()
                if summary == raw_field
            )
            self.tables["impact_summary_metrics"].append(
                {
                    "summary_metric_id": self.stable_id(
                        "impact_summary_metric", raw_field
                    ),
                    "observation_id": self.stable_id("response_key", "impactSummary"),
                    "raw_field": raw_field,
                    "stable_metric_name": "reported_monthly_employment_total"
                    if raw_field == "totalEmplyeeAmount"
                    else raw_field,
                    "amount": decimal_text(value),
                    "unit": unit,
                    "raw_locator": self.raw_locator(f"impactSummary/{raw_field}"),
                    "treatment": "reconciliation_only_not_additional_contribution",
                }
            )
        excluded = self.raw["excludedResourceExpense"]
        self.tables["excluded_amounts"].append(
            {
                "excluded_amount_id": self.stable_id("excluded_resource_expense"),
                "observation_id": self.stable_id(
                    "response_key", "excludedResourceExpense"
                ),
                "region_raw": excluded["region"],
                "amount": decimal_text(excluded["amount"]),
                "unit": "THB/month_assumed_for_K10B_only",
                "raw_locator": self.raw_locator("excludedResourceExpense"),
                "meaning_status": "reviewed_unresolved",
                "treatment": "separate_component_used_only_under_K10B_assumption",
            }
        )

    def add_coverage_and_measures(self):
        province_members = [
            row
            for row in self.tables["count_members"]
            if row["dimension"] == "provinces"
        ]
        for member in province_members:
            resolved = self.geography.resolve(member["label_raw"], "")
            assert resolved["province_code"], (
                f"unresolved coverage province: {member['label_raw']}"
            )
            self.tables["coverage_assertions"].append(
                {
                    "coverage_assertion_id": self.stable_id(
                        "coverage", member["count_member_id"]
                    ),
                    "count_member_id": member["count_member_id"],
                    "province_raw": member["label_raw"],
                    "province_normalized": resolved["province_normalized"],
                    "province_code": resolved["province_code"],
                    "reference_version": self.geography_version,
                    "reported_business_count": member["count"],
                    "coverage_role": "positive_source_reported_programme_coverage",
                    "raw_locator": member["raw_locator"],
                    "limitation": "Aggregate count only. It does not identify a business or link employment or income to a province.",
                }
            )
        totals = {
            field: sum(
                Decimal(row["amount"])
                for row in self.tables["impact_components"]
                if row["raw_field"] == field
            )
            for field in IMPACT_METRICS
        }
        province_count = len(
            {row["province_code"] for row in self.tables["coverage_assertions"]}
        )
        business_count = sum(int(row["count"]) for row in province_members)
        k10a = (
            totals["localEmployeeExpense"] + totals["localResourceExpense"]
        ) / Decimal("1000000")
        k10b = (
            totals["localResourceExpense"]
            + Decimal(self.tables["excluded_amounts"][0]["amount"])
        ) / Decimal("1000000")
        common_limits = "No year filter. No business/person inventory. Count dimensions are separate non-additive representations."
        self.tables["measure_results"].extend(
            [
                self.measure_result(
                    "K01A_dashboard_source_reported_coverage_provinces_v1",
                    str(province_count),
                    "provinces",
                    "supported_source_aggregate",
                    "positive province-count members",
                    "province counts only",
                    "province",
                    common_limits,
                ),
                self.measure_result(
                    "K08_dashboard_reported_participating_businesses_companion_v1",
                    str(business_count),
                    "source-reported businesses",
                    "supported_aggregate_companion",
                    "each of four independent count dimensions sums to 375",
                    "one selected count dimension",
                    "province, business_form, business_category, region",
                    "Unknown relationship to the directory-based K08 population. Do not add or allocate these breakdowns.",
                ),
                self.measure_result(
                    "K09_source_reported_monthly_employment_v1",
                    decimal_text(totals["localEmployeeAmount"]),
                    "people/month",
                    "supported_source_aggregate",
                    "sum of six localEmployeeAmount components",
                    "regional impact components",
                    "region only",
                    "Observation month and underlying employee identities are unknown. Province and category filters are unavailable.",
                ),
                self.measure_result(
                    "K10A_reported_monthly_income_to_local_workers_and_suppliers_v1",
                    decimal_text(k10a),
                    "million THB/month",
                    "supported_with_assumptions",
                    "(sum localEmployeeExpense + sum localResourceExpense) / 1,000,000",
                    "regional worker-payment and resource-spending components",
                    "region only",
                    self.config["k10_versions"][
                        "K10A_reported_monthly_income_to_local_workers_and_suppliers_v1"
                    ]["assumption"]
                    + " Versions overlap and must not be summed.",
                ),
                self.measure_result(
                    "K10B_assumed_historical_local_income_reconstruction_v1",
                    decimal_text(k10b),
                    "million THB/month",
                    "supported_with_assumptions",
                    "(sum localResourceExpense + excludedResourceExpense.amount) / 1,000,000",
                    "regional resource-spending components plus one Central assertion",
                    "region only for resource spending; no subregional breakdown for excluded amount",
                    self.config["k10_versions"][
                        "K10B_assumed_historical_local_income_reconstruction_v1"
                    ]["assumption"]
                    + " Versions overlap and must not be summed.",
                ),
            ]
        )
        for member in self.tables["count_members"]:
            self.contribution(
                "K08_dashboard_reported_participating_businesses_companion_v1",
                "count_member",
                member["count_member_id"],
                member["count"],
                "source-reported businesses",
                member["raw_locator"],
                "nonadditive_dimension_representation",
            )
        for coverage in self.tables["coverage_assertions"]:
            self.contribution(
                "K01A_dashboard_source_reported_coverage_provinces_v1",
                "coverage_assertion",
                coverage["coverage_assertion_id"],
                "1",
                "province",
                coverage["raw_locator"],
                "positive_coverage_assertion",
            )
        components = self.tables["impact_components"]
        for component in components:
            if component["raw_field"] == "localEmployeeAmount":
                self.contribution(
                    "K09_source_reported_monthly_employment_v1",
                    "impact_component",
                    component["component_id"],
                    component["amount"],
                    component["unit"],
                    component["raw_locator"],
                    "additive_regional_component",
                )
            if component["raw_field"] in {
                "localEmployeeExpense",
                "localResourceExpense",
            }:
                self.contribution(
                    "K10A_reported_monthly_income_to_local_workers_and_suppliers_v1",
                    "impact_component",
                    component["component_id"],
                    component["amount"],
                    component["unit"],
                    component["raw_locator"],
                    "additive_assumed_component",
                )
            if component["raw_field"] == "localResourceExpense":
                self.contribution(
                    "K10B_assumed_historical_local_income_reconstruction_v1",
                    "impact_component",
                    component["component_id"],
                    component["amount"],
                    component["unit"],
                    component["raw_locator"],
                    "additive_assumed_component",
                )
        excluded = self.tables["excluded_amounts"][0]
        self.contribution(
            "K10B_assumed_historical_local_income_reconstruction_v1",
            "excluded_amount",
            excluded["excluded_amount_id"],
            excluded["amount"],
            "THB/month_assumed",
            excluded["raw_locator"],
            "accepted_assumption_component",
        )

    def measure_result(
        self, measure, value, unit, status, basis, drilldown, filters, limitations
    ):
        reporting_period = (
            "monthly unit; observation month unavailable"
            if measure.startswith(("K09", "K10"))
            else "source snapshot; observation period unavailable"
        )
        return {
            "measure": measure,
            "definition_version": "v1",
            "value": value,
            "unit": unit,
            "status": status,
            "basis": basis,
            "reporting_period": reporting_period,
            "supported_drilldown": drilldown,
            "supported_filters": filters,
            "unsupported_filters": "Any unsupported filter returns unavailable, never zero or allocated overall values.",
            "filter_metadata_json": self.filter_metadata(measure, filters),
            "nonadditive_group": "K10_versions_overlap_do_not_sum"
            if measure.startswith("K10")
            else "",
            "limitations": limitations,
        }

    def filter_metadata(self, measure, supported_filters):
        if measure.startswith("K01A"):
            supported = ["province"]
        elif measure.startswith("K08"):
            supported = ["province", "business_form", "business_category", "region"]
        elif measure.startswith("K10B"):
            supported = ["region_resource_spending_only"]
        else:
            supported = ["region"]
        unavailable = ["year"]
        if measure.startswith("K08"):
            unavailable.extend(["dimension_intersection", "employment", "income"])
        elif measure.startswith("K01A"):
            unavailable.extend(["employment", "income", "category", "business_form"])
        else:
            unavailable.extend(["province", "business_form", "business_category"])
        return json_cell(
            {
                "supported_filters": supported,
                "unsupported_filters": unavailable,
                "unsupported_value": "unavailable",
                "allocation_policy": "do_not_allocate_overall_value",
            }
        )

    def contribution(
        self, measure, contributor_type, contributor_id, amount, unit, raw_locator, role
    ):
        self.tables["measure_contributions"].append(
            {
                "measure": measure,
                "contributor_type": contributor_type,
                "contributor_id": contributor_id,
                "amount": amount,
                "unit": unit,
                "raw_locator": raw_locator,
                "contribution_role": role,
            }
        )

    def add_review_coverage(self):
        for observation in self.tables["source_observations"]:
            self.tables["review_coverage"].append(
                {
                    "coverage_id": self.stable_id(
                        "coverage_response_key", observation["source_key"]
                    ),
                    "task": "response_key_family",
                    "source_reference": observation["source_key"],
                    "review_state": "reviewed_decided",
                    "disposition": observation["disposition"],
                    "evidence_locator": observation["raw_locator"],
                    "reason": "Aggregate key treatment is defined in the source profile.",
                    "affected_measures": "source_scope",
                }
            )
        for member in self.tables["count_members"]:
            self.tables["review_coverage"].append(
                {
                    "coverage_id": self.stable_id(
                        "coverage_count_member", member["count_member_id"]
                    ),
                    "task": "count_member",
                    "source_reference": member["count_member_id"],
                    "review_state": "reviewed_decided",
                    "disposition": "retained_nonadditive_aggregate_member",
                    "evidence_locator": member["raw_locator"],
                    "reason": "Header-excluded positive count member in a separately reconciled dimension.",
                    "affected_measures": "K01A,K08_companion",
                }
            )
        for impact in self.tables["regional_impacts"]:
            self.tables["review_coverage"].append(
                {
                    "coverage_id": self.stable_id(
                        "coverage_regional_impact", impact["regional_impact_id"]
                    ),
                    "task": "regional_impact_object",
                    "source_reference": impact["regional_impact_id"],
                    "review_state": "reviewed_decided",
                    "disposition": "retained_with_positional_region_mapping",
                    "evidence_locator": impact["raw_locator"],
                    "reason": impact["mapping_limit"],
                    "affected_measures": "K09,K10A,K10B",
                }
            )
        for metric in self.tables["impact_summary_metrics"]:
            self.tables["review_coverage"].append(
                {
                    "coverage_id": self.stable_id(
                        "coverage_summary_metric", metric["summary_metric_id"]
                    ),
                    "task": "impact_summary_metric",
                    "source_reference": metric["summary_metric_id"],
                    "review_state": "reviewed_decided",
                    "disposition": metric["treatment"],
                    "evidence_locator": metric["raw_locator"],
                    "reason": "Matches the six regional components for the same metric.",
                    "affected_measures": "K09,K10A,K10B",
                }
            )
        excluded = self.tables["excluded_amounts"][0]
        self.tables["review_coverage"].append(
            {
                "coverage_id": self.stable_id("coverage_excluded_amount"),
                "task": "excluded_resource_amount",
                "source_reference": excluded["excluded_amount_id"],
                "review_state": "reviewed_unresolved",
                "disposition": excluded["treatment"],
                "evidence_locator": excluded["raw_locator"],
                "reason": "Meaning and compatible period remain unresolved. ADR 0010 accepts the explicit K10B assumption.",
                "affected_measures": "K10B",
            }
        )

    def validate(self):
        for table, rows in self.tables.items():
            expected = set(TABLE_COLUMNS[table])
            for row in rows:
                if set(row) != expected:
                    _fail(f"{table} row columns differ from the legacy schema")
        totals = {
            dimension: sum(
                int(row["count"])
                for row in self.tables["count_members"]
                if row["dimension"] == dimension
            )
            for dimension in self.config["count_dimensions"]
        }
        if len(set(totals.values())) != 1:
            _fail(
                "independent count dimensions do not reconcile to one reported population"
            )
        summary_by_field = {
            row["raw_field"]: Decimal(row["amount"])
            for row in self.tables["impact_summary_metrics"]
        }
        for raw_field, (_, summary_field, _) in IMPACT_METRICS.items():
            component_total = sum(
                Decimal(row["amount"])
                for row in self.tables["impact_components"]
                if row["raw_field"] == raw_field
            )
            if component_total != summary_by_field.get(summary_field):
                _fail(
                    f"{raw_field} regional components do not reconcile to {summary_field}"
                )
        observations = {
            row["observation_id"] for row in self.tables["source_observations"]
        }
        headers = {row["header_id"] for row in self.tables["count_dimension_headers"]}
        regionals = {
            row["regional_impact_id"] for row in self.tables["regional_impacts"]
        }
        components = {row["component_id"] for row in self.tables["impact_components"]}
        summaries = {
            row["summary_metric_id"] for row in self.tables["impact_summary_metrics"]
        }
        if not all(
            row["observation_id"] in observations
            for table in (
                "count_dimension_headers",
                "count_members",
                "regional_impacts",
                "impact_components",
                "impact_summary_metrics",
                "excluded_amounts",
            )
            for row in self.tables[table]
        ):
            _fail("aggregate fact references an unknown response observation")
        if not all(row["header_id"] in headers for row in self.tables["count_members"]):
            _fail("count member references an unknown header")
        if not all(
            row["regional_impact_id"] in regionals
            for row in self.tables["impact_components"]
        ):
            _fail("impact component references an unknown regional object")
        if not all(
            row["component_id"] in components and row["summary_metric_id"] in summaries
            for row in self.tables["reconciliation_links"]
        ):
            _fail("reconciliation link references an unknown metric")
        reviewed_k10 = self.config.get("k10_versions", {})
        expected_k10 = {
            "K10A_reported_monthly_income_to_local_workers_and_suppliers_v1": [
                "localEmployeeExpense",
                "localResourceExpense",
            ],
            "K10B_assumed_historical_local_income_reconstruction_v1": [
                "localResourceExpense",
                "excludedResourceExpense.amount",
            ],
        }
        if any(
            reviewed_k10.get(name, {}).get("components") != fields
            for name, fields in expected_k10.items()
        ):
            _fail("reviewed K10 component definitions changed")
        if not all(
            row.get("raw_locator", row.get("evidence_locator", "")).startswith(
                "evidence://"
            )
            for table in (
                "source_observations",
                "count_dimension_headers",
                "count_members",
                "regional_impacts",
                "impact_components",
                "impact_summary_metrics",
                "excluded_amounts",
                "coverage_assertions",
                "measure_contributions",
                "review_coverage",
            )
            for row in self.tables[table]
        ):
            _fail("source-derived row lacks an evidence locator")

    def run(self):
        self.register_source_files()
        self.tables["source_files"] = self.files
        self.add_source_observations()
        self.add_count_dimensions()
        self.add_impact_facts()
        self.add_coverage_and_measures()
        self.add_review_coverage()
        discrepancy = next(
            (
                row
                for row in self.files
                if row["file"] == self.metadata("learning_dashboard_response")["file"]
            ),
            None,
        )
        if discrepancy is None:
            _fail("authoritative response source-file row missing")
        self.tables["integrity_reviews"].append(
            {
                "integrity_review_id": self.stable_id(
                    "integrity_review", discrepancy["file"]
                ),
                "file_id": discrepancy["file_id"],
                "actual_sha256": discrepancy["sha256"],
                "declared_sha256": discrepancy["manifest_sha256"],
                "status": discrepancy["integrity_status"],
                "treatment": "allowed_exact_documented_discrepancy_not_integrity_pass"
                if discrepancy["integrity_status"] == "known_declared_hash_discrepancy"
                else "declared_hash_matches",
                "reason": discrepancy["integrity_limitation"],
            }
        )
        self.validate()
        return self.tables


def build_tables(
    datasets: dict[str, Any],
    reviews: dict,
    geography: Any,
    input_metadata: dict[str, dict],
) -> dict[str, list[dict]]:
    return LearningDashboardPilot(datasets, reviews, geography, input_metadata).run()

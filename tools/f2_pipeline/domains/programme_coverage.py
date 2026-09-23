"""Source-supported programme geography and the distinct K01A province union."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

from ..common import PipelineError
from .raw_inputs import SOURCE_IDS, observation_uri, resolve_evidence


SOURCE_ALIASES = {
    "icommunity-v1": "icommunity",
    "atlocal-v1": "atlocal",
    "cultural-map-v1": "cultural_map",
    "pmua-apptech-v1": "pmua_apptech",
    "rinmp-v1": "rinmp",
    "learning-area-based-v1": "learning_area_based",
    "learning-dashboard-v1": "learning_dashboard",
}

TABLE_COLUMNS = {
    "coverage_assertions": [
        "coverage_assertion_id",
        "source",
        "source_table",
        "source_row_id",
        "observation_id",
        "province_code",
        "province_name",
        "location_role",
        "evidence_kind",
        "disposition",
        "reason",
        "raw_locator",
        "lineage_status",
        "source_details_json",
    ],
    "province_evidence_index": [
        "province_code",
        "province_name",
        "sources_json",
        "qualifying_assertion_count",
    ],
    "measure_results": ["measure", "value", "scope", "status"],
    "measure_contributions": [
        "measure",
        "entity_id",
        "source",
        "province_code",
        "contributor_ids_json",
        "reason",
    ],
}

TABLE_GRAINS = {
    "coverage_assertions": (
        "one qualifying, unresolved, or excluded source programme-location assertion"
    ),
    "province_evidence_index": (
        "one distinct Thai province with qualifying programme evidence"
    ),
    "measure_results": "one programme-coverage measure result",
    "measure_contributions": "one distinct Thai province contribution to K01A",
}


def _stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}_{hashlib.sha256(chr(31).join(parts).encode()).hexdigest()[:20]}"


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _truth(value: Any) -> bool:
    return value is True or value == "True"


class _Coverage:
    def __init__(self, source_tables, raw_inputs, geography):
        self.source_tables = source_tables
        self.raw_inputs = raw_inputs
        self.provinces = {
            str(row["provinceCode"]): row["provinceNameTh"]
            for row in geography.provinces
        }
        self.province_codes = {
            row["provinceNameTh"]: str(row["provinceCode"])
            for row in geography.provinces
        }
        self.observations: dict[str, dict[str, dict]] = {}
        self.rows: list[dict[str, Any]] = []

    def table(self, source: str, name: str) -> list[dict]:
        source_id = SOURCE_IDS[SOURCE_ALIASES[source]]
        tables = self.source_tables.get(source_id)
        if not isinstance(tables, dict) or name not in tables:
            raise PipelineError(
                f"Missing programme coverage source table: {source}/{name}"
            )
        return tables[name]

    def observation_index(self, source: str) -> dict[str, dict]:
        if source not in self.observations:
            rows = self.table(source, "source_observations")
            index = {row["observation_id"]: row for row in rows}
            if len(index) != len(rows) or "" in index:
                raise PipelineError(
                    f"Invalid programme coverage observations: {source}"
                )
            self.observations[source] = index
        return self.observations[source]

    def resolve_raw(self, source: str, observation_id: str, locator: str = "") -> str:
        source_id = SOURCE_IDS[SOURCE_ALIASES[source]]
        if observation_id:
            observation = self.observation_index(source).get(observation_id)
            if observation is None:
                raise PipelineError(
                    "Programme coverage evidence observation is absent: "
                    f"{source}/{observation_id}"
                )
            original = observation_uri(self.raw_inputs, source_id, observation)
            if locator.startswith("evidence://"):
                uri = locator
                if not uri.startswith(f"evidence://{source_id}/"):
                    raise PipelineError(
                        "Programme coverage evidence belongs to another source"
                    )
            elif locator:
                if "#" in locator:
                    raise PipelineError(
                        "Programme coverage locator still uses a raw path"
                    )
                base, _, original_pointer = original.partition("#")
                pointer = locator.lstrip("/")
                original_pointer = original_pointer.lstrip("/")
                if pointer != original_pointer and not pointer.startswith(
                    original_pointer.rstrip("/") + "/"
                ):
                    pointer = original_pointer.rstrip("/") + "/" + pointer
                uri = base + "#" + pointer
            else:
                uri = original
        else:
            uri = locator
            if not uri.startswith(f"evidence://{source_id}/"):
                raise PipelineError(
                    "Aggregate programme coverage requires canonical source evidence"
                )
        resolve_evidence(self.raw_inputs, uri)
        return uri

    def add(
        self,
        source: str,
        table: str,
        row: dict,
        key: str,
        role: str,
        qualifies: bool,
        reason: str,
        *,
        locator: str = "",
        province_code: str = "",
    ) -> None:
        code = str(province_code or row.get("province_code", ""))
        observation_id = str(row.get("observation_id", ""))
        raw_locator = self.resolve_raw(source, observation_id, locator)
        if code and code not in self.provinces:
            raise PipelineError(f"Unknown programme province: {source}/{key}/{code}")
        disposition = (
            "qualifying_resolved"
            if qualifies and code
            else "qualifying_unknown_province"
            if qualifies
            else "excluded_role_or_context"
        )
        self.rows.append(
            {
                "coverage_assertion_id": _stable_id("coverage", source, table, key),
                "source": source,
                "source_table": table,
                "source_row_id": key,
                "observation_id": observation_id,
                "province_code": code,
                "province_name": self.provinces.get(code, ""),
                "location_role": role,
                "evidence_kind": "aggregate_only"
                if source == "learning-dashboard-v1"
                else "record_derived",
                "disposition": disposition,
                "reason": reason,
                "raw_locator": raw_locator,
                "lineage_status": "resolved",
                "source_details_json": _json_text(row),
            }
        )

    def build(self) -> list[dict[str, Any]]:
        source = "icommunity-v1"
        community_roles = {
            (row["person_id"], row["observation_id"])
            for row in self.table(source, "person_roles")
            if row["role"] == "community_innovator"
        }
        for row in self.table(source, "locations"):
            role = row["location_role"]
            qualifies = role in {
                "declared_innovation_use",
                "cultural_product_area",
            } or (
                role == "source_person_location"
                and (row["entity_id"], row["observation_id"]) in community_roles
            )
            self.add(
                source,
                "locations",
                row,
                row["location_id"],
                role,
                qualifies,
                (
                    "Community person locations qualify only when the same "
                    "observation carries the community-innovator role."
                ),
            )
        for row in self.table(source, "activities"):
            self.add(
                source,
                "activities",
                row,
                row["activity_id"],
                "reported_activity_location",
                True,
                "Explicit activity venue or unknown/online activity geography.",
                province_code=self.province_codes.get(row["province"], ""),
            )

        source = "atlocal-v1"
        for row in self.table(source, "locations"):
            role = row["location_role"]
            self.add(
                source,
                "locations",
                row,
                row["location_id"],
                role,
                role in {"source_listing_location", "programme_cultural_area"},
                "Published listing or programme cultural-area evidence.",
            )
        for row in self.table(source, "activities"):
            self.add(
                source,
                "activities",
                row,
                row["activity_id"],
                "reported_activity_location",
                True,
                "Reported activity locality.",
                province_code=self.province_codes.get(row["province"], ""),
            )

        source = "cultural-map-v1"
        for row in self.table(source, "target_province_evidence"):
            self.add(
                source,
                "target_province_evidence",
                row,
                row["evidence_id"],
                row["location_role"],
                _truth(row["qualifies_target_province"]),
                row["basis"],
            )

        source = "pmua-apptech-v1"
        for row in self.table(source, "innovation_area_assertions"):
            self.add(
                source,
                "innovation_area_assertions",
                row,
                row["assertion_id"],
                "declared_innovation_use",
                True,
                (
                    "Declared detail area or source map area, independent of "
                    "researcher affiliation."
                ),
                locator=row["source_locator"],
            )

        source = "rinmp-v1"
        for row in self.table(source, "location_assertions"):
            self.add(
                source,
                "location_assertions",
                row,
                row["location_id"],
                row["location_role"],
                row["coverage_eligibility"]
                == "eligible_programme_target_or_use_coverage",
                row["coverage_eligibility"],
                locator=row["source_locator"],
            )

        source = "learning-area-based-v1"
        for row in self.table(source, "locations"):
            self.add(
                source,
                "locations",
                row,
                row["location_id"],
                row["location_role"],
                row["location_role"] == "programme_business_location",
                "Source-supported participating business location.",
            )

        source = "learning-dashboard-v1"
        for row in self.table(source, "coverage_assertions"):
            try:
                positive_count = Decimal(str(row["reported_business_count"])) > 0
            except (InvalidOperation, ValueError) as exc:
                raise PipelineError(
                    "Invalid dashboard programme coverage count"
                ) from exc
            qualifies = (
                row["coverage_role"] == "positive_source_reported_programme_coverage"
                and positive_count
            )
            self.add(
                source,
                "coverage_assertions",
                row,
                row["coverage_assertion_id"],
                row["coverage_role"],
                qualifies,
                (
                    "Aggregate coverage establishes only province coverage; "
                    "it does not identify businesses or allocate income."
                ),
                locator=row["raw_locator"],
            )

        return sorted(
            self.rows,
            key=lambda row: (row["source"], row["source_table"], row["source_row_id"]),
        )


def _source_provinces(rows: list[dict], source: str) -> set[str]:
    return {
        row["province_code"]
        for row in rows
        if row["source"] == source and row["disposition"] == "qualifying_resolved"
    }


def _contribution_provinces(rows: list[dict]) -> set[str]:
    provinces = set()
    for row in rows:
        measure = str(row.get("measure", ""))
        if not measure.startswith("K01") or measure.startswith("K01B"):
            continue
        code = str(row.get("province_code", ""))
        if not code:
            entity_id = str(row.get("entity_id", ""))
            code = entity_id.removeprefix("th-province:") if entity_id else ""
        if code:
            provinces.add(code)
    return provinces


def _validate_source_reconciliation(source_tables, coverage):
    checks = [
        (
            "cultural-map-v1",
            {
                str(row["province_code"])
                for row in source_tables[SOURCE_IDS["cultural_map"]]["target_provinces"]
            },
        ),
        (
            "pmua-apptech-v1",
            _contribution_provinces(
                source_tables[SOURCE_IDS["pmua_apptech"]]["measure_contributions"]
            ),
        ),
        (
            "rinmp-v1",
            _contribution_provinces(
                source_tables[SOURCE_IDS["rinmp"]]["measure_contributions"]
            ),
        ),
        (
            "learning-area-based-v1",
            _contribution_provinces(
                source_tables[SOURCE_IDS["learning_area_based"]][
                    "measure_contributions"
                ]
            ),
        ),
    ]
    mismatches = [
        source
        for source, expected in checks
        if _source_provinces(coverage, source) != expected
    ]
    if mismatches:
        raise PipelineError(
            f"Programme coverage source province reconciliation failed: {mismatches}"
        )


def _validate_innovation_relationships(coverage, innovation_tables):
    locations = innovation_tables.get("innovation_use_locations")
    if not isinstance(locations, list):
        raise PipelineError("Programme coverage requires innovation use locations")
    expected = {
        (row["source"], row["source_row_id"])
        for row in coverage
        if row["disposition"].startswith("qualifying_")
        and (
            (
                row["source"] == "icommunity-v1"
                and row["source_table"] == "locations"
                and row["location_role"] == "declared_innovation_use"
            )
            or row["source"] == "pmua-apptech-v1"
            or (
                row["source"] == "rinmp-v1"
                and row["source_table"] == "location_assertions"
            )
        )
    }
    actual = set()
    for row in locations:
        source = str(row.get("source", ""))
        eligibility = str(row.get("coverage_eligibility", ""))
        if (
            source == "icommunity"
            and row.get("location_role") == "declared_innovation_use"
        ):
            actual.add(("icommunity-v1", str(row["location_id"])))
        elif source == "pmua_apptech":
            actual.add(
                (
                    "pmua-apptech-v1",
                    str(row["location_id"]).rsplit(":", 1)[0],
                )
            )
        elif (
            source == "rinmp"
            and eligibility == "eligible_programme_target_or_use_coverage"
        ):
            actual.add(("rinmp-v1", str(row["location_id"])))
    if actual != expected:
        raise PipelineError(
            "Programme coverage disagrees with innovation location relationships"
        )


def build_tables(source_tables, reviews, raw_inputs, geography, innovation_tables):
    """Build the audited K01A evidence union without reading runtime files."""
    runtime = reviews.get("cross_source_activities_coverage/runtime.json")
    reviewed = reviews.get("cross_source_activities_coverage/reviewed_evidence.json")
    if not isinstance(runtime, dict) or runtime.get("schema_version") != 1:
        raise PipelineError("Unsupported programme coverage runtime review")
    if not isinstance(reviewed, dict) or reviewed.get("schema_version") != 1:
        raise PipelineError("Unsupported programme coverage evidence review")
    missing_sources = set(SOURCE_IDS.values()) - set(source_tables)
    if missing_sources:
        raise PipelineError(
            f"Programme coverage is missing source tables: {sorted(missing_sources)}"
        )
    # AppTech MRU exposes institution context but no accepted programme-use
    # location assertion. Its presence is accounted for without borrowing
    # institution geography into K01A.

    coverage = _Coverage(source_tables, raw_inputs, geography).build()
    if len({row["coverage_assertion_id"] for row in coverage}) != len(coverage):
        raise PipelineError("Duplicate programme coverage assertion ID")
    if any(set(row) != set(TABLE_COLUMNS["coverage_assertions"]) for row in coverage):
        raise PipelineError("Programme coverage assertion schema changed")

    _validate_source_reconciliation(source_tables, coverage)
    _validate_innovation_relationships(coverage, innovation_tables)

    by_source: dict[str, set[str]] = defaultdict(set)
    for row in coverage:
        if row["disposition"] == "qualifying_resolved":
            by_source[row["source"]].add(row["province_code"])
    province_codes = sorted(set().union(*by_source.values())) if by_source else []
    province_index = [
        {
            "province_code": code,
            "province_name": next(
                row["province_name"]
                for row in coverage
                if row["province_code"] == code
                and row["disposition"] == "qualifying_resolved"
            ),
            "sources_json": _json_text(
                sorted(source for source, codes in by_source.items() if code in codes)
            ),
            "qualifying_assertion_count": sum(
                row["province_code"] == code
                and row["disposition"] == "qualifying_resolved"
                for row in coverage
            ),
        }
        for code in province_codes
    ]
    contributions = [
        {
            "measure": "K01A_supported_target_provinces",
            "entity_id": f"th-province:{code}",
            "source": "multiple",
            "province_code": code,
            "contributor_ids_json": _json_text(
                [
                    row["coverage_assertion_id"]
                    for row in coverage
                    if row["province_code"] == code
                    and row["disposition"] == "qualifying_resolved"
                ]
            ),
            "reason": "Distinct qualifying source-supported province evidence.",
        }
        for code in province_codes
    ]
    return {
        "coverage_assertions": coverage,
        "province_evidence_index": province_index,
        "measure_results": [
            {
                "measure": "K01A_supported_target_provinces",
                "value": len(province_codes),
                "scope": "K01A demonstration; distinct qualifying Thai province codes",
                "status": "demonstration_not_final_release",
            }
        ],
        "measure_contributions": contributions,
    }

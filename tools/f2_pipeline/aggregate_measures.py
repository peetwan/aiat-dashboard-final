"""Assemble and validate aggregate and methodology measures."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .common import PipelineError
from .relationship_validation import TABLE_PRIMARY_KEYS
from .measure_query import MeasureQuery

AGGREGATE_MEASURES = frozenset(
    {"K02", "K09", "K10", "C10_ALTERNATIVE", "C08_REPORTED_BUSINESSES"}
)
NULL_MEASURES = frozenset({"K06", "K08", "K11A", "K11B"})
AGGREGATE_AND_RELATED_MEASURES = (
    AGGREGATE_MEASURES | NULL_MEASURES | {"C08_PARTICIPATING"}
)
ROOT_ADDITIONS = (
    "aggregate_breakdowns",
    "entity_contributions",
    "province_memberships",
    "eligibility_evidence",
    "evidence_links",
)
_ROOT_KEYS = {name: key for name, key in TABLE_PRIMARY_KEYS.items() if "/" not in name}
_ROOT_KEYS["aggregate_breakdowns"] = ("measure_id", "breakdown_id", "member_id")
AGGREGATE_TABLE_PRIMARY_KEYS = {
    **_ROOT_KEYS,
    **{f"domains/aggregates/{name}": _ROOT_KEYS[name] for name in ROOT_ADDITIONS},
    "measure_methodology": "measure_id",
    "measure_relationships": ("headline_measure_id", "related_measure_id"),
    "domains/aggregates/aggregate_results": "measure_id",
    "sources/f2_learning_area_based/businesses": "business_id",
}


def assemble_aggregate_measures(root, aggregate_tables, definitions):
    result = {name: list(rows) for name, rows in root.items()}
    for name in ROOT_ADDITIONS:
        if name not in aggregate_tables:
            raise PipelineError(f"Missing aggregate output: {name}")
        if any(
            row.get("measure_id") in AGGREGATE_AND_RELATED_MEASURES
            for row in result.get(name, [])
        ):
            raise PipelineError("Aggregate measures have already been assembled")
        result.setdefault(name, []).extend(dict(row) for row in aggregate_tables[name])
    by_id = {row["measure_id"]: row for row in definitions}
    if not AGGREGATE_AND_RELATED_MEASURES <= by_id.keys():
        raise PipelineError("Missing aggregate measure definitions")
    result["measure_methodology"] = [
        {
            "measure_id": measure,
            "status": by_id[measure]["status"],
            "reason": by_id[measure]["limitations"],
        }
        for measure in sorted(NULL_MEASURES)
    ]
    result["measure_relationships"] = [
        {
            "headline_measure_id": row["parent_measure_id"],
            "related_measure_id": row["measure_id"],
            "relationship": "overlapping_alternative"
            if row["measure_id"] == "C10_ALTERNATIVE"
            else "separate_related_population",
            "additive_to_headline": False,
            "reconciles_with_headline": False,
            "explanation": row["limitations"],
        }
        for row in definitions
        if row.get("parent_measure_id") in {"K02", "K08", "K10"}
    ]
    return result


def validate_aggregate_tables(
    root, source_tables, aggregate_tables, definitions, provinces
):
    checks = {}
    occurrences = {}

    def check(name, passed, actual: int | str | None = None):
        if not passed:
            raise PipelineError(f"Aggregate validation failed: {name}")
        if actual is None:
            occurrences[name] = occurrences.get(name, 0) + 1
            actual = occurrences[name]
        checks[name] = {"check": name, "status": "passed", "actual": actual}

    by_id = {row["measure_id"]: row for row in definitions}
    expected_definition_count = 22 if "C02_BROADER" in by_id else 21
    check(
        "complete implemented definition set",
        len(definitions) == len(by_id) == expected_definition_count,
    )
    check(
        "all aggregate definitions",
        AGGREGATE_AND_RELATED_MEASURES <= by_id.keys(),
    )
    all_tables = {
        **root,
        **{
            f"sources/{source}/{name}": rows
            for source, tables in source_tables.items()
            for name, rows in tables.items()
        },
        **{
            f"domains/aggregates/{name}": rows
            for name, rows in aggregate_tables.items()
        },
    }
    for name, columns in AGGREGATE_TABLE_PRIMARY_KEYS.items():
        check(name + " present", name in all_tables)
        columns = (columns,) if isinstance(columns, str) else columns
        keys = [
            tuple(row.get(column, "") for column in columns) for row in all_tables[name]
        ]
        check(
            name + " unique complete keys",
            all(all(key) for key in keys) and len(keys) == len(set(keys)),
            len(keys),
        )

    expected = {
        row["measure_id"]: row["value_exact"]
        for row in aggregate_tables["aggregate_results"]
    }
    check(
        "six independently reconciled non-null results",
        set(expected) == AGGREGATE_MEASURES | {"C08_PARTICIPATING"},
    )
    for measure in sorted(AGGREGATE_AND_RELATED_MEASURES):
        selection = MeasureQuery(by_id[measure], root, provinces).select()
        result = selection["result"]
        if measure in NULL_MEASURES:
            check(
                measure + " explicit null and explanation",
                result["value"] is None and bool(result["unavailable_reason"]),
            )
        else:
            try:
                exact = Decimal(result.get("value_exact", str(result["value"])))
                target = Decimal(str(expected[measure]))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise PipelineError("Invalid aggregate exact result") from exc
            check(
                measure + " query reconciles with source stage",
                exact.is_finite() and target.is_finite() and exact == target,
                str(exact),
            )
        if measure != "C08_PARTICIPATING":
            check(
                measure + " has no fabricated entity roster",
                not selection["entity_ids"],
            )

    contribution_keys = {
        (row["measure_id"], row["entity_id"]) for row in root["entity_contributions"]
    }
    check(
        "aggregate and null measures have no entity contributions",
        not any(
            measure in AGGREGATE_MEASURES | NULL_MEASURES
            for measure, _ in contribution_keys
        ),
    )
    expected_participating = {
        (row["measure_id"], row["entity_id"])
        for row in aggregate_tables["entity_contributions"]
    }
    actual_participating = {
        key for key in contribution_keys if key[0] == "C08_PARTICIPATING"
    }
    check(
        "participating business identities retained",
        expected_participating == actual_participating,
        len(actual_participating),
    )
    province_codes = {row["province_code"] for row in provinces}
    evidence_indexes = {}
    referenced = 0
    for name in ROOT_ADDITIONS:
        for row in root[name]:
            if row.get("measure_id") not in AGGREGATE_AND_RELATED_MEASURES:
                continue
            if name in {
                "province_memberships",
                "eligibility_evidence",
                "evidence_links",
            }:
                check(
                    name + " counted subject",
                    (row["measure_id"], row["entity_id"]) in contribution_keys,
                )
            if name == "province_memberships":
                check(
                    "participation official province",
                    row["province_code"] in province_codes,
                )
            if name == "entity_contributions":
                continue
            table, key, value = (
                (row["table"], row["key"], row["record_id"])
                if name == "evidence_links"
                else (row["evidence_table"], row["evidence_key"], row["evidence_id"])
            )
            check("aggregate/participation evidence table exists", table in all_tables)
            if (table, key) not in evidence_indexes:
                check(
                    "aggregate/participation evidence key exists",
                    all(key in target for target in all_tables[table]),
                )
                evidence_indexes[table, key] = {
                    target[key] for target in all_tables[table]
                }
            check(
                "aggregate/participation evidence resolves",
                bool(value) and value in evidence_indexes[table, key],
            )
            referenced += 1
    check("aggregate evidence references checked", referenced > 0, referenced)
    relationships = {
        (row["headline_measure_id"], row["related_measure_id"])
        for row in root["measure_relationships"]
    }
    expected_relationships = {
        ("K02", "C02_COMMUNITY"),
        ("K08", "C08_PARTICIPATING"),
        ("K08", "C08_REPORTED_BUSINESSES"),
        ("K08", "C08_ASSESSED_PEOPLE"),
        ("K08", "C08_INCREASED_PEOPLE"),
        ("K10", "C10_ALTERNATIVE"),
    }
    if "C02_BROADER" in by_id:
        expected_relationships.add(("K02", "C02_BROADER"))
    check(
        "separate companion populations declared",
        relationships == expected_relationships,
    )
    check(
        "companions never add to headlines",
        all(
            row["additive_to_headline"] is False
            and row["reconciles_with_headline"] is False
            for row in root["measure_relationships"]
        ),
    )
    return list(checks.values())

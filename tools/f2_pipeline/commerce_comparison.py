"""Compare commerce and programme-coverage content with frozen v2."""

from __future__ import annotations

from collections import Counter

from .common import PipelineError
from .domains.resolution import logical_source
from .comparison_core import (
    ENTITY_MEASURES,
    _baseline_reader,
    _compare_identity,
    _compare_measure_tables,
    _effective_dispositions,
    _groups,
    _set_delta,
)

COMMERCE_MEASURES = (*ENTITY_MEASURES, "K01A", "K05", "K07")


def _keys(rows, columns):
    return {tuple(str(row.get(column, "")) for column in columns) for row in rows}


def _coverage_citation_key(row):
    """Compare source-relative evidence, not regenerated observation/area IDs."""
    base, separator, pointer = row.get("raw_locator", "").partition("#")
    if not separator:
        raise PipelineError("Coverage comparison requires a source citation")
    if base.startswith("evidence://"):
        parts = base.removeprefix("evidence://").split("/", 2)
        if len(parts) != 3:
            raise PipelineError("Malformed current coverage citation")
        source, _, relative = parts
    else:
        base = base.removeprefix("raw/")
        if not base.startswith("data/"):
            raise PipelineError("Unrecognized frozen coverage citation")
        parts = base.removeprefix("data/").split("/")
        source = parts[0]
        relative = "/".join(parts[2:] if source.startswith("f2_") else parts[1:])
    if (
        not relative
        or any(part in {"", ".", ".."} for part in relative.split("/"))
        or logical_source(source) != logical_source(row["source"].removesuffix("-v1"))
    ):
        raise PipelineError(
            "Coverage citation source identity differs from its assertion"
        )
    return (
        row["source"],
        row["source_table"],
        relative.removesuffix(".gz"),
        pointer.lstrip("/"),
        row["province_code"],
        row["location_role"],
        row["disposition"],
    )


def _coverage_citation_comparison(old, new):
    old_counts = Counter(_coverage_citation_key(row) for row in old)
    new_counts = Counter(_coverage_citation_key(row) for row in new)
    added, removed = new_counts - old_counts, old_counts - new_counts
    return {
        "reference_rows": len(old),
        "current_rows": len(new),
        "reference_distinct": len(old_counts),
        "current_distinct": len(new_counts),
        "added": sum(added.values()),
        "removed": sum(removed.values()),
        "added_keys": [(*key, count) for key, count in sorted(added.items())],
        "removed_keys": [(*key, count) for key, count in sorted(removed.items())],
    }


def _commerce_identity(baseline, current, kind):
    table, group, member = f"{kind}_crosswalk", f"global_{kind}_id", f"source_{kind}_id"
    old = baseline(f"support/derived/cross-source/offerings-v2/{table}.csv")
    new = current[f"domains/commerce/{table}"]
    old_groups = _groups(old, group, lambda row: row[member])
    new_groups = _groups(new, group, lambda row: row[member])
    return {
        "grouping": _set_delta(set(old_groups), set(new_groups)),
        "member_keys": _set_delta(_keys(old, (member,)), _keys(new, (member,))),
        "source_to_global": _set_delta(
            _keys(old, (member, group)), _keys(new, (member, group))
        ),
    }




def compare_commerce_content(manifest, reference_manifest, baseline, tables, results):
    """Compare commerce and programme coverage inside a complete release."""
    required = {
        "domains/commerce/" + name
        for name in (
            "global_operators",
            "global_offerings",
            "operator_crosswalk",
            "offering_crosswalk",
            "offering_families",
            "offering_family_members",
            "reviewed_identity_decisions",
            "review_coverage",
            "reviewed_evidence",
            "identity_decisions",
            "listing_evidence",
            "seller_evidence",
            "locations",
            "operator_offering_edges",
            "reviewed_relationships",
        )
    } | {"domains/programme_coverage/coverage_assertions"}
    if not required <= tables.keys():
        raise PipelineError("Commerce comparison is missing implemented domain tables")

    def compare_commerce(table, columns):
        old = baseline(f"support/derived/cross-source/offerings-v2/{table}.csv")
        new = tables[f"domains/commerce/{table}"]
        return _set_delta(_keys(old, columns), _keys(new, columns))

    old_coverage = baseline(
        "support/derived/cross-source/activities-coverage-v1/coverage_assertions.csv"
    )
    new_coverage = tables["domains/programme_coverage/coverage_assertions"]
    coverage_fields = (
        "source",
        "source_table",
        "source_row_id",
        "province_code",
        "location_role",
        "disposition",
    )
    old_reviewed_evidence = baseline(
        "support/derived/cross-source/offerings-v2/reviewed_evidence.csv"
    )
    context_columns = ("candidate_id", "source", "global_innovation_id")
    return {
        "reference_release": reference_manifest["release_id"],
        "release_id": manifest["release_id"],
        "profile_measures": list(COMMERCE_MEASURES),
        "measures": _compare_measure_tables(
            baseline, tables, results, COMMERCE_MEASURES
        ),
        "identities": {
            "innovations": _compare_identity(baseline, tables, "innovations"),
            "people": _compare_identity(baseline, tables, "people"),
            "operators": _commerce_identity(baseline, tables, "operator"),
            "offerings": _commerce_identity(baseline, tables, "offering"),
        },
        "commerce": {
            "reviewed_candidate_innovation_contexts": _set_delta(
                _keys(
                    [
                        row
                        for row in old_reviewed_evidence
                        if row.get("global_innovation_id")
                    ],
                    context_columns,
                ),
                _keys(
                    [
                        row
                        for row in tables["domains/commerce/reviewed_evidence"]
                        if row.get("global_innovation_id")
                    ],
                    context_columns,
                ),
            ),
            "offering_identities": compare_commerce(
                "global_offerings", ("global_offering_id",)
            ),
            "family_definitions": compare_commerce(
                "offering_families",
                ("family_id", "member_count", "identity_status", "counting_basis"),
            ),
            "family_memberships": compare_commerce(
                "offering_family_members",
                ("family_id", "global_offering_id", "membership_role"),
            ),
            "review_coverage": compare_commerce(
                "review_coverage",
                (
                    "candidate_id",
                    "source",
                    "entity_kind",
                    "status",
                    "basis",
                    "global_entity_id",
                    "output_type",
                    "unit_basis",
                ),
            ),
            "operator_offering_relationships": compare_commerce(
                "operator_offering_edges",
                (
                    "source_operator_offering_edge_id",
                    "source_operator_id",
                    "global_operator_id",
                    "source_offering_id",
                    "global_offering_id",
                    "relationship",
                ),
            ),
            "reviewed_relationships": compare_commerce(
                "reviewed_relationships",
                (
                    "relationship_id",
                    "subject_global_id",
                    "object_global_id",
                    "relationship",
                ),
            ),
            "listing_evidence": compare_commerce(
                "listing_evidence",
                (
                    "source_listing_id",
                    "global_offering_id",
                    "global_operator_id",
                    "listing_eligibility",
                ),
            ),
            "seller_evidence": compare_commerce(
                "seller_evidence",
                (
                    "source_seller_evidence_id",
                    "global_operator_id",
                    "global_offering_id",
                    "role",
                ),
            ),
            "location_subjects_and_relationship_context": compare_commerce(
                "locations",
                (
                    "source_location_id",
                    "source_entity_id",
                    "source_operator_id",
                    "global_operator_id",
                    "source_offering_id",
                    "global_offering_id",
                    "province_code",
                    "location_role",
                ),
            ),
            "baseline_review_dispositions": _effective_dispositions(
                tables["domains/commerce/identity_decisions"]
            ),
            "additional_review_dispositions": _effective_dispositions(
                tables["domains/commerce/reviewed_identity_decisions"]
            ),
            "current_extra_detail_tables_not_packaged_by_v2": {
                name: len(tables.get("domains/commerce/" + name, []))
                for name in ("person_operator_links", "candidate_pairs", "source_files")
            },
        },
        "programme_coverage": {
            "source_citation_assertions": _coverage_citation_comparison(
                old_coverage, new_coverage
            ),
            "identity_comparison_note": "Assertion-ID deltas remain explicit; the separate source-relative citation comparison checks province, role, disposition and occurrence counts without requiring old producer ID encodings.",
            "assertion_memberships": _set_delta(
                _keys(old_coverage, coverage_fields),
                _keys(new_coverage, coverage_fields),
            ),
            "reference_dispositions": dict(
                sorted(Counter(row["disposition"] for row in old_coverage).items())
            ),
            "current_dispositions": dict(
                sorted(Counter(row["disposition"] for row in new_coverage).items())
            ),
            "source_province_memberships": _set_delta(
                _keys(
                    [
                        row
                        for row in old_coverage
                        if row["disposition"] == "qualifying_resolved"
                    ],
                    ("source", "province_code"),
                ),
                _keys(
                    [
                        row
                        for row in new_coverage
                        if row["disposition"] == "qualifying_resolved"
                    ],
                    ("source", "province_code"),
                ),
            ),
        },
        "intentional_contract_changes": [
            "K05 geography requires operator-owned evidence; an operator relationship decorating a product location does not lend that product's province to the operator.",
            "Normal builds consume freshly injected source and domain tables plus locked raw/review inputs, never frozen outputs or the external reference workspace.",
            "All original offerings and reviewed variant/range memberships remain available behind K07 product-family counts.",
            "Citation origins are distinguished from legacy reviewed candidate context; reused raw IDs cannot overwrite dataset-specific innovation relationships.",
        ],
        "interpretation": "Commerce and programme-coverage migration evidence inside the complete F2 comparison.",
    }

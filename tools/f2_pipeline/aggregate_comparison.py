"""Compare aggregate facts and source citations with frozen v2."""

from collections import Counter
from decimal import Decimal

from .commerce_comparison import _coverage_citation_key

_SOURCE_PATHS = {
    "support/derived/pilots/pmua-apptech-v1/": "sources/f2_target_household/",
    "support/derived/pilots/learning-dashboard-v1/": "sources/f2_learning_dashboard/",
    "support/derived/pilots/learning-area-based-v1/": "sources/f2_learning_area_based/",
}
_SOURCE_ALIASES = {
    "f2_target_household": "pmua_apptech",
    "f2_learning_dashboard": "learning_dashboard",
    "f2_learning_area_based": "learning_area_based",
}


def aggregate_key(row, *, citation=False):
    table = row["evidence_table"].removesuffix(".csv")
    for old, new in _SOURCE_PATHS.items():
        if table.startswith(old):
            table = new + table.removeprefix(old)
            break
    fields = (
        "measure_id",
        "breakdown_id",
        "member_id",
        "amount_unit",
        "province_code",
        "source_level",
        "member_label",
        "region",
        "component",
        "evidence_key",
        "evidence_id",
    )
    if citation:
        # Keep generated member-key changes explicit in the separate comparison.
        # This view identifies facts by their source row and exact leaf citation.
        fields = tuple(field for field in fields if field != "member_id")
    key = tuple(str(row.get(field, "")) for field in fields) + (
        str(Decimal(row["amount"]).normalize()),
        str(Decimal(row["result_divisor"]).normalize()),
        table,
    )
    if citation:
        source = table.split("/")[1]
        normalized = _coverage_citation_key(
            {
                "source": _SOURCE_ALIASES[source],
                "source_table": table,
                "raw_locator": row["raw_locator"],
                "province_code": "",
                "location_role": "",
                "disposition": "",
            }
        )
        key += normalized[2:4]
    return key


def compare_aggregate_rows(old, new, *, citation=False):
    before = Counter(aggregate_key(row, citation=citation) for row in old)
    after = Counter(aggregate_key(row, citation=citation) for row in new)
    removed, added = before - after, after - before
    return {
        "reference_rows": sum(before.values()),
        "current_rows": sum(after.values()),
        "removed": sum(removed.values()),
        "added": sum(added.values()),
        "removed_rows": [
            {"key": list(key), "occurrences": count}
            for key, count in sorted(removed.items())
        ],
        "added_rows": [
            {"key": list(key), "occurrences": count}
            for key, count in sorted(added.items())
        ],
    }



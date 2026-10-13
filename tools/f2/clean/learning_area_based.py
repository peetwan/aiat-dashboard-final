"""Learning area-based programme directory (f2_learning_area_based): area_based_rows.jsonl.

Each row is one business taking part in one project in one fiscal year. The same business can appear
in several rows (years, projects); joining those is the Resolve stage's job.
"""

from __future__ import annotations

from ..text import clean_or_none, norm

ROWS = "area_based_rows.jsonl"


def clean(raw, geo) -> dict[str, list[dict]]:
    operators = []
    for index, row in enumerate(raw.jsonl(ROWS)):
        operators.append({
            "record_id": row["id"],
            "kind": "declared",
            "name": norm(row.get("businessName")),
            "name_quality": "named",
            **geo.place(row.get("province"), row.get("district"), row.get("subDistrict")),
            "address_raw": " / ".join(filter(None, (norm(row.get(k)) for k in ("subDistrict", "district", "province")))),
            "raw_ref": f"{ROWS}#{index}",
            "details": {"fiscal_year_be": row.get("fiscalYear"), "project": clean_or_none(row.get("projectName")),
                        "research_unit": clean_or_none(row.get("researchUnit")), "region": row.get("region"),
                        "sequence": row.get("sequence")},
        })
    return {"operators": operators}

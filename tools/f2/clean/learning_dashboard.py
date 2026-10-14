"""Learning dashboard (f2_learning_dashboard): three files of totals, each a list in data[].

- dashboard_counts.json: business counts per dimension ("Popularity"): provinces / entityTypes / categories /
  geography, one row per table row with its row_index in the source table.
- dashboard_impact.json: six regional impact records. The API sends them without a region name; the scraper
  names them by the page's region order and checks that order (region, region_index).
- dashboard_totals.json: impactSummary (national totals) and excludedResourceExpense (an amount reported
  for one region).
"""

from __future__ import annotations

from ..text import norm

COUNTS, IMPACT, TOTALS = "dashboard_counts.json", "dashboard_impact.json", "dashboard_totals.json"
DIMENSIONS = {"provinces": "province", "entityTypes": "entity_type", "categories": "category", "geography": "region"}
# The scraper writes fields in alphabetical order; these are the dashboard API's own orders, which Measure
# keeps for the parts of a total.
IMPACT_FIELDS = ("localResourceConsumption", "localResourceExpense", "localEmployeeAmount", "localEmployeeExpense")
SUMMARY_FIELDS = ("totalEmplyeeAmount", "totalEmployeeExpense", "totalResourceConsumption", "totalResourceExpense")
RECORD_FIELDS = {"record_type", "source_key", "source_payload_hash"}


def clean(raw, geo) -> dict[str, list[dict]]:
    rows, counts = [], raw.json(COUNTS)["data"]
    unknown = {r["dimension"] for r in counts} - set(DIMENSIONS)
    if unknown:
        raise ValueError(f"learning dashboard: unknown count tables {sorted(unknown)}")
    for field, dimension in DIMENSIONS.items():
        table = sorted(((i, r) for i, r in enumerate(counts) if r["dimension"] == field), key=lambda x: x[1]["row_index"])
        for index, row in table:
            label = norm(row["label"])
            rows.append({"dataset": "learning_dashboard", "metric": f"businesses_by_{dimension}", "dimension": dimension,
                         "dimension_value": label, "value": row["count"], "raw_ref": f"{COUNTS}#data/{index}/count",
                         "province_code": geo.place(label)["province_code"] if dimension == "province" else None})
    impact = sorted(enumerate(raw.json(IMPACT)["data"]), key=lambda x: x[1]["region_index"])
    regions = {norm(r["label"]) for r in counts if r["dimension"] == "geography"}
    if {norm(r["region"]) for _, r in impact} != regions or len(impact) != len(regions):
        raise ValueError("learning dashboard: the impact regions no longer match the geography table")
    for index, record in impact:
        _known(record, {*IMPACT_FIELDS, "region", "region_index"})
        for metric in IMPACT_FIELDS:
            rows.append({"dataset": "learning_dashboard", "metric": metric, "dimension": "region",
                         "dimension_value": norm(record["region"]), "value": record[metric],
                         "raw_ref": f"{IMPACT}#data/{index}/{metric}"})
    totals = {r["record_type"]: (i, r) for i, r in enumerate(raw.json(TOTALS)["data"])}
    if set(totals) != {"dashboard_impact_summary", "dashboard_excluded_resource_expense"}:
        raise ValueError(f"learning dashboard: unexpected totals {sorted(totals)}")
    index, summary = totals["dashboard_impact_summary"]
    _known(summary, set(SUMMARY_FIELDS))
    for metric in SUMMARY_FIELDS:
        rows.append({"dataset": "learning_dashboard", "metric": metric, "value": summary[metric],
                     "raw_ref": f"{TOTALS}#data/{index}/{metric}"})
    index, excluded = totals["dashboard_excluded_resource_expense"]
    _known(excluded, {"region", "amount"})
    rows.append({"dataset": "learning_dashboard", "metric": "excludedResourceExpense", "dimension": "region",
                 "dimension_value": norm(excluded["region"]), "value": excluded["amount"],
                 "raw_ref": f"{TOTALS}#data/{index}/amount"})
    return {"reported_figures": rows}


def _known(record: dict, fields: set[str]) -> None:
    """A field this cleaner does not know would silently drop out of the measures, so it stops the run."""
    if set(record) - RECORD_FIELDS != fields:
        raise ValueError(f"learning dashboard: {record['source_key']} has fields {sorted(set(record) - RECORD_FIELDS)}, "
                         f"expected {sorted(fields)}")

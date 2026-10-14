"""Learning dashboard (f2_learning_dashboard): learning_dashboard.json, one response of totals.

- provinces / entityTypes / categories / geography: business counts per dimension ("Popularity").
- geographyImpact: six regional impact objects with NO region name; they follow the order of the
  geography list (as the old pipeline did). Re-check this order whenever a new capture arrives.
- impactSummary: national totals; excludedResourceExpense: an amount reported for one region.
"""

from __future__ import annotations

from ..text import norm

FILE = "learning_dashboard.json"
# Raw files this cleaner does not read, and why (the clean stage warns about any other unread file).
SKIPPED = {"dashboard_keys.jsonl": "the names of the dashboard's fields"}
DIMENSIONS = {"provinces": "province", "entityTypes": "entity_type", "categories": "category", "geography": "region"}


def clean(raw, geo) -> dict[str, list[dict]]:
    data, rows = raw.json(FILE), []
    for field, dimension in DIMENSIONS.items():
        header, *values = data[field]
        for index, (label, count) in enumerate(values, 1):
            rows.append({"dataset": "learning_dashboard", "metric": f"businesses_by_{dimension}", "dimension": dimension,
                         "dimension_value": norm(label), "value": count, "raw_ref": f"{FILE}#{field}/{index}/1",
                         "province_code": geo.place(label)["province_code"] if dimension == "province" else None})
    regions = [norm(label) for label, _ in data["geography"][1:]]
    if len(regions) != len(data["geographyImpact"]):
        raise ValueError("learning dashboard: geographyImpact no longer lines up with the geography list")
    for index, (region, impact) in enumerate(zip(regions, data["geographyImpact"])):
        for metric, value in impact.items():
            rows.append({"dataset": "learning_dashboard", "metric": metric, "dimension": "region",
                         "dimension_value": region, "value": value, "raw_ref": f"{FILE}#geographyImpact/{index}/{metric}"})
    for metric, value in data["impactSummary"].items():
        rows.append({"dataset": "learning_dashboard", "metric": metric, "value": value,
                     "raw_ref": f"{FILE}#impactSummary/{metric}"})
    excluded = data["excludedResourceExpense"]
    rows.append({"dataset": "learning_dashboard", "metric": "excludedResourceExpense", "dimension": "region",
                 "dimension_value": norm(excluded["region"]), "value": excluded["amount"],
                 "raw_ref": f"{FILE}#excludedResourceExpense/amount"})
    return {"reported_figures": rows}

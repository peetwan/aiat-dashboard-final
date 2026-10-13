"""Things reviewers found in record text (data/runtime/f2/decisions/extractions.json): businesses
(operators), offerings, people (or a role given to a listed person) and activities.

They become rows with kind = 'extracted'. Freshness check against the current raw snapshot: each
supporting quote must still be in its record, and an activity's publication must still exist; if not,
the source changed and the finding needs a new look (details.quotes_missing / publication_missing).
Rejected findings (not_established) stay in the file so they are not asked again, but are not rows.
"""

from __future__ import annotations

import re

from .. import decisions as reviewed
from ..text import norm, person, strip_html


def load() -> dict:
    return reviewed.load("extractions.json", {"extractions": [], "links": []})


def rows(source: str, raw, decisions: dict, tables: dict[str, list[dict]]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {"operators": [], "offerings": [], "people": [], "activities": []}
    publications = {p["record_id"]: p for p in tables.get("publications", [])}
    for e in decisions["extractions"]:
        if e["source"] != source or e["status"] == "not_established":
            continue
        quotes = [q for r in e["records"] for q in r["quotes"]]
        checked = {"quotes": len(quotes), "quotes_missing": sum(1 for q in quotes if q.get("text") and not _quoted(raw, q))}
        base = {"record_id": e["record_id"], "kind": "extracted", "review_status": e["status"]}
        if e["kind"] == "activity":
            publication = publications.get(e["publication_record_id"])
            out["activities"].append({
                **base, "name": e["name"], "publication_record_id": e["publication_record_id"],
                "start_date": e["start_date"], "end_date": e["end_date"], "venues": e["venues"],
                "raw_ref": publication["raw_ref"] if publication else f"missing publication {e['publication_record_id']}",
                "details": {"basis": e["basis"], "date_evidence": e["date_evidence"],
                            "publication_missing": publication is None}})
            continue
        row = {**base, "raw_ref": quotes[0]["ref"],
               "details": {"aliases": e["aliases"], "basis": e["basis"], "output_type": e.get("output_type"),
                           "source_records": [r["record_id"] for r in e["records"]],
                           "innovation_upstream_ids": e["innovation_upstream_ids"], **checked}}
        if e["kind"] == "operator":
            out["operators"].append({**row, "name": e["name"], "name_quality": "named"})
        elif e["kind"] == "offering":
            out["offerings"].append({**row, "name": e["name"]})
        else:
            row["details"]["also_roles"] = e.get("also_roles", [])
            out["people"].append({**row, **(person(e["name"]) or {"name": e["name"]}), "role": e["role"],
                                  "institution": e["institution"], "person_ref": e["person_ref"],
                                  "about_kind": "person" if e["person_ref"] else None,
                                  "about_record_id": e["person_ref"]})
    return out


def links(source: str, decisions: dict) -> list[dict]:
    return [link for link in decisions["links"] if link["source"] == source]


def _quoted(raw, quote: dict) -> bool:
    try:
        value = raw.at(quote["ref"])
    except (KeyError, IndexError, ValueError, FileNotFoundError):
        return False
    text = norm(" ".join(strip_html(v) for v in _strings(value))).replace(" ", "")
    # Old reviews masked phone numbers etc. as "[phone omitted]": every unmasked piece must be there.
    pieces = re.split(r"\[[^\]]*omitted\]", norm(strip_html(quote["text"])).replace(" ", ""))
    return all(piece in text for piece in pieces)


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        value = list(value.values())
    return [s for v in value for s in _strings(v)] if isinstance(value, list) else [str(value)]

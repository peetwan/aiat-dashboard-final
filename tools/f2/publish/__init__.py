"""Publish stage: the public F2 files (data/public/f2) from the Measure tables.

`python -m tools.f2 publish` builds a candidate in data/runtime/f2/publish/<stamp>/, laid out like the repo:

- data/public/f2/: the files the dashboard reads (overview, geography, one file per topic, detail shards);
- config/publication_contracts/f2_dashboard.json: the F2 publication contract (file list, record counts,
  allowed name/place fields), regenerated for these files;
- data/public/serving_manifest.json with its F2 entries replaced, and a new publication receipt;
- every other public file and contract, hard-linked, so the repo's own publication check
  (app.publication.validate_workspace: privacy, links, counts, receipt) runs on the whole candidate.

It then writes a diff report against the published files. Nothing public changes until the owner signs off
and runs `python -m tools.f2 publish --promote <candidate dir>`, which copies the candidate in, marks the
F2 manifest approved, rewrites the receipt and checks the repo again.

Fixed text (measure names, limitations, source descriptions, filter labels) lives in config.json.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from ..clean import DB_PATH, ROOT, needs_new_look
from ..geo import Geo
from . import details as detail_records
from .results import Results

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "config.json"
PUBLISH_ROOT = ROOT / "data" / "runtime" / "f2" / "publish"
PUBLIC, CONTRACTS = Path("data/public"), Path("config/publication_contracts")
F2, CONTRACT, SERVING = PUBLIC / "f2", CONTRACTS / "f2_dashboard.json", PUBLIC / "serving_manifest.json"
CATALOG = ROOT / "config" / "source_catalog.json"
SHARD_BYTES = 3_900_000   # detail child files stay under the contract's 4 MiB
INLINE_BYTES = 3_000_000  # a topic whose details are smaller keeps them in the topic file
MAX_BYTES = {"overview": 524_288, "geography": 4_194_304, "topic": 8_388_608, "detail": 4_194_304}
# Labels the generic privacy check would mistake for a contact or an address, reviewed as public.
FIELD_CONTEXTS = {
    "/details_by_id/*/children/organizations/*/organization": "organization",
    "/details_by_id/*/children/participations/*/research_unit": "organization",
    "/details_by_id/*/children/work_attributions/*/attribution": "work_attribution",
}


def dump(payload) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def run(db_path: Path = DB_PATH) -> dict:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    stage = PUBLISH_ROOT / stamp
    header = {"schema_version": config["schema_version"], "release_id": f"f2-{stamp}",
              "release_date": now.date().isoformat(), "source_ids": config["source_ids"]}
    con = duckdb.connect(str(db_path), read_only=True)
    results = Results(con, config)
    records, reviewed = detail_records.build(con, config)
    stale = needs_new_look({table: [{"record_id": rid, "details": json.loads(details) if details else {}}
                                    for rid, details in con.execute(f"SELECT record_id, details FROM {table}").fetchall()]
                            for table in ("operators", "offerings", "people", "activities", "innovations")})
    issues = [f"{kind} decision {ref} ({what}): {issue} {detail}" for kind, what, ref, issue, detail in con.execute(
        """SELECT 'matching', entity, decision_ref, issue, detail FROM decision_issues
           UNION ALL SELECT 'counting', measure_id, decision_ref, issue, detail FROM counting_issues ORDER BY ALL""").fetchall()]
    con.close()
    provinces = Geo().provinces

    files: dict[str, tuple[dict, str, list[str]]] = {}  # path in f2/ -> (payload, artifact key, source ids)
    for topic_id, topic in config["topics"].items():
        files.update(_topic(topic_id, topic, config, results, records.get(topic_id), provinces, header))
    files["overview.json"] = (_overview(config, results, header), "f2/overview", config["source_ids"])
    files["geography.json"] = (_geography(config, results, provinces, header), "f2/geography", config["source_ids"])

    out = stage / F2
    out.mkdir(parents=True)
    inventory = []
    for path, (payload, key, source_ids) in sorted(files.items()):
        data = dump(payload)
        kind = "detail" if path.startswith("details/") else "topic" if path.startswith("topics/") else path.split(".")[0]
        if len(data) > MAX_BYTES[kind]:
            raise SystemExit(f"{path} is {len(data):,} bytes, over the {MAX_BYTES[kind]:,} limit")
        (out / path).parent.mkdir(parents=True, exist_ok=True)
        (out / path).write_bytes(data)
        inventory.append({"artifact_key": key, "path": path, "sha256": hashlib.sha256(data).hexdigest(),
                          "size": len(data), "source_ids": source_ids})
    counts = {m: {"counted_entity_total": None if results.is_total(m) or meta.get("unavailable_reason")
                  else len(results.everyone[m]),
                  "public_detail_total": len(results.everyone[m]) if meta["detail_availability"] == "available" else 0,
                  # people counted without a public record of their own (C08 assessments)
                  "withheld_detail_total": len(results.everyone[m]) if meta["unit"] == "person"
                  and meta["detail_availability"] != "available" and not results.is_total(m) else 0}
              for m, meta in config["measures"].items()}
    manifest = {**header, "complete": True, "validation_status": "pending", "publication_status": "staged_for_review",
                "publication_approval_claimed": False, "staged_for_review": True, "topic_count": len(config["topics"]),
                "counts_by_measure": counts, "files": inventory,
                "detail_inventory": {"detail_child_artifact_count": sum(p.startswith("details/") for p in files),
                                     "detail_record_count": sum(len(r) for r in records.values())}}
    (out / "manifest.json").write_bytes(dump(manifest))

    _workspace(stage, files, reviewed, config)
    _receipt(stage)
    report = _validate(stage)
    (stage / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    from tools import f2_public_diff
    f2_public_diff.main(["--base", str(ROOT / F2), "--new", str(out), "--out", str(stage / "diff")])
    if stale:  # the sign-off must see reviews whose evidence changed; the rows are still counted
        with open(stage / "diff" / "diff.md", "a", encoding="utf-8") as f:
            f.write(f"\n## Reviewed findings whose source changed ({len(stale)})\n\nStill counted. Check each "
                    "review still holds, then update or reject it in data/runtime/f2/decisions/.\n\n"
                    + "".join(f"- {note}\n" for note in stale))
    if issues:  # decisions Resolve or Measure could not apply as reviewed
        with open(stage / "diff" / "diff.md", "a", encoding="utf-8") as f:
            f.write(f"\n## Reviewed decisions that no longer fit the data ({len(issues)})\n\nMatching decisions listed "
                    "here are not applied; each counting line says whether its exclusion still applies. Fix or remove "
                    "each in data/runtime/f2/decisions/.\n\n" + "".join(f"- {note}\n" for note in issues))
    return {"candidate": str(stage), "validation": report["status"], "problems": report["problems"][:20],
            "diff": str(stage / "diff" / "diff.md"), "needs_new_look": len(stale) + len(issues)}


# Files ------------------------------------------------------------------------

def _filter_contract(meta: dict) -> dict:
    return {k: meta[k] for k in ("detail_availability", "map_availability", "permitted_combinations", "supported_filters")}


def _places(config: dict, measure_ids: list[str], provinces: dict) -> list[dict]:
    places = [{}] + [{"province": [code]} for code in sorted(provinces)]
    if any("source_region" in config["measures"][m]["supported_filters"] for m in measure_ids):
        places += [{"source_region": [region]} for _, region in sorted(config["source_regions"].items())]
    return places


def _topic(topic_id: str, topic: dict, config: dict, results: Results, records: dict | None, provinces: dict,
           header: dict) -> dict:
    measure_ids = topic["measure_ids"]
    detail_measures = [m for m in measure_ids if config["measures"][m]["detail_availability"] == "available"]
    scopes, index = {}, {m: {} for m in detail_measures}
    for place in _places(config, measure_ids, provinces):
        key = results.result(measure_ids[0], place)["scope_key"]
        prepared = {m: results.prepared(m, place, m in detail_measures) for m in measure_ids}
        scopes[key] = {"scope_key": key, "results": {m: p["default"]["result"] for m, p in prepared.items()},
                       "coverage": {m: results.coverage(m, place) for m in measure_ids},
                       "prepared_filters": prepared, "context_results": results.context(measure_ids, place)}
        for m in detail_measures:
            if "source_region" not in place:
                index[m][key] = sorted(results.entities(m, place))
    sources = [config["sources"][s] for s in topic["source_ids"]]
    doc = {**header, "topic_id": topic_id, "measure_ids": measure_ids,
           "filter_contracts": {m: _filter_contract(config["measures"][m]) for m in measure_ids},
           "scopes": scopes, "sources": sources, "limitations": config["limitations"],
           "items_by_id": {}, "item_ids_by_measure_and_scope": index, "details_by_id": {}, "detail_artifacts": {}}
    files = {}
    if records:
        doc["items_by_id"] = {i: detail_records.items(topic_id, r) for i, r in sorted(records.items())}
        if len(dump(records)) < INLINE_BYTES:
            doc["details_by_id"] = dict(sorted(records.items()))
        else:
            shard, size = {}, 0
            for entity_id, record in sorted(records.items()):
                record_size = len(dump(record)) + len(entity_id) + 4
                if shard and size + record_size > SHARD_BYTES:
                    files.update(_shard(topic_id, len(files), shard, header))
                    shard, size = {}, 0
                shard[entity_id], size = record, size + record_size
            files.update(_shard(topic_id, len(files), shard, header))
            for path, (payload, key, _) in files.items():
                doc["detail_artifacts"].update({i: key for i in payload["details_by_id"]})
    group_sources = topic["source_ids"]
    files[f"topics/{topic_id}.json"] = (doc, f"f2/topic/{topic_id}", group_sources)
    return files


def _shard(topic_id: str, n: int, records: dict, header: dict) -> dict:
    sources = sorted({s for r in records.values() for s in r["source_ids"]})
    payload = {**header, "topic_id": topic_id, "detail_count": len(records), "details_by_id": records}
    return {f"details/{topic_id}-{n:03d}.json": (payload, f"f2/topic/{topic_id}/detail/{n:03d}", sources)}


def _overview(config: dict, results: Results, header: dict) -> dict:
    def headline(m: str) -> dict:
        meta = config["measures"][m]
        keep = {k: meta[k] for k in ("topic_id", "parent_measure_id", "display_order", "label_th", "formula", "scope",
                                     "limitations", "map_legend_th", "status", "unit", "detail_availability",
                                     "map_availability", "source_ids")}
        return {**keep, "measure_id": m, "artifact_key": f"f2/topic/{meta['topic_id']}",
                "filter_contract": {k: meta[k] for k in ("permitted_combinations", "supported_filters")},
                "result": results.result(m, {}), "coverage": results.coverage(m, {}), "companions": []}
    rows = {m: headline(m) for m in config["measures"]}
    for m, row in rows.items():
        if row["parent_measure_id"]:
            del row["artifact_key"], row["companions"]
            rows[row["parent_measure_id"]]["companions"].append(row)
    headlines = sorted((r for r in rows.values() if not r["parent_measure_id"]), key=lambda r: r["display_order"])
    for row in headlines:
        row["companions"].sort(key=lambda r: r["display_order"])
    return {**header, "headlines": headlines, "limitations": config["limitations"]}


def _geography(config: dict, results: Results, provinces: dict, header: dict) -> dict:
    measures = sorted(config["measures"], key=lambda m: config["measures"][m]["display_order"])

    def scope(place: dict) -> dict:
        return {"scope_key": results.result(measures[0], place)["scope_key"],
                "results": {m: results.result(m, place) for m in measures},
                "coverage": {m: results.coverage(m, place) for m in measures},
                "context_results": results.context(measures, place)}
    return {**header, **config["geography"], "national": scope({}),
            "provinces": {code: {"province_code": code, "province_name_th": name, **scope({"province": [code]})}
                          for code, name in sorted(provinces.items())}}


# Candidate workspace, contract and checks ---------------------------------------

def _workspace(stage: Path, files: dict, reviewed: dict[str, str], config: dict) -> None:
    """The rest of the public workspace next to the new F2 files (hard links: no copies of 30 MB)."""
    for path in sorted((ROOT / PUBLIC).rglob("*")):
        relative = path.relative_to(ROOT)
        if path.is_file() and not relative.is_relative_to(F2) and relative != SERVING:
            (stage / relative).parent.mkdir(parents=True, exist_ok=True)
            os.link(path, stage / relative)
    (stage / CONTRACTS).mkdir(parents=True)
    for path in sorted((ROOT / CONTRACTS).glob("*.json")):
        if path.name != CONTRACT.name:
            os.link(path, stage / CONTRACTS / path.name)
    (stage / CONTRACT).write_text(json.dumps(_contract(files, reviewed, config), ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8")
    serving = json.loads((ROOT / SERVING).read_text(encoding="utf-8"))
    serving["artifacts"] = [a for a in serving["artifacts"] if not str(a.get("key", "")).startswith("f2/")] + [
        {"group": "methodology" if not sources and path.startswith("topics/") else "source_dataset", "key": key,
         "path": f"f2/{path}", "source_ids": sources} for path, (_, key, sources) in sorted(files.items())]
    (stage / SERVING).write_text(json.dumps(serving, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _contract(files: dict, reviewed: dict[str, str], config: dict) -> dict:
    """The F2 publication contract for these files; reviewed labels get a field context where they appear.
    Measure names and formulas come from config.json, so the contract always matches the dashboard text."""
    contract = json.loads((ROOT / CONTRACT).read_text(encoding="utf-8"))
    contract["builder"] = "tools.f2.__main__:main"
    contract["measures"] = [{"name": f"{m}: {meta['label_th']}", "denominator": meta["formula"], "unit": meta["unit"]}
                            for m, meta in sorted(config["measures"].items(), key=lambda kv: kv[1]["display_order"])]
    outputs = []
    for path, (payload, _, sources) in sorted(files.items()):
        kind = "detail" if path.startswith("details/") else "topic" if path.startswith("topics/") else path.split(".")[0]
        pointer = {"overview": "/headlines", "geography": "/provinces", "topic": "/items_by_id", "detail": "/details_by_id"}[kind]
        records = payload[pointer.strip("/")]
        output = {"path": f"data/public/f2/{path}", "role": "database", "format": "json", "downloadable": True,
                  "schema_policy": "stable", "expected_files": 1, "expected_count": len(records),
                  "minimum_count": len(records), "records_pointer": pointer, "max_bytes": MAX_BYTES[kind],
                  "identity_fields": ["measure_id"] if kind == "overview" else ["$key"],
                  "max_identity_churn_ratio": 1}
        if kind in ("detail", "topic") and payload.get("details_by_id"):
            output["field_contexts"] = dict(FIELD_CONTEXTS)
        for entity_id, context in sorted(reviewed.items()):
            if entity_id in payload.get("details_by_id", {}):
                output.setdefault("field_contexts", {}).update({f"/details_by_id/{entity_id}/label": context,
                                                                f"/details_by_id/{entity_id}/listings/*/label": context})
            if entity_id in payload.get("items_by_id", {}):
                output.setdefault("field_contexts", {})[f"/items_by_id/{entity_id}/label"] = context
        if "f2_culturalmap_university" in sources and kind in ("detail", "topic"):
            output["media_source_prefixes"] = {"f2_culturalmap_university": [
                "https://dp.culturalmapthailand.info/file-upload/", "https://dp.culturalmapthailand.info/gallery/"]}
        outputs.append(output)
    outputs.append({"path": "data/public/f2/manifest.json", "role": "provenance", "format": "json", "downloadable": False,
                    "schema_policy": "stable", "expected_files": 1, "max_bytes": 1_048_576})
    contract["outputs"] = outputs
    return contract


def _validate(root: Path) -> dict:
    from app.publication import validate_workspace
    return validate_workspace(root, root / CONTRACTS, CATALOG)


def _receipt(root: Path) -> None:
    from app.publication import write_receipt
    target = root / PUBLIC / "publication_receipt.json"
    if target.exists():
        target.unlink()  # a hard link to the repo's receipt: never write through it
    write_receipt(root, root / CONTRACTS, CATALOG)


# Promote (after sign-off) -------------------------------------------------------

def promote(candidate: Path) -> dict:
    """Copy a signed-off candidate into the repo: data/public/f2, the F2 contract and the F2 serving entries,
    mark the F2 manifest approved, rewrite the receipt and check the whole repo workspace."""
    candidate = Path(candidate).resolve()
    # checked again now, not trusted from validation.json: the candidate may have changed since it was built
    if _validate(candidate)["status"] != "valid":
        raise SystemExit("the candidate does not pass the publication check; fix it and publish again")
    manifest = json.loads((candidate / F2 / "manifest.json").read_text(encoding="utf-8"))
    manifest.update({"publication_status": "approved_local_publication", "publication_approval_claimed": True,
                     "staged_for_review": False, "validation_status": "passed",
                     "approved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    shutil.rmtree(ROOT / F2)
    shutil.copytree(candidate / F2, ROOT / F2)
    (ROOT / F2 / "manifest.json").write_bytes(dump(manifest))
    for path in (CONTRACT, SERVING):
        shutil.copyfile(candidate / path, ROOT / path)
    from app.publication import write_receipt
    write_receipt(ROOT, ROOT / CONTRACTS, CATALOG)
    report = _validate(ROOT)
    return {"release_id": manifest["release_id"], "validation": report["status"], "problems": report["problems"][:20]}

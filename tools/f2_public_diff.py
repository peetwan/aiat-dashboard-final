"""เทียบข้อมูล F2 สาธารณะ (data/public/f2) สองชุด แล้วสรุปความต่างให้ owner ตรวจก่อน sign-off.

ค่าเริ่มต้น: baseline = git ref `main`, ชุดใหม่ = data/public/f2 ในเครื่อง
รายงาน (Markdown + JSON) เขียนลง data/runtime/f2/diffs/ ซึ่งไม่เข้า git

    python tools/f2_public_diff.py
    python tools/f2_public_diff.py --base-ref main --new path/to/candidate/f2
    python tools/f2_public_diff.py --base path/to/old/f2 --new path/to/new/f2
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = "data/public/f2"
EXAMPLES = 8

# Provenance/approval bookkeeping changes on every build; reported only as "metadata changed".
METADATA_KEYS = {
    "internal_review", "local_promotion", "release_date", "release_id", "private_revision_id",
    "detail_owner_approval", "c02_field_review", "c02_geography_review", "publication_status",
    "publication_approval_claimed", "staged_for_review", "owner_checkpoint_required",
    "additional_field_review_status", "files", "source_snapshots", "validation_status",
}


def is_metadata(key: str) -> bool:
    return key in METADATA_KEYS or "sha256" in key


def load_dir(path: Path) -> dict[str, object]:
    if not path.is_dir():
        raise SystemExit(f"ไม่พบโฟลเดอร์: {path}")
    return {p.relative_to(path).as_posix(): json.loads(p.read_text(encoding="utf-8")) for p in sorted(path.rglob("*.json"))}


def load_ref(ref: str) -> dict[str, object]:
    def git(*args: str) -> bytes:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout
    try:
        names = git("ls-tree", "-r", "--name-only", ref, "--", PUBLIC).decode().split()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"อ่าน git ref ไม่ได้: {ref}: {exc.stderr.decode().strip()}") from exc
    if not names:
        raise SystemExit(f"ไม่มี {PUBLIC} ใน git ref {ref}")
    return {n[len(PUBLIC) + 1:]: json.loads(git("show", f"{ref}:{n}")) for n in names if n.endswith(".json")}


def results(bundle: dict) -> dict[tuple[str, str], dict]:
    """(measure_id, scope_key) -> result, from every topic scope (national + provinces/regions)."""
    out = {}
    for name, doc in bundle.items():
        if name.startswith("topics/"):
            for scope_key, scope in doc.get("scopes", {}).items():
                for measure_id, result in (scope.get("results") or {}).items():
                    out[(measure_id, scope_key)] = {"value": result.get("value"), "status": result.get("status")}
    return out


def items(bundle: dict) -> dict[str, dict[str, dict]]:
    """topic -> entity id -> item summary (label, identity, provinces, sources)."""
    return {name.split("/")[1].removesuffix(".json"): doc.get("items_by_id", {})
            for name, doc in bundle.items() if name.startswith("topics/")}


def details(bundle: dict) -> dict[tuple[str, str], dict]:
    """(topic, entity id) -> full public detail record, inline or in details/*.json child files."""
    out = {}
    for name, doc in bundle.items():
        if name.startswith("topics/"):
            topic = name.split("/")[1].removesuffix(".json")
        elif name.startswith("details/"):
            topic = name.split("/")[1].split("-")[0]
        else:
            continue
        for entity_id, record in (doc.get("details_by_id") or {}).items():
            out[(topic, entity_id)] = record
    return out


def compare_results(base: dict, new: dict) -> dict:
    changed = []
    for key in sorted(base.keys() | new.keys()):
        b, n = base.get(key), new.get(key)
        if b != n:
            bv, nv = (b or {}).get("value"), (n or {}).get("value")
            delta = nv - bv if isinstance(bv, (int, float)) and isinstance(nv, (int, float)) else None
            changed.append({"measure_id": key[0], "scope": key[1], "base": b, "new": n, "delta": delta})
    national = [c for c in changed if c["scope"] == "national"]
    by_measure = defaultdict(list)
    for c in changed:
        if c["scope"] != "national":
            by_measure[c["measure_id"]].append(c)
    return {"compared": len(base.keys() | new.keys()), "changed": len(changed), "national": national,
            "sub_national": {m: {"scopes_changed": len(v),
                                 "largest": sorted(v, key=lambda c: -abs(c["delta"] or 0))[:EXAMPLES]}
                             for m, v in sorted(by_measure.items())}}


def compare_items(base: dict, new: dict) -> dict:
    out = {}
    for topic in sorted(base.keys() | new.keys()):
        b, n = base.get(topic, {}), new.get(topic, {})
        added, removed = sorted(n.keys() - b.keys()), sorted(b.keys() - n.keys())
        # Entity ids are hashes: a rebuilt pipeline may re-key the same entity. Pair those by identical label
        # so they are reported once as "re-keyed", not as one removal plus one addition.
        unpaired = defaultdict(list)
        for i in removed:
            unpaired[b[i].get("label")].append(i)
        rekeyed = set()
        for i in added:
            label = n[i].get("label")
            if unpaired[label]:
                rekeyed |= {i, unpaired[label].pop()}
        added = [i for i in added if i not in rekeyed]
        removed = [i for i in removed if i not in rekeyed]
        field_changes = Counter()
        examples = []
        for i in sorted(b.keys() & n.keys()):
            fields = sorted(k for k in b[i].keys() | n[i].keys() if b[i].get(k) != n[i].get(k))
            field_changes.update(fields)
            if fields and len(examples) < EXAMPLES:
                examples.append({"id": i, "label": n[i].get("label"), "fields": fields})
        if added or removed or field_changes:
            out[topic] = {
                "base_total": len(b), "new_total": len(n), "added": len(added), "removed": len(removed),
                "rekeyed_same_label": len(rekeyed) // 2, "changed": sum(1 for i in b.keys() & n.keys() if b[i] != n[i]),
                "changed_fields": dict(field_changes.most_common()),
                "added_examples": [{"id": i, "label": n[i].get("label")} for i in added[:EXAMPLES]],
                "removed_examples": [{"id": i, "label": b[i].get("label")} for i in removed[:EXAMPLES]],
                "changed_examples": examples,
            }
    return out


def compare_details(base: dict, new: dict) -> dict:
    per_topic = defaultdict(lambda: {"added": 0, "removed": 0, "changed": 0, "changed_fields": Counter()})
    for key in base.keys() | new.keys():
        t = per_topic[key[0]]
        if key not in base:
            t["added"] += 1
        elif key not in new:
            t["removed"] += 1
        elif base[key] != new[key]:
            t["changed"] += 1
            t["changed_fields"].update(k for k in base[key].keys() | new[key].keys() if base[key].get(k) != new[key].get(k))
    return {topic: {**v, "changed_fields": dict(v["changed_fields"].most_common())}
            for topic, v in sorted(per_topic.items()) if v["added"] or v["removed"] or v["changed"]}


def compare_structure(base: dict, new: dict) -> dict:
    files_added, files_removed = sorted(new.keys() - base.keys()), sorted(base.keys() - new.keys())
    key_changes, metadata_changed = {}, set()
    for name in sorted(base.keys() & new.keys()):
        b, n = base[name], new[name]
        if not (isinstance(b, dict) and isinstance(n, dict)):
            continue
        added, removed = sorted(n.keys() - b.keys()), sorted(b.keys() - n.keys())
        if added or removed:
            key_changes[name] = {"added_keys": added, "removed_keys": removed}
        metadata_changed |= {k for k in b.keys() & n.keys() if is_metadata(k) and b[k] != n[k]}
    return {"files_added": files_added, "files_removed": files_removed, "top_level_key_changes": key_changes,
            "metadata_changed": sorted(metadata_changed)}


ID_MAP = 20  # a dict with more keys than this is keyed by ids (scopes, provinces, entities): one path for all


def changed_paths(b, n, path: str, out: dict) -> None:
    """Every value that differs, as path pattern -> [count, first example]; bookkeeping keys skipped."""
    if isinstance(b, dict) and isinstance(n, dict):
        for k in sorted(b.keys() | n.keys()):
            if not is_metadata(k):
                part = "*" if max(len(b), len(n)) > ID_MAP else k
                changed_paths(b.get(k), n.get(k), f"{path}/{part}", out)
    elif isinstance(b, list) and isinstance(n, list) and len(b) == len(n):
        for x, y in zip(b, n):
            changed_paths(x, y, f"{path}/#", out)
    elif b != n:
        entry = out.setdefault(path, [0, (b, n)])
        entry[0] += 1


SHARD_KEYS = {"detail_artifacts", "detail_count"}  # which detail file holds a record: not visible to a reader


def merged(bundle: dict) -> dict:
    """The bundle with each topic's detail files as one (a record moving to another file is not a change)."""
    out = {}
    for name, doc in bundle.items():
        if name.startswith("details/") and isinstance(doc, dict):
            topic = out.setdefault(f"details/{name.split('/')[1].split('-')[0]}-*.json", {"details_by_id": {}})
            topic["details_by_id"].update(doc.get("details_by_id") or {})
        else:
            out[name] = doc
    return out


def compare_everything(base: dict, new: dict) -> list[dict]:
    """A safety net under sections 1-6: whatever a reader can see that changed, in any file."""
    base, new = merged(base), merged(new)
    rows = []  # results and lists (overview, geography, topics) before the detail files
    for name in sorted(base.keys() & new.keys(), key=lambda n: (n.startswith("details/"), n)):
        out: dict = {}
        changed_paths(_without(base[name]), _without(new[name]), "", out)
        rows += [{"file": name, "path": path or "/", "changed": count, "example": example}
                 for path, (count, example) in out.items()]
    return rows


def _without(doc):
    return {k: v for k, v in doc.items() if k not in SHARD_KEYS} if isinstance(doc, dict) else doc


def compare_counts(base: dict, new: dict) -> list[dict]:
    b = (base.get("manifest.json") or {}).get("counts_by_measure", {})
    n = (new.get("manifest.json") or {}).get("counts_by_measure", {})
    return [{"measure_id": m, "base": b.get(m), "new": n.get(m)} for m in sorted(b.keys() | n.keys()) if b.get(m) != n.get(m)]


def fmt(value) -> str:
    if value is None:
        return "—"
    return f"{value:,}" if isinstance(value, int) else (f"{value:,.4g}" if isinstance(value, float) else str(value))


def markdown(report: dict) -> str:
    r, lines = report, []
    lines += [f"# F2 public data diff", "", f"- Base: `{r['base']}`", f"- New: `{r['new']}`", f"- Generated: {r['generated_at']}", ""]
    if r["identical"]:
        return "\n".join(lines + ["**No differences.** The two bundles are identical.", ""])
    res = r["results"]
    lines += ["## 1. Headline values (national)", "",
              f"{res['changed']} of {res['compared']} measure × scope results changed.", ""]
    if res["national"]:
        lines += ["| Measure | Base | New | Change | Status (base → new) |", "|---|---:|---:|---:|---|"]
        for c in res["national"]:
            b, n = c["base"] or {}, c["new"] or {}
            status = "" if b.get("status") == n.get("status") else f"{b.get('status')} → {n.get('status')}"
            lines.append(f"| {c['measure_id']} | {fmt(b.get('value'))} | {fmt(n.get('value'))} | {fmt(c['delta'])} | {status} |")
    else:
        lines.append("No national value changed.")
    lines += ["", "## 2. Province / region results", ""]
    if res["sub_national"]:
        lines += ["| Measure | Scopes changed | Largest changes |", "|---|---:|---|"]
        for m, v in res["sub_national"].items():
            top = ", ".join(f"{c['scope']} {fmt((c['base'] or {}).get('value'))}→{fmt((c['new'] or {}).get('value'))}" for c in v["largest"][:4])
            lines.append(f"| {m} | {v['scopes_changed']} | {top} |")
    else:
        lines.append("No province or region result changed.")
    lines += ["", "## 3. Counted entities per topic", ""]
    if r["items"]:
        lines += ["| Topic | Base | New | Added | Removed | Re-keyed (same label) | Changed |", "|---|---:|---:|---:|---:|---:|---:|"]
        for t, v in r["items"].items():
            lines.append(f"| {t} | {fmt(v['base_total'])} | {fmt(v['new_total'])} | {fmt(v['added'])} | {fmt(v['removed'])} | "
                         f"{fmt(v['rekeyed_same_label'])} | {fmt(v['changed'])} |")
        for t, v in r["items"].items():
            lines += ["", f"### {t}"]
            if v["changed_fields"]:
                lines.append("Changed fields: " + ", ".join(f"`{k}` ({n})" for k, n in v["changed_fields"].items()))
            for title, key in (("Added", "added_examples"), ("Removed", "removed_examples")):
                if v[key]:
                    lines.append(f"{title} (first {len(v[key])}): " + "; ".join(e["label"] or e["id"] for e in v[key]))
    else:
        lines.append("No entity was added, removed or changed.")
    lines += ["", "## 4. Detail records", ""]
    if r["details"]:
        lines += ["| Topic | Added | Removed | Changed | Most-changed fields |", "|---|---:|---:|---:|---|"]
        for t, v in r["details"].items():
            top = ", ".join(f"`{k}` ({n})" for k, n in list(v["changed_fields"].items())[:5])
            lines.append(f"| {t} | {fmt(v['added'])} | {fmt(v['removed'])} | {fmt(v['changed'])} | {top} |")
    else:
        lines.append("No detail record changed.")
    lines += ["", "## 5. Manifest counts", ""]
    if r["counts"]:
        lines += ["| Measure | Base | New |", "|---|---|---|"]
        for c in r["counts"]:
            lines.append(f"| {c['measure_id']} | `{json.dumps(c['base'])}` | `{json.dumps(c['new'])}` |")
    else:
        lines.append("Unchanged.")
    s = r["structure"]
    lines += ["", "## 6. Structure", "",
              f"- Files added: {', '.join(s['files_added']) or 'none'}",
              f"- Files removed: {', '.join(s['files_removed']) or 'none'}",
              f"- Files with added/removed top-level keys: {', '.join(s['top_level_key_changes']) or 'none'}",
              f"- Metadata changed (provenance/approval bookkeeping): {', '.join(s['metadata_changed']) or 'none'}", ""]
    every = r["everything"]
    lines += ["## 7. Every changed value", "",
              "All values that differ in files present in both bundles, release bookkeeping excepted, including those "
              "summarised above (filtered results, labels, limitations, filter choices...).", ""]
    if every:
        lines += ["| File | Path (`*` = every id, `#` = every list item) | Values changed | Example: base → new |",
                  "|---|---|---:|---|"]
        for e in every[:EVERYTHING_ROWS]:
            b, n = e["example"]
            if isinstance(b, str) and isinstance(n, str):  # long texts: show where they start to differ
                start = max(0, next((i for i, (x, y) in enumerate(zip(b, n)) if x != y), min(len(b), len(n))) - 20)
                b, n = (("…" if start else "") + v[start:] for v in (b, n))
            b, n = short(b), short(n)
            lines.append(f"| {e['file']} | `{e['path']}` | {e['changed']:,} | {b} → {n} |")
        if len(every) > EVERYTHING_ROWS:
            lines.append(f"\n{len(every) - EVERYTHING_ROWS} more paths in diff.json (`everything`).")
    else:
        lines.append("None.")
    return "\n".join(lines + [""])


EVERYTHING_ROWS = 60


def short(value) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    text = text.replace("|", "\\|").replace("\n", " ")
    return f"`{text[:80]}{'…' if len(text) > 80 else ''}`"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="เทียบ data/public/f2 สองชุดและเขียนรายงานความต่าง")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--base", type=Path, help="โฟลเดอร์ baseline")
    group.add_argument("--base-ref", default="main", help="git ref ของ baseline (ค่าเริ่มต้น: main)")
    parser.add_argument("--new", type=Path, default=ROOT / PUBLIC, help=f"โฟลเดอร์ชุดใหม่ (ค่าเริ่มต้น: {PUBLIC})")
    parser.add_argument("--out", type=Path, help="โฟลเดอร์รายงาน (ค่าเริ่มต้น: data/runtime/f2/diffs/<เวลา>)")
    args = parser.parse_args(argv)

    base_label = str(args.base) if args.base else f"git:{args.base_ref}:{PUBLIC}"
    base = load_dir(args.base) if args.base else load_ref(args.base_ref)
    new = load_dir(args.new)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = {"base": base_label, "new": str(args.new), "generated_at": stamp, "identical": base == new}
    if not report["identical"]:
        report.update(results=compare_results(results(base), results(new)), items=compare_items(items(base), items(new)),
                      details=compare_details(details(base), details(new)), counts=compare_counts(base, new),
                      structure=compare_structure(base, new), everything=compare_everything(base, new))
    out = args.out or ROOT / "data/runtime/f2/diffs" / stamp
    out.mkdir(parents=True, exist_ok=True)
    (out / "diff.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out / "diff.md").write_text(markdown(report), encoding="utf-8")
    if report["identical"]:
        print("No differences.")
    else:
        res = report["results"]
        print(f"{res['changed']} of {res['compared']} results changed ({len(res['national'])} national); "
              f"entity changes in {len(report['items'])} topics; detail changes in {len(report['details'])} topics")
    print(f"Report: {out / 'diff.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

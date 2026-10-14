"""python -m tools.f2 clean     — rebuild the entity tables from the latest raw snapshots.
python -m tools.f2 resolve   — decide which records are the same entity (reviewed decisions, then rules).
python -m tools.f2 measure   — compute the measures (which entities each counts, and source totals).
python -m tools.f2 judge     — show what the LLM judge would be asked for the queued pairs; --send asks it
                               (paid, needs OPENROUTER_API_KEY), then run resolve again.
python -m tools.f2 review    — open a local page to review the queued pairs; answers go into the decisions,
                               then run resolve again.
python -m tools.f2 publish   — build the public files as a checked candidate with a diff report;
                               --promote <candidate dir> installs a signed-off candidate."""

from __future__ import annotations

import argparse
import json

import duckdb

from . import clean, measure, publish, resolve, review
from .resolve import judge


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.f2", description=__doc__)
    parser.add_argument("stage", choices=["clean", "resolve", "measure", "judge", "review", "publish"])
    parser.add_argument("--send", action="store_true", help="judge: send the requests (paid)")
    parser.add_argument("--budget", type=float, default=0.5, help="judge: stop once this many USD are spent")
    parser.add_argument("--entity", choices=judge.ENTITIES, action="append", help="judge: only these kinds")
    parser.add_argument("--port", type=int, default=8765, help="review: the local port")
    parser.add_argument("--promote", metavar="CANDIDATE", help="publish: install this signed-off candidate")
    args = parser.parse_args()
    stage = args.stage
    if stage == "judge":
        print(json.dumps(judge.run(args.budget, args.entity or judge.ENTITIES, args.send), ensure_ascii=False, indent=1))
        return 0
    if stage == "review":
        review.serve(args.port)
        return 0
    if stage == "publish":
        outcome = publish.promote(args.promote) if args.promote else publish.run()
        print(json.dumps(outcome, ensure_ascii=False, indent=1))
        return 0 if outcome["validation"] == "valid" else 1
    if stage == "measure":
        for measure_id, value in measure.run().items():
            print(f"{measure_id}: {value:,.6g}")
        with duckdb.connect(str(clean.DB_PATH), read_only=True) as con:
            for measure_id, ref, issue, detail in con.execute("SELECT * FROM counting_issues ORDER BY ALL").fetchall():
                print(f"  NEEDS A NEW LOOK (counting decision {ref}, {measure_id}): {issue} {detail}")
    elif stage == "clean":
        for source, result in clean.run().items():
            print(source, ", ".join(f"{table} {n:,}" for table, n in sorted(result["rows"].items())))
            for name in result["unaccounted_raw_files"]:
                print(f"  WARNING raw file not read and not listed as skipped: {name}")
            for note in result["needs_new_look"]:
                print(f"  NEEDS A NEW LOOK (source changed since the review): {note}")
    else:
        for entity, n in resolve.run().items():
            print(f"{entity}: {n['records']:,} records -> {n['entities']:,} entities; pairs same {n['same']:,}, "
                  f"different {n['different']:,}, waiting for review {n['queue']:,}; decision issues {n['issues']}")
    print(f"wrote {clean.DB_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""python -m tools.f2 clean     — rebuild the entity tables from the latest raw snapshots.
python -m tools.f2 resolve   — decide which records are the same entity (reviewed decisions, then rules).
python -m tools.f2 measure   — compute the measures (which entities each counts, and source totals).
python -m tools.f2 judge     — show what the LLM judge would be asked for the queued pairs; --send asks it
                               (paid, needs OPENROUTER_API_KEY), then run resolve again."""

from __future__ import annotations

import argparse
import json

from . import clean, measure, resolve
from .resolve import judge


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.f2", description=__doc__)
    parser.add_argument("stage", choices=["clean", "resolve", "measure", "judge"])
    parser.add_argument("--send", action="store_true", help="judge: send the requests (paid)")
    parser.add_argument("--budget", type=float, default=0.5, help="judge: stop once this many USD are spent")
    parser.add_argument("--entity", choices=judge.ENTITIES, action="append", help="judge: only these kinds")
    args = parser.parse_args()
    stage = args.stage
    if stage == "judge":
        print(json.dumps(judge.run(args.budget, args.entity or judge.ENTITIES, args.send), ensure_ascii=False, indent=1))
        return 0
    if stage == "measure":
        for measure_id, value in measure.run().items():
            print(f"{measure_id}: {value:,.6g}")
    elif stage == "clean":
        for source, tables in clean.run().items():
            print(source, ", ".join(f"{table} {n:,}" for table, n in sorted(tables.items())))
    else:
        for entity, n in resolve.run().items():
            print(f"{entity}: {n['records']:,} records -> {n['entities']:,} entities; pairs same {n['same']:,}, "
                  f"different {n['different']:,}, waiting for review {n['queue']:,}; decision issues {n['issues']}")
    print(f"wrote {clean.DB_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Reviewed decisions live in data/runtime/f2/decisions/ (local, not in git), keyed by source record ids.

- extractions.json: businesses, offerings, people and activities found in record text.
- parsing.json: corrections to how a source field is read (source -> field -> record_id).
- matching.json: same / different decisions between records (also product families).
- counting.json: records a measure does not count, with the reason.
- judge.json: the LLM judge's answers for queued pairs (written by python -m tools.f2 judge).
"""

from __future__ import annotations

import json
from pathlib import Path

DIR = Path(__file__).resolve().parents[2] / "data" / "runtime" / "f2" / "decisions"


def load(name: str, empty: dict) -> dict:
    path = DIR / name
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else empty

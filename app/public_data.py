from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.settings import PROJECT_ROOT


PUBLIC_DATA_ROOT = PROJECT_ROOT / "data" / "public"


@lru_cache(maxsize=8)
def load_public_file(filename: str) -> dict[str, Any]:
    path = (PUBLIC_DATA_ROOT / filename).resolve()
    if path.parent != PUBLIC_DATA_ROOT.resolve() or not path.exists():
        raise FileNotFoundError(filename)
    return json.loads(path.read_text(encoding="utf-8"))


def public_catalog() -> dict[str, Any]:
    return load_public_file("public_dashboard.json")


def province_boundaries() -> dict[str, Any]:
    return load_public_file("thailand_provinces.geojson")


def cultural_points() -> dict[str, Any]:
    return load_public_file("cultural_points.geojson")


@lru_cache(maxsize=77)
def provincial_briefing(province_code: str) -> dict[str, Any]:
    code = province_code.strip().zfill(2)
    path = (PUBLIC_DATA_ROOT / "provincial_briefings" / f"{code}.json").resolve()
    briefing_root = (PUBLIC_DATA_ROOT / "provincial_briefings").resolve()
    if path.parent != briefing_root or not path.exists():
        raise FileNotFoundError(code)
    return json.loads(path.read_text(encoding="utf-8"))

"""Clean stage: run every source cleaner and write the entity tables (../schema.sql) to DuckDB.

A cleaner is a module with `clean(raw: Raw, geo: Geo) -> dict[table, list[row dict]]`.
It reads only its own source's raw snapshot and states facts; it never merges records.
"""

from __future__ import annotations

import gzip
import json
from collections import Counter
from pathlib import Path

import duckdb

from ..geo import Geo
from . import (apptech_mru, atlocal, cultural_map, extracted, icommunity, learning_area_based,
               learning_dashboard, pmua_apptech, rinmp)

ROOT = Path(__file__).resolve().parents[3]
RAW_ROOT = ROOT / "data" / "runtime" / "f2" / "raw"
DB_PATH = ROOT / "data" / "runtime" / "f2" / "pipeline" / "f2.duckdb"
SCHEMA = Path(__file__).resolve().parents[1] / "schema.sql"

# source name -> (raw snapshot folder, cleaner)
CLEANERS = {
    "apptech_mru": ("f2_apptech_mru", apptech_mru),
    "rinmp": ("f2_apptech_mtr", rinmp),
    "pmua_apptech": ("f2_target_household", pmua_apptech),
    "icommunity": ("f2_icommunity", icommunity),
    "atlocal": ("f2_cultural_market_civil", atlocal),
    "cultural_map": ("f2_culturalmap_university", cultural_map),
    "learning_area_based": ("f2_learning_area_based", learning_area_based),
    "learning_dashboard": ("f2_learning_dashboard", learning_dashboard),
}


class Raw:
    """One source's raw snapshot run folder."""

    def __init__(self, folder: Path):
        self.folder = folder
        self._cache: dict[str, object] = {}

    def json(self, name: str):
        """Read name.gz (preferred) or name. Parsed once per run."""
        if name not in self._cache:
            gz = self.folder / f"{name}.gz"
            if gz.is_file():
                with gzip.open(gz, "rt", encoding="utf-8") as f:
                    self._cache[name] = json.load(f)
            else:
                self._cache[name] = json.loads((self.folder / name).read_text(encoding="utf-8"))
        return self._cache[name]

    def at(self, ref: str):
        """The value a raw_ref ("file.json#data/3/title") points to."""
        name, _, path = ref.partition("#")
        value = self.json(name)
        for part in filter(None, path.split("/")):
            value = value[int(part)] if isinstance(value, list) else value[part]
        return value

    def jsonl(self, name: str) -> list:
        """Read name.gz (preferred) or name, one JSON value per line."""
        gz = self.folder / f"{name}.gz"
        with (gzip.open(gz, "rt", encoding="utf-8") if gz.is_file() else open(self.folder / name, encoding="utf-8")) as f:
            return [json.loads(line) for line in f if line.strip()]


def latest_run(folder: str) -> Path:
    runs = sorted(p for p in (RAW_ROOT / folder).iterdir() if p.is_dir())
    if not runs:
        raise SystemExit(f"no raw snapshot under {RAW_ROOT / folder}")
    return runs[-1]


def insert(con: duckdb.DuckDBPyConnection, table: str, rows: list[dict]) -> None:
    columns = [r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()]
    unknown = {key for row in rows for key in row} - set(columns)
    if unknown:
        raise ValueError(f"{table}: unknown columns {sorted(unknown)}")
    values = [
        [json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for v in (row.get(c) for c in columns)]
        for row in rows
    ]
    if values:
        con.executemany(f"INSERT INTO {table} VALUES ({', '.join('?' * len(columns))})", values)


def run(db_path: Path = DB_PATH) -> dict[str, Counter]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    con.execute(SCHEMA.read_text(encoding="utf-8"))
    geo, counts, reviewed = Geo(), {}, extracted.load()
    for source, (folder, cleaner) in CLEANERS.items():
        run_dir = latest_run(folder)
        raw = Raw(run_dir)
        tables = cleaner.clean(raw, geo)
        for table, rows in extracted.rows(source, raw, reviewed, tables).items():
            tables[table] = tables.get(table, []) + rows
        _link(source, tables, extracted.links(source, reviewed))
        insert(con, "runs", [{"source": source, "raw_folder": folder, "run_id": run_dir.name}])
        for table, rows in tables.items():
            insert(con, table, [{"source": source, **row} for row in rows])
        counts[source] = Counter({table: len(rows) for table, rows in tables.items()})
    con.close()
    tmp.replace(db_path)  # only a complete run replaces the previous database
    return counts


def _link(source: str, tables: dict, links: list[dict]) -> None:
    """Add reviewed seller/maker links (operator → offering) to the links the source states."""
    operators = {row["record_id"] for row in tables.get("operators", [])}
    offerings = {row["record_id"] for row in tables.get("offerings", [])}
    for link in links:
        if link["offering_record_id"] not in offerings or link["operator_record_id"] not in operators:
            raise ValueError(f"{source}: reviewed link points at a missing record: {link}")
        tables.setdefault("offering_operators", []).append({
            "offering_record_id": link["offering_record_id"], "operator_record_id": link["operator_record_id"],
            "relationship": "seller" if link["relationship"] in ("seller_of", "seller_of_listed_product")
            else link["relationship"], "basis": "review"})

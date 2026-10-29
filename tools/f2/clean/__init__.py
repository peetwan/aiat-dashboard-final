"""Clean stage: run every source cleaner and write the entity tables (../schema.sql) to DuckDB.

A cleaner is a module with `clean(raw: Raw, geo: Geo) -> dict[table, list[row dict]]`.
It reads only its own source's raw snapshot and states facts; it never merges records.
A cleaner whose source dates its records also has `updated(raw) -> list` (the stated last-change dates);
the runs table keeps the latest, next to when we fetched the snapshot.
"""

from __future__ import annotations

import gzip
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb

from .. import institutions
from ..geo import Geo
from . import (apptech_mru, atlocal, cultural_map, extracted, icommunity, learning_area_based,
               learning_dashboard, pmua_apptech, rinmp)

ROOT = Path(__file__).resolve().parents[3]
RAW_ROOT = ROOT / "data" / "runtime" / "f2" / "raw"
DB_PATH = ROOT / "data" / "runtime" / "f2" / "pipeline" / "f2.duckdb"
SCHEMA = Path(__file__).resolve().parents[1] / "schema.sql"
BANGKOK = timezone(timedelta(hours=7), "Asia/Bangkok")  # Thailand keeps no daylight saving

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

    def jsonl(self, name: str) -> list:
        """Read name.gz (preferred) or name, one JSON value per line. Parsed once per run."""
        if name not in self._cache:
            gz = self.folder / f"{name}.gz"
            with (gzip.open(gz, "rt", encoding="utf-8") if gz.is_file() else open(self.folder / name, encoding="utf-8")) as f:
                self._cache[name] = [json.loads(line) for line in f if line.strip()]
        return self._cache[name]

    def at(self, ref: str, record_id: str | None = None):
        """The value a raw_ref ("file.json#data/3/title") points to. Path parts are escaped like JSON Pointer
        (text.ref_part). With record_id, the record (the first list item on the path) is found by its id when the
        snapshot lists records in another order; KeyError when no record has that id."""
        name, _, path = ref.partition("#")
        value = self.jsonl(name) if name.endswith(".jsonl") else self.json(name)
        found = record_id is None
        for part in filter(None, path.split("/")):
            part = part.replace("~1", "/").replace("~0", "~")
            if isinstance(value, list):
                if not found:
                    value, found = _record(value, int(part), record_id), True
                    continue
                value = value[int(part)]
            else:
                value = value[part]
        return value

    def files_read(self) -> set[str]:
        return set(self._cache)

    def files(self) -> set[str]:
        """Data files in the snapshot (one name per file, with or without .gz), not its manifests or notes."""
        names = {str(p.relative_to(self.folder)).removesuffix(".gz") for p in self.folder.rglob("*") if p.is_file()}
        return {n for n in names if n.endswith((".json", ".jsonl"))
                and not (n.endswith("manifest.json") or Path(n).name == "complete_refresh_summary.json")}


ID_SUFFIXES = ("id", "_key")


def _record(items: list, index: int, record_id: str):
    """The item with this source record id: the one at index if it has that id, else the one that has it.
    Ids are compared with the item's id fields; "articles:1" also matches an item whose id is "1"."""
    wanted = {str(record_id), str(record_id).rpartition(":")[2]}

    def has_id(item) -> bool:
        return isinstance(item, dict) and any(str(v) in wanted for k, v in item.items()
                                              if k.endswith(ID_SUFFIXES) and isinstance(v, (str, int)))
    if 0 <= index < len(items) and has_id(items[index]):
        return items[index]
    match = next((item for item in items if has_id(item)), None)
    if match is None:
        raise KeyError(f"no record {record_id}")
    return match


def latest_run(folder: str) -> Path:
    runs = sorted(p for p in (RAW_ROOT / folder).iterdir() if p.is_dir())
    if not runs:
        raise SystemExit(f"no raw snapshot under {RAW_ROOT / folder}")
    return runs[-1]


def fetched(run_dir: Path) -> datetime:
    """When the snapshot was fetched, from the manifest evidence_push writes next to it."""
    manifest = run_dir / "manifest.json"
    try:
        value = datetime.fromisoformat(json.loads(manifest.read_text(encoding="utf-8"))["fetched_at"])
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise SystemExit(f"{manifest}: no readable fetched_at ({error})") from error
    if value.tzinfo is None:
        raise SystemExit(f"{manifest}: fetched_at has no time zone")
    return value


def thai_day(moment: datetime) -> date:
    """The calendar day in Thailand of a time-zone-aware moment."""
    return moment.astimezone(BANGKOK).date()


def updated_dates(values, fetched_at: datetime) -> list[date]:
    """The Thai calendar days of a cleaner's updated() values. A stamp with a time zone is converted to Thai time;
    one without (most of these Thai sites) is read as Thai local time. Unreadable values are skipped, and so is a day
    after the fetch day: the record cannot have been changed after we read it."""
    out = []
    for value in values:
        try:
            moment = datetime.fromisoformat(str(value))
        except ValueError:
            continue
        day = thai_day(moment) if moment.tzinfo else moment.date()
        if day <= thai_day(fetched_at):
            out.append(day)
    return out


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


def run(db_path: Path = DB_PATH) -> dict[str, dict]:
    """Per source: rows per table, and notes for a person to look at (raw files no cleaner accounts for,
    reviewed findings whose source text changed); then institution_names, with the names to check."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    con.execute(SCHEMA.read_text(encoding="utf-8"))
    geo, out, reviewed = Geo(), {}, extracted.load()
    for source, (folder, cleaner) in CLEANERS.items():
        run_dir = latest_run(folder)
        raw = Raw(run_dir)
        tables = cleaner.clean(raw, geo)
        for table, rows in extracted.rows(source, raw, reviewed, tables).items():
            tables[table] = tables.get(table, []) + rows
        _link(source, tables, extracted.links(source, reviewed))
        for table, rows in tables.items():
            insert(con, table, [{"source": source, **row} for row in rows])
        unread = raw.files() - raw.files_read() - set(getattr(cleaner, "SKIPPED", {}))
        fetched_at = fetched(run_dir)
        changed = updated_dates(getattr(cleaner, "updated", lambda _raw: [])(raw), fetched_at)
        insert(con, "runs", [{"source": source, "raw_folder": folder, "run_id": run_dir.name,
                              "fetched_at": fetched_at.isoformat(), "updated_latest": max(changed, default=None),
                              "updated_records": len(changed), "updated_days": len(set(changed))}])
        out[source] = {"rows": Counter({table: len(rows) for table, rows in tables.items()}),
                       "unaccounted_raw_files": sorted(unread), "needs_new_look": needs_new_look(tables)}
    names = institutions.rows(n for (n,) in con.execute(
        "SELECT institution FROM innovations UNION SELECT institution FROM people "
        "UNION SELECT details->>'research_unit' FROM operators WHERE source = 'learning_area_based'").fetchall())
    insert(con, "institution_names", names)
    con.close()
    out["institution_names"] = {"rows": Counter({"institution_names": len(names)}), "unaccounted_raw_files": [],
                                "needs_new_look": [], "institution_notes": institutions.review(names, _universities(db_path))}
    tmp.replace(db_path)  # only a complete run replaces the previous database
    return out


def _universities(db_path: Path) -> set[str]:
    """The university names of the previous Clean run (none on a first run)."""
    if not db_path.is_file():
        return set()
    with duckdb.connect(str(db_path), read_only=True) as con:
        if not con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name = 'institution_names'").fetchone()[0]:
            return set()
        return {u for (u,) in con.execute("SELECT DISTINCT university FROM institution_names").fetchall()}


def needs_new_look(tables: dict) -> list[str]:
    """Rows built from a review whose evidence is no longer in the current snapshot ("table record_id: why").
    They are still written; a person decides whether the review still holds."""
    notes = []
    for table, rows in tables.items():
        for row in rows:
            details = row.get("details") or {}
            why = [f"{details['quotes_missing']} of {details['quotes']} quotes missing" if details.get("quotes_missing") else "",
                   "publication missing" if details.get("publication_missing") else "",
                   "publication text changed since the review" if details.get("publication_changed") else "",
                   "reviewed inventor reading no longer matches the text" if details.get("reviewed_reading_stale") else ""]
            if any(why):
                notes.append(f"{table} {row['record_id']}: {'; '.join(w for w in why if w)}")
    return notes


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

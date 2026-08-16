from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
import time
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import load_ingestion_plans, source_config
from app.models import DashboardRecord, IngestionRun
from app.privacy import payload_hash, sanitize_payload, stable_record_id
from app.settings import PROJECT_ROOT, Settings, get_settings


class PolicyViolation(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_run_id(source_id: str) -> str:
    stamp = utc_now().strftime("%Y%m%dT%H%M%S%fZ")
    return f"{stamp}_{source_id}"


def relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return cleaned[:100] or "response"


def nested_record_lists(value: Any, path: str = "root") -> Iterator[tuple[str, list[dict]]]:
    if isinstance(value, list):
        rows = [item for item in value if isinstance(item, dict)]
        if rows:
            yield path, rows
        return
    if not isinstance(value, dict):
        return
    found = False
    for key, item in value.items():
        if isinstance(item, (dict, list)):
            child_path = f"{path}.{key}"
            for result in nested_record_lists(item, child_path):
                found = True
                yield result
    if not found:
        yield path, [value]


class ResponseRecorder:
    def __init__(self, source_id: str, run_id: str, settings: Settings):
        self.root = settings.raw_root / source_id / run_id
        self.root.mkdir(parents=True, exist_ok=False)
        self.settings = settings
        self.artifacts: list[dict] = []
        self.counter = 0
        self.client = httpx.Client(
            timeout=settings.http_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "AIAT-dashboard-ingestion/0.1 (+read-only)"},
        )

    def close(self) -> None:
        self.client.close()

    def request(
        self,
        method: str,
        url: str,
        *,
        name: str,
        params: dict | None = None,
        data: dict | None = None,
        json_body: dict | None = None,
    ) -> tuple[httpx.Response, Path]:
        if self.counter:
            time.sleep(self.settings.http_delay_seconds)
        response = self.client.request(method, url, params=params, data=data, json=json_body)
        response.raise_for_status()
        self.counter += 1
        suffix = ".json" if "json" in response.headers.get("content-type", "").lower() else ".bin"
        path = self.root / f"{self.counter:04d}_{safe_filename(name)}{suffix}"
        path.write_bytes(response.content)
        self.artifacts.append(
            {
                "path": relative_path(path),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "method": method.upper(),
                "url": str(response.url),
                "http_status": response.status_code,
                "content_type": response.headers.get("content-type", ""),
            }
        )
        return response, path

    def write_manifest(self, source_id: str, run_id: str, records_seen: int) -> Path:
        manifest = {
            "manifest_version": "0.1.0",
            "source_id": source_id,
            "run_id": run_id,
            "fetched_at": utc_now().isoformat(),
            "records_seen": records_seen,
            "artifacts": self.artifacts,
        }
        path = self.root / "manifest.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path


class IngestionPipeline:
    def __init__(self, session: Session, settings: Settings | None = None):
        self.session = session
        self.settings = settings or get_settings()
        self.plans = load_ingestion_plans().get("sources", {})

    def _guard_source(self, source: dict) -> None:
        policy = source["cloud_policy"]
        if policy == "restricted_local_only":
            raise PolicyViolation(f"{source['source_id']} เป็น restricted local-only และห้าม ingest ในแอปนี้")
        if policy == "owner_terms_pending" and not self.settings.allow_pending_owner_sources:
            raise PolicyViolation(
                f"{source['source_id']} ยังรอ owner/terms; ตั้ง ALLOW_PENDING_OWNER_SOURCES=true ได้เฉพาะ local review"
            )
        if self.settings.is_production and not source["production_values_allowed"]:
            raise PolicyViolation(
                f"{source['source_id']} ยังไม่ได้รับอนุมัติให้เก็บค่าจริงบน Cloud/Railway"
            )

    def ingest_source(self, source_id: str, strategy: str = "auto") -> dict:
        source = source_config(source_id)
        self._guard_source(source)
        run_id = new_run_id(source_id)
        run = IngestionRun(
            run_id=run_id,
            source_id=source_id,
            strategy=strategy,
            status="running",
        )
        self.session.add(run)
        self.session.commit()

        records: list[tuple[str, dict]] = []
        manifest_path: Path | None = None
        fallback_note: str | None = None
        actual_strategy = strategy
        try:
            if strategy == "auto":
                actual_strategy = "api" if source["acquisition_mode"] == "api_first" else "snapshot"
            if actual_strategy == "api":
                try:
                    records, manifest_path = self._fetch_api(source, run_id)
                except Exception as exc:
                    if source.get("snapshot_fallback", False):
                        fallback_note = f"API failed; snapshot fallback used: {type(exc).__name__}: {exc}"
                        records, manifest_path = self._load_snapshot(source, run_id)
                        actual_strategy = "api_then_snapshot"
                    else:
                        raise
            elif actual_strategy == "snapshot":
                records, manifest_path = self._load_snapshot(source, run_id)
            else:
                raise ValueError("strategy ต้องเป็น auto, api หรือ snapshot")

            loaded, skipped = self._store_records(source, records)
            run.strategy = actual_strategy
            run.status = "complete"
            run.finished_at = utc_now()
            run.fetched_at = utc_now()
            run.records_seen = len(records)
            run.records_loaded = loaded
            run.records_skipped = skipped
            run.manifest_path = relative_path(manifest_path) if manifest_path else None
            run.error_message = fallback_note
            self.session.commit()
            return {
                "run_id": run_id,
                "source_id": source_id,
                "strategy": actual_strategy,
                "status": "complete",
                "records_seen": len(records),
                "records_loaded": loaded,
                "records_skipped": skipped,
                "manifest_path": run.manifest_path,
                "note": fallback_note,
            }
        except Exception as exc:
            run.status = "failed"
            run.finished_at = utc_now()
            run.error_message = f"{type(exc).__name__}: {exc}"[:4000]
            self.session.commit()
            raise

    def _store_records(self, source: dict, records: Iterable[tuple[str, dict]]) -> tuple[int, int]:
        source_id = source["source_id"]
        existing = {
            (dataset, record_id, record_hash)
            for dataset, record_id, record_hash in self.session.execute(
                select(
                    DashboardRecord.dataset_key,
                    DashboardRecord.source_record_id,
                    DashboardRecord.record_hash,
                ).where(DashboardRecord.source_id == source_id)
            )
        }
        loaded = 0
        skipped = 0
        for dataset_key, raw_payload in records:
            payload = sanitize_payload(raw_payload)
            digest = payload_hash(payload)
            record_id = stable_record_id(payload, digest)
            key = (dataset_key[:200], record_id, digest)
            if key in existing:
                skipped += 1
                continue
            self.session.add(
                DashboardRecord(
                    source_id=source_id,
                    dataset_key=dataset_key[:200],
                    source_record_id=record_id,
                    record_hash=digest,
                    quality_status=source["readiness_status"],
                    payload=payload,
                )
            )
            existing.add(key)
            loaded += 1
            if loaded % 1000 == 0:
                self.session.flush()
        self.session.commit()
        return loaded, skipped

    def _limit_reached(self, count: int) -> bool:
        limit = self.settings.max_records_per_source
        return limit > 0 and count >= limit

    def _fetch_api(self, source: dict, run_id: str) -> tuple[list[tuple[str, dict]], Path]:
        plan = self.plans.get(source["source_id"])
        if not plan:
            raise RuntimeError("source นี้ยังไม่มี executable API plan")
        recorder = ResponseRecorder(source["source_id"], run_id, self.settings)
        try:
            driver = plan["driver"]
            if driver == "sradss":
                records = self._fetch_sradss(plan, recorder)
            elif driver == "apptech_mtr":
                records = self._fetch_apptech_mtr(plan, recorder)
            elif driver == "apptech_mru":
                records = self._fetch_apptech_mru(plan, recorder)
            elif driver == "learning_dashboard":
                records = self._fetch_learning_dashboard(plan, recorder)
            elif driver == "pmua_area_based":
                records = self._fetch_pmua(plan, recorder)
            elif driver == "housing_ckan":
                records = self._fetch_housing(plan, recorder)
            else:
                raise RuntimeError(f"ไม่รู้จัก API driver: {driver}")
            manifest = recorder.write_manifest(source["source_id"], run_id, len(records))
            return records, manifest
        finally:
            recorder.close()

    def _fetch_sradss(self, plan: dict, recorder: ResponseRecorder) -> list[tuple[str, dict]]:
        records: list[tuple[str, dict]] = []
        for request in plan["requests"]:
            params = {
                key: (self.settings.sra_year if value == "$SRA_YEAR" else value)
                for key, value in request.get("params", {}).items()
            }
            response, _ = recorder.request(
                "GET",
                request["url"],
                name=request["name"],
                params=params,
            )
            payload = response.json()
            for path, rows in nested_record_lists(payload, request["name"]):
                records.extend((path, row) for row in rows)
                if self._limit_reached(len(records)):
                    return records[: self.settings.max_records_per_source]
        return records

    def _fetch_apptech_mtr(self, plan: dict, recorder: ResponseRecorder) -> list[tuple[str, dict]]:
        records: list[tuple[str, dict]] = []
        offset = 0
        page_size = int(plan.get("page_size", 99))
        total = None
        while total is None or offset < total:
            response, _ = recorder.request(
                "GET",
                plan["url"],
                name=f"apptech_mtr_offset_{offset:05d}",
                params={"__template": "appTech.public.list", "offset": offset, "max": page_size},
            )
            payload = response.json()
            rows = payload.get("data") or []
            total = int(payload.get("totalCount") or len(rows))
            records.extend(("innovations", row) for row in rows if isinstance(row, dict))
            if not rows or self._limit_reached(len(records)):
                break
            offset += page_size
        limit = self.settings.max_records_per_source
        return records[:limit] if limit > 0 else records

    def _fetch_apptech_mru(self, plan: dict, recorder: ResponseRecorder) -> list[tuple[str, dict]]:
        records: list[tuple[str, dict]] = []
        page_size = int(plan.get("page_size", 12))
        for dataset in plan["datasets"]:
            offset = 0
            total = None
            while total is None or offset < total:
                form = dict(dataset["form"])
                form.update(
                    {
                        "startlimit": offset,
                        "endlimit": page_size,
                        "maxpage": 0,
                        "targetpagenumber": (offset // page_size) + 1,
                    }
                )
                response, _ = recorder.request(
                    "POST",
                    dataset["url"],
                    name=f"{dataset['name']}_offset_{offset:05d}",
                    data=form,
                )
                envelope = response.json().get("data") or {}
                rows = envelope.get("data") or []
                total = int(envelope.get("totaldata") or len(rows))
                records.extend((dataset["name"], row) for row in rows if isinstance(row, dict))
                if not rows or self._limit_reached(len(records)):
                    break
                offset += page_size
            if self._limit_reached(len(records)):
                break
        limit = self.settings.max_records_per_source
        return records[:limit] if limit > 0 else records

    def _fetch_pmua(self, plan: dict, recorder: ResponseRecorder) -> list[tuple[str, dict]]:
        response, _ = recorder.request("GET", plan["url"], name="area_based")
        rows = response.json().get("data") or []
        records = [("area_based", row) for row in rows if isinstance(row, dict)]
        limit = self.settings.max_records_per_source
        return records[:limit] if limit > 0 else records

    def _fetch_learning_dashboard(
        self,
        plan: dict,
        recorder: ResponseRecorder,
    ) -> list[tuple[str, dict]]:
        response, _ = recorder.request(
            "POST",
            plan["url"],
            name="learning_dashboard",
            json_body={} if plan.get("body_mode") == "json_empty" else None,
        )
        payload = response.json()
        expected_keys = set(plan.get("expected_keys", []))
        missing = sorted(expected_keys - set(payload))
        if missing:
            raise RuntimeError(f"learning dashboard response missing keys: {', '.join(missing)}")

        scope_warning = plan.get("scope_warning_th")
        records: list[tuple[str, dict]] = []
        table_names = ("provinces", "entityTypes", "categories", "geography")
        for table_name in table_names:
            table = payload.get(table_name)
            if not isinstance(table, list) or not table or not isinstance(table[0], list):
                raise RuntimeError(f"learning dashboard {table_name} is not a header-array table")
            headers = table[0]
            if len(headers) != 2:
                raise RuntimeError(f"learning dashboard {table_name} header width must be 2")
            for row_number, row in enumerate(table[1:], start=1):
                if not isinstance(row, list) or len(row) != 2:
                    raise RuntimeError(
                        f"learning dashboard {table_name} row {row_number} width must be 2"
                    )
                records.append(
                    (
                        table_name,
                        {
                            "source_row_number": row_number,
                            "label_field": headers[0],
                            "value_field": headers[1],
                            "label": row[0],
                            "value": row[1],
                            "unit": None,
                            "as_of": None,
                            "scope_warning_th": scope_warning,
                        },
                    )
                )

        impact_rows = payload.get("geographyImpact")
        if not isinstance(impact_rows, list) or not all(
            isinstance(row, dict) for row in impact_rows
        ):
            raise RuntimeError("learning dashboard geographyImpact must be an object array")
        records.extend(
            (
                "geographyImpact",
                {
                    "source_row_number": row_number,
                    **row,
                    "unit": None,
                    "as_of": None,
                    "scope_warning_th": scope_warning,
                },
            )
            for row_number, row in enumerate(impact_rows, start=1)
        )
        impact_summary = payload.get("impactSummary")
        if not isinstance(impact_summary, dict):
            raise RuntimeError("learning dashboard impactSummary must be an object")
        records.append(
            (
                "impactSummary",
                {
                    **impact_summary,
                    "unit": None,
                    "as_of": None,
                    "scope_warning_th": scope_warning,
                },
            )
        )
        limit = self.settings.max_records_per_source
        return records[:limit] if limit > 0 else records

    def _fetch_housing(self, plan: dict, recorder: ResponseRecorder) -> list[tuple[str, dict]]:
        records: list[tuple[str, dict]] = []
        for dataset in plan["datasets"]:
            response, _ = recorder.request(
                "GET",
                plan["package_show_url"],
                name=f"package_{dataset['id']}",
                params={"id": dataset["id"]},
            )
            resources = (response.json().get("result") or {}).get("resources") or []
            if dataset["value_policy"] != "values":
                continue
            for resource in resources:
                url = resource.get("url")
                if not url:
                    continue
                file_response, path = recorder.request(
                    "GET",
                    url,
                    name=f"{dataset['id']}_{resource.get('id', 'resource')}",
                )
                content_type = file_response.headers.get("content-type", "").lower()
                if "csv" not in content_type and not url.lower().endswith(".csv"):
                    continue
                text = file_response.content.decode("utf-8-sig", errors="replace")
                for row_number, row in enumerate(csv.DictReader(text.splitlines()), start=1):
                    records.append(
                        (
                            f"{dataset['id']}:{resource.get('id', path.stem)}",
                            {
                                "resource_id": resource.get("id"),
                                "resource_name": resource.get("name"),
                                "row_number": row_number,
                                "source_fields": row,
                            },
                        )
                    )
                    if self._limit_reached(len(records)):
                        return records
        return records

    def _load_snapshot(self, source: dict, run_id: str) -> tuple[list[tuple[str, dict]], Path]:
        root = self.settings.resolved_snapshot_root / source["source_id"]
        if not root.exists():
            raise FileNotFoundError(
                f"ไม่พบ snapshot ที่ {root}; รัน tools/prepare_snapshots.py หรือกำหนด SNAPSHOT_ROOT"
            )
        files = sorted(
            path
            for path in root.rglob("*")
            if path.is_file()
            and (
                path.suffix.lower() in {".csv", ".json", ".jsonl"}
                or path.name.lower().endswith((".csv.gz", ".jsonl.gz"))
            )
            and path.name != "manifest.json"
        )
        if not files:
            raise FileNotFoundError(f"ไม่พบ CSV/JSON/JSONL ใน {root}")

        records: list[tuple[str, dict]] = []
        artifacts: list[dict] = []
        for path in files:
            artifacts.append(
                {
                    "path": relative_path(path),
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                }
            )
            for dataset_key, row in self._read_snapshot_file(path):
                records.append((dataset_key, row))
                if self._limit_reached(len(records)):
                    break
            if self._limit_reached(len(records)):
                break
        run_root = self.settings.raw_root / source["source_id"] / run_id
        run_root.mkdir(parents=True, exist_ok=False)
        manifest = {
            "manifest_version": "0.1.0",
            "source_id": source["source_id"],
            "run_id": run_id,
            "mode": "snapshot_replay",
            "replayed_at": utc_now().isoformat(),
            "records_seen": len(records),
            "input_artifacts": artifacts,
        }
        manifest_path = run_root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return records, manifest_path

    def _read_snapshot_file(self, path: Path) -> Iterator[tuple[str, dict]]:
        name = path.name.lower()
        dataset = path.name
        for suffix in (".csv.gz", ".jsonl.gz", ".csv", ".jsonl", ".json"):
            if dataset.lower().endswith(suffix):
                dataset = dataset[: -len(suffix)]
                break
        if name.endswith(".csv") or name.endswith(".csv.gz"):
            opener = gzip.open if name.endswith(".gz") else open
            with opener(path, "rt", encoding="utf-8-sig", errors="replace", newline="") as handle:
                for row in csv.DictReader(handle):
                    yield dataset, dict(row)
            return
        if name.endswith(".jsonl") or name.endswith(".jsonl.gz"):
            opener = gzip.open if name.endswith(".gz") else open
            with opener(path, "rt", encoding="utf-8-sig", errors="replace") as handle:
                for line in handle:
                    if line.strip():
                        value = json.loads(line)
                        if isinstance(value, dict):
                            yield dataset, value
            return
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        for child, rows in nested_record_lists(payload, dataset):
            for row in rows:
                yield child, row

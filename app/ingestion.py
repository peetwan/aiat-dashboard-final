from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
import time
from collections import Counter
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import load_ingestion_plans, source_config
from app.connectors import ConnectorContext, load_connector
from app.models import DashboardRecord, IngestionRun
from app.privacy import payload_hash, sanitize_payload, stable_record_id
from app.settings import PROJECT_ROOT, Settings, get_settings


class PolicyViolation(RuntimeError):
    pass


class IngestionFetchError(RuntimeError):
    """Preserve the failed-run manifest while surfacing the original cause."""

    def __init__(self, message: str, manifest_path: Path):
        super().__init__(message)
        self.manifest_path = manifest_path


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
        headers: dict | None = None,
    ) -> tuple[httpx.Response, Path]:
        if self.counter:
            time.sleep(self.settings.http_delay_seconds)
        self.counter += 1
        response = self.client.request(
            method,
            url,
            params=params,
            data=data,
            json=json_body,
            headers=headers,
        )
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
        # Persist the response before raising so a 4xx/5xx boundary remains
        # auditable instead of leaving an empty raw run directory.
        response.raise_for_status()
        return response, path

    def write_manifest(
        self,
        source_id: str,
        run_id: str,
        records_seen: int,
        *,
        status: str = "complete",
        error: str | None = None,
    ) -> Path:
        manifest = {
            "manifest_version": "0.1.0",
            "source_id": source_id,
            "run_id": run_id,
            "fetched_at": utc_now().isoformat(),
            "status": status,
            "records_seen": records_seen,
            "artifacts": self.artifacts,
        }
        if error:
            manifest["error"] = error[:2000]
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
                    if strategy == "auto" and source.get("snapshot_fallback", False):
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
            failed_manifest = getattr(exc, "manifest_path", None)
            if failed_manifest:
                run.manifest_path = relative_path(failed_manifest)
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
            connector = load_connector(plan["connector"])
            if connector.driver_name != plan["driver"]:
                raise RuntimeError(
                    f"connector driver mismatch: plan={plan['driver']} "
                    f"connector={connector.driver_name}"
                )
            records = connector.fetch(
                ConnectorContext(
                    source=source,
                    plan=plan,
                    settings=self.settings,
                    recorder=recorder,
                )
            )
            manifest = recorder.write_manifest(source["source_id"], run_id, len(records))
            return records, manifest
        except Exception as exc:
            manifest = recorder.write_manifest(
                source["source_id"],
                run_id,
                0,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise IngestionFetchError(f"{type(exc).__name__}: {exc}", manifest) from exc
        finally:
            recorder.close()

    def _fetch_sradss(self, plan: dict, recorder: ResponseRecorder) -> list[tuple[str, dict]]:
        from app.connectors.sradss import SradssConnector

        return SradssConnector().fetch(self._connector_context(plan, recorder))

    def _fetch_apptech_mtr(self, plan: dict, recorder: ResponseRecorder) -> list[tuple[str, dict]]:
        from app.connectors.apptech_mtr import ApptechMtrConnector

        return ApptechMtrConnector().fetch(self._connector_context(plan, recorder))

    def _connector_context(
        self,
        plan: dict,
        recorder: ResponseRecorder,
        source: dict | None = None,
    ) -> ConnectorContext:
        """Compatibility helper for focused connector tests and local debugging."""

        return ConnectorContext(
            source=source or {},
            plan=plan,
            settings=self.settings,
            recorder=recorder,
        )

    def _fetch_apptech_mru(self, plan: dict, recorder: ResponseRecorder) -> list[tuple[str, dict]]:
        from app.connectors.apptech_mru import ApptechMruConnector

        return ApptechMruConnector().fetch(self._connector_context(plan, recorder))

    def _fetch_pmua(self, plan: dict, recorder: ResponseRecorder) -> list[tuple[str, dict]]:
        from app.connectors.pmua_area_based import PmuaAreaBasedConnector

        return PmuaAreaBasedConnector().fetch(self._connector_context(plan, recorder))

    def _fetch_learning_dashboard(
        self,
        plan: dict,
        recorder: ResponseRecorder,
    ) -> list[tuple[str, dict]]:
        from app.connectors.learning_dashboard import LearningDashboardConnector

        return LearningDashboardConnector().fetch(self._connector_context(plan, recorder))

    def _fetch_housing(
        self,
        source: dict,
        plan: dict,
        recorder: ResponseRecorder,
    ) -> list[tuple[str, dict]]:
        from app.connectors.housing_ckan import HousingCkanConnector

        return HousingCkanConnector().fetch(
            self._connector_context(plan, recorder, source=source)
        )

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
        if source["source_id"] == "f3_ruamthiao_lamphun":
            records = self._read_ruamthiao_snapshot(source, files)
        else:
            for path in files:
                for dataset_key, row in self._read_snapshot_file(path):
                    records.append((dataset_key, row))
                    if self._limit_reached(len(records)):
                        break
                if self._limit_reached(len(records)):
                    break
        if source["source_id"] == "f3_city_capital_open_data":
            self._validate_city_capital_snapshot(source, records)
        run_root = self.settings.raw_root / source["source_id"] / run_id
        if run_root.exists():
            run_root = run_root / "snapshot_fallback"
        run_root.mkdir(parents=True, exist_ok=False)
        manifest = {
            "manifest_version": "0.1.0",
            "source_id": source["source_id"],
            "run_id": run_id,
            "mode": "snapshot_replay",
            "replayed_at": utc_now().isoformat(),
            "records_seen": len(records),
            "dataset_record_counts": dict(Counter(dataset for dataset, _ in records)),
            "input_artifacts": artifacts,
        }
        manifest_path = run_root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return records, manifest_path

    @staticmethod
    def _validate_city_capital_snapshot(
        source: dict,
        records: list[tuple[str, dict]],
    ) -> None:
        cities = [row for dataset, row in records if dataset.endswith(".cities")]
        metrics = [row for dataset, row in records if dataset.endswith(".metrics")]
        observations = [row for dataset, row in records if dataset.endswith(".observations")]
        city_ids = [str(row.get("city_id")) for row in cities if row.get("city_id")]
        metric_ids = [str(row.get("metric_id")) for row in metrics if row.get("metric_id")]
        pairs = [
            (str(row.get("city_id")), str(row.get("metric_id")))
            for row in observations
            if row.get("city_id") and row.get("metric_id")
        ]
        expected_observations = len(cities) * len(metrics)
        problems: list[str] = []
        if not cities or len(city_ids) != len(cities) or len(set(city_ids)) != len(cities):
            problems.append("city IDs are missing or duplicated")
        if not metrics or len(metric_ids) != len(metrics) or len(set(metric_ids)) != len(metrics):
            problems.append("metric IDs are missing or duplicated")
        if len(pairs) != len(observations) or len(set(pairs)) != len(observations):
            problems.append("observation keys are missing or duplicated")
        if len(observations) != expected_observations:
            problems.append(
                f"observations={len(observations)} but cities*metrics={expected_observations}"
            )
        if any(city_id not in set(city_ids) or metric_id not in set(metric_ids) for city_id, metric_id in pairs):
            problems.append("observation references an unknown city or metric")
        expected_count = int(source.get("expected_record_count") or 0)
        if expected_count and len(observations) != expected_count:
            problems.append(
                f"observations={len(observations)} but catalog expected_record_count={expected_count}"
            )
        if problems:
            raise RuntimeError("City Capital snapshot incomplete: " + "; ".join(problems))

    @staticmethod
    def _read_ruamthiao_snapshot(
        source: dict,
        files: list[Path],
    ) -> list[tuple[str, dict]]:
        """Normalize every public Visit Lamphun content item into a queryable grain.

        The five page snapshots contain 54 primary records and 103 supporting
        records nested at different depths.  The generic JSON walker only sees
        the nearest lists, so it cannot prove that all visible venues and contact
        resources reached the database.
        """

        documents: dict[str, dict] = {}
        problems: list[str] = []
        required_pages = {"homepage", "recommend", "travel", "komepage", "contact"}
        for path in files:
            if path.suffix.lower() != ".json":
                problems.append(f"unsupported snapshot file: {path.name}")
                continue
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(payload, dict):
                problems.append(f"{path.name} is not a JSON object")
                continue
            page_id = str(payload.get("page_id") or path.stem)
            if page_id in documents:
                problems.append(f"duplicate page_id: {page_id}")
            documents[page_id] = payload

        missing_pages = sorted(required_pages - set(documents))
        extra_pages = sorted(set(documents) - required_pages)
        if missing_pages:
            problems.append("missing pages: " + ", ".join(missing_pages))
        if extra_pages:
            problems.append("unexpected pages: " + ", ".join(extra_pages))

        bundle_hashes = {
            str(document.get("bundle_sha256"))
            for document in documents.values()
            if document.get("bundle_sha256")
        }
        if len(bundle_hashes) != 1:
            problems.append(f"bundle_sha256 values={len(bundle_hashes)}; expected exactly one")
        for page_id, document in documents.items():
            warnings = document.get("warnings")
            if not isinstance(warnings, list):
                problems.append(f"{page_id}.warnings is not a list")
            elif warnings:
                problems.append(f"{page_id}.warnings has {len(warnings)} item(s)")
            if not isinstance(document.get("data"), dict):
                problems.append(f"{page_id}.data is not an object")
        if problems:
            raise RuntimeError("Visit Lamphun snapshot incomplete: " + "; ".join(problems))

        records: list[tuple[str, dict]] = []

        def add(dataset: str, row: Any, page_id: str, **context: Any) -> None:
            if not isinstance(row, dict):
                problems.append(f"{page_id}.{dataset} contains a non-object item")
                return
            document = documents[page_id]
            normalized = dict(row)
            normalized.update(context)
            normalized["source_page_id"] = page_id
            normalized["source_url"] = document.get("source_url")
            normalized["source_scraped_at"] = document.get("scraped_at")
            normalized["source_bundle_sha256"] = document.get("bundle_sha256")
            records.append((dataset, normalized))

        homepage = documents["homepage"]["data"]
        stations = homepage.get("map", {}).get("stations", [])
        if not isinstance(stations, list):
            problems.append("homepage.data.map.stations is not a list")
            stations = []
        for station in stations:
            if not isinstance(station, dict):
                problems.append("homepage station is not an object")
                continue
            station_row = dict(station)
            venues = station_row.pop("venues", [])
            add("tourism_stations", station_row, "homepage")
            if not isinstance(venues, list):
                problems.append("homepage station.venues is not a list")
                continue
            for venue in venues:
                add(
                    "tourism_venues",
                    venue,
                    "homepage",
                    station_id=station.get("station_id"),
                    station_name=station.get("name"),
                )

        categories = documents["recommend"]["data"].get("categories", [])
        if not isinstance(categories, list):
            problems.append("recommend.data.categories is not a list")
            categories = []
        for category in categories:
            if not isinstance(category, dict):
                problems.append("recommend category is not an object")
                continue
            items = category.get("items", [])
            if not isinstance(items, list):
                problems.append("recommend category.items is not a list")
                continue
            for item in items:
                add(
                    "recommendations",
                    item,
                    "recommend",
                    category_id=category.get("category_id"),
                    category_label=category.get("label"),
                )

        travel = documents["travel"]["data"]
        train = travel.get("train", {})
        tram = travel.get("tourism_tram", {})
        for item in train.get("services", []) if isinstance(train, dict) else []:
            add("transport_services", item, "travel", transport_mode="train")
        for item in tram.get("services", []) if isinstance(tram, dict) else []:
            add(
                "transport_services",
                item,
                "travel",
                transport_mode="tourism_tram",
                operating_days=tram.get("operating_days"),
                closed_days=tram.get("closed_days"),
            )
        other_transport = travel.get("other_transport", [])
        if not isinstance(other_transport, list):
            problems.append("travel.data.other_transport is not a list")
            other_transport = []
        for item in other_transport:
            add("transport_services", item, "travel", transport_mode="other")

        lantern_groups = documents["komepage"]["data"].get("lantern_production_groups", [])
        if not isinstance(lantern_groups, list):
            problems.append("komepage.data.lantern_production_groups is not a list")
            lantern_groups = []
        for item in lantern_groups:
            add("lantern_groups", item, "komepage")

        contact = documents["contact"]["data"]
        for field, dataset in (
            ("emergency_numbers", "emergency_numbers"),
            ("service_contacts", "service_contacts"),
            ("resources", "resources"),
        ):
            rows = contact.get(field, [])
            if not isinstance(rows, list):
                problems.append(f"contact.data.{field} is not a list")
                continue
            for item in rows:
                add(dataset, item, "contact")

        counts = Counter(dataset for dataset, _ in records)
        expected_counts = {
            "tourism_stations": 12,
            "tourism_venues": 97,
            "recommendations": 13,
            "transport_services": 13,
            "lantern_groups": 10,
            "emergency_numbers": 6,
            "service_contacts": 3,
            "resources": 3,
        }
        for dataset, expected in expected_counts.items():
            observed = counts.get(dataset, 0)
            if observed != expected:
                problems.append(f"{dataset}={observed}; expected {expected}")
        primary_count = sum(
            counts.get(dataset, 0)
            for dataset in (
                "tourism_stations",
                "recommendations",
                "transport_services",
                "lantern_groups",
                "emergency_numbers",
            )
        )
        catalog_expected = int(source.get("expected_record_count") or 0)
        if catalog_expected and primary_count != catalog_expected:
            problems.append(
                f"primary records={primary_count}; catalog expected_record_count={catalog_expected}"
            )
        if len(records) != sum(expected_counts.values()):
            problems.append(
                f"all content records={len(records)}; expected {sum(expected_counts.values())}"
            )

        id_fields = {
            "tourism_stations": "station_id",
            "tourism_venues": "venue_id",
            "recommendations": "item_id",
            "transport_services": "service_id",
            "lantern_groups": "group_id",
            "service_contacts": "contact_id",
            "resources": "resource_id",
        }
        for dataset, id_field in id_fields.items():
            identifiers = [row.get(id_field) for name, row in records if name == dataset]
            if any(identifier in (None, "") for identifier in identifiers):
                problems.append(f"{dataset}.{id_field} is missing")
            if len(set(map(str, identifiers))) != len(identifiers):
                problems.append(f"{dataset}.{id_field} is duplicated")
        if problems:
            raise RuntimeError("Visit Lamphun snapshot incomplete: " + "; ".join(problems))
        return records

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

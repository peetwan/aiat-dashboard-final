from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.connectors.base import ConnectorContext, DatasetRecord

SUKHOTHAI_BOUNDS = {
    "swLat": 16.8,
    "swLng": 99.5,
    "neLat": 17.4,
    "neLng": 100.2,
}


def _extract_collection(payload: Any) -> tuple[list[Any], dict]:
    if isinstance(payload, list):
        return payload, {}
    if not isinstance(payload, dict):
        return [], {}
    for key in ("data", "items", "results", "records"):
        if isinstance(payload.get(key), list):
            meta = {k: v for k, v in payload.items() if k != key}
            return payload[key], meta
    return [], payload


def _flatten_record(record: dict, source_url: str, fetched_at: str) -> dict:
    result = dict(record)
    result["_source_url"] = source_url
    result["_fetched_at"] = fetched_at
    return result


class SpuSukhothaiCareConnector:
    driver_name = "spu_sukhothai_care"

    def fetch(self, context: ConnectorContext) -> list[DatasetRecord]:
        records: list[DatasetRecord] = []
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        for dataset in context.plan["datasets"]:
            name = dataset["name"]
            url_template = dataset["url"]
            paginate = dataset.get("paginate", False)
            page_size = dataset.get("page_size", 100)
            max_pages = dataset.get("max_pages", 50)

            if name == "incident_map":
                # Map endpoint needs bounds params
                sep = "&" if "?" in url_template else "?"
                params = "&".join(f"{k}={v}" for k, v in SUKHOTHAI_BOUNDS.items())
                url = f"{url_template}{sep}{params}"
                response, _ = context.recorder.request("GET", url, name=name)
                payload = response.json()
                items, _ = _extract_collection(payload)
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            records.append((f"{name}.row", _flatten_record(item, url, fetched_at)))
            elif paginate:
                page = 1
                while page <= max_pages:
                    sep = "&" if "?" in url_template else "?"
                    url = f"{url_template}{sep}page={page}&limit={page_size}"
                    response, _ = context.recorder.request("GET", url, name=f"{name}_p{page}")
                    payload = response.json()
                    items, meta = _extract_collection(payload)
                    for item in items:
                        if isinstance(item, dict):
                            records.append((f"{name}.row", _flatten_record(item, url, fetched_at)))
                    total_pages = meta.get("totalPages") if isinstance(meta, dict) else None
                    if not items or (isinstance(total_pages, int) and page >= total_pages):
                        break
                    page += 1
                    if context.limit_reached(len(records)):
                        return context.apply_limit(records)
            else:
                response, _ = context.recorder.request("GET", url_template, name=name)
                payload = response.json()
                items, _ = _extract_collection(payload)
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            records.append((f"{name}.row", _flatten_record(item, url_template, fetched_at)))
                elif isinstance(items, dict):
                    records.append((f"{name}.row", _flatten_record(items, url_template, fetched_at)))

            if context.limit_reached(len(records)):
                return context.apply_limit(records)

        return records

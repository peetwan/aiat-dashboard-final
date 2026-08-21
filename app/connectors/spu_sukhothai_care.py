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
        raise RuntimeError("Sukhothai Care response is not an object or array")
    for key in ("data", "items", "results", "records"):
        if isinstance(payload.get(key), list):
            meta = {k: v for k, v in payload.items() if k != key}
            return payload[key], meta
    return [payload], {}


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
                expected_total_pages: int | None = None
                completed = False
                while page <= max_pages:
                    sep = "&" if "?" in url_template else "?"
                    url = f"{url_template}{sep}page={page}&limit={page_size}"
                    response, _ = context.recorder.request("GET", url, name=f"{name}_p{page}")
                    payload = response.json()
                    items, meta = _extract_collection(payload)
                    for item in items:
                        if not isinstance(item, dict):
                            raise RuntimeError(
                                f"Sukhothai Care {name} page {page} returned a non-object row"
                            )
                        records.append((f"{name}.row", _flatten_record(item, url, fetched_at)))
                    raw_total_pages = meta.get("totalPages") if isinstance(meta, dict) else None
                    if raw_total_pages is not None:
                        try:
                            total_pages = int(raw_total_pages)
                        except (TypeError, ValueError) as exc:
                            raise RuntimeError(
                                f"Sukhothai Care {name} totalPages is invalid"
                            ) from exc
                        if total_pages < 0:
                            raise RuntimeError(
                                f"Sukhothai Care {name} totalPages is invalid"
                            )
                        if expected_total_pages is None:
                            expected_total_pages = total_pages
                            if total_pages > max_pages:
                                raise RuntimeError(
                                    f"Sukhothai Care {name} needs {total_pages} pages but "
                                    f"max_pages={max_pages}; partial commits are forbidden"
                                )
                        elif total_pages != expected_total_pages:
                            raise RuntimeError(
                                f"Sukhothai Care {name} totalPages changed during pagination: "
                                f"{expected_total_pages} -> {total_pages}"
                            )
                    if not items:
                        if expected_total_pages is not None and page < expected_total_pages:
                            raise RuntimeError(
                                f"Sukhothai Care {name} pagination ended at page {page} "
                                f"before totalPages={expected_total_pages}"
                            )
                        completed = True
                        break
                    if expected_total_pages is not None and page >= expected_total_pages:
                        completed = True
                        break
                    page += 1
                    if (
                        context.settings.max_records_per_source > 0
                        and len(records) > context.settings.max_records_per_source
                    ):
                        raise RuntimeError(
                            "Sukhothai Care max_records_per_source would truncate a complete "
                            "snapshot; partial commits are forbidden"
                        )
                if not completed:
                    raise RuntimeError(
                        f"Sukhothai Care {name} reached max_pages={max_pages} before completion"
                    )
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

            if (
                context.settings.max_records_per_source > 0
                and len(records) > context.settings.max_records_per_source
            ):
                raise RuntimeError(
                    "Sukhothai Care max_records_per_source would truncate a complete snapshot; "
                    "partial commits are forbidden"
                )

        return records

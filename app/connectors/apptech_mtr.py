from __future__ import annotations

from app.connectors.base import ConnectorContext, DatasetRecord


class ApptechMtrConnector:
    driver_name = "apptech_mtr"

    def fetch(self, context: ConnectorContext) -> list[DatasetRecord]:
        records: list[DatasetRecord] = []
        seen_ids: set[str] = set()
        offset = 0
        page_size = int(context.plan.get("page_size", 99))
        total: int | None = None
        while total is None or offset < total:
            response, _ = context.recorder.request(
                "GET",
                context.plan["url"],
                name=f"apptech_mtr_offset_{offset:05d}",
                params={"__template": "appTech.public.list", "offset": offset, "max": page_size},
            )
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("AppTech MTR response is not an object")
            rows = payload.get("data")
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise RuntimeError("AppTech MTR data is not an object list")
            try:
                reported_total = int(payload["totalCount"])
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError("AppTech MTR totalCount is missing or invalid") from exc
            if total is None:
                total = reported_total
                limit = context.settings.max_records_per_source
                if limit > 0 and total > limit:
                    raise RuntimeError(
                        "AppTech MTR max_records_per_source is below totalCount; "
                        "partial database commits are forbidden"
                    )
            elif reported_total != total:
                raise RuntimeError(
                    f"AppTech MTR totalCount changed during pagination: {total} -> {reported_total}"
                )
            if not rows and offset < total:
                raise RuntimeError(
                    f"AppTech MTR incomplete pagination at offset {offset}: totalCount={total}"
                )
            for row in rows:
                record_id = row.get("id")
                if record_id in (None, ""):
                    raise RuntimeError("AppTech MTR row is missing id")
                record_id_text = str(record_id)
                if record_id_text in seen_ids:
                    raise RuntimeError(f"AppTech MTR duplicate id={record_id_text}")
                seen_ids.add(record_id_text)
                records.append(("innovations", row))
            if not rows:
                break
            offset += page_size
        if total is None or len(records) != total or len(seen_ids) != total:
            raise RuntimeError(
                f"AppTech MTR incomplete: unique={len(seen_ids)}, "
                f"rows={len(records)}, reported_total={total}"
            )
        return records

from __future__ import annotations

from app.connectors.base import ConnectorContext, DatasetRecord, nested_record_lists


class SradssConnector:
    driver_name = "sradss"

    def fetch(self, context: ConnectorContext) -> list[DatasetRecord]:
        records: list[DatasetRecord] = []
        for request in context.plan["requests"]:
            params = {
                key: (context.settings.sra_year if value == "$SRA_YEAR" else value)
                for key, value in request.get("params", {}).items()
            }
            response, _ = context.recorder.request(
                "GET",
                request["url"],
                name=request["name"],
                params=params,
            )
            payload = response.json()
            for path, rows in nested_record_lists(payload, request["name"]):
                records.extend((path, row) for row in rows)
                if context.limit_reached(len(records)):
                    return context.apply_limit(records)
        return records

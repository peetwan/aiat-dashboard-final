"""Copy this file to app/connectors/<source_id>.py and replace the example names."""

from __future__ import annotations

from app.connectors.base import ConnectorContext, DatasetRecord


class ExampleConnector:
    driver_name = "replace_with_driver_name"

    def fetch(self, context: ConnectorContext) -> list[DatasetRecord]:
        response, _ = context.recorder.request(
            "GET",
            context.plan["url"],
            name="first_page",
        )
        payload = response.json()
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise RuntimeError("example connector response must contain an object array at data")

        # Add source-specific count, uniqueness, pagination, and schema checks here.
        # Never write to the database or public_artifacts from a connector.
        records: list[DatasetRecord] = [("replace_dataset_key", row) for row in rows]
        return context.apply_limit(records)

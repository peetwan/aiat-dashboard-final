from __future__ import annotations

from app.connectors.base import ConnectorContext, DatasetRecord


class PmuaAreaBasedConnector:
    driver_name = "pmua_area_based"

    def fetch(self, context: ConnectorContext) -> list[DatasetRecord]:
        response, _ = context.recorder.request(
            "GET",
            context.plan["url"],
            name="area_based",
        )
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("PMUA Area Based response is not an object")
        rows = payload.get("data")
        stats = payload.get("stats")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise RuntimeError("PMUA Area Based data is not an object list")
        if not isinstance(stats, dict):
            raise RuntimeError("PMUA Area Based response has no stats object")

        ids = [str(row.get("id")) for row in rows if row.get("id") not in (None, "")]
        if len(ids) != len(rows) or len(set(ids)) != len(rows):
            raise RuntimeError(
                f"PMUA Area Based IDs incomplete or duplicated: rows={len(rows)}, "
                f"non_null={len(ids)}, unique={len(set(ids))}"
            )
        try:
            total_records = int(stats["totalRecords"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("PMUA Area Based stats.totalRecords is missing or invalid") from exc
        if total_records != len(rows):
            raise RuntimeError(
                f"PMUA Area Based incomplete: rows={len(rows)}, totalRecords={total_records}"
            )

        dimension_fields = {
            "byRegion": "region",
            "byProvince": "province",
            "byDistrict": "district",
            "bySubDistrict": "subDistrict",
            "byBusinessType": None,
            "byResearchUnit": "researchUnit",
            "byFiscalYear": "fiscalYear",
        }
        aggregate_records: list[DatasetRecord] = [
            (
                "aggregate_summary",
                {
                    "id": "summary:totalRecords",
                    "dimension": "summary",
                    "label": "totalRecords",
                    "value": total_records,
                    "unit": "participant_or_business_records",
                },
            )
        ]
        for dimension, source_field in dimension_fields.items():
            values = stats.get(dimension)
            if not isinstance(values, dict):
                raise RuntimeError(f"PMUA Area Based stats.{dimension} is not an object")
            parsed_values: dict[str, int] = {}
            for label, value in values.items():
                try:
                    parsed_values[str(label)] = int(value)
                except (TypeError, ValueError) as exc:
                    raise RuntimeError(
                        f"PMUA Area Based stats.{dimension}[{label!r}] is not an integer"
                    ) from exc
            expected_sum = (
                len(rows)
                if source_field is None
                else sum(row.get(source_field) not in (None, "") for row in rows)
            )
            if sum(parsed_values.values()) != expected_sum:
                raise RuntimeError(
                    f"PMUA Area Based stats.{dimension} does not reconcile: "
                    f"sum={sum(parsed_values.values())}, expected={expected_sum}"
                )
            dataset_key = f"aggregate_{dimension}"
            aggregate_records.extend(
                (
                    dataset_key,
                    {
                        "id": f"{dimension}:{label}",
                        "dimension": dimension,
                        "label": label,
                        "value": value,
                        "unit": "participant_or_business_records",
                    },
                )
                for label, value in parsed_values.items()
            )

        records: list[DatasetRecord] = [("area_based", row) for row in rows]
        records.extend(aggregate_records)
        return context.apply_limit(records)

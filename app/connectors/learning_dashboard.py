from __future__ import annotations

from app.connectors.base import ConnectorContext, DatasetRecord


class LearningDashboardConnector:
    driver_name = "learning_dashboard"

    def fetch(self, context: ConnectorContext) -> list[DatasetRecord]:
        response, _ = context.recorder.request(
            "POST",
            context.plan["url"],
            name="learning_dashboard",
            json_body={} if context.plan.get("body_mode") == "json_empty" else None,
        )
        payload = response.json()
        expected_keys = set(context.plan.get("expected_keys", []))
        missing = sorted(expected_keys - set(payload))
        if missing:
            raise RuntimeError(f"learning dashboard response missing keys: {', '.join(missing)}")

        scope_warning = context.plan.get("scope_warning_th")
        records: list[DatasetRecord] = []
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
        for object_name in ("impactSummary", "excludedResourceExpense"):
            if object_name not in expected_keys:
                continue
            value = payload.get(object_name)
            if not isinstance(value, dict):
                raise RuntimeError(f"learning dashboard {object_name} must be an object")
            records.append(
                (
                    object_name,
                    {
                        **value,
                        "unit": None,
                        "as_of": None,
                        "scope_warning_th": scope_warning,
                    },
                )
            )
        return context.apply_limit(records)

from __future__ import annotations

import csv

from app.connectors.base import ConnectorContext, DatasetRecord


class HousingCkanConnector:
    driver_name = "housing_ckan"

    def fetch(self, context: ConnectorContext) -> list[DatasetRecord]:
        records: list[DatasetRecord] = []
        plan = context.plan
        dataset_ids = [str(dataset.get("id") or "") for dataset in plan["datasets"]]
        resource_ids: list[str] = []
        value_resource_ids: list[str] = []
        problems: list[str] = []
        if not all(dataset_ids) or len(set(dataset_ids)) != len(dataset_ids):
            problems.append("dataset IDs are missing or duplicated")
        for dataset in plan["datasets"]:
            response, _ = context.recorder.request(
                "GET",
                plan["package_show_url"],
                name=f"package_{dataset['id']}",
                params={"id": dataset["id"]},
            )
            payload = response.json()
            result = payload.get("result") if isinstance(payload, dict) else None
            if not isinstance(payload, dict) or payload.get("success") is not True:
                problems.append(f"{dataset['id']} package_show success is not true")
                continue
            if not isinstance(result, dict):
                problems.append(f"{dataset['id']} package_show result is not an object")
                continue
            if result.get("name") and result.get("name") != dataset["id"]:
                problems.append(
                    f"{dataset['id']} package_show returned name={result.get('name')}"
                )
            resources = result.get("resources")
            if not isinstance(resources, list):
                problems.append(f"{dataset['id']} resources is not a list")
                continue
            for resource in resources:
                if not isinstance(resource, dict) or not resource.get("id"):
                    problems.append(f"{dataset['id']} resource ID is missing")
                    continue
                resource_ids.append(str(resource["id"]))
            if dataset["value_policy"] != "values":
                continue
            for resource in resources:
                if not isinstance(resource, dict) or not resource.get("id"):
                    continue
                value_resource_ids.append(str(resource["id"]))
                url = resource.get("url")
                if not url:
                    problems.append(f"{dataset['id']}:{resource['id']} URL is missing")
                    continue
                file_response, path = context.recorder.request(
                    "GET",
                    url,
                    name=f"{dataset['id']}_{resource.get('id', 'resource')}",
                )
                content_type = file_response.headers.get("content-type", "").lower()
                if "csv" not in content_type and not url.lower().endswith(".csv"):
                    problems.append(
                        f"{dataset['id']}:{resource['id']} is not a CSV resource"
                    )
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
        expected_dataset_count = int(plan.get("expected_dataset_count") or 0)
        expected_resource_count = int(plan.get("expected_resource_count") or 0)
        expected_value_resource_count = int(plan.get("expected_value_resource_count") or 0)
        expected_value_record_count = int(
            plan.get("expected_value_record_count")
            or context.source.get("expected_record_count")
            or 0
        )
        if expected_dataset_count and len(dataset_ids) != expected_dataset_count:
            problems.append(f"datasets={len(dataset_ids)}; expected {expected_dataset_count}")
        if len(set(resource_ids)) != len(resource_ids):
            problems.append("resource IDs are duplicated across packages")
        if expected_resource_count and len(resource_ids) != expected_resource_count:
            problems.append(f"resources={len(resource_ids)}; expected {expected_resource_count}")
        if expected_value_resource_count and len(value_resource_ids) != expected_value_resource_count:
            problems.append(
                f"value resources={len(value_resource_ids)}; expected {expected_value_resource_count}"
            )
        if expected_value_record_count and len(records) != expected_value_record_count:
            problems.append(f"value records={len(records)}; expected {expected_value_record_count}")
        if context.settings.max_records_per_source > 0 and (
            len(records) > context.settings.max_records_per_source
        ):
            problems.append(
                "max_records_per_source is below the complete housing value row count; "
                "partial database commits are forbidden"
            )
        if problems:
            raise RuntimeError("Thai Housing CKAN incomplete: " + "; ".join(problems))
        return records

from __future__ import annotations

from app.connectors.base import ConnectorContext, DatasetRecord


def _resolve_body_template(value, replacements: dict[str, int]):
    if isinstance(value, dict):
        return {
            str(key): _resolve_body_template(item, replacements)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_resolve_body_template(item, replacements) for item in value]
    if isinstance(value, str) and value.startswith("$"):
        if value not in replacements:
            raise RuntimeError(f"AppTech MRU request body has unknown placeholder {value}")
        return replacements[value]
    return value


class ApptechMruConnector:
    driver_name = "apptech_mru"

    def fetch(self, context: ConnectorContext) -> list[DatasetRecord]:
        records: list[DatasetRecord] = []
        page_size = int(context.plan.get("page_size", 12))
        id_fields = {
            "innovation": "innovationid",
            "requirement": "requirementid",
            "news": "newsid",
        }
        for dataset in context.plan["datasets"]:
            offset = 0
            total = None
            dataset_records: list[dict] = []
            seen_ids: set[str] = set()
            dataset_name = dataset["name"]
            id_field = dataset.get("id_field") or id_fields.get(dataset_name)
            if not id_field:
                raise RuntimeError(f"AppTech MRU dataset {dataset_name} has no configured id field")
            body_template = dataset.get("json_body")
            if not isinstance(body_template, dict) or not body_template:
                raise RuntimeError(f"AppTech MRU dataset {dataset_name} has no JSON body contract")
            while total is None or offset < total:
                json_body = _resolve_body_template(
                    body_template,
                    {
                        "$OFFSET": offset,
                        "$PAGE_SIZE": page_size,
                        "$PAGE_NUMBER": (offset // page_size) + 1,
                    },
                )
                response, _ = context.recorder.request(
                    "POST",
                    dataset["url"],
                    name=f"{dataset_name}_offset_{offset:05d}",
                    json_body=json_body,
                    headers={
                        "Origin": "https://38rat.nstru.ac.th",
                        "Referer": "https://38rat.nstru.ac.th/",
                    },
                )
                payload = response.json()
                envelope = payload.get("data") if isinstance(payload, dict) else None
                if not isinstance(envelope, dict):
                    raise RuntimeError(f"AppTech MRU {dataset_name} response has no data envelope")
                if "totaldata" not in envelope:
                    raise RuntimeError(f"AppTech MRU {dataset_name} response has no totaldata")
                try:
                    reported_total = int(envelope["totaldata"])
                except (TypeError, ValueError) as exc:
                    raise RuntimeError(
                        f"AppTech MRU {dataset_name} totaldata is not an integer"
                    ) from exc
                if total is None:
                    total = reported_total
                elif reported_total != total:
                    raise RuntimeError(
                        f"AppTech MRU {dataset_name} totaldata changed during pagination: "
                        f"{total} -> {reported_total}"
                    )

                rows = envelope.get("data")
                if not isinstance(rows, list):
                    raise RuntimeError(f"AppTech MRU {dataset_name} data is not a list")
                for row in rows:
                    if not isinstance(row, dict):
                        raise RuntimeError(f"AppTech MRU {dataset_name} returned a non-object row")
                    record_id = row.get(id_field)
                    if record_id in (None, ""):
                        raise RuntimeError(
                            f"AppTech MRU {dataset_name} row is missing {id_field}"
                        )
                    record_id_text = str(record_id)
                    if record_id_text in seen_ids:
                        raise RuntimeError(
                            f"AppTech MRU {dataset_name} duplicate {id_field}={record_id_text}"
                        )
                    seen_ids.add(record_id_text)
                    dataset_records.append(row)

                if not rows or context.limit_reached(len(records) + len(dataset_records)):
                    break
                offset += page_size

            if total is None or len(dataset_records) != total or len(seen_ids) != total:
                raise RuntimeError(
                    f"AppTech MRU {dataset_name} incomplete: "
                    f"unique={len(seen_ids)}, rows={len(dataset_records)}, reported_total={total}"
                )
            records.extend((dataset_name, row) for row in dataset_records)
            if context.limit_reached(len(records)):
                break
        return context.apply_limit(records)

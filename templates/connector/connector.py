"""Candidate-only connector scaffold for __SOURCE_ID__."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.connectors.base import ConnectorContext, DatasetRecord


DATASET_KEY = __DATASET_KEY_PY__
IDENTITY_OPTIONS = __IDENTITY_OPTIONS_PY__


def _path_value(payload: dict, path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _record_identity(payload: dict) -> tuple[str, ...]:
    for fields in IDENTITY_OPTIONS:
        if fields == ("$payload_hash",):
            canonical = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            return (hashlib.sha256(canonical).hexdigest(),)
        values = tuple(_path_value(payload, field) for field in fields)
        if all(value is not None and str(value).strip() for value in values):
            return tuple(str(value) for value in values)
    raise RuntimeError(f"{DATASET_KEY} record has no complete identity option")


class __CLASS_NAME__:
    driver_name = __DRIVER_NAME_PY__

    def fetch(self, context: ConnectorContext) -> list[DatasetRecord]:
        response, _ = context.recorder.request(
            "GET",
            context.plan["url"],
            name="first_page",
        )
        payload = response.json()
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise RuntimeError("connector response must contain an object array at data")

        # Add source-specific total-count, pagination, and schema-drift checks here.
        identities = [_record_identity(row) for row in rows]
        if len(identities) != len(set(identities)):
            raise RuntimeError(f"{DATASET_KEY} contains duplicate record identities")

        records: list[DatasetRecord] = [(DATASET_KEY, row) for row in rows]
        # Keep limit handling last so completeness checks inspect the full response first.
        return context.apply_limit(records)

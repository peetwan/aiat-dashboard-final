from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.settings import Settings


DatasetRecord = tuple[str, dict]


class ResponseRecorderProtocol(Protocol):
    """Small boundary connectors may use to make auditable HTTP requests."""

    def request(
        self,
        method: str,
        url: str,
        *,
        name: str,
        params: dict | None = None,
        data: dict | None = None,
        json_body: dict | None = None,
        headers: dict | None = None,
    ) -> tuple[httpx.Response, Path]: ...


@dataclass(frozen=True)
class ConnectorContext:
    source: dict
    plan: dict
    settings: Settings
    recorder: ResponseRecorderProtocol

    def limit_reached(self, count: int) -> bool:
        limit = self.settings.max_records_per_source
        return limit > 0 and count >= limit

    def apply_limit(self, records: list[DatasetRecord]) -> list[DatasetRecord]:
        limit = self.settings.max_records_per_source
        return records[:limit] if limit > 0 else records


class ConnectorProtocol(Protocol):
    """Contract implemented by every importable connector."""

    driver_name: str

    def fetch(self, context: ConnectorContext) -> list[DatasetRecord]: ...


def nested_record_lists(
    value: Any,
    path: str = "root",
) -> Iterator[tuple[str, list[dict]]]:
    """Yield the nearest object-list grains from a nested JSON response."""

    if isinstance(value, list):
        rows = [item for item in value if isinstance(item, dict)]
        if rows:
            yield path, rows
        return
    if not isinstance(value, dict):
        return
    found = False
    for key, item in value.items():
        if isinstance(item, (dict, list)):
            child_path = f"{path}.{key}"
            for result in nested_record_lists(item, child_path):
                found = True
                yield result
    if not found:
        yield path, [value]

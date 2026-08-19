from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.connectors.base import ConnectorContext, DatasetRecord

BASE_URL = "https://nsn-flood.nsru.ac.th/"


def _parse_station_links(soup: BeautifulSoup, page_url: str) -> list[dict]:
    """Find station links from water-level page."""
    stations: list[dict] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full_url = urljoin(page_url, href)
        path = urlparse(full_url).path

        station_code = None
        if "/water-station/" in path:
            station_code = path.split("/water-station/")[-1].rstrip("/")
        elif "/telemetry/dpm/station/" in path:
            station_code = "dpm_" + path.split("/telemetry/dpm/station/")[-1].rstrip("/")

        if station_code and station_code not in seen:
            seen.add(station_code)
            name = a.get_text(strip=True)
            # Extract just the station code and name from the long text
            display_name = name if name and len(name) < 80 else station_code
            stations.append({
                "station_code": station_code,
                "station_url": full_url,
                "station_name": display_name,
                "link_text": (name or "")[:200],
            })
    return stations


class SpuNsnFloodConnector:
    driver_name = "spu_nsn_flood"

    def fetch(self, context: ConnectorContext) -> list[DatasetRecord]:
        records: list[DatasetRecord] = []
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        for dataset in context.plan["datasets"]:
            name = dataset["name"]
            url = dataset["url"]
            response, _ = context.recorder.request("GET", url, name=name)
            soup = BeautifulSoup(response.text, "html.parser")

            stations = _parse_station_links(soup, url)
            for station in stations:
                station["_fetched_at"] = fetched_at
                records.append(("stations.row", station))

            if context.limit_reached(len(records)):
                return context.apply_limit(records)

        return records

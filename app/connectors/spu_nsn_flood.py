from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.connectors.base import ConnectorContext, DatasetRecord

BASE_URL = "https://nsn-flood.nsru.ac.th/"


def _parse_station_list(soup: BeautifulSoup, source_url: str) -> list[dict]:
    stations: list[dict] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full_url = urljoin(source_url, href)
        path = urlparse(full_url).path
        parts = path.rstrip("/").split("/")
        if len(parts) >= 2 and parts[-2] == "station":
            station_code = parts[-1]
            if station_code and station_code not in seen:
                seen.add(station_code)
                stations.append({
                    "station_code": station_code,
                    "station_url": full_url,
                    "station_name": a.get_text(strip=True) or station_code,
                })
    return stations


def _parse_station_tables(soup: BeautifulSoup) -> list[dict]:
    tables: list[dict] = []
    for table in soup.find_all("table"):
        headers: list[str] = []
        rows: list[dict] = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
            if tr.find_all("th"):
                headers = cells
            elif cells and headers:
                row = dict(zip(headers, cells))
                rows.append(row)
            elif cells and not headers:
                rows.append({f"col_{i}": v for i, v in enumerate(cells)})
        if rows:
            tables.append({"headers": headers, "rows": rows})
    return tables


def _parse_forecast_charts(soup: BeautifulSoup) -> list[dict]:
    charts: list[dict] = []
    for script in soup.find_all("script"):
        text = script.string or ""
        if "forecast" in text.lower() or "chart" in text.lower():
            charts.append({"script_snippet": text[:500]})
    return charts


class SpuNsnFloodConnector:
    driver_name = "spu_nsn_flood"

    def fetch(self, context: ConnectorContext) -> list[DatasetRecord]:
        records: list[DatasetRecord] = []
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        for dataset in context.plan["datasets"]:
            name = dataset["name"]
            url = dataset["url"]

            if name == "forecast_page":
                response, _ = context.recorder.request("GET", url, name=name)
                soup = BeautifulSoup(response.text, "html.parser")

                stations = _parse_station_list(soup, url)
                for station in stations:
                    station["_fetched_at"] = fetched_at
                    records.append(("stations.row", station))

                chart_snippets = _parse_forecast_charts(soup)
                for i, snippet in enumerate(chart_snippets):
                    snippet["_fetched_at"] = fetched_at
                    records.append((f"forecast_chart.{i}", snippet))

                if context.limit_reached(len(records)):
                    return context.apply_limit(records)

                for station in stations:
                    station_url = station["station_url"]
                    try:
                        resp, _ = context.recorder.request(
                            "GET", station_url,
                            name=f"station_{station['station_code']}",
                        )
                        station_soup = BeautifulSoup(resp.text, "html.parser")
                        tables = _parse_station_tables(station_soup)
                        for ti, table in enumerate(tables):
                            for ri, row in enumerate(table["rows"]):
                                row["_station_code"] = station["station_code"]
                                row["_station_url"] = station_url
                                row["_fetched_at"] = fetched_at
                                records.append((f"station_tables.{ti}", row))
                    except Exception:
                        pass

                    if context.limit_reached(len(records)):
                        return context.apply_limit(records)

        return records

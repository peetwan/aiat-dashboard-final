#!/usr/bin/env python3
"""Scrape public PMUA AppTech product detail fields for F4 evidence enrichment.

This scraper targets public detail pages such as:
https://pmua-apptech.com/product/show/3788

It writes a run folder compatible with ``tools/evidence_push.py``. Use
``--push`` only after reviewing the local output.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.evidence_store import config_from_env, make_client  # noqa: E402


PRODUCT_LIST_KEY = "raw/f2/f2_target_household/20260818T163603Z/products_redacted.jsonl.gz"
SOURCE_ID = "f4/pmua_product_details"
BASE_URL = "https://pmua-apptech.com/product/show/{product_id}"
USER_AGENT = "AIAT dashboard evidence scraper/1.0"


@dataclass(frozen=True)
class FetchResult:
    url: str
    status_code: int
    html: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def parse_number(value: str) -> int | float | str | None:
    text = clean_text(value)
    if not text:
        return None
    normalized = text.replace(",", "")
    try:
        numeric = float(normalized)
    except ValueError:
        return text
    return int(numeric) if numeric.is_integer() else numeric


def split_amount_unit(text: str) -> tuple[int | float | str | None, str]:
    cleaned = clean_text(text)
    if not cleaned:
        return None, ""
    match = re.match(r"^([0-9][0-9,]*(?:\.[0-9]+)?)(?:\s*(.*))?$", cleaned)
    if not match:
        return cleaned, ""
    return parse_number(match.group(1)), clean_text(match.group(2) or "")


def text_after_label(container: BeautifulSoup, label: str) -> str:
    strong = container.find("strong", string=lambda value: value and label in value)
    if not strong:
        return ""
    parent = strong.parent
    if not parent:
        return ""
    text = clean_text(parent.get_text(" ", strip=True))
    return clean_text(text.replace(strong.get_text(" ", strip=True), "", 1))


def _find_heading(soup: BeautifulSoup, label: str):
    return next(
        (
            heading
            for heading in soup.find_all(["h5", "h6"])
            if label in clean_text(heading.get_text(" ", strip=True))
        ),
        None,
    )


def _parse_metric_section(soup: BeautifulSoup, heading_label: str) -> list[dict[str, Any]]:
    heading = _find_heading(soup, heading_label)
    if not heading:
        return []
    metric_list = heading.find_next("ul")
    if not metric_list:
        return []

    rows: list[dict[str, Any]] = []
    for item in metric_list.find_all("li", recursive=False):
        spans = item.find_all("span", recursive=False)
        if not spans:
            continue
        label = clean_text(spans[0].get_text(" ", strip=True))
        value_node = spans[-1]
        unit_node = value_node.find("small")
        unit = clean_text(unit_node.get_text(" ", strip=True) if unit_node else "")
        raw_value = clean_text(value_node.get_text(" ", strip=True))
        value_text = raw_value
        if unit and raw_value.endswith(unit):
            value_text = clean_text(raw_value[: -len(unit)])
        numeric = parse_number(value_text)
        rows.append(
            {
                "label": label,
                "value": numeric if isinstance(numeric, (int, float)) else None,
                "value_text": value_text,
                "unit": unit,
                "evidence_type": "source_reported",
            }
        )
    return rows


def parse_product_detail_html(html: str, product_id: int | str, source_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        title = clean_text(str(og_title["content"]))
    if not title:
        h1 = soup.find(["h1", "h2", "h3"])
        title = clean_text(h1.get_text(" ", strip=True) if h1 else "")

    trl_level = None
    trl_status = ""
    trl_header = soup.find(string=lambda value: value and "ระดับความพร้อม (TRL)" in value)
    if trl_header:
        trl_card = trl_header.find_parent(class_="sidebar-card")
        if trl_card:
            level_text = clean_text(trl_card.find(string=re.compile(r"ระดับ\s*\d+")) or "")
            level_match = re.search(r"ระดับ\s*(\d+)", level_text)
            if level_match:
                trl_level = int(level_match.group(1))
            status_span = trl_card.find("span", class_=lambda value: value and "text-dark" in value)
            trl_status = clean_text(status_span.get_text(" ", strip=True) if status_span else "")

    lat = lon = None
    latlng = soup.find(id="viewMapLatLngText")
    if latlng:
        match = re.search(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", latlng.get_text(" ", strip=True))
        if match:
            lat = float(match.group(1))
            lon = float(match.group(2))

    html_bytes = html.encode("utf-8")
    return {
        "product_id": int(product_id),
        "source_url": source_url,
        "title": title,
        "trl_level": trl_level,
        "trl_status": trl_status,
        "latitude": lat,
        "longitude": lon,
        "outcomes": _parse_metric_section(soup, "ผลลัพธ์ (Outcomes)"),
        "impacts": _parse_metric_section(soup, "ผลกระทบ (Impacts)"),
        "raw_html_bytes": len(html_bytes),
        "raw_html_sha256": hashlib.sha256(html_bytes).hexdigest(),
    }


def load_product_ids_from_r2() -> list[int]:
    config = config_from_env()
    client = make_client(config)
    raw = client.get_object(Bucket=config.bucket, Key=PRODUCT_LIST_KEY)["Body"].read()
    with gzip.GzipFile(fileobj=io.BytesIO(raw), mode="rb") as handle:
        ids = {
            int(row["product_id"])
            for line in handle
            if line.strip()
            for row in [json.loads(line)]
            if row.get("product_id") not in (None, "")
        }
    return sorted(ids)


def fetch_product(product_id: int, timeout: float) -> FetchResult:
    url = BASE_URL.format(product_id=product_id)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            encoding = response.headers.get_content_charset() or "utf-8"
            return FetchResult(
                url=url,
                status_code=int(response.status),
                html=raw.decode(encoding, errors="replace"),
            )
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"PMUA product {product_id} returned HTTP {error.code}: {body[:200]}") from error


def missing_product_detail_row(product_id: int, source_url: str, error: Exception, as_of: str) -> dict[str, Any]:
    return {
        "product_id": int(product_id),
        "source_url": source_url,
        "title": "",
        "trl_level": None,
        "trl_status": "",
        "latitude": None,
        "longitude": None,
        "outcomes": [],
        "impacts": [],
        "raw_html_bytes": 0,
        "raw_html_sha256": "",
        "http_status": None,
        "fetched_at": as_of,
        "fetch_error": clean_text(str(error)),
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(
            {
                key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
                for key, value in row.items()
            }
            for row in rows
        )


def write_manifest_input(
    run_dir: Path,
    as_of: str,
    upstream: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> None:
    payload = {
        "fetched_by": "codex",
        "fetched_at": as_of,
        "upstream": upstream,
        "datasets": [
            {
                "dataset_key": "f4.pmua_product_details",
                "file": "product_details.jsonl",
                "as_of": as_of,
                "grain": "หนึ่งแถว = หนึ่งหน้า product detail สาธารณะจาก PMUA AppTech พร้อม TRL พิกัด ผลลัพธ์ และผลกระทบที่ดึงได้",
                "identity_fields": ["product_id"],
                "row_count": len(rows),
                "outcome_row_count": sum(1 for row in rows if row.get("outcomes")),
                "impact_row_count": sum(1 for row in rows if row.get("impacts")),
            }
        ],
    }
    (run_dir / "manifest_input.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product-id", action="append", type=int, default=[], help="PMUA product id to scrape; repeatable")
    parser.add_argument("--from-r2-products", action="store_true", help="Read product ids from the existing R2 PMUA product catalogue")
    parser.add_argument("--limit", type=int, default=0, help="Optional max product ids to scrape")
    parser.add_argument("--sleep", type=float, default=0.2, help="Seconds to sleep between product requests")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout seconds")
    parser.add_argument("--retries", type=int, default=3, help="Retry attempts per product before recording fetch_error")
    parser.add_argument("--output-root", type=Path, default=Path("data/raw/f4/pmua_product_details"))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--push", action="store_true", help="Push the run folder to R2 with tools/evidence_push.py")
    args = parser.parse_args()

    product_ids = set(args.product_id)
    if args.from_r2_products:
        product_ids.update(load_product_ids_from_r2())
    ids = sorted(product_ids)
    if args.limit:
        ids = ids[: args.limit]
    if not ids:
        parser.error("provide --product-id or --from-r2-products")

    run_id = args.run_id or utc_run_id()
    as_of = utc_now()
    run_dir = args.output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    rows: list[dict[str, Any]] = []
    upstream: list[dict[str, Any]] = []
    for index, product_id in enumerate(ids, start=1):
        source_url = BASE_URL.format(product_id=product_id)
        last_error: Exception | None = None
        for attempt in range(1, max(args.retries, 1) + 1):
            try:
                result = fetch_product(product_id, args.timeout)
                row = parse_product_detail_html(result.html, product_id, result.url)
                row["http_status"] = result.status_code
                row["fetched_at"] = as_of
                row["fetch_error"] = ""
                break
            except (RuntimeError, TimeoutError, URLError, OSError) as error:
                last_error = error
                if attempt < max(args.retries, 1):
                    time.sleep(min(2.0 * attempt, 6.0))
        else:
            row = missing_product_detail_row(product_id, source_url, last_error or RuntimeError("unknown fetch error"), as_of)
        rows.append(row)
        upstream.append({"url": source_url, "http_status": row.get("http_status"), "content_type": "text/html"})
        error_suffix = f" error={row['fetch_error'][:80]}" if row.get("fetch_error") else ""
        print(f"[{index}/{len(ids)}] product {product_id}: TRL={row['trl_level'] or 'ไม่ระบุ'}{error_suffix}")
        if index < len(ids) and args.sleep > 0:
            time.sleep(args.sleep)

    write_jsonl(run_dir / "product_details.jsonl", rows)
    write_csv(run_dir / "product_details.csv", rows)
    (run_dir / "network_observation.json").write_text(
        json.dumps(
            {
                "as_of": as_of,
                "product_count": len(rows),
                "source_url_template": BASE_URL,
                "from_r2_products": bool(args.from_r2_products),
                "product_list_key": PRODUCT_LIST_KEY if args.from_r2_products else None,
                "outcome_row_count": sum(1 for row in rows if row.get("outcomes")),
                "impact_row_count": sum(1 for row in rows if row.get("impacts")),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_manifest_input(
        run_dir,
        as_of,
        upstream[:25] + ([{"url": BASE_URL, "note": f"{len(upstream)} product detail pages requested; first 25 concrete URLs listed"}] if len(upstream) > 25 else []),
        rows,
    )
    print(f"wrote {len(rows)} rows to {run_dir}")

    if args.push:
        subprocess.run(
            [sys.executable, "tools/evidence_push.py", SOURCE_ID, str(run_dir), "--run-id", run_id],
            check=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

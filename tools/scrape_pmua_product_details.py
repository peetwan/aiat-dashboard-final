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
import io
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.connectors.pmua_product_details import clean_text, parse_product_detail_html  # noqa: E402
from tools.evidence_store import config_from_env, make_client  # noqa: E402


PRODUCT_LIST_KEY = "raw/f2/f2_target_household/20260818T163603Z/products_redacted.jsonl.gz"
SOURCE_ID = "f4_pmua_product_details"
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
        "empirical_evidence": [
            {
                "metric": metric,
                "domain": domain,
                "indicator_text": "",
                "quantity_text": "",
                "status": "not_reported",
                "evidence_type": "source_reported",
            }
            for metric, domain in (("ROI", "Economic"), ("SROI", "Social"))
        ],
        "outcomes": [],
        "impacts": [],
        "evidence_status": "not_reported",
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
                "grain": "หนึ่งแถว = หนึ่งหน้า product detail สาธารณะจาก PMUA AppTech พร้อม TRL พิกัด ROI/SROI ผลลัพธ์ และผลกระทบที่ดึงได้",
                "identity_fields": ["product_id"],
                "row_count": len(rows),
                "reported_evidence_row_count": sum(1 for row in rows if row.get("evidence_status") != "not_reported"),
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
                "reported_evidence_row_count": sum(1 for row in rows if row.get("evidence_status") != "not_reported"),
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

    failed_rows = [row for row in rows if row.get("fetch_error")]
    if failed_rows:
        print(
            f"refusing to publish incomplete PMUA detail snapshot: {len(failed_rows)} fetch errors",
            file=sys.stderr,
        )
        return 2

    if args.push:
        subprocess.run(
            [sys.executable, "tools/evidence_push.py", SOURCE_ID, str(run_dir), "--run-id", run_id],
            check=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

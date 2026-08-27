#!/usr/bin/env python3
"""Scrape CLIG public project records into an R2 evidence-store run folder.

The script writes local evidence files only by default.  With ``--push-r2`` it
delegates upload to ``tools/evidence_push.py`` so gzip, sha256, row counts, and
manifest upload ordering stay identical to the rest of the repo.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.connectors.clig_projects import (  # noqa: E402
    DEFAULT_MAX_PAGES,
    DETAIL_URL_TEMPLATE,
    LIST_URL,
    candidate_record,
    is_policy_candidate,
    parse_project_detail,
    parse_project_list,
)
from tools.evidence_store import REQUIRED_ENV_KEYS, load_dotenv, utc_now_run_id  # noqa: E402


CSV_FIELDS = [
    "row_number",
    "contract_no",
    "fiscal_year",
    "project_title",
    "project_id",
    "budget_baht",
    "status",
    "area_count",
    "cooperation_count",
    "product_count",
    "link_count",
    "lead_organization",
    "detail_url",
    "candidate_keywords",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flat = dict(row)
            keywords = flat.get("candidate_keywords")
            if isinstance(keywords, list):
                flat["candidate_keywords"] = "|".join(str(item) for item in keywords)
            writer.writerow(flat)


def fetch_text(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    data: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any]]:
    response = client.request(method, url, data=data)
    observation = {
        "method": method.upper(),
        "url": str(response.url),
        "http_status": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "bytes": len(response.content),
    }
    response.raise_for_status()
    return response.text, observation


def scrape(
    *,
    keyword: str,
    year: str,
    max_pages: int,
    delay_seconds: float,
    expected_candidate_count: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    fetched_at = utc_now_iso()
    observations: list[dict[str, Any]] = []
    warnings: list[str] = []
    projects: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    with httpx.Client(
        timeout=30,
        follow_redirects=False,
        headers={"User-Agent": "AIAT-CLIG-public-project-scraper/0.1 (+read-only)"},
    ) as client:
        page = 1
        while page <= max_pages:
            html, observation = fetch_text(
                client,
                "POST",
                LIST_URL,
                data={"project_name": keyword, "project_year": year, "page": str(page)},
            )
            observation["name"] = f"project_list_page_{page}"
            observations.append(observation)
            parsed = parse_project_list(html)
            if parsed.no_data or not parsed.projects:
                break
            for row in parsed.projects:
                project_id = str(row.get("project_id") or "")
                if project_id in seen_ids:
                    raise RuntimeError(f"duplicate CLIG project_id={project_id}")
                seen_ids.add(project_id)
                if delay_seconds:
                    time.sleep(delay_seconds)
                url = DETAIL_URL_TEMPLATE.format(project_id=quote(project_id, safe=""))
                detail_html, detail_observation = fetch_text(client, "GET", url)
                detail_observation["name"] = f"project_detail_{project_id}"
                observations.append(detail_observation)
                row.update(parse_project_detail(detail_html))
                row["source_url"] = "https://clig.oas.psu.ac.th/project/search_project"
                row["list_endpoint_url"] = LIST_URL
                row["fetched_at"] = fetched_at
                projects.append(row)
            if not parsed.page_numbers or page >= max(parsed.page_numbers):
                break
            page += 1
            if delay_seconds:
                time.sleep(delay_seconds)

    candidates = [candidate_record(row) for row in projects if is_policy_candidate(row)]
    if expected_candidate_count and len(candidates) != expected_candidate_count:
        warnings.append(
            "policy candidate count mismatch: "
            f"expected={expected_candidate_count} observed={len(candidates)}"
        )
    network_observation = {
        "source_id": "clig_projects",
        "fetched_at": fetched_at,
        "source_url": "https://clig.oas.psu.ac.th/project/search_project",
        "list_endpoint_url": LIST_URL,
        "detail_url_template": DETAIL_URL_TEMPLATE,
        "keyword": keyword,
        "project_year": year,
        "project_count": len(projects),
        "policy_candidate_count": len(candidates),
        "expected_policy_candidate_count": expected_candidate_count,
        "warnings": warnings,
        "upstream": observations,
    }
    return projects, candidates, network_observation


def write_manifest_input(
    run_dir: Path,
    *,
    fetched_at: str,
    fetched_by: str,
    upstream: list[dict[str, Any]],
) -> None:
    payload = {
        "fetched_at": fetched_at,
        "fetched_by": fetched_by,
        "upstream": upstream,
        "datasets": [
            {
                "dataset_key": "clig.projects",
                "file": "projects.jsonl",
                "as_of": fetched_at,
                "grain": "หนึ่งแถว = หนึ่งโครงการวิจัยจาก CLIG พร้อมข้อมูลหน้ารายละเอียด",
                "identity_fields": ["contract_no", "project_id"],
            },
            {
                "dataset_key": "clig.policy_candidates",
                "file": "policy_candidates.jsonl",
                "as_of": fetched_at,
                "grain": "หนึ่งแถว = หนึ่งโครงการวิจัยที่เกี่ยวข้องกับ อปท./นโยบาย/กลไก/มาตรการ",
                "identity_fields": ["contract_no", "project_id"],
            },
        ],
    }
    (run_dir / "manifest_input.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def push_r2(run_dir: Path) -> int:
    load_dotenv()
    missing = [key for key in REQUIRED_ENV_KEYS if not os.environ.get(key)]
    if missing:
        print(
            "R2 upload skipped: missing required environment variables: "
            + ", ".join(missing),
            file=sys.stderr,
        )
        return 2
    return subprocess.call(
        [sys.executable, "tools/evidence_push.py", "clig_projects", str(run_dir)],
        cwd=PROJECT_ROOT,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keyword", default="", help="CLIG project_name search keyword")
    parser.add_argument("--year", default="", help="CLIG fiscal year filter, e.g. 2567")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--delay-seconds", type=float, default=0.5)
    parser.add_argument("--expected-candidate-count", type=int, default=107)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Run directory. Defaults to data/raw/clig_projects/<UTC_RUN_ID>",
    )
    parser.add_argument("--fetched-by", default=os.environ.get("USER", "clig-scraper"))
    parser.add_argument("--push-r2", action="store_true")
    args = parser.parse_args()

    run_id = utc_now_run_id()
    run_dir = args.out_dir or PROJECT_ROOT.parent / "data/raw/clig_projects" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    projects, candidates, observation = scrape(
        keyword=args.keyword,
        year=args.year,
        max_pages=args.max_pages,
        delay_seconds=args.delay_seconds,
        expected_candidate_count=args.expected_candidate_count,
    )
    write_jsonl(run_dir / "projects.jsonl", projects)
    write_jsonl(run_dir / "policy_candidates.jsonl", candidates)
    write_csv(run_dir / "projects.csv", projects)
    write_csv(run_dir / "policy_candidates.csv", candidates)
    (run_dir / "network_observation.json").write_text(
        json.dumps(observation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_manifest_input(
        run_dir,
        fetched_at=observation["fetched_at"],
        fetched_by=args.fetched_by,
        upstream=observation["upstream"],
    )

    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "project_count": len(projects),
                "policy_candidate_count": len(candidates),
                "warnings": observation["warnings"],
            },
            ensure_ascii=False,
        )
    )
    if args.push_r2:
        return push_r2(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

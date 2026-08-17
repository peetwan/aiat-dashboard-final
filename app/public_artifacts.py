from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import PublicArtifact, utc_now
from app.settings import PROJECT_ROOT


PUBLIC_DATA_ROOT = PROJECT_ROOT / "data" / "public"
REQUIRED_GROUP_COUNTS = {
    "catalog": 1,
    "source_insights": 1,
    "source_coverage": 1,
    "unmapped_records": 1,
    "housing_spatial_summary": 1,
    "housing_demand_summary": 1,
    "source_dataset": 1,
    "map": 2,
    "provincial_briefing": 77,
    "executive_summary": 77,
}
REQUIRED_ARTIFACT_COUNT = sum(REQUIRED_GROUP_COUNTS.values())


@dataclass(frozen=True)
class ArtifactInput:
    key: str
    group: str
    path: Path
    province_code: str | None = None


def artifact_inputs(root: Path = PUBLIC_DATA_ROOT) -> list[ArtifactInput]:
    """Return the deterministic public serving set shipped with the app."""

    core_inputs = [
        ArtifactInput("catalog", "catalog", root / "public_dashboard.json"),
        ArtifactInput("source-insights", "source_insights", root / "source_insights.json"),
        ArtifactInput("source-coverage", "source_coverage", root / "source_coverage.json"),
        ArtifactInput("unmapped-records", "unmapped_records", root / "unmapped_records.json"),
        ArtifactInput(
            "housing-spatial-summary",
            "housing_spatial_summary",
            root / "housing_spatial_summary.json",
        ),
        ArtifactInput(
            "housing-demand-summary",
            "housing_demand_summary",
            root / "housing_demand_summary.json",
        ),
        ArtifactInput("learning-dashboard", "source_dataset", root / "learning_dashboard.json"),
        ArtifactInput("map/provinces", "map", root / "thailand_provinces.geojson"),
        ArtifactInput("map/cultural-points", "map", root / "cultural_points.geojson"),
    ]
    briefing_paths = sorted((root / "provincial_briefings").glob("[0-9][0-9].json"))
    summary_paths = sorted((root / "executive_summaries").glob("[0-9][0-9].json"))
    missing_core = [item.path.name for item in core_inputs if not item.path.is_file()]
    if missing_core or len(briefing_paths) != 77 or len(summary_paths) != 77:
        raise RuntimeError(
            "public serving set is incomplete: "
            f"missing_core={missing_core}, briefings={len(briefing_paths)}, "
            f"executive_summaries={len(summary_paths)}"
        )
    briefing_codes = {path.stem for path in briefing_paths}
    summary_codes = {path.stem for path in summary_paths}
    if briefing_codes != summary_codes:
        raise RuntimeError("province briefing and executive summary codes do not match")

    inputs = list(core_inputs)
    inputs.extend(
        ArtifactInput(
            f"province/{path.stem}/briefing",
            "provincial_briefing",
            path,
            path.stem,
        )
        for path in briefing_paths
    )
    inputs.extend(
        ArtifactInput(
            f"province/{path.stem}/summary",
            "executive_summary",
            path,
            path.stem,
        )
        for path in summary_paths
    )
    return inputs


def _item_count(payload: Any) -> int:
    if isinstance(payload, dict):
        for key in ("features", "provinces", "sources", "items"):
            value = payload.get(key)
            if isinstance(value, (list, dict)):
                return len(value)
        return 1
    if isinstance(payload, list):
        return len(payload)
    return 1


def _load_input(item: ArtifactInput) -> tuple[dict, str, int]:
    raw = item.path.read_bytes()
    payload = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"public artifact must be a JSON object: {item.path}")
    return payload, hashlib.sha256(raw).hexdigest(), _item_count(payload)


def sync_public_artifacts(
    session: Session,
    inputs: Iterable[ArtifactInput] | None = None,
) -> dict[str, Any]:
    """Idempotently synchronize cleaned public artifacts into the active DB."""

    selected = list(inputs if inputs is not None else artifact_inputs())
    if inputs is None:
        group_counts = Counter(item.group for item in selected)
        if dict(group_counts) != REQUIRED_GROUP_COUNTS:
            raise RuntimeError(
                "public serving artifact groups do not match the required contract: "
                f"actual={dict(group_counts)}, expected={REQUIRED_GROUP_COUNTS}"
            )
    expected_keys: list[str] = []
    inserted = 0
    updated = 0
    unchanged = 0
    for item in selected:
        payload, digest, item_count = _load_input(item)
        expected_keys.append(item.key)
        artifact = session.get(PublicArtifact, item.key)
        changed = (
            artifact is None
            or artifact.content_hash != digest
            or artifact.artifact_group != item.group
            or artifact.province_code != item.province_code
            or artifact.source_path != item.path.relative_to(PROJECT_ROOT).as_posix()
            or artifact.item_count != item_count
        )
        if artifact is None:
            artifact = PublicArtifact(artifact_key=item.key)
            inserted += 1
        elif not changed:
            unchanged += 1
        else:
            updated += 1
        if changed:
            artifact.artifact_group = item.group
            artifact.province_code = item.province_code
            artifact.content_hash = digest
            artifact.source_path = item.path.relative_to(PROJECT_ROOT).as_posix()
            artifact.item_count = item_count
            artifact.payload = payload
            artifact.updated_at = utc_now()
        session.add(artifact)

    if expected_keys:
        session.execute(
            delete(PublicArtifact).where(PublicArtifact.artifact_key.not_in(expected_keys))
        )
    else:
        session.execute(delete(PublicArtifact))
    session.commit()
    return {
        "expected": len(expected_keys),
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
    }


def artifact_payload(session: Session, artifact_key: str) -> dict | None:
    return session.scalar(
        select(PublicArtifact.payload).where(PublicArtifact.artifact_key == artifact_key)
    )


def database_artifact_counts(session: Session) -> dict[str, int]:
    return {
        group: count
        for group, count in session.execute(
            select(PublicArtifact.artifact_group, func.count())
            .group_by(PublicArtifact.artifact_group)
            .order_by(PublicArtifact.artifact_group)
        ).all()
    }

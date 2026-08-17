from __future__ import annotations

from pathlib import Path

import pytest

from tools.build_learning_dashboard import provenance_path as learning_provenance_path
from tools.build_provincial_briefings import provenance_path as briefing_provenance_path
from tools.build_source_catalog import provenance_path as catalog_provenance_path
from tools.build_source_coverage import provenance_path as coverage_provenance_path
from tools.build_source_insights import provenance_path as insights_provenance_path
from tools.prepare_snapshots import resolve_snapshot_origin


PROVENANCE_HELPERS = (
    learning_provenance_path,
    briefing_provenance_path,
    catalog_provenance_path,
    coverage_provenance_path,
    insights_provenance_path,
)


@pytest.mark.parametrize("helper", PROVENANCE_HELPERS)
def test_provenance_paths_do_not_require_repo_to_live_under_evidence_root(
    helper,
    tmp_path: Path,
):
    evidence_root = tmp_path / "evidence-workspace"
    dashboard_root = tmp_path / "public-clone"

    assert helper(
        evidence_root / "data/raw/source/run/response.json",
        evidence_root=evidence_root,
        dashboard_root=dashboard_root,
    ) == "data/raw/source/run/response.json"
    assert helper(
        dashboard_root / "data/public/artifact.json",
        evidence_root=evidence_root,
        dashboard_root=dashboard_root,
    ) == "dashboard_final/data/public/artifact.json"


@pytest.mark.parametrize("helper", PROVENANCE_HELPERS)
def test_provenance_paths_reject_files_outside_both_roots(helper, tmp_path: Path):
    with pytest.raises(ValueError, match="outside the dashboard and evidence roots"):
        helper(
            tmp_path / "elsewhere/file.json",
            evidence_root=tmp_path / "evidence-workspace",
            dashboard_root=tmp_path / "public-clone",
        )


def test_snapshot_origin_uses_independent_evidence_or_dashboard_root(tmp_path: Path):
    evidence_root = tmp_path / "evidence-workspace"
    dashboard_root = tmp_path / "public-clone"

    assert resolve_snapshot_origin(
        "data/staged/source/records.jsonl",
        evidence_root=evidence_root,
        dashboard_root=dashboard_root,
    ) == evidence_root / "data/staged/source/records.jsonl"
    assert resolve_snapshot_origin(
        "dashboard_final/data/public/artifact.json",
        evidence_root=evidence_root,
        dashboard_root=dashboard_root,
    ) == dashboard_root / "data/public/artifact.json"


@pytest.mark.parametrize("unsafe", ("../secret.json", "data/../../secret.json"))
def test_snapshot_origin_rejects_parent_traversal(unsafe: str):
    with pytest.raises(ValueError, match="safe relative path"):
        resolve_snapshot_origin(unsafe)

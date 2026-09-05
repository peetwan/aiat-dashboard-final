"""Public build provenance must describe the exact bytes stored in Git."""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "data/public"
MANIFESTS = sorted(PUBLIC.rglob("*manifest.json")) + sorted(PUBLIC.rglob("index.json"))


def declared_outputs(manifest: dict) -> list[dict]:
    entries = []
    for key in ("output", "outputs", "files", "unmapped"):
        value = manifest.get(key, [])
        entries.extend([value] if isinstance(value, dict) else value)
    return entries


def resolve_output(manifest_path: Path, entry: dict) -> Path:
    path = entry["path"].removeprefix("dashboard_final/")
    return ROOT / path if path.startswith(("data/", "config/")) else manifest_path.parent / path


@pytest.mark.parametrize("manifest_path", MANIFESTS, ids=lambda p: str(p.relative_to(PUBLIC)))
def test_public_manifest_hashes_match_published_bytes(manifest_path: Path):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in declared_outputs(manifest):
        path = resolve_output(manifest_path, entry)
        content = path.read_bytes()
        assert entry["sha256"] == hashlib.sha256(content).hexdigest(), str(path)
        if "bytes" in entry:
            assert entry["bytes"] == len(content), str(path)


def test_public_text_has_portable_lf_line_endings():
    for path in PUBLIC.rglob("*"):
        if path.suffix in {".json", ".geojson", ".csv"}:
            assert b"\r" not in path.read_bytes(), str(path)


@pytest.mark.parametrize("module_name", [
    "build_public_data", "build_source_insights", "build_provincial_briefings",
    "build_executive_summaries", "build_learning_dashboard", "build_f1_detail_projection",
])
def test_public_json_writers_emit_lf_on_every_platform(tmp_path: Path, module_name: str):
    path = tmp_path / "projection.json"
    importlib.import_module(f"tools.{module_name}").write_json(path, {"items": []})
    content = path.read_bytes()
    assert content.endswith(b"\n")
    assert b"\r" not in content

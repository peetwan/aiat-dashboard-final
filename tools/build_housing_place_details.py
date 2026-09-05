"""เติมรายละเอียดสถานที่สาธารณะจาก R2 snapshot ที่ตรวจ hash แล้วลง housing_points.

ใช้งาน: python tools/build_housing_place_details.py <โฟลเดอร์ run ที่มี manifest.json>
จับคู่ place_id ให้ครบกับ seed เดิมก่อนเขียนไฟล์ เก็บ geometry/พื้นที่/หลักฐานเดิมไว้.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.privacy import sanitize_payload
from app.spatial_artifacts import HOUSING_POINT_CONTEXTS, _mapping, load_spatial_manifest

DETAIL_FIELDS = ("name", "address", "rating", "user_ratings_total")


def encode_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def merge_place_details(seed: list[dict], features: list[dict]) -> list[dict]:
    source = {}
    for feature in features:
        properties = feature.get("properties", {})
        identifier = properties.get("place_id")
        if not isinstance(identifier, str) or not identifier or identifier in source:
            raise ValueError("source place_id must be present and unique")
        if feature.get("type") != "Feature" or not isinstance(feature.get("geometry"), dict):
            raise ValueError("source must contain public place features")
        source[identifier] = feature
    seed_ids = [row["feature_id"] for row in seed]
    if len(seed_ids) != len(set(seed_ids)) or set(seed_ids) != set(source):
        raise ValueError("source and serving place_id sets must match exactly")
    result = []
    for row in seed:
        feature = source[row["feature_id"]]
        if feature["geometry"] != row["geometry"]:
            raise ValueError("place geometry changed; rebuild the spatial layer before adding details")
        details = {key: feature["properties"].get(key) for key in DETAIL_FIELDS}
        details = sanitize_payload(details, field_contexts=HOUSING_POINT_CONTEXTS)
        merged = {**row, "properties": {**row["properties"], **details}}
        _mapping(merged, "housing_points")
        result.append(merged)
    return result


def build(run_dir: Path, *, root: Path = ROOT) -> dict:
    source_manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if source_manifest.get("source_id") != "f3_housing_portal":
        raise ValueError("source manifest must belong to f3_housing_portal")
    dataset = next(d for d in source_manifest["datasets"] if d["dataset_key"] == "housing.housing_points")
    source_path = (run_dir / dataset["file"]).resolve()
    if not source_path.is_relative_to(run_dir.resolve()):
        raise ValueError("dataset path escapes the evidence run")
    raw = source_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != dataset["sha256"]:
        raise ValueError("source SHA-256 does not match manifest")
    features = [json.loads(line) for line in gzip.decompress(raw).splitlines() if line.strip()]
    if len(features) != dataset["row_count"]:
        raise ValueError("source row count does not match manifest")
    manifest_path = root / "data/spatial/manifest.json"
    manifest = load_spatial_manifest(manifest_path)
    seed_path = root / manifest["layers"]["housing_points"]["artifact_path"]
    with gzip.open(seed_path, "rt", encoding="utf-8") as handle:
        seed = [json.loads(line) for line in handle if line.strip()]
    rows = merge_place_details(seed, features)
    stream = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as handle:
        for row in rows:
            handle.write((json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
    encoded = stream.getvalue()
    layer = manifest["layers"]["housing_points"]
    layer.update(artifact_bytes=len(encoded), artifact_sha256=hashlib.sha256(encoded).hexdigest())
    layer["detail_projection"] = {
        "source_run_id": source_manifest["run_id"], "source_file": dataset["file"],
        "source_sha256": dataset["sha256"], "fields": list(DETAIL_FIELDS),
        "field_contexts": HOUSING_POINT_CONTEXTS,
    }
    manifest["privacy_projection"]["point_fields_excluded"] = []
    summary_path = root / "data/public/housing_spatial_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["housing_points"]["excluded_fields"] = []
    summary["housing_points"]["public_place_fields"] = list(DETAIL_FIELDS)
    summary_bytes = encode_json(summary)
    summary_layer = manifest["layers"]["housing_spatial_summary"]
    summary_layer.update(artifact_bytes=len(summary_bytes), artifact_sha256=hashlib.sha256(summary_bytes).hexdigest())
    # All joins and checks finish before the first write. The manifest is last.
    seed_path.write_bytes(encoded)
    summary_path.write_bytes(summary_bytes)
    manifest_path.write_bytes(encode_json(manifest))
    return {"status": "built", "records": len(rows), "fields": list(DETAIL_FIELDS), "artifact_sha256": layer["artifact_sha256"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.run_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

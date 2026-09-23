"""CLI for deterministic F2 releases, review staging, and local promotion."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .common import PipelineError, load_json, output_directory, write_json
from .comparison import compare_release
from .inputs import validate_sources
from .public_projection import build_public_projection
from .measure_query import MeasureQuery
from .release import build_internal_release
from .reviews import validate_review_inputs
from .validation import load_release_tables, verify_release
from .promotion import build_local_promotion, verify_local_promotion


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser(
        "build", help="Build an immutable complete internal release"
    )
    build.add_argument("--config", type=Path, required=True)
    build.add_argument("--evidence-root", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument(
        "--review-root",
        type=Path,
        help="Repository root containing declared private review inputs",
    )
    project = commands.add_parser(
        "project-public", help="Project a complete release to a new review directory"
    )
    project.add_argument("--release", type=Path, required=True)
    project.add_argument("--output", type=Path, required=True)
    project.add_argument(
        "--comparison", type=Path, required=True, help="Full v2-to-v3 comparison file"
    )
    project.add_argument(
        "--comparison-review",
        type=Path,
        required=True,
        help="Hash-bound accepted internal comparison dispositions",
    )
    staged = commands.add_parser(
        "validate-public-stage",
        help="Validate an isolated publication overlay; never promote",
    )
    staged.add_argument("--stage", type=Path, required=True)
    staged.add_argument("--contract", type=Path, required=True)
    staged.add_argument("--release", type=Path, required=True)
    staged.add_argument("--comparison", type=Path, required=True)
    staged.add_argument("--comparison-review", type=Path, required=True)
    staged.add_argument(
        "--repository", type=Path, default=Path(__file__).resolve().parents[2]
    )
    staged.add_argument(
        "--f2-only", action="store_true", help="Diagnostic F2-only validation"
    )
    promote = commands.add_parser(
        "promote-local",
        help="Build an explicitly authorized local-only publication bundle",
    )
    promote.add_argument("--stage", type=Path, required=True)
    promote.add_argument("--release", type=Path, required=True)
    promote.add_argument("--comparison", type=Path, required=True)
    promote.add_argument("--comparison-review", type=Path, required=True)
    promote.add_argument("--decision", type=Path, required=True)
    promote.add_argument("--output", type=Path, required=True)
    verify_promotion = commands.add_parser(
        "verify-local-promotion",
        help="Rebuild and verify every byte of a local promotion bundle",
    )
    verify_promotion.add_argument("--bundle", type=Path, required=True)
    verify_promotion.add_argument("--stage", type=Path, required=True)
    verify_promotion.add_argument("--release", type=Path, required=True)
    verify_promotion.add_argument("--comparison", type=Path, required=True)
    verify_promotion.add_argument("--comparison-review", type=Path, required=True)
    verify_promotion.add_argument("--decision", type=Path, required=True)
    audit = commands.add_parser(
        "audit-inputs",
        help="Verify all evidence bundles and optional migrated review ledgers",
    )
    audit.add_argument(
        "--lock", type=Path, default=Path("config/f2_pipeline/inputs.v3.json")
    )
    audit.add_argument("--evidence-root", type=Path, required=True)
    audit.add_argument("--review-root", type=Path)
    audit.add_argument(
        "--inventory",
        type=Path,
        default=Path("config/f2_pipeline/migration_inventory.json"),
    )
    compare = commands.add_parser(
        "compare",
        help="Compare an internal release against the verified frozen v2 reference",
    )
    compare.add_argument("--release", type=Path, required=True)
    compare.add_argument("--reference", type=Path, required=True)
    compare.add_argument(
        "--output",
        type=Path,
        help="New comparison directory; never modifies the release",
    )
    query = commands.add_parser(
        "query", help="Exercise internal measure filter semantics"
    )
    query.add_argument("--release", type=Path, required=True)
    query.add_argument("--filters", default="{}", help="JSON object of filter lists")
    query.add_argument(
        "--measure", default="K12", help="Implemented measure ID; default K12"
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            report = asdict(
                build_internal_release(
                    args.config,
                    args.evidence_root,
                    args.output,
                    review_root=args.review_root,
                )
            )
        elif args.command == "project-public":
            report = asdict(
                build_public_projection(
                    args.release,
                    args.output,
                    comparison_path=args.comparison,
                    review_path=args.comparison_review,
                )
            )
        elif args.command == "validate-public-stage":
            from .public_stage import validate_public_stage

            report = validate_public_stage(
                args.stage,
                args.contract,
                args.repository,
                release_dir=args.release,
                comparison_path=args.comparison,
                review_path=args.comparison_review,
                include_existing=not args.f2_only,
            )
            if report["status"] != "valid":
                print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
                return 1
        elif args.command == "promote-local":
            report = asdict(
                build_local_promotion(
                    args.stage,
                    args.release,
                    args.comparison,
                    args.comparison_review,
                    args.decision,
                    args.output,
                )
            )
        elif args.command == "verify-local-promotion":
            report = asdict(
                verify_local_promotion(
                    args.bundle,
                    stage_dir=args.stage,
                    release_dir=args.release,
                    comparison_path=args.comparison,
                    review_path=args.comparison_review,
                    decision_path=args.decision,
                )
            )
        elif args.command == "audit-inputs":
            lock = load_json(args.lock)
            rows = validate_sources(lock, args.evidence_root)
            report = {
                "source_count": len(lock["sources"]),
                "file_count": len(rows),
                "integrity_exception_count": len(lock.get("integrity_exceptions", [])),
                "status": "passed",
            }
            if args.review_root is not None:
                config_root = args.lock.resolve().parent
                report["reviews"] = validate_review_inputs(
                    [
                        config_root / "reviews/reviewed_commerce.lock.json",
                        config_root / "reviews/source_resolution.lock.json",
                    ],
                    args.review_root,
                    lock,
                    args.evidence_root,
                    load_json(args.inventory),
                )
        elif args.command == "compare":
            report = compare_release(args.release, args.reference)
            if args.output:
                with output_directory(
                    args.output, (args.release, args.reference)
                ) as stage:
                    write_json(stage / "comparison.json", report)
        else:
            manifest = verify_release(args.release)
            if args.measure not in manifest["enabled_measures"]:
                raise PipelineError("Measure is not implemented in this release")
            tables = load_release_tables(args.release)
            definition = next(
                row
                for row in load_json(args.release / "definitions.json")["measures"]
                if row["measure_id"] == args.measure
            )
            report = MeasureQuery(definition, tables, tables["provinces"]).select(
                json.loads(args.filters)
            )
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (PipelineError, ValueError, OSError) as exc:
        parser.exit(2, f"F2 pipeline failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())

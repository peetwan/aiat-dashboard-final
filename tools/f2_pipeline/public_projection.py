"""Build a reviewed public candidate from a complete internal F2 release."""

from pathlib import Path

from .comparison_review import verify_comparison_review
from .common import PipelineError
from .full_projection import FullProjectionReport, build_full_projection
from .validation import verify_release

ProjectionReport = FullProjectionReport


def build_public_projection(
    release_dir,
    public_output_dir,
    *,
    comparison_path=None,
    review_path=None,
) -> FullProjectionReport:
    release_dir = Path(release_dir)
    manifest = verify_release(release_dir, require_complete=True)
    if manifest.get("profile") != "full":
        raise PipelineError("Public projection requires a complete full F2 release")
    proof = verify_comparison_review(release_dir, comparison_path, review_path)
    return build_full_projection(
        release_dir,
        Path(public_output_dir),
        comparison_proof=proof,
    )

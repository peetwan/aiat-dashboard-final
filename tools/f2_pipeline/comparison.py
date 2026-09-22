"""Compare a complete F2 release with the frozen v2 reference."""

from pathlib import Path

from .full_comparison import compare_full_release


def compare_release(release_dir: Path, reference_dir: Path) -> dict:
    return compare_full_release(Path(release_dir), Path(reference_dir))

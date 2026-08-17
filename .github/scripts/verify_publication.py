from __future__ import annotations

import sys
from pathlib import Path


# This file is executed by the read-only PR workflow.  Routine publication PRs
# may change only data/public, so both this wrapper and app.publication come from
# the already reviewed default branch.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.publication import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())

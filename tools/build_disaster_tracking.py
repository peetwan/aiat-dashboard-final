from __future__ import annotations

import json
from pathlib import Path

from app.database import SessionLocal
from app.main import build_candidate_disaster_tracking_artifact
from app.settings import PROJECT_ROOT


OUTPUT_PATH = PROJECT_ROOT / "data" / "public" / "disaster_tracking.json"


def build_disaster_tracking(output_path: Path = OUTPUT_PATH) -> dict:
    """Build the reviewable public projection without promoting it automatically."""

    with SessionLocal() as session:
        payload = build_candidate_disaster_tracking_artifact(session)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return payload


def main() -> None:
    payload = build_disaster_tracking()
    print(
        json.dumps(
            {
                "status": "ok",
                "output": OUTPUT_PATH.relative_to(PROJECT_ROOT).as_posix(),
                "province_count": len(payload["provinces"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

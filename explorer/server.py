from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "explorer.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()


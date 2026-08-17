from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_EMPTY_RUNTIME_FILES = {
    "data/runtime/.gitkeep",
    "data/snapshots/.gitkeep",
}
FORBIDDEN_EXACT = {
    ".env",
    "data/runtime/dashboard.sqlite",
}
FORBIDDEN_SUFFIXES = (
    ".sqlite",
    ".sqlite3",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
)
FORBIDDEN_PREFIXES = (
    "data/raw/",
    "data/runtime/",
    "data/snapshots/",
)
TEXT_SUFFIXES = {
    ".cfg",
    ".css",
    ".example",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
SECRET_PATTERNS = {
    "private key block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\b(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    "OpenAI key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    "credential in URL": re.compile(r"https?://[^\s/:@]+:[^\s/@]+@"),
}


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return sorted(item.decode("utf-8") for item in result.stdout.split(b"\0") if item)


def validate_paths(paths: list[str]) -> list[str]:
    problems: list[str] = []
    for path in paths:
        normalized = path.replace("\\", "/")
        lower = normalized.lower()
        if normalized in ALLOWED_EMPTY_RUNTIME_FILES:
            continue
        if lower in FORBIDDEN_EXACT:
            problems.append(f"forbidden tracked file: {normalized}")
        if lower.endswith(FORBIDDEN_SUFFIXES):
            problems.append(f"forbidden tracked file type: {normalized}")
        if lower.startswith(FORBIDDEN_PREFIXES):
            problems.append(f"runtime/raw evidence must not be tracked: {normalized}")
        file_path = ROOT / normalized
        if file_path.is_file() and file_path.stat().st_size > 95 * 1024 * 1024:
            problems.append(f"tracked file is too large for normal GitHub use: {normalized}")
    return problems


def scan_secrets(paths: list[str]) -> list[str]:
    problems: list[str] = []
    for path in paths:
        file_path = ROOT / path
        if file_path.suffix.lower() not in TEXT_SUFFIXES or not file_path.is_file():
            continue
        if file_path.stat().st_size > 5 * 1024 * 1024:
            continue
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                problems.append(f"possible {label}: {path}")
    return problems


def validate_runtime_is_standalone() -> list[str]:
    problems: list[str] = []
    for directory in (ROOT / "app", ROOT / "explorer"):
        for path in directory.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "PROJECT_ROOT.parent" in text or "WORKSPACE_ROOT" in text:
                problems.append(
                    f"public runtime imports the private parent workspace: {path.relative_to(ROOT).as_posix()}"
                )
    return problems


def main() -> int:
    paths = tracked_files()
    problems = validate_paths(paths)
    problems.extend(scan_secrets(paths))
    problems.extend(validate_runtime_is_standalone())
    report = {
        "status": "valid" if not problems else "invalid",
        "tracked_files": len(paths),
        "problems": problems,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

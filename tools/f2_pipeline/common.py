"""Deterministic, local-only primitives for F2 evidence builds."""

from __future__ import annotations

import csv
import ctypes
import hashlib
import html
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path
from typing import Generator


class PipelineError(ValueError):
    """A declared input or derived contract failed; no release may be committed."""


def stream_digest(stream) -> str:
    result = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        result.update(chunk)
    return result.hexdigest()


def digest(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return stream_digest(stream)


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def stable_id(kind: str, *parts: object) -> str:
    # Keep the accepted namespace/normalization encoding, not capture row order.
    return (
        kind
        + "_"
        + hashlib.sha256(canonical_json(parts).encode("utf-8")).hexdigest()[:20]
    )


def normalize(value: object) -> str:
    if value is None:
        return ""
    return re.sub(
        r"\s+",
        " ",
        unicodedata.normalize("NFC", html.unescape(str(value))).replace("\u200b", ""),
    ).strip()


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        if tag in ("br", "p", "div", "li", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)
        if tag in ("p", "div", "li"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def readable(value: object) -> str:
    parser = TextParser()
    parser.feed(str(value or ""))
    return "\n".join(
        normalize(line)
        for line in "".join(parser.parts).splitlines()
        if normalize(line)
    )


def safe_text(value: object) -> str:
    """Preserve legacy internal narrative treatment; not a public-field approval."""
    lines = []
    for line in str(value or "").splitlines():
        line = re.sub(
            r"(?i)(?:meeting\s*id)\s*[:：]?\s*[\d\s-]+",
            "[meeting access omitted]",
            line,
        )
        line = re.sub(
            r"(?i)\b(?:passcode|password)\s*[:：]\s*\S+",
            "[meeting access omitted]",
            line,
        )
        line = re.sub(
            r"(?i)\bline\s*(?:id)?\s*[:：]\s*[@\w.+-]+", "[line account omitted]", line
        )
        line = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[email omitted]", line)
        line = re.sub(r"(?<!\d)0\d[\d -]{7,12}\d(?!\d)", "[phone omitted]", line)
        lines.append(line)
    return "\n".join(lines)


def matching_name(value):
    """Remove supported person titles without accepting a one-token remainder."""
    name = normalize(value)
    titles = [
        "ผู้ช่วยศาสตราจารย์",
        "รองศาสตราจารย์",
        "ศาสตราจารย์",
        "แพทย์หญิง",
        "นายแพทย์",
        "ทันตแพทย์หญิง",
        "ทันตแพทย์",
        "นางสาว",
        "ผศ.ดร.",
        "รศ.ดร.",
        "ศ.ดร.",
        "ผศ.",
        "รศ.",
        "ศ.",
        "ดร.",
        "พญ.",
        "นพ.",
        "ทพญ.",
        "ทพ.",
        "นาย",
        "นาง",
    ]
    for _ in range(4):
        title = next((title for title in titles if name.startswith(title)), None)
        if title is None:
            match = re.match(r"^(?:ผศ|รศ|ศ|ดร|พญ|นพ|ทพญ|ทพ)\s+", name)
            title = match.group() if match else None
        if not title:
            break
        candidate = name[len(title) :].strip()
        if len(candidate.split()) < 2:
            break
        name = candidate
    return name


class Components:
    """Union reviewed identities only when no protection crosses either component."""

    def __init__(self, keys, cannot=()):
        self.parent = {key: key for key in keys}
        self.members = {key: {key} for key in keys}
        self.cannot = {frozenset(pair) for pair in cannot}

    def find(self, key):
        while self.parent[key] != key:
            self.parent[key] = self.parent[self.parent[key]]
            key = self.parent[key]
        return key

    def merge(self, left, right):
        left, right = self.find(left), self.find(right)
        if left == right:
            return "already_linked"
        if any(
            frozenset((a, b)) in self.cannot
            for a in self.members[left]
            for b in self.members[right]
        ):
            return "blocked_cannot_link"
        left, right = sorted((left, right))
        self.parent[right] = left
        self.members[left] |= self.members.pop(right)
        return "merged"


def local_path(root: Path, relative: str) -> Path:
    """Resolve a declared relative file without following evidence symlinks."""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise PipelineError("Invalid relative input path")
    part = Path(relative)
    if part.is_absolute() or any(p in ("..", ".scratch") for p in part.parts):
        raise PipelineError("Input path escapes its declared root or uses scratch")
    root = Path(root).resolve()
    candidate = root / part
    for parent in (candidate, *candidate.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise PipelineError("Symlinked input paths are not immutable inputs")
    if not candidate.resolve().is_relative_to(root):
        raise PipelineError("Input path escapes its declared root")
    return candidate


def parse_json(text: str):
    """Decode JSON without accepting duplicate keys or non-finite numbers."""

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise PipelineError("Duplicate JSON object key")
            result[key] = value
        return result

    def reject_constant(value):
        raise PipelineError("Non-finite JSON value")

    return json.loads(
        text, object_pairs_hook=unique_keys, parse_constant=reject_constant
    )


def load_json(path: Path):
    try:
        return parse_json(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineError(
            f"Cannot read declared JSON input: {Path(path).name}"
        ) from exc


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or sorted({key for row in rows for key in row})
    if not fields:
        raise PipelineError(f"Empty table needs explicit columns: {path.name}")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=fields, extrasaction="raise", lineterminator="\n"
        )
        writer.writeheader()
        for row in sorted(rows, key=canonical_json):
            writer.writerow(
                {
                    key: canonical_json(value)
                    if isinstance(value, (dict, list, tuple))
                    else value
                    for key, value in row.items()
                }
            )


def read_csv(path: Path) -> list[dict]:
    # Pinned source-envelope JSON cells exceed csv's default field-size limit.
    csv.field_size_limit(64 * 1024 * 1024)
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))
    except csv.Error as exc:
        raise PipelineError(f"Invalid or oversized CSV table: {path.name}") from exc


def ensure_new_output(output: Path, protected: tuple[Path, ...]) -> Path:
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise PipelineError("Output must be a new directory")
    resolved = output.resolve()
    for path in protected:
        protected_path = Path(path).resolve()
        if resolved.is_relative_to(protected_path) or protected_path.is_relative_to(
            resolved
        ):
            raise PipelineError("Output overlaps a protected input directory")
    return resolved


def rename_new_directory(source: Path, destination: Path) -> None:
    """Commit atomically without replacing a concurrently created destination."""
    if sys.platform == "win32":
        # Windows rename fails if the destination exists, including empty dirs.
        # Do not use os.replace: the no-overwrite guarantee is part of the build.
        os.rename(source, destination)
        return
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        rename = libc.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        # Darwin sys/stdio.h: RENAME_EXCL. Ordinary rename may replace empty dirs.
        result = rename(os.fsencode(source), os.fsencode(destination), 0x00000004)
    elif sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
        rename = libc.renameat2
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        result = rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    else:
        raise PipelineError("This platform lacks an atomic no-replace directory rename")
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))


@contextmanager
def output_directory(
    output: Path, protected: tuple[Path, ...]
) -> Generator[Path, None, None]:
    output = ensure_new_output(output, protected)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        yield stage
        if output.exists() or output.is_symlink():
            raise PipelineError("Output appeared during build; refusing replacement")
        rename_new_directory(stage, output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)

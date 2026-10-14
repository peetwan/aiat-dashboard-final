"""Text helpers shared by all cleaners."""

from __future__ import annotations

import html
import re
import unicodedata

# Values sources use for "not stated".
PLACEHOLDERS = {"", "-", "--", "ไม่ระบุ", "ไม่มี", "none", "null", "n/a", "na"}

# Longest first, so "นางสาว" wins over "นาง" and "รศ.ดร." over "รศ.".
TITLES = sorted(
    [
        "ผู้ช่วยศาสตราจารย์", "รองศาสตราจารย์", "ศาสตราจารย์", "แพทย์หญิง", "นายแพทย์",
        "ผู้ช่วยศาสตราจาร", "รองศาสตราจาร",  # frequent misspellings
        "ทันตแพทย์หญิง", "ทันตแพทย์", "อาจารย์", "นางสาว", "นาย", "นาง", "เด็กชาย", "เด็กหญิง",
        "ผศ.ดร.", "รศ.ดร.", "ศ.ดร.", "ผศ.", "รศ.", "ศ.", "ดร.", "พญ.", "นพ.", "ทพญ.", "ทพ.", "อ.",
        "Mr.", "Mrs.", "Ms.", "Miss", "Dr.", "Prof.",
    ],
    key=len,
    reverse=True,
)
MALE_TITLES = {"นาย", "นายแพทย์", "นพ.", "เด็กชาย", "Mr."}
FEMALE_TITLES = {"นาง", "นางสาว", "แพทย์หญิง", "พญ.", "ทันตแพทย์หญิง", "ทพญ.", "เด็กหญิง", "Mrs.", "Ms.", "Miss"}


def norm(value: object) -> str:
    """NFC, unescape HTML entities, drop zero-width spaces, "ํา" -> "ำ", collapse whitespace."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", html.unescape(str(value)))
    # "ํา" (nikhahit + sara aa, a common typing form) is the same letter as "ำ"
    return re.sub(r"\s+", " ", text.replace("​", "").replace("ํา", "ำ")).strip()


def key(value: object) -> str:
    """A comparison key: letters, marks and digits only, case-folded ("ร้าน ABC-1" -> "ร้านabc1")."""
    return "".join(c for c in norm(value).casefold() if unicodedata.category(c)[0] in "LMN")


def member_id(parent: str, role: str, name: str, seen: dict) -> str:
    """Record id of a person listed inside another record: "<parent>#<role>#<name key>". It stays with the
    person when the source reorders the list (decisions are keyed by it); a repeated name gets "#2", "#3"."""
    base = f"{parent}#{role}#{key(name)}"
    seen[base] = seen.get(base, 0) + 1
    return base if seen[base] == 1 else f"{base}#{seen[base]}"


def ref_part(key: object) -> str:
    """A dictionary key as one raw_ref path part ("วิสาหกิจ/แปลงใหญ่" must not split the path)."""
    return str(key).replace("~", "~0").replace("/", "~1")


def clean_or_none(value: object) -> str | None:
    text = norm(value)
    return None if text.casefold() in PLACEHOLDERS else text


def strip_html(value: object) -> str:
    text = re.sub(r"<\s*(br|/p|/div|/li)\s*/?\s*>", "\n", str(value or ""), flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return "\n".join(line for line in (norm(part) for part in html.unescape(text).split("\n")) if line)


def sections(items) -> str | None:
    """Description sections as "label: text" lines; empty sections dropped."""
    lines = [f"{norm(s.get('label'))}: {norm(s.get('text'))}" for s in items or [] if clean_or_none(s.get("text"))]
    return "\n".join(lines) or None


def level(value, low: int = 1, high: int = 9) -> int | None:
    """A readiness level as an int, or None when it is not a whole number in [low, high]."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high else None


def _title_at(text: str) -> str | None:
    """The title that starts text. An English title must end the word ("Miss " but not "Missaya");
    an academic abbreviation written without its dot ("ดร สมศรี") must be followed by a space."""
    bare = re.match(r"(ผศ|รศ|ดร)\s", text)
    if bare:
        return bare[1]
    for t in TITLES:
        if text.casefold().startswith(t.casefold()):
            after = text[len(t):len(t) + 1]
            if t[-1].isascii() and t[-1].isalpha() and after.isalpha():
                continue
            return t
    return None


def split_title(value: object) -> tuple[str, str]:
    """("รศ.ดร.", "สมชาย ใจดี") from "รศ.ดร.สมชาย ใจดี". Titles are kept, not thrown away:
    นาย vs นาง/นางสาว is evidence that two same-named records are different people.
    A short title that can also start a word (นาย, นาง, อ.) is removed only when it is clearly a title:
    followed by a space or another title, or leaving at least two name words ("นางรอง" stays a name)."""
    name = re.sub(r"^\s*\d+\s*[.)]\s*", "", norm(value))
    titles, rest = [], name
    while (title := _title_at(rest)) and rest[len(title):].strip():
        titles.append(rest[: len(title)])
        rest = rest[len(title):].lstrip()
    if not titles:
        return "", name
    chain = "".join(titles)
    clear = (len(titles) > 1 or len(chain) >= 5 or (chain.endswith(".") and len(chain) > 2)
             or name[len(titles[0])].isspace() or len(rest.split()) >= 2)
    return (chain, rest) if clear else ("", name)


def title_sex(title: str) -> str | None:
    """'male' / 'female' when one of the (concatenated) titles states it, else None."""
    while title:
        t = _title_at(title)
        if t is None:
            return None
        if t in MALE_TITLES:
            return "male"
        if t in FEMALE_TITLES:
            return "female"
        title = title[len(t):]
    return None


def person(raw_name: object) -> dict | None:
    """title / name / sex for a written person name; None when there is no usable name."""
    title, name = split_title(raw_name)
    name = name.strip("`'\".,;: ")
    if (not clean_or_none(name) or not re.search(r"[^\W\d_]", name)
            or all(re.fullmatch(r"([A-Za-z])\1*", word) for word in name.split())):
        return None  # empty, no letters ("0"), or a test entry like "นายAAA BBBB" / "นายA B"
    return {"title": title or None, "name": name, "sex": title_sex(title)}

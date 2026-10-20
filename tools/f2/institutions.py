"""Institution names -> one university name and its group, for counting work by university.

Sources spell one university many ways (abbreviations, typos, campus suffixes, "ในพระบรมราชูปถัมภ์").
The entity tables keep the stated name; Clean writes this mapping as the institution_names table.
A campus counts as its university, and a former name as the institution that exists now: funding goes to it.
Separate from resolve/innovations.py _institution(), which builds matching keys (changing it changes matches).
"""

from __future__ import annotations

import re

from .text import norm

# Abbreviations no prefix rule can expand.
ALIASES = {
    # RINMP institute 11, listed next to มนร. (10); all three of its innovations are in Pattani. We found no
    # source that uses this abbreviation (Fatoni writes FTU): an inference from the letters and the place.
    "ม.ฟ.น.": "มหาวิทยาลัยฟาฏอนี",
    "มจธ.": "มหาวิทยาลัยเทคโนโลยีพระจอมเกล้าธนบุรี",
    "มนร.": "มหาวิทยาลัยนราธิวาสราชนครินทร์",
}
RENAMED = {"มหาวิทยาลัยราชภัฏกาฬสินธุ์": "มหาวิทยาลัยกาฬสินธุ์"}  # merged into it by the 2558 (2015) Act
PREFIXES = [
    (re.compile(r"^มทร\.?\s*"), "มหาวิทยาลัยเทคโนโลยีราชมงคล"),
    (re.compile(r"^(มรภ\.?|ม\.ราชภัฏ|มหาวิทยาราชภัฏ)\s*"), "มหาวิทยาลัยราชภัฏ"),
    (re.compile(r"^ม\.\s*"), "มหาวิทยาลัย"),
]
FAMILY_SPACE = re.compile(r"^(มหาวิทยาลัยเทคโนโลยีราชมงคล|มหาวิทยาลัยราชภัฏ)\s+")  # "...ราชมงคล ล้านนา"
TYPOS = {
    "ราชภัฎ": "ราชภัฏ", "ราชถัฏ": "ราชภัฏ", "ราชภํก": "ราชภัฏ", "บ้าสมเด็จ": "บ้านสมเด็จ",
    "นครศรีธรมราช": "นครศรีธรรมราช", "สุราษฏร์": "สุราษฎร์", "เจ้าคุณหทาร": "เจ้าคุณทหาร",
}
ROYAL = re.compile(r"\s*(ในพระบรมราชูปถัมภ์|ฯ)\s*$")
CAMPUS = re.compile(r"\s+(วิทยาเขต|ศูนย์การศึกษา|จังหวัด).*$")
# Campuses sources name by the town alone; only these reviewed names, as a town can also be part of a name.
TOWN_CAMPUSES = {"มหาวิทยาลัยเทคโนโลยีราชมงคลล้านนา น่าน", "มหาวิทยาลัยเทคโนโลยีราชมงคลล้านนา เชียงราย",
                 "มหาวิทยาลัยราชภัฏกำแพงเพชร แม่สอด"}
FAMILIES = {"มหาวิทยาลัย", "มหาวิทยาลัยราชภัฏ", "มหาวิทยาลัยเทคโนโลยีราชมงคล"}


def university(raw: object) -> str | None:
    text = norm(raw)
    if not text:
        return None
    text = CAMPUS.sub("", text)
    text = ROYAL.sub("", ROYAL.sub("", text))  # "...ในพระบรมราชูปถัมภ์ฯ" carries both
    text = ALIASES.get(text, text)
    for pattern, full in PREFIXES:
        if pattern.match(text):
            text = pattern.sub(full, text, count=1)
            break
    text = FAMILY_SPACE.sub(r"\1", text)
    for wrong, right in TYPOS.items():
        text = text.replace(wrong, right)
    if text in TOWN_CAMPUSES:
        text = text.rsplit(" ", 1)[0]
    return RENAMED.get(text, text)


def group(name: str) -> str:
    """rajabhat | rajamangala | university | other (agencies, companies, foundations, colleges)."""
    if name.startswith("มหาวิทยาลัยราชภัฏ"):
        return "rajabhat"
    if name.startswith("มหาวิทยาลัยเทคโนโลยีราชมงคล"):
        return "rajamangala"
    # "จุฬาลงกรณ์มหาวิทยาลัย" ends with it; "มูลนิธิมหาวิทยาลัย..." is a foundation
    if name.startswith(("มหาวิทยาลัย", "สถาบันเทคโนโลยีพระจอมเกล้า")) or name.endswith("มหาวิทยาลัย"):
        return "university"
    return "other"


def rows(raw_names) -> list[dict]:
    """One institution_names row per distinct stated name."""
    out = []
    for raw in sorted({n for n in raw_names if n}):
        name = university(raw)
        if name:
            out.append({"raw": raw, "university": name, "university_group": group(name)})
    return out


def review(rows: list[dict], known: set[str]) -> list[str]:
    """Names a person should look at: a result still abbreviated or naming only a university family, and
    universities the previous Clean run did not have (often a new spelling of a known one: add a rule)."""
    notes = [f"{r['raw']} -> {r['university']}: still abbreviated or names no university"
             for r in rows if "." in r["university"] or r["university"] in FAMILIES]
    if known:
        for name in sorted({r["university"] for r in rows} - known):
            notes.append(f"new university {name} (stated as: {', '.join(r['raw'] for r in rows if r['university'] == name)})")
    return notes

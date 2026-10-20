"""Institution names -> one university name and its group, for counting work by university.

Sources spell one university many ways (abbreviations, typos, campus suffixes, "ในพระบรมราชูปถัมภ์").
The entity tables keep the stated name; Clean writes this mapping as the institution_names table.
A campus counts as its university: funding goes to the university.
"""

from __future__ import annotations

import re

from .text import norm

# Abbreviations no prefix rule can expand (checked against the records' provinces).
ALIASES = {
    "ม.ฟ.น.": "มหาวิทยาลัยฟาฏอนี",
    "มจธ.": "มหาวิทยาลัยเทคโนโลยีพระจอมเกล้าธนบุรี",
    "มนร.": "มหาวิทยาลัยนราธิวาสราชนครินทร์",
}
PREFIXES = [
    (re.compile(r"^มทร\.\s*"), "มหาวิทยาลัยเทคโนโลยีราชมงคล"),
    (re.compile(r"^(มรภ\.?|ม\.ราชภัฏ|มหาวิทยาราชภัฏ)\s*"), "มหาวิทยาลัยราชภัฏ"),
    (re.compile(r"^ม\.\s*"), "มหาวิทยาลัย"),
]
TYPOS = {
    "ราชภัฎ": "ราชภัฏ", "ราชถัฏ": "ราชภัฏ", "ราชภํก": "ราชภัฏ", "บ้าสมเด็จ": "บ้านสมเด็จ",
    "นครศรีธรมราช": "นครศรีธรรมราช", "สุราษฏร์": "สุราษฎร์", "เจ้าคุณหทาร": "เจ้าคุณทหาร",
}
ROYAL = re.compile(r"\s*(ในพระบรมราชูปถัมภ์|ฯ)\s*$")
# "<university> วิทยาเขต..." / "ศูนย์การศึกษา..." and the campus towns sources append without that word.
CAMPUS = re.compile(r"\s+(วิทยาเขต|ศูนย์การศึกษา).*$|\s+(น่าน|เชียงราย|แม่สอด)$")


def university(raw: object) -> str | None:
    text = norm(raw)
    if not text:
        return None
    text = ALIASES.get(text, text)
    for pattern, full in PREFIXES:
        if pattern.match(text):
            text = pattern.sub(full, text, count=1)
            break
    for wrong, right in TYPOS.items():
        text = text.replace(wrong, right)
    text = ROYAL.sub("", ROYAL.sub("", text))  # "...ในพระบรมราชูปถัมภ์ฯ" carries both
    return CAMPUS.sub("", text)


def group(name: str) -> str:
    """rajabhat | rajamangala | university | other (agencies, companies, foundations, colleges)."""
    if name.startswith("มหาวิทยาลัยราชภัฏ"):
        return "rajabhat"
    if name.startswith("มหาวิทยาลัยเทคโนโลยีราชมงคล"):
        return "rajamangala"
    if "มหาวิทยาลัย" in name or name.startswith("สถาบันเทคโนโลยี"):  # "จุฬาลงกรณ์มหาวิทยาลัย" ends with it
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

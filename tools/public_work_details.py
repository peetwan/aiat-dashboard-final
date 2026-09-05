"""รายละเอียดผลงานและข้อมูลติดต่อจากหน้าสาธารณะ โดยไม่ดึงบัญชีผู้ใช้มาปน."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from app.privacy import sanitize_payload


WORK_CONTEXTS = {
    "/owner_name": "work_attribution", "/inventor": "work_attribution",
    "/coordinator": "work_attribution", "/co_owner": "work_attribution",
    "/address": "public_contact", "/phone": "public_contact", "/email": "public_contact",
    "/secondary_phone": "public_contact",
}
CULTURAL_CONTEXTS = {
    "/address": "public_location", "/sales_channels": "public_contact",
    "/work_contact": "public_contact", "/recorded_by": "work_attribution",
    "/team_members/*/name": "work_attribution",
}


def project_cultural_supporting(row: dict, dataset_id: str) -> dict:
    from tools.build_provincial_briefings import sanitize_public_text
    data = row.get("data") or {}
    item = {"record_id": row["external_id"], "dataset_id": dataset_id,
            "title": sanitize_public_text(row.get("title")), "source_url": row.get("source_url")}
    if dataset_id == "products":
        item.update(category=data.get("product_category"), price_text=data.get("price_text"),
                    address=data.get("address_text"), sales_channels=data.get("sales_channels"),
                    related_cultural_record=data.get("related_cultural_record"))
    elif dataset_id == "activities":
        item["date_text"] = data.get("date_text")
    elif dataset_id == "recreation":
        item.update(category=data.get("recreation_category"), work_contact=data.get("contact_text"),
                    recorded_by=data.get("recorded_by"), team_name=data.get("team_name"),
                    team_members=[{"name": name} for name in data.get("team_members") or []])
    elif dataset_id == "team":
        item["group"] = data.get("group")
    else:
        raise ValueError("unsupported cultural supporting dataset")
    return sanitize_payload(item, field_contexts=CULTURAL_CONTEXTS)


def project_mtr_work(row: dict, contacts: dict | None = None) -> dict:
    fields = row["normalized_fields"]
    return sanitize_payload({
        "record_id": row["source_record_id"], "title": fields.get("innovation_name"),
        "display_name": fields.get("display_name"), "owner_name": fields.get("owner_name"),
        "institute_name": fields.get("institute_name"), "category": fields.get("category_name"),
        "sub_category": fields.get("sub_category_name"), "atl_level": fields.get("atl_level"),
        "source_url": row.get("provenance", {}).get("source_url"),
        **(contacts or {}),
    }, field_contexts=WORK_CONTEXTS)


def mtr_public_contacts(evidence_root: Path, rows: list[dict]) -> dict[str, dict]:
    pages = {}
    result = {}
    for row in rows:
        provenance = row["provenance"]
        path = (evidence_root / provenance["raw_evidence_uri"]).resolve()
        if not path.is_relative_to(evidence_root.resolve()):
            raise ValueError("MTR evidence path escapes workspace")
        digest = provenance["raw_sha256"]
        if (path, digest) not in pages:
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError("MTR evidence hash mismatch")
            payload = json.loads(raw)
            records = payload["data"]
            ids = [str(item["id"]) for item in records]
            if len(ids) != len(set(ids)):
                raise ValueError("MTR evidence contains duplicate IDs")
            pages[path, digest] = dict(zip(ids, records))
        source = pages[path, digest][str(row["normalized_fields"]["innovation_id"])]
        contact = source.get("ownerContact") or {}
        identifier = row["source_record_id"]
        if identifier in result:
            raise ValueError("MTR Silver contains duplicate IDs")
        result[identifier] = {"email": contact.get("email"), "phone": contact.get("phone"),
                              "secondary_phone": contact.get("phone1"), "source_sha256": digest}
    return result


def rmutdb_public_contacts(evidence_root: Path, silver_rows: list[dict]) -> dict[str, dict]:
    """Replay the evidence workspace's Thai PDF parser; verify hashes and identities.

    Uses the same glyph/font-aware parser that created Silver. The parser modules
    stay in the evidence workspace, together with the original PDF run.
    """
    scripts = evidence_root / "scripts"
    if not (scripts / "rmutdb_ebook_silver.py").is_file():
        raise RuntimeError("RMUTDB build needs the evidence workspace PDF parser; see docs/field-contexts.md")
    previous_path = list(sys.path)
    sys.path.insert(0, str(scripts))
    try:
        import rmutdb_ebook_silver as parser
    finally:
        sys.path[:] = previous_path
    manifest_path = evidence_root / "data/raw/export/f2_rmutdb/20260805T_ebook_export_01/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    contacts = {}
    for book in manifest["files"]:
        path = (evidence_root / book["path"]).resolve()
        if not path.is_relative_to(evidence_root.resolve()):
            raise ValueError("PDF path escapes evidence workspace")
        if hashlib.sha256(path.read_bytes()).hexdigest() != book["sha256"]:
            raise ValueError("RMUTDB PDF hash mismatch")
        document = parser.Document(path.read_bytes())
        cache = {}
        for page_number, page in enumerate(document.pages(), 1):
            lines = parser.pdftext.page_lines(document, page, cache)
            if book["slug"] == "all":
                parsed_rows = parser.parse_summary_page(lines)
                phones = [parser.SUMMARY_PHONE.match(line["text"].strip()) for line in lines]
                phones = [match.group(1).strip() for match in phones if match]
                if parsed_rows and len(phones) != len(parsed_rows):
                    raise ValueError("RMUTDB summary phone-to-work alignment changed")
                for index, (parsed, phone) in enumerate(zip(parsed_rows, phones), 1):
                    contacts[f"all:p{page_number}:{index}"] = {"phone": phone, "title": parsed["title"]}
            else:
                parsed = parser.parse_page("\n".join(line["text"] for line in lines))
                if parsed:
                    fields = parsed["fields"]
                    contacts[f"{book['slug']}:p{page_number}"] = {
                        "phone": fields.get("contact_phone"), "email": fields.get("contact_email"),
                        "title": parsed["title"],
                    }
    expected = {row["source_record_id"] for row in silver_rows}
    if len(expected) != len(silver_rows) or set(contacts) != expected:
        raise ValueError("RMUTDB PDF and Silver identities must match exactly")
    for row in silver_rows:
        source = contacts[row["source_record_id"]]
        title = parser.redact_contacts(source.pop("title"))[0]
        if title != row["normalized_fields"]["title"]:
            raise ValueError("RMUTDB PDF-to-work title mismatch")
    return contacts


def project_rmutdb_work(row: dict, contacts: dict) -> dict:
    fields = row["normalized_fields"]
    return sanitize_payload({
        "record_id": row["source_record_id"], "record_type": row["record_type"],
        "title": fields.get("title"), "inventor": fields.get("inventor"),
        "owner_affiliation": fields.get("owner_affiliation"), "co_owner": fields.get("co_owner"),
        "coordinator": fields.get("coordinator"), "address": fields.get("contact_address"),
        "technology_group": fields.get("technology_group"), "trl_level": fields.get("trl_level"),
        **contacts, "pdf_page": row["source_fields"]["pdf_page_index"],
        "source_url": row["provenance"]["source_url"], "source_sha256": row["provenance"]["raw_sha256"],
    }, field_contexts=WORK_CONTEXTS)

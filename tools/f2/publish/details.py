"""List items and public detail records for every counted entity, per topic.

Only fields the dashboard shows are written, and only the kinds of fields that were public before (names of
works, public descriptions, places, links to the source, reviewed quotes). Free text goes through the
repo's contact redaction (app/privacy.py) and is cut to an excerpt; a text the publication check
(app/publication.py) would still flag, or a label that would need redaction, is not shown.
Each builder returns {entity_id: detail}; the list item is a short form of the detail.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from urllib.parse import urlsplit

from app.privacy import sanitize_payload
from app.publication import PERSON_LEVEL_SENSITIVE_RE, PublicationError, _canonical_url
from app.publication import _privacy_reasons_for_text as privacy_reasons

EXCERPT = 1000
CULTURAL_DESCRIPTIONS = ("history", "identity")      # Cultural Map description fields that are public
SECTIONED = {"apptech_mru", "pmua_apptech", "rinmp"}  # innovation descriptions stored as "label: text" lines
RECORD_LINKS = {"pmua_apptech", "cultural_map"}       # sources whose record pages are linked; others link the site
MEDIA_HOSTS = {"dp.culturalmapthailand.info", "atlocalthailand.com", "www.icommunity.in.th"}
# sources also hold media file names with spaces or "???" in them, which are not working links
BROKEN_LINK = re.compile(r"[\s\"<>\\^`{|}?#]")
# a house address: "บ้านเลขที่ 12", "123 ม.4", "เลขที่ 25/463 หมู่ 10" (the place names around it stay)
MOO = r"\s*(?:ม\.|หมู่(?:ที่)?)\s?\d+(?![\d.,])"  # village number: "ม.4", "หมู่ที่ 10"
ADDRESS = re.compile(rf"บ้านเลขที่\s*\d+(?:/\d+)?(?:{MOO})?|(?:เลขที่\s*)?(?<![\d.,/-])\d+(?:/\d+)?{MOO}")
PRIVATE_SECTIONS = {"targetUserAddressDetail"}  # RINMP: where the target user lives
# what a source shows when no price is given (0; AtLocal also 99999): not a price, and 0 does not mean free
PLACEHOLDER_PRICES = {0, 99999}
# role in the Clean tables -> public role code (f2-detail.js has the Thai labels)
WORK_ROLES = {"lead": "researcher", "co": "researcher", "researcher": "researcher", "inventor": "inventor",
              "owner": "listing_account_owner", "rights_holder": "rights_holder", "collector": "source_reported_owner"}
ORGANIZATION_ROLES = {"pmua_apptech": "university", "rinmp": "institute", "icommunity": "institution"}
VARIANT_WORDS = {"ขนาด", "สี", "โทนสี", "รุ่น", "แบบ", "ลาย", "สูตร", "กลิ่น", "รส", "size"}  # end a variant's name
NAME_ORDER = ("icommunity", "pmua_apptech", "apptech_mru", "rinmp")  # whose title names a merged innovation
C02_ROLES = {"community_innovator": ("community_innovator", "นวัตกรชุมชน"),
             "inventor": ("inventor", "ผู้ประดิษฐ์"), "inventor_and_developer": ("inventor", "ผู้ประดิษฐ์")}


# Text -----------------------------------------------------------------------

def text(value, limit: int = EXCERPT) -> tuple[str | None, bool, bool]:
    """(public text, is_excerpt, was_sanitized); contact values are replaced by [redacted-…], and a text the
    repo's publication check would still flag (an address, a labelled contact, ...) is not shown at all."""
    if value is None or not str(value).strip():
        return None, False, False
    changes: list = []
    clean = sanitize_payload(str(value).strip(), changes=changes)
    # checked before the house addresses are removed (removing them never makes a refused text public), and
    # after (the shorter text's excerpt reaches further)
    if refused(clean[:limit]):
        return None, False, True
    clean = ADDRESS.sub("[redacted-address]", clean)  # an address form the publication check does not catch
    shown = clean[:limit]
    if refused(shown):
        return None, False, True
    return shown, len(clean) > limit, bool(changes) or "[redacted-address]" in shown


def refused(text: str) -> bool:
    """The publication check would flag it; every public text sits next to a source_id, where the check also
    refuses money, health and household words."""
    return bool(privacy_reasons(text, restricted_source_ids=set(), allow_restricted=True)
                or PERSON_LEVEL_SENSITIVE_RE.search(text))


def label(value) -> str | None:
    """A short public label, or None when it would need redaction."""
    clean, cut, sanitized = text(value, 300)
    return None if cut or sanitized else clean


WITHHELD = "Title withheld pending review"


def title(value) -> str | None:
    """An entity's name: its public label, WITHHELD when the source has a name that cannot be shown, or None
    when the source has no name."""
    return label(value) or (WITHHELD if value and str(value).strip() else None)


def description(kind: str, value, source_id: str) -> dict | None:
    clean, cut, sanitized = text(value)
    if not clean:
        return None
    return {"kind": kind, "text": clean, "is_excerpt": cut, "was_sanitized": sanitized, "source_id": source_id}


def link(url) -> str | None:
    """An https link the publication check accepts (no encoded or ../ paths, no credentials)."""
    if not url or urlsplit(str(url)).scheme != "https":
        return None
    try:
        _canonical_url(str(url), catalog=False)
    except PublicationError:
        return None
    return str(url)


def media(url, source_id: str, kind: str = "image", caption=None) -> dict | None:
    if not url or BROKEN_LINK.search(str(url).removeprefix("https://")):
        return None
    url = link(url)
    if not url or urlsplit(url).hostname not in MEDIA_HOSTS:
        return None
    name = label(caption)
    return {"kind": kind, "url": url, "label": name, "source_id": source_id,
            "label_availability": "available" if name else "withheld" if caption else "not_provided"}


def location(row: dict, source_id: str, role: str) -> dict | None:
    if not row.get("province_code"):
        return None
    return {"location_role": role, "source_id": source_id, **{k: row.get(k) for k in (
        "province", "province_code", "district", "district_code", "subdistrict", "subdistrict_code")}}


def unique(rows: list) -> list:
    seen, out = set(), []
    for row in rows:
        key = json.dumps(row, ensure_ascii=False, sort_keys=True)
        if row and key not in seen:
            seen.add(key)
            out.append(row)
    return out


# Shared shape -----------------------------------------------------------------

class Context:
    """Rows of the pipeline database, grouped for the builders."""

    def __init__(self, con, config: dict):
        self.con = con
        self.source_id = dict(con.execute("SELECT source, raw_folder FROM runs").fetchall())
        self.systems = {sid: s["originating_system"] for sid, s in config["sources"].items()}
        self.site = {sid: s["public_url"] for sid, s in config["sources"].items()}
        self.members: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
        self.entity_of: dict[tuple[str, str, str], str] = {}
        for entity, entity_id, source, record_id in con.execute(
                "SELECT entity, entity_id, source, record_id FROM entity_members ORDER BY ALL").fetchall():
            self.members[entity, entity_id].append((source, record_id))
            self.entity_of[entity, source, record_id] = entity_id
        self.unresolved = {self.entity_of.get((e, s, r)) for e, *pair in con.execute(
            "SELECT entity, a_source, a_record_id, b_source, b_record_id FROM match_pairs WHERE status = 'queue'").fetchall()
            for s, r in (pair[:2], pair[2:])}
        self.reviewed = {(r["source"], r["record_id"]): (r["label_sha256"], r["context"]) for r in config["reviewed_labels"]["labels"]}
        self.contexts: dict[str, str] = {}  # entity_id -> field context of its reviewed label

    def name(self, entity_id: str, key: tuple[str, str], value) -> str | None:
        """A record's public label: a reviewed label as written (and noted for the contract), else label().
        A reviewed record whose label has changed since the review is checked like any other."""
        reviewed_hash, context = self.reviewed.get(key, (None, None))
        if value and reviewed_hash == hashlib.sha256(str(value).strip().encode()).hexdigest()[:16]:
            self.contexts[entity_id] = context
            return str(value).strip()
        return title(value)

    def rows(self, sql: str, *params) -> list[dict]:
        cursor = self.con.execute(sql, list(params))
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]

    def by_record(self, table: str, where: str = "true") -> dict[tuple[str, str], dict]:
        return {(r["source"], r["record_id"]): r for r in self.rows(f"SELECT * FROM {table} WHERE {where}")}

    def identity(self, entity: str, entity_id: str, grouped: bool = False) -> dict:
        members = self.members[entity, entity_id]
        if len(members) > 1:
            if grouped:
                return {"outcome": "grouped_family", "counting": "grouped", "merge_scope": None, "name_quality": "supported"}
            scope = "cross_source" if len({s for s, _ in members}) > 1 else "within_source"
            return {"outcome": "merged", "counting": "merged", "merge_scope": scope, "name_quality": "supported"}
        outcome = "unresolved" if entity_id in self.unresolved else "source_record_only"
        return {"outcome": outcome, "counting": "separate", "merge_scope": None, "name_quality": "supported"}

    def base(self, entity: str, entity_id: str, name: str | None, sources: list[str], **fields) -> dict:
        source_ids = sorted({self.source_id[s] for s in sources})
        withheld = name == WITHHELD
        locations = unique(fields.pop("locations", []))
        provinces = sorted({l["province_code"] for l in locations})
        return {
            "entity_id": entity_id,
            "label": name or "Name unavailable",
            "identity_review": fields.pop("identity_review", None) or self.identity(entity, entity_id),
            "source_ids": source_ids,
            "originating_systems": [self.systems[s] for s in source_ids],
            "category_codes": fields.pop("category_codes", []),
            "province_codes": provinces,  # replaced by the counted provinces in build()
            "locations": locations,
            "descriptions": unique([d for d in fields.pop("descriptions", []) if d]),
            "listings": unique([l for l in fields.pop("listings", []) if l]),
            "media": unique([m for m in fields.pop("media", []) if m]),
            "relationships": unique(fields.pop("relationships", [])),
            "children": fields.pop("children", {}),
            "flags": {"missing_geography": not provinces, **fields.pop("flags", {}),
                      **({"label_availability": "withheld", "label_withholding_reason": "public_scalar_admission_failed"}
                         if withheld else {})},
            "detail_availability": "available",
            **fields,
        }

    def listing(self, source: str, name: str | None, url) -> dict:
        """A link to the record's page (RECORD_LINKS sources) or else to the source's site; name is a public label."""
        sid = self.source_id[source]
        if source in RECORD_LINKS and link(url):
            return {"label": name, "source_id": sid, "source_url": link(url), "link_scope": "record"}
        return {"label": name, "source_id": sid, "source_url": self.site[sid], "link_scope": "source",
                "record_link_availability": "withheld"}


def item(detail: dict, *extra: str) -> dict:
    """The list form of a detail record."""
    keys = ("label", "identity_review", "category_codes", "province_codes", "source_ids", *extra)
    return {k: detail[k] for k in keys if k in detail}


def entity_ids(con, measure_ids: tuple[str, ...]) -> list[str]:
    marks = ",".join("?" * len(measure_ids))
    return [r[0] for r in con.execute(
        f"SELECT DISTINCT entity_id FROM measure_members WHERE measure_id IN ({marks}) ORDER BY 1", list(measure_ids)).fetchall()]


# Innovations (K04, C04_LISTED) ------------------------------------------------

def innovations(ctx: Context) -> dict[str, dict]:
    records = ctx.by_record("innovations")
    readiness, places, people = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in ctx.rows("SELECT * FROM innovation_readiness ORDER BY source, record_id, scale"):
        readiness[r["source"], r["record_id"]].append(r)
    for r in ctx.rows("SELECT * FROM innovation_places WHERE role = 'use' ORDER BY ALL"):
        places[r["source"], r["record_id"]].append(r)
    # role, then the order the source lists people in (rowid = insertion order; ids no longer carry a position)
    for r in ctx.rows("SELECT * FROM people WHERE about_kind = 'innovation' ORDER BY source, about_record_id, role, rowid"):
        people[r["source"], r["about_record_id"]].append(r)
    out = {}
    for entity_id in entity_ids(ctx.con, ("C04_LISTED", "K04")):
        members = ctx.members["innovation", entity_id]
        rows = [records[m] for m in members]
        descriptions, levels, organizations, attributions, listings, locations = [], [], [], [], [], []
        for key, row in zip(members, rows):
            source, sid = row["source"], ctx.source_id[row["source"]]
            for line in (row["description"] or "").split("\n"):
                kind, _, body = line.partition(": ") if source in SECTIONED else ("description", "", line)
                if kind not in PRIVATE_SECTIONS:
                    descriptions.append(description(kind, body, sid))
            for r in readiness[key]:
                levels.append({"scale": r["scale"], "numeric_level": None if r["level"] is None else str(r["level"]),
                               "label": None, "qualifies": r["scale"] == "TRL" and (r["level"] or 0) >= 8, "source_id": sid})
            if row["institution"] and source in ORGANIZATION_ROLES:
                organizations.append({"organization": label(row["institution"]), "role": ORGANIZATION_ROLES[source], "source_id": sid})
            for p in people[key]:
                if p["role"] in WORK_ROLES and label(p["name"]):
                    attributions.append({"attribution": label((p["title"] or "") + p["name"]),
                                         "role": WORK_ROLES[p["role"]], "source_id": sid})
            if source in ("pmua_apptech", "rinmp"):
                listings.append(ctx.listing(source, ctx.name(entity_id, key, row["title"]), row["url"]))
            locations += [location(p, sid, "declared_innovation_use") for p in places[key]]
        trl = {l["numeric_level"] for l in levels if l["scale"] == "TRL" and l["numeric_level"]}
        key, row = min(zip(members, rows), key=lambda m: NAME_ORDER.index(m[0][0]))
        out[entity_id] = ctx.base(
            "innovation", entity_id, ctx.name(entity_id, key, row["title"]), [s for s, _ in members],
            descriptions=descriptions, listings=listings, locations=[l for l in locations if l],
            children={"readiness": unique(levels), "organizations": unique(organizations),
                      "work_attributions": unique(attributions)},
            flags={"readiness_conflict": len(trl) > 1})
    return out


# People (C02_COMMUNITY) -------------------------------------------------------

def people(ctx: Context, innovation_details: dict[str, dict]) -> dict[str, dict]:
    records = ctx.by_record("people")
    # community innovators name their innovation and project; find it among the source's innovations
    by_project = defaultdict(list)
    for r in ctx.rows("SELECT source, record_id, title, details->>'project_code' AS project FROM innovations WHERE source = 'icommunity'"):
        by_project[r["project"]].append(r)
    k04 = {r[0] for r in ctx.con.execute("SELECT entity_id FROM measure_members WHERE measure_id = 'K04'").fetchall()}
    out = {}
    for entity_id in entity_ids(ctx.con, ("C02_COMMUNITY",)):
        members = ctx.members["person", entity_id]
        rows = [records[m] for m in members]
        roles, works, locations = [], [], []
        for row in rows:
            sid = ctx.source_id[row["source"]]
            code, name = C02_ROLES.get(row["role"], (None, None))
            if code:
                roles.append({"role_code": code, "role_label_th": name, "qualifies_for": ["C02_COMMUNITY"], "source_id": sid})
            targets = []
            if row["role"] == "community_innovator":
                details = json.loads(row["details"] or "{}")
                candidates = by_project.get(details.get("project_code"), [])
                named = [c for c in candidates if c["title"] == details.get("linked_innovation")]
                targets = [(c["source"], c["record_id"]) for c in named or (candidates if len(candidates) == 1 else [])]
                if "geocode_disagrees" not in (row["geo_note"] or ""):
                    place = location(row, sid, "source_reported_innovator_location")  # a person: province only
                    locations.append(place and {k: place[k] for k in ("location_role", "source_id", "province", "province_code")})
            elif code and row["about_kind"] == "innovation":
                targets = [(row["source"], row["about_record_id"])]
            for target in targets:
                work = ctx.entity_of.get(("innovation", *target))
                if work in innovation_details:
                    measure = "K04" if work in k04 else "C04_LISTED"
                    works.append({"entity_id": work, "kind": "contributed_to_innovation",
                                  "label": innovation_details[work]["label"], "role_code": code, "role_label_th": name,
                                  "source_id": sid, "target_detail": {"entity_id": work, "measure_id": measure, "topic_id": "k04"}})
        first = rows[0]  # iCommunity writes the title as part of the name; other sources keep it apart
        written = (first["title"] or "") + first["name"] if first["source"] == "icommunity" else first["name"]
        detail = ctx.base(
            "person", entity_id, title(written), [s for s, _ in members],
            locations=[l for l in locations if l], relationships=works,
            listings=[{"label": "ข้อมูลนวัตกรจากแหล่งต้นทาง", "source_id": ctx.source_id[s], "link_scope": "source",
                       "source_url": ctx.site[ctx.source_id[s]], "record_link_availability": "available"}
                      for s in sorted({s for s, _ in members})],
            children={"qualifying_roles": unique(roles)},
            flags={"k02_relationship": "not_established"})
        detail["label_availability"] = "withheld" if detail["label"] in (WITHHELD, "Name unavailable") else "available"
        detail["related_work_count"] = len({w["entity_id"] for w in detail["relationships"]})
        detail["role_codes"] = sorted({r["role_code"] for r in roles})
        detail["flags"]["person_province_basis"] = "source_reported_innovator_location" if detail["province_codes"] else "unavailable"
        detail["flags"].pop("missing_geography")
        out[entity_id] = detail
    return out


# Cultural records (K12, K01B) -------------------------------------------------

def cultural_records(ctx: Context, measure_id: str) -> dict[str, dict]:
    records = ctx.by_record("cultural_records")
    out = {}
    for entity_id in entity_ids(ctx.con, (measure_id,)):
        members = ctx.members["cultural_record", entity_id]
        rows = [records[m] for m in members]
        descriptions, listings, media_rows, locations, codes, related = [], [], [], [], [], []
        for row in rows:
            sid, details = ctx.source_id[row["source"]], json.loads(row["details"] or "{}")
            if row["source"] == "cultural_map":
                for line in (row["description"] or "").split("\n"):
                    kind, _, body = line.partition(": ")
                    if kind in CULTURAL_DESCRIPTIONS:
                        descriptions.append(description(kind, body, sid))
                listing = ctx.listing(row["source"], ctx.name(entity_id, (row["source"], row["record_id"]), row["title"]), row["url"])
                listing["source_dates"] = {k: v for k, v in (details.get("dates") or {}).items() if v}
                listings.append(listing)
                media_rows += [media(i["url"], sid, caption=i.get("caption")) for i in details.get("images") or []]
                codes += [row["category"], *json.loads(row["categories"] or "[]")]
            else:
                descriptions.append(description("description", row["description"], sid))
                media_rows += [media(url, sid) for url in details.get("images") or []]
            locations.append(location(row, sid, "mapped_subject_location"))
            if measure_id == "K01B":  # an area lists the source records it is made of
                related.append({"kind": "source_membership", "label": label(row["title"]), "source_id": sid})
        out[entity_id] = ctx.base(
            "cultural_record", entity_id, ctx.name(entity_id, members[0], rows[0]["title"]), [s for s, _ in members],
            category_codes=sorted({c for c in codes if c}), descriptions=descriptions, listings=listings,
            media=media_rows, locations=[l for l in locations if l], relationships=related)
    return out


# Activities (K03) -------------------------------------------------------------

def activities(ctx: Context) -> dict[str, dict]:
    records = ctx.by_record("activities")
    publications = ctx.by_record("publications")
    names = {r["province_code"]: r["province"] for r in ctx.rows(
        "SELECT DISTINCT province_code, province FROM cultural_records WHERE province_code IS NOT NULL")}
    out = {}
    for entity_id in entity_ids(ctx.con, ("K03",)):
        members = ctx.members["activity", entity_id]
        rows = [records[m] for m in members]
        dates, listings, media_rows, locations, descriptions = [], [], [], [], []
        for row in rows:
            sid = ctx.source_id[row["source"]]
            if row["start_date"] or row["end_date"]:
                dates.append({"start_date": row["start_date"] and str(row["start_date"]),
                              "end_date": row["end_date"] and str(row["end_date"]), "source_id": sid})
            publication = publications.get((row["source"], row["publication_record_id"]))
            if publication:
                if row["source"] == "cultural_map":  # the activity page's own text describes the activity
                    descriptions.append(description("description", publication["text"], sid))
                listing = ctx.listing(row["source"], label(publication["title"]), publication["url"])
                if row["source"] != "cultural_map" and link(publication["url"]):  # AtLocal / iCommunity pages
                    listing |= {"source_url": link(publication["url"]), "link_scope": "record"}
                    listing.pop("record_link_availability")
                listing["published_at"] = publication["published_at"]
                listing["description"] = description("publication", publication["text"], sid)
                listings.append(listing)
                details = json.loads(publication["details"] or "{}")
                media_rows += [media(i["url"], sid, "gallery_image", i.get("caption")) for i in details.get("images") or []]
            for venue in json.loads(row["venues"] or "[]"):
                code = venue.get("province_code")
                if code and venue.get("role") != "online_delivery":
                    locations.append({"location_role": venue.get("role"), "source_id": sid, "province": names.get(code),
                                      "province_code": code})
        conflict = len({(d["start_date"], d["end_date"]) for d in dates}) > 1
        for d in dates:
            d["has_conflict"] = conflict
        out[entity_id] = ctx.base(
            "activity", entity_id, title(rows[0]["name"]), [s for s, _ in members], listings=listings, media=media_rows,
            descriptions=descriptions,
            locations=locations, children={"dates": unique(dates)},
            identity_review={"outcome": "reported_activity", "counting": "separate", "merge_scope": None,
                             "name_quality": "supported"},
            flags={"source_reported_occurrence_not_completion": True})
    return out


# Businesses (K05) and participating businesses (C08_PARTICIPATING) ------------

def operators(ctx: Context, measure_id: str) -> dict[str, dict]:
    records = ctx.by_record("operators")
    offerings = ctx.by_record("offerings")
    sells = defaultdict(list)
    for r in ctx.rows("SELECT * FROM offering_operators"):
        sells[r["source"], r["operator_record_id"]].append((r["source"], r["offering_record_id"]))
    out = {}
    for entity_id in entity_ids(ctx.con, (measure_id,)):
        members = ctx.members["operator", entity_id]
        if measure_id == "C08_PARTICIPATING":  # a participating business is shown as the directory lists it
            members = [m for m in members if m[0] == "learning_area_based"]
        rows = [records[m] for m in members]
        descriptions, locations, related, memberships, participations = [], [], [], [], []
        for key, row in zip(members, rows):
            sid, details = ctx.source_id[row["source"]], json.loads(row["details"] or "{}")
            if row["source"] == "learning_area_based" and measure_id == "C08_PARTICIPATING":
                participations.append({"project": label(details.get("project")), "fiscal_year_be": details.get("fiscal_year_be"),
                                       "research_unit": label(details.get("research_unit")), "source_id": sid})
            descriptions += [description("source_reported_business", q, sid) for q in details.get("evidence") or []]
            descriptions.append(description("source_reported_business", row["description"], sid))
            role = "programme_business_location" if row["source"] == "learning_area_based" else "operator_location"
            locations.append(location(row, sid, role))
            memberships.append({"label": label(row["name"]), "source_id": sid})
            for offering in sells[key]:
                if offering in offerings and label(offerings[offering]["name"]):
                    related.append({"kind": "offers", "label": label(offerings[offering]["name"]), "source_id": sid})
        named = [r for r in rows if r["name_quality"] == "named"]
        name_quality = "supported" if named else "unavailable"
        identity = ctx.identity("operator", entity_id)
        if name_quality == "unavailable":
            identity = {**identity, "outcome": "malformed_name", "name_quality": "unavailable"}
        if measure_id == "C08_PARTICIPATING":
            out[entity_id] = ctx.base(
                "operator", entity_id, title((named or rows)[0]["name"]), [s for s, _ in members],
                locations=[l for l in locations if l],
                identity_review=identity, children={"participations": unique(participations)},
                flags={"person_assessments_withheld": True})
        else:
            out[entity_id] = ctx.base(
                "operator", entity_id, title((named or rows)[0]["name"]), [s for s, _ in members],
                descriptions=descriptions,
                locations=[l for l in locations if l], relationships=related, identity_review=identity,
                children={"source_memberships": unique(memberships)},
                flags={"geography_not_borrowed_from_offerings": True})
    return out


# Product families (K07) -------------------------------------------------------

def offering_families(ctx: Context) -> dict[str, dict]:
    records = ctx.by_record("offerings")
    operators = ctx.by_record("operators")
    innovation_titles = {(r["source"], r["upstream_id"]): r["title"] for r in ctx.rows(
        "SELECT source, upstream_id, any_value(title) AS title FROM innovations GROUP BY ALL")}
    sellers = defaultdict(list)
    for r in ctx.rows("SELECT * FROM offering_operators"):
        sellers[r["source"], r["offering_record_id"]].append((r["source"], r["operator_record_id"]))
    excluded = {(r["source"], r["record_id"]) for r in ctx.rows("SELECT * FROM counting_exclusions WHERE measure_id = 'K07'")}
    out = {}
    for entity_id in entity_ids(ctx.con, ("K07",)):
        members = ctx.members["offering_family", entity_id]
        offerings: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for m in members:
            offerings[ctx.entity_of["offering", *m]].append(m)
        children = []
        for offering_id, keys in sorted(offerings.items()):
            rows = [records[k] for k in keys]
            listings, media_rows, locations, prices, descriptions, related, context = [], [], [], [], [], [], []
            for key, row in zip(keys, rows):
                sid, details = ctx.source_id[row["source"]], json.loads(row["details"] or "{}")
                if row["kind"] == "listed":
                    listing = ctx.listing(row["source"], label(row["name"]), row["url"])
                    if row["source"] == "icommunity" and link(row["url"]):
                        listing |= {"source_url": link(row["url"]), "link_scope": "record"}
                        listing.pop("record_link_availability")
                    elif row["source"] == "atlocal":  # its product pages are not registered sources: no link
                        listing["source_url"] = None
                    listings.append({**listing, "category": label(row["category"])})
                    media_rows += [media(url, sid) for url in details.get("images") or []]
                    if row["price_thb"] in PLACEHOLDER_PRICES:
                        shown = str(int(row["price_thb"]))
                        prices.append({"amounts": [{"value": shown, "status": "unspecified",
                                                    "display_label": f"price unspecified/source reports {shown}"}],
                                       "currency": "THB", "source_id": sid})
                    elif row["price_thb"] is not None or details.get("price_amounts"):  # one price, or a range/choices
                        amounts = [row["price_thb"]] if row["price_thb"] is not None else details["price_amounts"]
                        prices.append({"amounts": [{"value": f"{a:f}".rstrip("0").rstrip("."), "status": "source_reported"} for a in amounts],
                                       "currency": "THB", "source_id": sid})
                descriptions.append(description("listing", row["description"], sid))
                locations.append(location(row, sid, "source_listing_location"))
                related += [{"kind": "source_reported_operator", "label": label(operators[s]["name"]), "source_id": sid}
                            for s in sellers[key] if s in operators and operators[s]["name_quality"] == "named"]
                context += [{"label": label(innovation_titles.get((row["source"], u)))}
                            for u in details.get("innovation_upstream_ids") or [] if innovation_titles.get((row["source"], u))]
            role = "range_evidence" if any(k in excluded for k in keys) else "variant" if len(offerings) > 1 else "family_representation"
            children.append({
                "entity_id": offering_id, "label": label(rows[0]["name"]), "membership_role": role,
                "descriptions": unique([d for d in descriptions if d]), "listings": unique(listings),
                "media": unique([m for m in media_rows if m]), "locations": unique([l for l in locations if l]),
                "relationships": unique([r for r in related if r["label"]]),
                "children": {"prices": unique(prices), "innovation_context": unique(context)}})
        counted = [c for c in children if c["membership_role"] != "range_evidence"] or children
        out[entity_id] = ctx.base(
            "offering_family", entity_id, family_name([c["label"] for c in counted if c["label"]]) or WITHHELD,
            [s for s, _ in members],
            identity_review=ctx.identity("offering_family", entity_id, grouped=len(offerings) > 1),
            children={"offerings": children})
    return out


def family_name(names: list[str]) -> str | None:
    """A family of variants is named by the words its member names share ("เซรั่มกราวเครือขาว" for the
    10, 30 and 120 ml); a single offering, or variants sharing no whole word, by the first name."""
    if len(set(names)) < 2:
        return names[0] if names else None
    shared = names[0]
    for name in names[1:]:
        while not name.startswith(shared):
            shared = shared[:-1]
    shared = shared.rstrip()
    if not all(len(n) == len(shared) or n[len(shared)].isspace() for n in names):
        shared = shared.rsplit(" ", 1)[0] if " " in shared else ""
    words = shared.strip(" -(/,").split(" ")
    while len(words) > 1 and words[-1] in VARIANT_WORDS:
        words.pop()
    shared = " ".join(words)
    return shared if len(shared) >= 4 else names[0]


def build(con, config: dict) -> tuple[dict[str, dict[str, dict]], dict[str, str]]:
    """(topic -> entity_id -> detail record, entity_id -> field context of a reviewed label)."""
    ctx = Context(con, config)
    innovation = innovations(ctx)
    topics = {
        "k01b": cultural_records(ctx, "K01B"),
        "k02": people(ctx, innovation),
        "k03": activities(ctx),
        "k04": innovation,
        "k05": operators(ctx, "K05"),
        "k07": offering_families(ctx),
        "k08": operators(ctx, "C08_PARTICIPATING"),
        "k12": cultural_records(ctx, "K12"),
    }
    # the provinces shown are the provinces the entity is counted in
    measure = {"k01b": "K01B", "k02": "C02_COMMUNITY", "k03": "K03", "k04": "C04_LISTED", "k05": "K05", "k07": "K07",
               "k08": "C08_PARTICIPATING", "k12": "K12"}
    for topic, records in topics.items():
        provinces = defaultdict(list)
        for entity_id, code in con.execute("SELECT entity_id, province_code FROM measure_members WHERE measure_id = ? "
                                           "AND province_code IS NOT NULL ORDER BY ALL", [measure[topic]]).fetchall():
            provinces[entity_id].append(code)
        for entity_id, detail in records.items():
            detail["province_codes"] = provinces[entity_id]
            if "missing_geography" in detail["flags"]:
                detail["flags"]["missing_geography"] = not provinces[entity_id]
    return topics, ctx.contexts


ITEM_EXTRA = {"k02": ("label_availability", "role_codes", "related_work_count")}


def items(topic: str, detail: dict) -> dict:
    return item(detail, *ITEM_EXTRA.get(topic, ()))

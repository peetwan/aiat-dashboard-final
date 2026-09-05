from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.field_contexts import is_contact_exposure_metadata

DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROOT = DASHBOARD_ROOT / "data/public"
BRIEFING_ROOT = PUBLIC_ROOT / "provincial_briefings"
EXECUTIVE_SUMMARY_ROOT = PUBLIC_ROOT / "executive_summaries"
CATALOG_PATH = DASHBOARD_ROOT / "config/source_catalog.json"
CONTRACT_ROOT = DASHBOARD_ROOT / "config/publication_contracts"

RESTRICTED_SOURCE_IDS = {
    "f3_nonthaburi_city_learning",
    "f3_healthcare_nonthaburi",
}

# These match fields that can carry person-level contact or private attributes.  In
# particular, `line` by itself is not banned: it can legitimately mean a train
# line.  A LINE contact is caught by an account-like key or by the value rules.
SENSITIVE_KEY_RULES = (
    (
        "contact key",
        re.compile(
            r"(?:^|_)(?:phone|telephone|tel|mobile|email|e_mail|contact|"
            r"facebook|instagram|tiktok|twitter|social)(?:_|$)"
        ),
    ),
    (
        "LINE account key",
        re.compile(r"(?:^|_)(?:line_id|lineid|line_oa|line_account)(?:_|$)"),
    ),
    (
        "address key",
        re.compile(
            r"(?:^|_)(?:(?:home|residential|mailing|postal)_?address|address)(?:_|$)"
        ),
    ),
    (
        "birth key",
        re.compile(
            r"(?:^|_)(?:birth|birthdate|birthday|date_of_birth|dob)(?:_|$)"
        ),
    ),
    (
        "income key",
        re.compile(r"(?:^|_)(?:income|salary|wage|earnings)(?:_|$)"),
    ),
)

SENSITIVE_THAI_KEY_PARTS = {
    "โทรศัพท์": "phone key",
    "เบอร์โทร": "phone key",
    "อีเมล": "email key",
    "อีเมล์": "email key",
    "ไลน์": "LINE account key",
    "เฟซบุ๊ก": "social key",
    "อินสตาแกรม": "social key",
    "ติ๊กต็อก": "social key",
    "ทวิตเตอร์": "social key",
    "ช่องทางติดต่อ": "contact key",
    "ผู้ติดต่อ": "contact key",
    "ที่อยู่": "address key",
    "วันเกิด": "birth key",
    "วันเดือนปีเกิด": "birth key",
    "รายได้": "income key",
    "เงินเดือน": "income key",
    "ค่าจ้าง": "income key",
}

SENSITIVE_VALUE_RULES = (
    (
        "email value",
        re.compile(r"(?i)(?<![\w.+-])[\w.+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+"),
    ),
    (
        "LINE contact value",
        re.compile(
            r"(?i)(?:\bline\s*(?:id|oa|official|account)?\s*(?:[:：]|@)|"
            r"(?:line\.me|lin\.ee)/|ไลน์\s*(?:ไอดี)?\s*(?:[:：]|@))"
        ),
    ),
    (
        "social contact value",
        re.compile(
            r"(?i)(?:\b(?:facebook|instagram|tiktok|twitter)\b|"
            r"(?:facebook|instagram|tiktok|twitter)\.com/|"
            r"เฟซบุ๊ก|อินสตาแกรม|ติ๊กต็อก|ทวิตเตอร์)"
        ),
    ),
    (
        "explicit phone label",
        re.compile(
            r"(?i)(?:\b(?:phone|telephone|mobile|tel)\s*(?:no\.?|number)?\s*[:：]|"
            r"(?:โทรศัพท์|เบอร์โทร|โทร)\s*[:：])"
        ),
    ),
    (
        "home address value",
        re.compile(
            r"(?i)(?:\b(?:home|residential|mailing)\s+address\b|"
            r"ที่อยู่(?:บ้าน|ปัจจุบัน|ตามทะเบียนบ้าน)|บ้านเลขที่)"
        ),
    ),
    (
        "birth value",
        re.compile(
            r"(?i)(?:\b(?:date\s+of\s+birth|birth\s*date|birthday|dob)\b|"
            r"วัน(?:เดือนปี)?เกิด|ปีเกิด)"
        ),
    ),
    (
        "personal income value",
        re.compile(
            r"(?i)(?:\b(?:personal|household|monthly|annual)\s+income\b|"
            r"\b(?:salary|wage|earnings)\b|"
            r"รายได้(?:ส่วนบุคคล|ครัวเรือน|ต่อเดือน|ต่อปี|เฉลี่ย)|เงินเดือน|ค่าจ้าง)"
        ),
    ),
)

# Thai phone numbers are 9-10 digits domestically (or 8-9 digits after +66).
# Requiring a Thai prefix and scanning strings only avoids treating years and
# numeric dashboard metrics as phone numbers.
THAI_PHONE_VALUE = re.compile(
    r"(?<!\d)(?:(?:\+?66)[\s().-]*[1-9]|0[1-9])(?:[\s().-]*\d){7,8}(?!\d)"
)

OPAQUE_PHONE_VALUE_KEYS = {
    "amount",
    "category_code",
    "code",
    "count",
    "date",
    "external_id",
    "fare",
    "fiscal_year",
    "hash",
    "id",
    "item_id",
    "latitude",
    "longitude",
    "page_id",
    "record_code",
    "record_hash",
    "record_id",
    "resource_id",
    "source_row_number",
    "time",
    "updated_at",
    "year",
}

# These keys are aggregate public measures, not person-level attributes.  They
# are allowed only in the broader non-cultural artifacts that pass them
# explicitly to the scanner; cultural/tourism projections keep the strict rule.
SECONDARY_AGGREGATE_KEY_ALLOWLIST = {
    "income_rank_id",
    "society_economy_wage",
    "wage",
}
PUBLIC_DASHBOARD_AGGREGATE_KEY_ALLOWLIST = {"social"}

# A cultural asset title can legitimately describe a birth story or ceremony.
# Only the birth-text rule is exempted; email, phone, LINE and social detectors
# still apply to titles.  Metric labels/identifiers are likewise definitions,
# not disclosed income values.
VALUE_RULE_EXEMPT_LEAF_KEYS = {
    "birth value": {"title", "title_en", "title_th"},
    "personal income value": {
        "key",
        "label",
        "label_en",
        "label_th",
        "metric_name",
        "title",
        "title_en",
        "title_th",
    },
}

NEGATIVE_AUDIT_FLAG_KEYS = {"contact_fields_exposed"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalise_key(key: object) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(key))
    return re.sub(r"[^a-z0-9ก-๙]+", "_", text.lower()).strip("_")


def sensitive_key_reason(key: object) -> str | None:
    normalised = normalise_key(key)
    for reason, rule in SENSITIVE_KEY_RULES:
        if rule.search(normalised):
            return reason
    raw_key = str(key)
    for part, reason in SENSITIVE_THAI_KEY_PARTS.items():
        if part in raw_key:
            return reason
    return None


def find_privacy_violations(
    payload: Any,
    root_path: str,
    *,
    allowed_sensitive_keys: set[str] | None = None,
) -> list[tuple[str, str]]:
    """Return exact JSON paths without echoing a possibly private value to CI logs."""

    violations: list[tuple[str, str]] = []
    allowed_keys = allowed_sensitive_keys or set()

    def walk(value: Any, path: str, leaf_key: str | None = None) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}"
                normalised_key = normalise_key(key)
                reason = sensitive_key_reason(key)
                is_negative_audit_flag = (
                    normalised_key in NEGATIVE_AUDIT_FLAG_KEYS and child is False
                )
                is_contact_audit_flag = is_contact_exposure_metadata(path.rsplit(".", 1)[-1], str(key), child)
                if (
                    reason is not None
                    and normalised_key not in allowed_keys
                    and not is_negative_audit_flag
                    and not is_contact_audit_flag
                ):
                    violations.append((child_path, reason))
                walk(child, child_path, normalised_key)
            return

        if isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]", leaf_key)
            return

        if not isinstance(value, str):
            return

        for reason, rule in SENSITIVE_VALUE_RULES:
            exempt_leaf_keys = VALUE_RULE_EXEMPT_LEAF_KEYS.get(reason, set())
            if leaf_key not in exempt_leaf_keys and rule.search(value):
                violations.append((path, reason))

        # URLs, opaque identifiers, dates and numeric measures may contain long
        # digit sequences.  Other detectors (email/LINE/social) still run on them.
        if (
            leaf_key not in OPAQUE_PHONE_VALUE_KEYS
            and not (leaf_key or "").endswith("_url")
            and THAI_PHONE_VALUE.search(value)
        ):
            violations.append((path, "Thai phone-like value"))

    walk(payload, root_path)
    return violations


def assert_no_privacy_violations(violations: list[tuple[str, str]]) -> None:
    evidence = "\n".join(
        f"- {path}: {reason}" for path, reason in violations[:40]
    )
    remainder = len(violations) - 40
    if remainder > 0:
        evidence += f"\n- ... and {remainder} more"
    assert not violations, (
        f"Found {len(violations)} contact/private-value projection violations. "
        "Paths are reported without reproducing private values:\n"
        f"{evidence}"
    )


def find_exact_identifier_hits(
    payload: Any,
    identifiers: set[str],
    root_path: str,
) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}"
                if str(key) in identifiers:
                    hits.append((child_path, str(key)))
                walk(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")
        elif isinstance(value, str) and value in identifiers:
            hits.append((path, value))

    walk(payload, root_path)
    return hits


def briefing_paths() -> list[Path]:
    return sorted(
        path
        for path in BRIEFING_ROOT.glob("*.json")
        if path.stem.isdigit()
    )


def executive_summary_paths() -> list[Path]:
    return sorted(
        path
        for path in EXECUTIVE_SUMMARY_ROOT.glob("*.json")
        if path.stem.isdigit()
    )


def test_cultural_geojson_has_no_contact_or_private_attribute_projection():
    payload = read_json(PUBLIC_ROOT / "cultural_points.geojson")
    assert payload["type"] == "FeatureCollection"
    assert payload["features"]

    violations: list[tuple[str, str]] = []
    for index, feature in enumerate(payload["features"]):
        violations.extend(
            find_privacy_violations(
                feature.get("properties", {}),
                f"cultural_points.features[{index}].properties",
            )
        )
    assert_no_privacy_violations(violations)


def test_all_provincial_culture_and_tourism_sections_are_privacy_projected():
    paths = briefing_paths()
    contract = read_json(CONTRACT_ROOT / "provincial_briefings.json")
    expected_files = next(
        output["expected_files"]
        for output in contract["outputs"]
        if "path_glob" in output
    )
    assert len(paths) == expected_files

    violations: list[tuple[str, str]] = []
    for path in paths:
        payload = read_json(path)
        sections = payload["sections"]
        assert {"culture", "tourism"} <= sections.keys()
        from app.publication import _privacy_problems
        problems = _privacy_problems(
            {"sections": {key: sections[key] for key in ("culture", "tourism")}},
            artifact_path=f"provincial_briefings/{path.name}",
            restricted_source_ids=RESTRICTED_SOURCE_IDS,
            profile=contract["privacy_profile"],
            field_contexts=contract["outputs"][0]["field_contexts"],
        )
        violations.extend((path.name, problem) for problem in problems)
    assert_no_privacy_violations(violations)


def test_secondary_value_artifacts_do_not_shadow_contact_rows():
    insights = read_json(PUBLIC_ROOT / "source_insights.json")
    cultural_audit = insights["sources"]["f2_culturalmap_university"]
    assert cultural_audit["privacy_projection"] == {
        "supporting_records_exposed": True,
        "contact_fields_exposed": True,
        "aggregate_counts_only": False,
        "public_work_details": True,
        "account_identifiers_exposed": False,
    }
    from app.publication import _privacy_problems
    contract = read_json(CONTRACT_ROOT / "source_insights.json")
    assert not _privacy_problems(insights, artifact_path="source_insights",
                                restricted_source_ids=RESTRICTED_SOURCE_IDS,
                                profile=contract["privacy_profile"],
                                field_contexts=contract["outputs"][0]["field_contexts"])

    learning = read_json(PUBLIC_ROOT / "learning_dashboard.json")
    learning_projection = {
        key: learning[key]
        for key in (
            "province_rows",
            "unmatched_province_rows",
            "province_links",
            "non_province_tables",
            "non_province_impact",
        )
    }
    unmapped = read_json(PUBLIC_ROOT / "unmapped_records.json")

    violations = find_privacy_violations(
        insights["province_links"],
        "source_insights.province_links",
        allowed_sensitive_keys=SECONDARY_AGGREGATE_KEY_ALLOWLIST,
    )
    violations.extend(
        find_privacy_violations(learning_projection, "learning_dashboard.values")
    )
    violations.extend(
        find_privacy_violations(
            unmapped["sources"],
            "unmapped_records.sources",
            allowed_sensitive_keys=SECONDARY_AGGREGATE_KEY_ALLOWLIST,
        )
    )
    assert_no_privacy_violations(violations)


def test_executive_portfolio_contains_aggregate_values_only():
    insights = read_json(PUBLIC_ROOT / "source_insights.json")
    portfolio = insights["executive_portfolio"]

    status_rows = portfolio["audit"]["status_rows"]
    assert portfolio["audit"]["source_count"] == len(status_rows)
    assert len({row["source_id"] for row in status_rows}) == len(status_rows)
    assert portfolio["audit"]["source_count"] == sum(
        portfolio["audit"][f"{status}_source_count"]
        for status in ("complete", "partial", "mixed")
    )
    headline_metrics = portfolio["headline_metrics"]
    assert headline_metrics
    assert len({item["key"] for item in headline_metrics}) == len(headline_metrics)
    demand = next(
        item for item in headline_metrics
        if item["key"] == "housing_demand_responses"
    )
    demand_summary = read_json(PUBLIC_ROOT / "housing_demand_summary.json")
    assert demand["value"] == demand_summary["record_count"]
    assert demand["value"] >= 0
    violations = find_privacy_violations(
        portfolio,
        "source_insights.executive_portfolio",
        allowed_sensitive_keys=SECONDARY_AGGREGATE_KEY_ALLOWLIST,
    )
    assert_no_privacy_violations(violations)


def test_all_executive_summary_dimensions_and_highlights_are_privacy_projected():
    paths = executive_summary_paths()
    contract = read_json(CONTRACT_ROOT / "executive_summaries.json")
    expected_files = next(
        output["expected_files"]
        for output in contract["outputs"]
        if "path_glob" in output
    )
    assert len(paths) == expected_files

    violations: list[tuple[str, str]] = []
    for path in paths:
        payload = read_json(path)
        dimensions = payload["dimensions"]
        assert isinstance(dimensions, list)
        for dimension_index, dimension in enumerate(dimensions):
            dimension_values = {
                key: value
                for key, value in dimension.items()
                if key != "highlights"
            }
            dimension_path = (
                f"executive_summaries/{path.name}.dimensions[{dimension_index}]"
            )
            violations.extend(
                find_privacy_violations(dimension_values, dimension_path)
            )
            violations.extend(
                find_privacy_violations(
                    dimension.get("highlights", []),
                    f"{dimension_path}.highlights",
                )
            )
    assert_no_privacy_violations(violations)


def test_public_dashboard_value_sections_have_no_contact_or_private_projection():
    dashboard = read_json(PUBLIC_ROOT / "public_dashboard.json")
    dashboard_values = {
        key: dashboard[key]
        for key in ("unmapped", "themes", "metrics", "sources", "provinces")
    }
    violations = find_privacy_violations(
        dashboard_values,
        "public_dashboard.values",
        allowed_sensitive_keys=PUBLIC_DASHBOARD_AGGREGATE_KEY_ALLOWLIST,
    )
    assert_no_privacy_violations(violations)


def test_restricted_source_ids_never_enter_public_value_sections():
    catalog = read_json(CATALOG_PATH)
    catalog_restricted_ids = {
        source["source_id"]
        for source in catalog["sources"]
        if source["value_visibility"] == "restricted_local_only"
    }
    assert catalog_restricted_ids == RESTRICTED_SOURCE_IDS

    dashboard = read_json(PUBLIC_ROOT / "public_dashboard.json")
    dashboard_values = {
        key: dashboard[key]
        for key in ("unmapped", "themes", "metrics", "sources", "provinces")
    }
    hits = find_exact_identifier_hits(
        dashboard_values,
        RESTRICTED_SOURCE_IDS,
        "public_dashboard.values",
    )

    for path in briefing_paths():
        payload = read_json(path)
        hits.extend(
            find_exact_identifier_hits(
                {
                    "executive_signals": payload["executive_signals"],
                    "sections": payload["sections"],
                },
                RESTRICTED_SOURCE_IDS,
                f"provincial_briefings/{path.name}.values",
            )
        )

    evidence = "\n".join(f"- {path}: {source_id}" for path, source_id in hits)
    assert not hits, f"Restricted source IDs reached public value sections:\n{evidence}"


def test_source_coverage_may_name_restricted_sources_only_as_withheld_audit_metadata():
    """source_coverage is an audit artifact, not a value-bearing public projection."""

    coverage = read_json(PUBLIC_ROOT / "source_coverage.json")
    assert coverage["summary"]["restricted_value_leak_count"] == 0
    by_id = {source["source_id"]: source for source in coverage["sources"]}
    assert RESTRICTED_SOURCE_IDS <= by_id.keys()

    for source_id in RESTRICTED_SOURCE_IDS:
        source = by_id[source_id]
        assert source["public_visibility"]["classification"] == "restricted_local_only"
        assert source["records"]["observed_count"] is None
        assert source["records"]["local_record_count_withheld"] is True
        assert source["records"]["serving_projection_count"] is None

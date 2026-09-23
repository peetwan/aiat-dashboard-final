"""Assemble commerce and programme-coverage measures."""

from __future__ import annotations

from collections import defaultdict

from .common import PipelineError, parse_json

COMMERCE_MEASURES = frozenset({"K01A", "K05", "K07"})


def json_cell(value, expected_type, context):
    if isinstance(value, expected_type):
        return value
    try:
        decoded = parse_json(value or ("[]" if expected_type is list else "{}"))
    except (TypeError, ValueError) as exc:
        raise PipelineError(f"Invalid commerce JSON field: {context}") from exc
    if not isinstance(decoded, expected_type):
        raise PipelineError(f"Invalid commerce JSON field: {context}")
    return decoded


def location_subject(row, kind):
    """A relationship endpoint is not ownership of the location assertion."""
    subject = row.get("source_entity_id")
    return bool(subject) and subject == row.get(f"source_{kind}_id")


def assemble_commerce_measures(root, domains):
    """Append evidence-backed commerce and programme-coverage populations."""
    result = {name: list(rows) for name, rows in root.items()}
    identities = {
        (row["measure_id"], row["entity_id"]) for row in result["entity_contributions"]
    }

    def contribute(measure, entity_id, label, table, key):
        identity = (measure, entity_id)
        if identity in identities:
            raise PipelineError("Duplicate commerce root contribution")
        identities.add(identity)
        result["entity_contributions"].append(
            dict(measure_id=measure, entity_id=entity_id, label=label)
        )
        result["evidence_links"].append(
            dict(
                measure_id=measure,
                entity_id=entity_id,
                table=table,
                key=key,
                record_id=entity_id,
                evidence_role="counted_identity",
            )
        )

    def criterion(measure, entity_id, table, key, evidence_id, role):
        if (measure, entity_id) not in identities:
            raise PipelineError("Commerce qualifying evidence has no counted identity")
        result["eligibility_evidence"].append(
            dict(
                measure_id=measure,
                entity_id=entity_id,
                evidence_table=table,
                evidence_key=key,
                evidence_id=evidence_id,
                evidence_role=role,
            )
        )

    def province(measure, entity_id, row, table, key, role):
        if row.get("province_code") and (measure, entity_id) in identities:
            result["province_memberships"].append(
                dict(
                    measure_id=measure,
                    entity_id=entity_id,
                    province_code=str(row["province_code"]),
                    location_role=role,
                    evidence_table=table,
                    evidence_key=key,
                    evidence_id=row[key],
                )
            )

    coverage = domains["programme_coverage"]
    province_index = {
        row["province_code"]: row for row in coverage["province_evidence_index"]
    }
    for row in coverage["measure_contributions"]:
        if row["measure"] != "K01A_supported_target_provinces":
            raise PipelineError("Unexpected programme coverage contribution measure")
        code = row["province_code"]
        item = province_index[code]
        contribute(
            "K01A",
            code,
            item["province_name"],
            "domains/programme_coverage/province_evidence_index",
            "province_code",
        )
        for assertion_id in json_cell(
            row["contributor_ids_json"], list, "coverage contributors"
        ):
            criterion(
                "K01A",
                code,
                "domains/programme_coverage/coverage_assertions",
                "coverage_assertion_id",
                assertion_id,
                "programme_coverage",
            )
        province(
            "K01A",
            code,
            item,
            "domains/programme_coverage/province_evidence_index",
            "province_code",
            "programme_coverage",
        )

    commerce = domains["commerce"]
    families = defaultdict(set)
    for row in commerce["offering_family_members"]:
        families[row["global_offering_id"]].add(row["family_id"])
    for measure, table, key in (
        ("K05", "global_operators", "global_operator_id"),
        ("K07", "offering_families", "family_id"),
    ):
        for row in commerce[table]:
            contribute(
                measure, row[key], row["display_name"], "domains/commerce/" + table, key
            )

    for row in commerce["seller_evidence"]:
        if row.get("global_operator_id"):
            criterion(
                "K05",
                row["global_operator_id"],
                "domains/commerce/seller_evidence",
                "source_seller_evidence_id",
                row["source_seller_evidence_id"],
                "source_reported_operator",
            )
    for row in commerce["listing_evidence"]:
        for family_id in sorted(families[row["global_offering_id"]]):
            criterion(
                "K07",
                family_id,
                "domains/commerce/listing_evidence",
                "source_listing_id",
                row["source_listing_id"],
                "source_reported_offering",
            )
    for row in commerce["reviewed_evidence"]:
        if row["status"] != "supported":
            continue
        if row.get("global_operator_id"):
            criterion(
                "K05",
                row["global_operator_id"],
                "domains/commerce/reviewed_evidence",
                "evidence_id",
                row["evidence_id"],
                "reviewed_supported_operator",
            )
        if row.get("global_offering_id"):
            for family_id in sorted(families[row["global_offering_id"]]):
                criterion(
                    "K07",
                    family_id,
                    "domains/commerce/reviewed_evidence",
                    "evidence_id",
                    row["evidence_id"],
                    "reviewed_supported_offering",
                )
    for row in commerce["locations"]:
        # iCommunity product locations carry an operator relationship as context.
        # That context must not turn the product's province into operator geography.
        if location_subject(row, "operator"):
            province(
                "K05",
                row["global_operator_id"],
                row,
                "domains/commerce/locations",
                "source_location_id",
                row["location_role"],
            )
        if location_subject(row, "offering"):
            for family_id in sorted(families[row["global_offering_id"]]):
                province(
                    "K07",
                    family_id,
                    row,
                    "domains/commerce/locations",
                    "source_location_id",
                    row["location_role"],
                )
    for row in commerce["operator_crosswalk"]:
        details = json_cell(row["source_details_json"], dict, "operator details")
        province(
            "K05",
            row["global_operator_id"],
            {**row, "province_code": details.get("province_code", "")},
            "domains/commerce/operator_crosswalk",
            "source_operator_id",
            "source_operator_location",
        )
    return result

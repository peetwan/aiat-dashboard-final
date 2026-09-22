"""Fail-closed validation for commerce and programme-coverage measures."""

from __future__ import annotations

from collections import defaultdict

from .common import PipelineError
from .relationship_validation import TABLE_PRIMARY_KEYS, ENTITY_MEASURES
from .commerce_measures import COMMERCE_MEASURES, json_cell

_COMMERCE_KEYS = {
    "global_operators": "global_operator_id",
    "global_offerings": "global_offering_id",
    "operator_crosswalk": "source_operator_id",
    "offering_crosswalk": "source_offering_id",
    "listing_evidence": "source_listing_id",
    "seller_evidence": "source_seller_evidence_id",
    "operator_offering_edges": "source_operator_offering_edge_id",
    "locations": "source_location_id",
    "prices": "source_price_id",
    "media": "source_media_id",
    "channels": "source_channel_id",
    "person_operator_links": "source_person_operator_link_id",
    "source_local_boundaries": "source_boundary_id",
    "identity_decisions": "review_id",
    "candidate_pairs": "review_id",
    "measure_results": "measure",
    "measure_contributions": ("measure", "entity_id"),
    "source_files": "path",
}
COMMERCE_TABLE_PRIMARY_KEYS = {
    **{
        f"domains/{domain}/{table}": key
        for domain in ("commerce_baseline", "commerce")
        for table, key in _COMMERCE_KEYS.items()
    },
    "domains/commerce/reviewed_evidence": "evidence_id",
    "domains/commerce/review_coverage": "candidate_id",
    "domains/commerce/reviewed_identity_decisions": "review_id",
    "domains/commerce/reviewed_relationships": "relationship_id",
    "domains/commerce/reported_product_totals": "claim_id",
    "domains/commerce/offering_families": "family_id",
    "domains/commerce/offering_family_members": ("family_id", "global_offering_id"),
    "domains/commerce/offering_family_decisions": "family_id",
    "domains/programme_coverage/coverage_assertions": "coverage_assertion_id",
    "domains/programme_coverage/province_evidence_index": "province_code",
    "domains/programme_coverage/measure_results": "measure",
    "domains/programme_coverage/measure_contributions": ("measure", "entity_id"),
}


def validate_commerce_tables(root, domains, province_rows, enabled_measures):
    checks = {}
    repeated_checks = defaultdict(int)

    def check(name, passed, actual: int | str = ""):
        if not passed:
            raise PipelineError(f"Commerce relationship validation failed: {name}")
        if actual == "":
            repeated_checks[name] += 1
            actual = repeated_checks[name]
        checks[name] = dict(check=name, status="passed", actual=actual)

    expected_measures = ENTITY_MEASURES | COMMERCE_MEASURES
    if "C02_BROADER" in enabled_measures:
        expected_measures = expected_measures | {"C02_BROADER"}
    check(
        "exact implemented commerce scope",
        set(enabled_measures) == expected_measures,
    )
    tables = {
        **root,
        **{
            f"domains/{domain}/{name}": rows
            for domain, group in domains.items()
            for name, rows in group.items()
        },
    }
    for name, key in {**TABLE_PRIMARY_KEYS, **COMMERCE_TABLE_PRIMARY_KEYS}.items():
        if name not in tables:
            # Entity relationship tables are checked by their own validator.
            if name in COMMERCE_TABLE_PRIMARY_KEYS:
                raise PipelineError(f"Missing commerce table: {name}")
            continue
        keys = (key,) if isinstance(key, str) else key
        values = [tuple(row.get(column, "") for column in keys) for row in tables[name]]
        check(
            name + " complete unique keys",
            all(all(value) for value in values) and len(values) == len(set(values)),
            len(values),
        )

    commerce, baseline, coverage = (
        domains[name]
        for name in ("commerce", "commerce_baseline", "programme_coverage")
    )
    operators = {row["global_operator_id"] for row in commerce["global_operators"]}
    offerings = {row["global_offering_id"] for row in commerce["global_offerings"]}
    families = {row["family_id"]: row for row in commerce["offering_families"]}
    operator_members = {
        row["source_operator_id"]: row["global_operator_id"]
        for row in commerce["operator_crosswalk"]
    }
    offering_members = {
        row["source_offering_id"]: row["global_offering_id"]
        for row in commerce["offering_crosswalk"]
    }
    for kind, members in (
        ("operator", operator_members),
        ("offering", offering_members),
    ):
        check(
            f"reviewed commerce preserves every baseline {kind} identity",
            all(
                members.get(row[f"source_{kind}_id"]) == row[f"global_{kind}_id"]
                for row in baseline[f"{kind}_crosswalk"]
            ),
        )
    family_members, product_owners, range_ids = defaultdict(set), {}, set()
    for row in commerce["offering_family_members"]:
        offering, family, role = (
            row["global_offering_id"],
            row["family_id"],
            row["membership_role"],
        )
        check(
            "family member endpoints and role",
            offering in offerings
            and family in families
            and role in {"family_representation", "variant", "range_evidence"},
        )
        family_members[offering].add(family)
        if role == "range_evidence":
            range_ids.add(offering)
        else:
            check(
                "product or variant has one counted family",
                offering not in product_owners,
            )
            product_owners[offering] = family
    check(
        "families preserve all offering drilldown identities",
        set(family_members) == offerings,
        len(offerings),
    )
    check(
        "range evidence does not create an additional product family",
        not range_ids & product_owners.keys(),
        len(range_ids),
    )
    members_by_family = defaultdict(list)
    for row in commerce["offering_family_members"]:
        members_by_family[row["family_id"]].append(row)
    check(
        "family size and identified product support",
        all(
            int(row["member_count"]) == len(members_by_family[family])
            and any(
                member["membership_role"] != "range_evidence"
                for member in members_by_family[family]
            )
            for family, row in families.items()
        ),
        len(families),
    )
    check(
        "reported product totals remain nonadditive",
        all(
            str(row["additive_to_k07"]) == "False"
            and row["membership_status"] == "not_reconciled"
            for row in commerce["reported_product_totals"]
        ),
    )
    candidate_index = {row["candidate_id"]: row for row in commerce["review_coverage"]}
    check(
        "review status governs commerce identity admission",
        all(
            row["status"] in {"supported", "unresolved", "not_established"}
            and (
                (
                    row["global_entity_id"]
                    in (operators if row["entity_kind"] == "operator" else offerings)
                )
                if row["status"] == "supported"
                else not row["global_entity_id"]
            )
            for row in candidate_index.values()
        ),
        len(candidate_index),
    )
    check(
        "reviewed claims retain candidate identity and status",
        all(
            row["candidate_id"] in candidate_index
            and row["status"] == candidate_index[row["candidate_id"]]["status"]
            and row.get(
                "global_operator_id"
                if row["entity_kind"] == "operator"
                else "global_offering_id",
                "",
            )
            == candidate_index[row["candidate_id"]]["global_entity_id"]
            for row in commerce["reviewed_evidence"]
        ),
    )

    province_codes = {str(row["province_code"]) for row in province_rows}
    qualifying = defaultdict(set)
    for row in coverage["coverage_assertions"]:
        check(
            "coverage assertion has known disposition and province",
            row["disposition"]
            in {
                "qualifying_resolved",
                "qualifying_unknown_province",
                "excluded_role_or_context",
            }
            and (not row["province_code"] or row["province_code"] in province_codes),
        )
        if row["disposition"] == "qualifying_resolved":
            check(
                "qualifying programme evidence has a province",
                row["province_code"] in province_codes,
            )
            qualifying[row["province_code"]].add(row["coverage_assertion_id"])
    index = {row["province_code"]: row for row in coverage["province_evidence_index"]}
    check(
        "K01A index is exact qualifying province union",
        index.keys() == qualifying.keys(),
        len(index),
    )
    check(
        "K01A index counts qualifying assertions only",
        all(
            int(row["qualifying_assertion_count"]) == len(qualifying[code])
            for code, row in index.items()
        ),
    )
    coverage_contributions = {
        row["province_code"]: row for row in coverage["measure_contributions"]
    }
    check(
        "K01A domain contributions cover the exact province union",
        coverage_contributions.keys() == qualifying.keys()
        and len(coverage_contributions) == len(coverage["measure_contributions"]),
    )
    for code, row in coverage_contributions.items():
        ids = json_cell(row["contributor_ids_json"], list, "coverage contributors")
        check(
            "K01A contribution keeps every qualifying assertion exactly once",
            row["measure"] == "K01A_supported_target_provinces"
            and len(ids) == len(set(ids))
            and set(ids) == qualifying[code],
        )
    expected = {"K01A": set(qualifying), "K05": operators, "K07": set(families)}
    check(
        "root contributions stay within enabled measures",
        all(
            row["measure_id"] in enabled_measures
            for row in root["entity_contributions"]
        ),
    )
    for measure, population in expected.items():
        actual = {
            row["entity_id"]
            for row in root["entity_contributions"]
            if row["measure_id"] == measure
        }
        check(measure + " exact eligible population", actual == population, len(actual))
    check(
        "commerce domain measures use operators and families",
        {
            (row["measure"], row["entity_id"])
            for row in commerce["measure_contributions"]
        }
        == {("K05_source_supported_operators", entity) for entity in operators}
        | {("K07_source_reported_offerings", entity) for entity in families},
    )
    navigation = {
        (measure, entity, table, key, entity)
        for measure, table, key in (
            (
                "K01A",
                "domains/programme_coverage/province_evidence_index",
                "province_code",
            ),
            ("K05", "domains/commerce/global_operators", "global_operator_id"),
            ("K07", "domains/commerce/offering_families", "family_id"),
        )
        for entity in expected[measure]
    }
    check(
        "commerce counted identities resolve to their actual registries",
        {
            (
                row["measure_id"],
                row["entity_id"],
                row["table"],
                row["key"],
                row["record_id"],
            )
            for row in root["evidence_links"]
            if row["measure_id"] in COMMERCE_MEASURES
        }
        == navigation,
    )
    eligibility = {
        (
            "K01A",
            code,
            "domains/programme_coverage/coverage_assertions",
            "coverage_assertion_id",
            assertion,
        )
        for code, assertions in qualifying.items()
        for assertion in assertions
    }
    eligibility.update(
        (
            "K05",
            row["global_operator_id"],
            "domains/commerce/seller_evidence",
            "source_seller_evidence_id",
            row["source_seller_evidence_id"],
        )
        for row in commerce["seller_evidence"]
        if row.get("global_operator_id")
    )
    eligibility.update(
        (
            "K07",
            family,
            "domains/commerce/listing_evidence",
            "source_listing_id",
            row["source_listing_id"],
        )
        for row in commerce["listing_evidence"]
        for family in family_members[row["global_offering_id"]]
    )
    for row in commerce["reviewed_evidence"]:
        if row["status"] != "supported":
            continue
        if row.get("global_operator_id"):
            eligibility.add(
                (
                    "K05",
                    row["global_operator_id"],
                    "domains/commerce/reviewed_evidence",
                    "evidence_id",
                    row["evidence_id"],
                )
            )
        for family in family_members.get(row.get("global_offering_id"), set()):
            eligibility.add(
                (
                    "K07",
                    family,
                    "domains/commerce/reviewed_evidence",
                    "evidence_id",
                    row["evidence_id"],
                )
            )
    check(
        "commerce root eligibility is exact and supported",
        {
            (
                row["measure_id"],
                row["entity_id"],
                row["evidence_table"],
                row["evidence_key"],
                row["evidence_id"],
            )
            for row in root["eligibility_evidence"]
            if row["measure_id"] in COMMERCE_MEASURES
        }
        == eligibility,
        len(eligibility),
    )
    check(
        "every commerce identity has qualifying evidence",
        {(row[0], row[1]) for row in eligibility}
        == {
            (measure, entity)
            for measure, population in expected.items()
            for entity in population
        },
    )

    provinces = {
        (
            "K01A",
            code,
            code,
            "domains/programme_coverage/province_evidence_index",
            "province_code",
            code,
        )
        for code in qualifying
    }
    for row in commerce["locations"]:
        subject = row["source_entity_id"]
        check(
            "commerce location retains its source subject",
            subject in operator_members or subject in offering_members,
        )
        if not row.get("province_code"):
            continue
        code = str(row["province_code"])
        check("commerce location province is official", code in province_codes)
        if subject in operator_members:
            check(
                "operator location belongs to its mapped identity",
                operator_members[subject] == row.get("global_operator_id")
                and subject == row.get("source_operator_id"),
            )
            provinces.add(
                (
                    "K05",
                    operator_members[subject],
                    code,
                    "domains/commerce/locations",
                    "source_location_id",
                    row["source_location_id"],
                )
            )
        if subject in offering_members:
            check(
                "offering location belongs to its mapped identity",
                offering_members[subject] == row.get("global_offering_id")
                and subject == row.get("source_offering_id"),
            )
            provinces.update(
                (
                    "K07",
                    family,
                    code,
                    "domains/commerce/locations",
                    "source_location_id",
                    row["source_location_id"],
                )
                for family in family_members[offering_members[subject]]
            )
    for row in commerce["operator_crosswalk"]:
        details = json_cell(row["source_details_json"], dict, "operator details")
        if details.get("province_code"):
            code = str(details["province_code"])
            check(
                "operator source location province is official", code in province_codes
            )
            provinces.add(
                (
                    "K05",
                    row["global_operator_id"],
                    code,
                    "domains/commerce/operator_crosswalk",
                    "source_operator_id",
                    row["source_operator_id"],
                )
            )
    check(
        "commerce provinces have exact subject-owned evidence",
        {
            (
                row["measure_id"],
                row["entity_id"],
                row["province_code"],
                row["evidence_table"],
                row["evidence_key"],
                row["evidence_id"],
            )
            for row in root["province_memberships"]
            if row["measure_id"] in COMMERCE_MEASURES
        }
        == provinces,
        len(provinces),
    )
    check(
        "commerce adds no unimplemented category or aggregate measures",
        not any(
            row.get("measure_id") in COMMERCE_MEASURES
            for name in ("category_memberships", "aggregate_breakdowns")
            for row in root[name]
        ),
    )
    return list(checks.values())

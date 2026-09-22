"""Build the complete internal F2 release from all locked source bundles."""

from __future__ import annotations

import importlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .common import (
    PipelineError,
    canonical_json,
    digest,
    load_json,
    local_path,
    output_directory,
    parse_json,
    stable_id,
    write_csv,
    write_json,
)
from .inputs import load_build_config, load_source, validate_sources
from .geography import ThaiGeography
from .measure_query import MeasureQuery
from .reviews import validate_review_inputs
from .domains import cultural_areas, activities
from .relationship_validation import (
    ENTITY_MEASURES,
    TABLE_PRIMARY_KEYS,
    validate_identity_tables,
)
from .domains.raw_inputs import SOURCE_IDS

SOURCE_MODULES = {
    "apptech_mru": "apptech_mru",
    "rinmp": "rinmp",
    "atlocal": "atlocal",
    "cultural_map": "cultural_map_details",
    "icommunity": "icommunity",
    "learning_area_based": "learning_area_based",
    "learning_dashboard": "learning_dashboard",
    "pmua_apptech": "pmua_apptech",
}
SOURCE_PRIMARY_KEYS = {
    "source_observations": "observation_id",
    "innovations": "innovation_id",
    "people": "person_id",
    "businesses": "business_id",
    "mapped_subjects": "subject_id",
    "mapped_listing_observations": "listing_id",
    "category_assertions": "category_assertion_id",
    "mapped_locations": "location_id",
    "offerings": "offering_id",
    "sellers": "seller_id",
    "areas": "area_id",
    "researchers": "researcher_id",
    "universities": "university_id",
    "stations": "station_id",
    "owner_groups": "owner_group_id",
}


@dataclass(frozen=True)
class BuildReport:
    release_id: str
    output_dir: str
    publication_status: str
    source_count: int
    domain_count: int
    measure_values: dict
    file_count: int


def dashboard_provinces(payload: dict) -> list[dict]:
    result = []
    for row in payload["provinces"]:
        region = row.get("dashboard_region", row.get("region"))
        if not isinstance(region, str) or not region:
            raise PipelineError("Dashboard province lacks a pinned region")
        result.append(
            {
                "province_code": row["province_code"],
                "province_name_th": row["province_name_th"],
                "province_name_en": row.get("province_name_en", ""),
                "region": region,
                "region_id": stable_id("region", region),
            }
        )
    return sorted(result, key=lambda row: row["province_code"])


def code_inputs() -> list[dict]:
    root = Path(__file__).parent
    files = [
        (path, "code/" + path.relative_to(root).as_posix())
        for path in sorted(root.rglob("*.py"))
    ]
    files.extend(
        (root.parents[1] / "app" / name, "code/shared/app/" + name)
        for name in ("__init__.py", "privacy.py", "field_contexts.py", "publication.py")
    )
    return [
        {
            "input_kind": "code",
            "source_id": "",
            "run_id": "",
            "path": name,
            "sha256": digest(path),
            "size": path.stat().st_size,
        }
        for path, name in files
    ]


def csv_rows(rows):
    """Use the same scalar boundary as CSV-backed legacy source adapters."""
    return [
        {
            key: canonical_json(value)
            if isinstance(value, (dict, list, tuple))
            else ""
            if value is None
            else str(value)
            for key, value in row.items()
        }
        for row in rows
    ]


def truth(value):
    return value is True or value == "True"


def validate_json_columns(tables):
    """Check the exact cell encoding consumed by the immutable release reader."""
    checked = 0
    for table, rows in tables.items():
        for row in rows:
            for column, value in row.items():
                if not column.endswith("_json") or value is None or value == "":
                    continue
                serialized = (
                    canonical_json(value)
                    if isinstance(value, (dict, list, tuple))
                    else str(value)
                )
                try:
                    parse_json(serialized)
                except (ValueError, TypeError) as exc:
                    raise PipelineError(
                        f"Invalid serialized JSON column: {table}/{column}"
                    ) from exc
                checked += 1
    return dict(check="json_column_serialization", status="passed", actual=checked)


def load_decisions(config_path, inputs, review_root, evidence_root):
    lock = inputs["source_resolution_lock"]
    role_path = next(
        row["path"]
        for row in load_json(config_path)["config_files"]
        if row.get("role") == "source_resolution_lock"
    )
    audit = validate_review_inputs(
        [config_path.parent / role_path],
        review_root,
        inputs["input_lock"],
        evidence_root,
        inputs["migration_inventory"],
    )
    decisions, rows = {}, []
    for entry in lock["entries"]:
        path = local_path(review_root, entry["runtime_path"])
        if digest(path) != entry["runtime_sha256"]:
            raise PipelineError("Reviewed decisions changed after validation")
        key = entry["legacy_path"]
        if key in decisions:
            raise PipelineError("Duplicate logical review input")
        decisions[key] = load_json(path)
        rows.append(
            dict(
                input_kind="private_review",
                source_id="",
                run_id="",
                path="reviews/" + key,
                sha256=entry["runtime_sha256"],
                size=entry["runtime_size"],
            )
        )
    decisions["cultural_map/k12_review.json"] = inputs["reviews"]
    return decisions, rows, audit


def validate_source(source_id, tables):
    observations = tables.get("source_observations", [])
    if not observations:
        raise PipelineError(f"Source has no accounted observations: {source_id}")
    known = {row["observation_id"] for row in observations}
    if len(known) != len(observations) or "" in known:
        raise PipelineError(
            f"Duplicate or empty source observation identity: {source_id}"
        )
    for name, rows in tables.items():
        key = SOURCE_PRIMARY_KEYS.get(name)
        if key and rows and all(key in row for row in rows):
            if len({row[key] for row in rows}) != len(rows):
                raise PipelineError(f"Duplicate source identity: {source_id}/{name}")
        for row in rows:
            observation = row.get("observation_id")
            if observation and observation not in known:
                raise PipelineError(
                    f"Missing source observation endpoint: {source_id}/{name}"
                )
    return dict(
        check="source_identity_and_observation_endpoints",
        source_id=source_id,
        status="passed",
        observation_count=len(known),
    )


def assemble_measures(sources, domains):
    contributions, links, provinces, categories, eligibility = {}, [], [], [], []

    def contribute(measure, entity_id, label, table, key):
        identity = (measure, entity_id)
        if identity in contributions:
            raise PipelineError("Duplicate root measure contribution")
        contributions[identity] = dict(
            measure_id=measure, entity_id=entity_id, label=label
        )
        links.append(
            dict(
                measure_id=measure,
                entity_id=entity_id,
                table=table,
                key=key,
                record_id=entity_id,
                evidence_role="counted_identity",
            )
        )

    def criterion(measure, entity_id, table, key, record_id, role):
        eligibility.append(
            dict(
                measure_id=measure,
                entity_id=entity_id,
                evidence_table=table,
                evidence_key=key,
                evidence_id=record_id,
                evidence_role=role,
            )
        )

    def province(measure, entity_id, row, role, table, key):
        if (measure, entity_id) in contributions and row.get("province_code"):
            provinces.append(
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

    cultural = sources[SOURCE_IDS["cultural_map"]]
    for row in cultural["mapped_subjects"]:
        if truth(row["k12_eligible"]):
            contribute(
                "K12",
                row["subject_id"],
                row["display_title"],
                "sources/" + SOURCE_IDS["cultural_map"] + "/mapped_subjects",
                "subject_id",
            )
    for row in domains["areas"]["global_cultural_areas"]:
        if truth(row["k01b_eligible"]):
            contribute(
                "K01B",
                row["global_area_id"],
                row["display_name"],
                "domains/areas/global_cultural_areas",
                "global_area_id",
            )
    for row in domains["activities"]["global_activities"]:
        contribute(
            "K03",
            row["global_activity_id"],
            row["name"],
            "domains/activities/global_activities",
            "global_activity_id",
        )
    innovation_index = {
        row["global_innovation_id"]: row
        for row in domains["innovations"]["global_innovations"]
    }
    for row in domains["innovations"]["measure_contributions"]:
        measure = row["measure"]
        if measure not in {"K04", "C04_LISTED"}:
            continue
        item = innovation_index[row["global_innovation_id"]]
        label = (
            item.get("display_name")
            or item.get("display_title")
            or item.get("preferred_title")
            or item.get("title")
            or item["global_innovation_id"]
        )
        contribute(
            measure,
            item["global_innovation_id"],
            label,
            "domains/innovations/global_innovations",
            "global_innovation_id",
        )
    people_index = {
        row["global_person_id"]: row for row in domains["people"]["global_people"]
    }
    for row in domains["people"]["measure_contributions"]:
        measure = row["measure_id"]
        if measure not in {
            "C02_COMMUNITY",
            "C08_ASSESSED_PEOPLE",
            "C08_INCREASED_PEOPLE",
        }:
            continue
        item = people_index[row["global_person_id"]]
        contribute(
            measure,
            item["global_person_id"],
            item.get("display_name", item["global_person_id"]),
            "domains/people/global_people",
            "global_person_id",
        )
    for row in domains["people"]["person_location_assertions"]:
        province(
            "C02_COMMUNITY",
            row["global_person_id"],
            row,
            row["location_role"],
            "domains/people/person_location_assertions",
            "location_assertion_id",
        )
    for row in domains["activities"]["activity_venues"]:
        province(
            "K03",
            row["global_activity_id"],
            row,
            row["location_role"],
            "domains/activities/activity_venues",
            "venue_assertion_id",
        )
    for row in domains["innovations"]["innovation_use_locations"]:
        if row["coverage_eligibility"] in {
            "eligible_innovation_use",
            "eligible_programme_target_or_use_coverage",
        }:
            for measure in ("K04", "C04_LISTED"):
                province(
                    measure,
                    row["global_innovation_id"],
                    row,
                    row["location_role"],
                    "domains/innovations/innovation_use_locations",
                    "location_id",
                )
    area_members = {}
    for row in domains["areas"]["area_crosswalk"]:
        if truth(row["k01b_eligible"]):
            area_members.setdefault((row["source"], row["local_entity_id"]), []).append(
                row["global_area_id"]
            )
    for alias, table, entity_key in [
        ("cultural_map", "mapped_locations", "subject_id"),
        ("atlocal", "locations", "entity_id"),
    ]:
        source_id = SOURCE_IDS[alias]
        for row in sources[source_id][table]:
            path = f"sources/{source_id}/{table}"
            if alias == "cultural_map":
                province(
                    "K12",
                    row[entity_key],
                    row,
                    row["location_role"],
                    path,
                    "location_id",
                )
            for area_id in area_members.get((alias, row[entity_key]), []):
                province(
                    "K01B", area_id, row, row["location_role"], path, "location_id"
                )
    for row in cultural["category_assertions"]:
        if ("K12", row["subject_id"]) in contributions:
            categories.append(
                dict(
                    measure_id="K12",
                    entity_id=row["subject_id"],
                    category_code=row["category_code"],
                    category_name_th=row.get("category_name_th"),
                    category_kind=row["category_kind"],
                    evidence_table="sources/"
                    + SOURCE_IDS["cultural_map"]
                    + "/category_assertions",
                    evidence_key="category_assertion_id",
                    evidence_id=row["category_assertion_id"],
                )
            )
    for row in cultural["mapped_listing_observations"]:
        if ("K12", row["subject_id"]) in contributions:
            criterion(
                "K12",
                row["subject_id"],
                "sources/"
                + SOURCE_IDS["cultural_map"]
                + "/mapped_listing_observations",
                "listing_id",
                row["listing_id"],
                "source_mapped_listing",
            )
    for row in domains["areas"]["area_assertions"]:
        if truth(row["k01b_eligible"]):
            criterion(
                "K01B",
                row["global_area_id"],
                "domains/areas/area_assertions",
                "assertion_id",
                row["assertion_id"],
                "source_supported_cultural_area",
            )
    for row in domains["activities"]["activity_publication_links"]:
        if ("K03", row["global_activity_id"]) in contributions:
            criterion(
                "K03",
                row["global_activity_id"],
                "domains/activities/activity_publication_links",
                "source_publication_id",
                row["source_publication_id"],
                "activity_publication",
            )
    for row in domains["innovations"]["measure_contributions"]:
        if row["measure"] == "K04":
            for assessment_id in json.loads(row["qualifying_assessment_ids_json"]):
                criterion(
                    "K04",
                    row["global_innovation_id"],
                    "domains/innovations/readiness_evidence",
                    "assessment_id",
                    assessment_id,
                    "qualifying_readiness_assessment",
                )
        elif row["measure"] == "C04_LISTED":
            criterion(
                "C04_LISTED",
                row["global_innovation_id"],
                "domains/innovations/global_innovations",
                "global_innovation_id",
                row["global_innovation_id"],
                "listed_innovation_identity",
            )
    for row in domains["people"]["measure_contributions"]:
        measure = row["measure_id"]
        if measure == "C02_COMMUNITY":
            table, key, role = (
                "person_assertions",
                "assertion_id",
                "source_supported_person_role",
            )
        elif measure in {"C08_ASSESSED_PEOPLE", "C08_INCREASED_PEOPLE"}:
            table, key = "development_assessments", "assessment_id"
            role = (
                "complete_paired_assessment_with_increase"
                if measure == "C08_INCREASED_PEOPLE"
                else "complete_paired_assessment"
            )
        else:
            raise PipelineError("Unexpected person measure at checkpoint boundary")
        for evidence_id in json.loads(row["qualifying_assertion_ids_json"]):
            criterion(
                measure,
                row["global_person_id"],
                "domains/people/" + table,
                key,
                evidence_id,
                role,
            )
    populations = defaultdict(set)
    for measure, entity_id in contributions:
        populations[measure].add(entity_id)
    for smaller, larger in [
        ("K04", "C04_LISTED"),
        ("C08_INCREASED_PEOPLE", "C08_ASSESSED_PEOPLE"),
    ]:
        if not populations.get(smaller, set()) <= populations.get(larger, set()):
            raise PipelineError(
                f"Required measure subset does not hold: {smaller}/{larger}"
            )
    return dict(
        entity_contributions=list(contributions.values()),
        evidence_links=links,
        eligibility_evidence=eligibility,
        province_memberships=provinces,
        category_memberships=categories,
        aggregate_breakdowns=[],
    )


def validate_full_release_contract(root, results, selected):
    """Fail closed on the published internal root-table and result contract."""
    required = {
        "aggregate_breakdowns",
        "category_memberships",
        "entity_contributions",
        "evidence_links",
        "eligibility_evidence",
        "measure_dictionary",
        "province_coverage",
        "province_memberships",
        "provinces",
        "validation_checks",
    }
    missing = sorted(required - root.keys())
    if missing:
        raise PipelineError(
            "Full release lacks required root tables: " + ", ".join(missing)
        )
    measure_ids = [row.get("measure_id") for row in selected]
    if len(measure_ids) != 21 or len(set(measure_ids)) != 21:
        raise PipelineError(
            "Full release requires exactly twenty-one measure definitions"
        )
    if set(results) != set(measure_ids):
        raise PipelineError("Full release results do not cover every measure")
    coverage_ids = [row.get("measure_id") for row in root["province_coverage"]]
    if len(coverage_ids) != 21 or set(coverage_ids) != set(measure_ids):
        raise PipelineError("Full release lacks unique complete measure coverage rows")
    dictionary_ids = [row.get("measure_id") for row in root["measure_dictionary"]]
    if len(dictionary_ids) != 21 or set(dictionary_ids) != set(measure_ids):
        raise PipelineError(
            "Full release lacks unique complete measure dictionary rows"
        )
    dictionary_fields = {
        "measure_id",
        "kind",
        "display_order",
        "label_th",
        "requested_label_th",
        "unit",
        "formula",
        "scope",
        "status",
        "supported_filters",
        "permitted_filter_combinations",
        "drilldown",
        "limitations",
        "parent_measure_id",
    }
    if any(not dictionary_fields <= row.keys() for row in root["measure_dictionary"]):
        raise PipelineError("Full release measure dictionary lacks required metadata")
    headline_count = sum(row.get("kind") == "headline" for row in selected)
    companion_count = sum(row.get("kind") == "companion" for row in selected)
    if (headline_count, companion_count) != (14, 7):
        raise PipelineError(
            "Full release requires fourteen headline and seven companion results"
        )
    return {
        "check": "full internal root-table contract",
        "status": "passed",
        "actual": "21 measures; 14 headline; 7 companion",
    }


def build_internal_release(config_path, evidence_root, output_dir, *, review_root=None):
    config_path, evidence_root, output_dir = (
        Path(config_path),
        Path(evidence_root),
        Path(output_dir),
    )
    review_root = (
        Path(review_root)
        if review_root is not None
        else Path(__file__).resolve().parents[2]
    )
    config, inputs, config_rows = load_build_config(config_path)
    if "c02_projection_extension" in inputs:
        from .c02_projection import apply_c02_projection_policy

        acceptance = None
        acceptance_ref = config.get("c02_owner_acceptance")
        if acceptance_ref is not None:
            if (
                not isinstance(acceptance_ref, dict)
                or set(acceptance_ref) != {"path", "sha256"}
                or acceptance_ref.get("path")
                != "data/runtime/f2/checkpoints/c02-local-promotion-v1/owner-field-acceptance.json"
            ):
                raise PipelineError("C02 owner acceptance reference is malformed")
            acceptance_path = local_path(review_root, acceptance_ref["path"])
            if (
                not acceptance_path.is_file()
                or digest(acceptance_path) != acceptance_ref.get("sha256")
            ):
                raise PipelineError("C02 owner acceptance bytes changed or are missing")
            acceptance = load_json(acceptance_path)
            config_rows.append(
                {
                    "input_kind": "owner_acceptance",
                    "source_id": "",
                    "run_id": "",
                    "path": acceptance_ref["path"],
                    "sha256": acceptance_ref["sha256"],
                    "size": acceptance_path.stat().st_size,
                }
            )
        geography_acceptance = None
        geography_acceptance_ref = config.get("c02_geography_acceptance")
        if geography_acceptance_ref is not None:
            geography_path_value = (
                geography_acceptance_ref.get("path")
                if isinstance(geography_acceptance_ref, dict)
                else ""
            )
            if (
                not isinstance(geography_acceptance_ref, dict)
                or set(geography_acceptance_ref) != {"path", "sha256"}
                or not geography_path_value.startswith(
                    "data/runtime/f2/checkpoints/"
                )
                or not geography_path_value.endswith(
                    "/owner-geography-acceptance.json"
                )
            ):
                raise PipelineError(
                    "C02 geography acceptance reference is malformed"
                )
            geography_acceptance_path = local_path(
                review_root, geography_path_value
            )
            if (
                not geography_acceptance_path.is_file()
                or digest(geography_acceptance_path)
                != geography_acceptance_ref.get("sha256")
            ):
                raise PipelineError(
                    "C02 geography acceptance bytes changed or are missing"
                )
            geography_acceptance = load_json(geography_acceptance_path)
            config_rows.append(
                {
                    "input_kind": "owner_acceptance",
                    "source_id": "",
                    "run_id": "",
                    "path": geography_path_value,
                    "sha256": geography_acceptance_ref["sha256"],
                    "size": geography_acceptance_path.stat().st_size,
                }
            )
        inputs["projection_policy"] = apply_c02_projection_policy(
            inputs["projection_policy"],
            inputs["c02_projection_extension"],
            acceptance,
            geography_acceptance,
        )
        if (
            config.get("private_revision_id")
            != inputs["projection_policy"]["private_revision_id"]
        ):
            raise PipelineError(
                "C02 config and projection policy private revisions differ"
            )
    if config.get("profile") != "full":
        raise PipelineError("The F2 builder supports only complete full releases")
    evidence_rows = validate_sources(
        inputs["input_lock"], evidence_root, config["enabled_sources"]
    )
    reviews, review_rows, review_audit = load_decisions(
        config_path, inputs, review_root, evidence_root
    )
    geography = ThaiGeography(
        local_path(config_path.parent, config["geography_directory"])
    )
    province_rows = dashboard_provinces(inputs["dashboard_provinces"])
    geography.check_dashboard(province_rows)
    if len(province_rows) != config["expected_province_count"]:
        raise PipelineError("Incomplete dashboard province reference")
    raw_inputs, source_tables, source_columns, checks = {}, {}, {}, []
    for alias, module_name in SOURCE_MODULES.items():
        source_id = SOURCE_IDS[alias]
        datasets, metadata = load_source(
            inputs["input_lock"], evidence_root, source_id, include_support=True
        )
        locked = next(
            row
            for row in inputs["input_lock"]["sources"]
            if row["source_id"] == source_id
        )
        raw_inputs[source_id] = dict(
            datasets=datasets, metadata=metadata, files=locked["files"]
        )
        source_reviews = {
            key[len(alias) + 1 :]: value
            for key, value in reviews.items()
            if key.startswith(alias + "/")
        }
        module = importlib.import_module("tools.f2_pipeline.sources." + module_name)
        required_datasets = getattr(module, "DATASET_KEYS", tuple(datasets))
        if not set(required_datasets) <= datasets.keys():
            raise PipelineError(
                f"Missing required normalized source capture: {source_id}"
            )
        source_datasets = {key: datasets[key] for key in required_datasets}
        source_metadata = {key: metadata[key] for key in required_datasets}
        tables = module.build_tables(
            source_datasets, source_reviews, geography, source_metadata
        )
        checks.append(validate_source(source_id, tables))
        source_tables[source_id] = {
            name: csv_rows(rows) for name, rows in tables.items()
        }
        source_columns[source_id] = getattr(module, "TABLE_COLUMNS", {})
    from .domains import innovations, people

    domain_modules = {
        "areas": cultural_areas,
        "activities": activities,
        "innovations": innovations,
        "people": people,
    }
    domain_tables = {}
    for name, module in domain_modules.items():
        args = (source_tables, reviews, raw_inputs, geography)
        tables = (
            module.build_tables(*args, domain_tables["innovations"])
            if name == "people"
            else module.build_tables(*args)
        )
        domain_tables[name] = {table: csv_rows(rows) for table, rows in tables.items()}
        checks.append(
            dict(
                check="domain_build_and_protected_identity_validation",
                domain=name,
                status="passed",
            )
        )
    from .commerce_measures import COMMERCE_MEASURES, assemble_commerce_measures
    from .commerce_validation import (
        COMMERCE_TABLE_PRIMARY_KEYS,
        validate_commerce_tables,
    )
    from .domains import aggregates, commerce, reviewed_commerce, programme_coverage
    from .aggregate_measures import (
        AGGREGATE_TABLE_PRIMARY_KEYS,
        assemble_aggregate_measures,
        validate_aggregate_tables,
    )

    for name, module, dependencies in (
        ("commerce_baseline", commerce, ("people",)),
        (
            "commerce",
            reviewed_commerce,
            ("commerce_baseline", "people", "innovations"),
        ),
        ("programme_coverage", programme_coverage, ("innovations",)),
    ):
        domain_modules[name] = module
        tables = module.build_tables(
            source_tables,
            reviews,
            raw_inputs,
            geography,
            *(domain_tables[dependency] for dependency in dependencies),
        )
        domain_tables[name] = {
            table: csv_rows(rows) for table, rows in tables.items()
        }
        checks.append(
            dict(
                check="domain_build_and_protected_identity_validation",
                domain=name,
                status="passed",
            )
        )
    root = assemble_commerce_measures(
        assemble_measures(source_tables, domain_tables), domain_tables
    )
    entity_root = {
        name: [
            row
            for row in rows
            if row.get("measure_id") not in COMMERCE_MEASURES
        ]
        for name, rows in root.items()
    }
    checks.extend(
        validate_identity_tables(
            entity_root,
            source_tables,
            domain_tables,
            province_rows,
            [
                measure
                for measure in config["enabled_measures"]
                if measure in ENTITY_MEASURES
            ],
        )
    )
    checks.extend(
        validate_commerce_tables(
            root,
            domain_tables,
            province_rows,
            [
                measure
                for measure in config["enabled_measures"]
                if measure in ENTITY_MEASURES | COMMERCE_MEASURES
            ],
        )
    )
    domain_modules["aggregates"] = aggregates
    domain_tables["aggregates"] = {
        name: csv_rows(rows)
        for name, rows in aggregates.build_tables(
            source_tables, reviews, raw_inputs, geography
        ).items()
    }
    root = assemble_aggregate_measures(
        root, domain_tables["aggregates"], inputs["measures"]["measures"]
    )
    checks.extend(
        validate_aggregate_tables(
            root,
            source_tables,
            domain_tables["aggregates"],
            inputs["measures"]["measures"],
            province_rows,
        )
    )
    additional_keys = {
        **COMMERCE_TABLE_PRIMARY_KEYS,
        **AGGREGATE_TABLE_PRIMARY_KEYS,
    }
    root["provinces"] = province_rows
    definitions = inputs["measures"]["measures"]
    selected = [
        row for row in definitions if row["measure_id"] in config["enabled_measures"]
    ]
    if len(selected) != len(config["enabled_measures"]):
        raise PipelineError("Missing or duplicate full-release measure definition")
    results, coverage = {}, []
    for definition in selected:
        query = MeasureQuery(definition, root, province_rows)
        selection = query.select()
        results[definition["measure_id"]] = selection["result"]
        coverage.append(
            dict(measure_id=definition["measure_id"], **selection["coverage"])
        )
    root["province_coverage"] = coverage
    root["measure_dictionary"] = selected
    root["validation_checks"] = checks
    checks.append(validate_full_release_contract(root, results, selected))
    all_tables = {
        **root,
        **{
            f"sources/{sid}/{name}": rows
            for sid, tables in source_tables.items()
            for name, rows in tables.items()
        },
        **{
            f"domains/{domain}/{name}": rows
            for domain, tables in domain_tables.items()
            for name, rows in tables.items()
        },
    }
    checks.append(validate_json_columns(all_tables))
    root_empty = {
        "aggregate_breakdowns": ["measure_id", "breakdown_id"],
        "category_memberships": ["measure_id", "entity_id", "category_code"],
        "province_memberships": ["measure_id", "entity_id", "province_code"],
        "evidence_links": ["measure_id", "entity_id", "table", "key", "record_id"],
        "eligibility_evidence": [
            "measure_id",
            "entity_id",
            "evidence_table",
            "evidence_key",
            "evidence_id",
            "evidence_role",
        ],
        "entity_contributions": ["measure_id", "entity_id", "label"],
    }
    protected = (
        evidence_root,
        config_path.parent,
        review_root / "data/runtime/f2/reviews",
        Path(__file__).resolve().parents[2] / "data/public",
    )
    with output_directory(output_dir, protected) as stage:
        catalog = []
        catalog_keys = {
            **TABLE_PRIMARY_KEYS,
            **additional_keys,
            "provinces": "province_code",
            "province_coverage": "measure_id",
            "measure_dictionary": "measure_id",
        }
        domain_entities = {
            "areas": (("global_cultural_areas", "global_area_id"),),
            "activities": (("global_activities", "global_activity_id"),),
            "innovations": (("global_innovations", "global_innovation_id"),),
            "people": (("global_people", "global_person_id"),),
            "commerce_baseline": (
                ("global_operators", "global_operator_id"),
                ("global_offerings", "global_offering_id"),
            ),
            "commerce": (
                ("global_operators", "global_operator_id"),
                ("global_offerings", "global_offering_id"),
                ("offering_families", "family_id"),
            ),
            "programme_coverage": (),
            "aggregates": (),
        }
        for name, rows in sorted(all_tables.items()):
            declared = root_empty.get(name, [])
            if name.startswith("sources/"):
                _, sid, table = name.split("/", 2)
                declared = source_columns[sid].get(table, [])
            elif name.startswith("domains/"):
                _, domain, table = name.split("/", 2)
                declared = getattr(domain_modules[domain], "TABLE_COLUMNS", {}).get(
                    table, []
                )
            fields = sorted({key for row in rows for key in row} | set(declared))
            if not fields:
                raise PipelineError(
                    f"Missing schema for empty checkpoint table: {name}"
                )
            path = name + ".csv"
            write_csv(stage / path, rows, fields)
            primary_key = catalog_keys.get(name, "")
            foreign_keys = {}
            if name.startswith("sources/"):
                candidate = SOURCE_PRIMARY_KEYS.get(table, "")
                if candidate and candidate in fields:
                    primary_key = candidate
                if table != "source_observations" and "observation_id" in fields:
                    foreign_keys["source_observation"] = {
                        "columns": ["observation_id"],
                        "target_table": f"sources/{sid}/source_observations",
                        "target_columns": ["observation_id"],
                        "nullable": True,
                    }
            elif name.startswith("domains/"):
                for entity_table, entity_key in domain_entities[domain]:
                    if table != entity_table and entity_key in fields:
                        relationship = (
                            "global_identity"
                            if len(domain_entities[domain]) == 1
                            else entity_key
                        )
                        foreign_keys[relationship] = {
                            "columns": [entity_key],
                            "target_table": f"domains/{domain}/{entity_table}",
                            "target_columns": [entity_key],
                            "nullable": True,
                        }
                if domain in {"commerce_baseline", "commerce"}:
                    for kind in ("operator", "offering"):
                        source_key = f"source_{kind}_id"
                        target = f"{kind}_crosswalk"
                        if table != target and source_key in fields:
                            foreign_keys[f"source_{kind}"] = {
                                "columns": [source_key],
                                "target_table": f"domains/{domain}/{target}",
                                "target_columns": [source_key],
                                "nullable": True,
                            }
                    if table == "person_operator_links":
                        foreign_keys["person_identity"] = {
                            "columns": ["global_person_id"],
                            "target_table": "domains/people/global_people",
                            "target_columns": ["global_person_id"],
                            "nullable": False,
                        }
                    if table == "reviewed_evidence":
                        foreign_keys["reviewed_candidate"] = {
                            "columns": ["candidate_id"],
                            "target_table": "domains/commerce/review_coverage",
                            "target_columns": ["candidate_id"],
                            "nullable": False,
                        }
                    if table == "reviewed_relationships":
                        for kind, column in (
                            ("operator", "subject_global_id"),
                            ("offering", "object_global_id"),
                        ):
                            foreign_keys[kind] = {
                                "columns": [column],
                                "target_table": f"domains/commerce/global_{kind}s",
                                "target_columns": [f"global_{kind}_id"],
                                "nullable": False,
                            }
                if domain == "programme_coverage" and "province_code" in fields:
                    foreign_keys["province"] = {
                        "columns": ["province_code"],
                        "target_table": "provinces",
                        "target_columns": ["province_code"],
                        "nullable": True,
                    }
                if domain == "aggregates" and {
                    "evidence_table",
                    "evidence_key",
                    "evidence_id",
                } <= set(fields):
                    foreign_keys["evidence_record"] = {
                        "table_column": "evidence_table",
                        "key_column": "evidence_key",
                        "value_column": "evidence_id",
                    }
            elif name in {
                "evidence_links",
                "eligibility_evidence",
                "province_memberships",
                "category_memberships",
            }:
                foreign_keys["counted_identity"] = {
                    "columns": ["measure_id", "entity_id"],
                    "target_table": "entity_contributions",
                    "target_columns": ["measure_id", "entity_id"],
                    "nullable": False,
                }
                foreign_keys["evidence_record"] = (
                    {
                        "table_column": "table",
                        "key_column": "key",
                        "value_column": "record_id",
                    }
                    if name == "evidence_links"
                    else {
                        "table_column": "evidence_table",
                        "key_column": "evidence_key",
                        "value_column": "evidence_id",
                    }
                )
                if name == "province_memberships":
                    foreign_keys["province"] = {
                        "columns": ["province_code"],
                        "target_table": "provinces",
                        "target_columns": ["province_code"],
                        "nullable": False,
                    }
            elif name == "aggregate_breakdowns":
                foreign_keys["evidence_record"] = {
                    "table_column": "evidence_table",
                    "key_column": "evidence_key",
                    "value_column": "evidence_id",
                }
            catalog.append(
                dict(
                    table=name,
                    path=path,
                    row_count=len(rows),
                    fields_json=fields,
                    primary_key=canonical_json(primary_key)
                    if isinstance(primary_key, tuple)
                    else primary_key,
                    foreign_keys_json=foreign_keys,
                )
            )
        write_csv(stage / "table_catalog.csv", catalog)
        write_csv(
            stage / "input_manifest.csv",
            evidence_rows + config_rows + review_rows + code_inputs(),
        )
        write_json(stage / "definitions.json", inputs["measures"])
        write_json(stage / "results.json", results)
        write_csv(
            stage / "kpi_results.csv",
            [
                dict(measure_id=row["measure_id"], **results[row["measure_id"]])
                for row in selected
                if row["kind"] == "headline"
            ],
        )
        write_csv(
            stage / "companion_results.csv",
            [
                dict(measure_id=row["measure_id"], **results[row["measure_id"]])
                for row in selected
                if row["kind"] == "companion"
            ],
        )
        write_json(stage / "projection_policy.json", inputs["projection_policy"])
        write_json(stage / "review_input_audit.json", review_audit)
        files = [
            dict(
                path=path.relative_to(stage).as_posix(),
                sha256=digest(path),
                size=path.stat().st_size,
            )
            for path in sorted(stage.rglob("*"))
            if path.is_file()
        ]
        write_json(
            stage / "manifest.json",
            dict(
                schema_version=1,
                profile=config["profile"],
                release_id=config["release_id"],
                release_date=config["release_date"],
                complete=config["complete"],
                publication_status=config["publication_status"],
                enabled_sources=config["enabled_sources"],
                enabled_measures=config["enabled_measures"],
                input_lock_sha256=next(
                    row["sha256"]
                    for row in config["config_files"]
                    if row.get("role") == "input_lock"
                ),
                validation_status="passed",
                known_exceptions=inputs["input_lock"].get("integrity_exceptions", []),
                files=files,
                owner_checkpoint="full_internal_comparison_review_pending_public_projection_policy",
                privacy_scope="internal_only_no_person_directory_publication",
            ),
        )
    return BuildReport(
        config["release_id"],
        str(output_dir),
        config["publication_status"],
        len(source_tables),
        len(domain_tables),
        {key: value["value"] for key, value in results.items()},
        len(files) + 1,
    )

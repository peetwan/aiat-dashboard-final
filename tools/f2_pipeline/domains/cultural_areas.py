"""Accepted cross-source cultural areas from fresh, source-local identities."""

from __future__ import annotations

import json
from collections import defaultdict

from ..common import Components, PipelineError, stable_id
from .raw_inputs import SOURCE_IDS, observation_record

TABLE_COLUMNS = {
    "global_cultural_areas": [
        "global_area_id",
        "display_name",
        "k01b_eligible",
        "source_member_count",
        "identity_status",
    ],
    "area_crosswalk": [
        "global_area_id",
        "source_member_id",
        "source",
        "local_entity_id",
        "display_name",
        "k01b_eligible",
        "primary_category_codes_json",
    ],
    "area_assertions": [
        "assertion_id",
        "source_member_id",
        "source",
        "observation_id",
        "source_key",
        "source_id",
        "title_raw",
        "primary_category_code",
        "k01b_eligible",
        "raw_file",
        "row_locator",
        "file_sha256",
        "captured_at",
        "source_local_record_json",
        "raw_record_json",
        "global_area_id",
    ],
    "identity_decisions": [
        "decision_id",
        "left_source_member_id",
        "right_source_member_id",
        "decision",
        "evidence",
        "review_status",
        "left_global_area_id",
        "right_global_area_id",
    ],
    "measure_contributions": [
        "measure_id",
        "global_area_id",
        "source_member_id",
        "source",
        "eligible",
        "eligibility_basis",
    ],
    "measure_results": ["measure_id", "value", "unit", "status"],
    "source_files": ["source_id", "file", "sha256"],
}


def _source_file(raw_inputs, source_id, dataset):
    bundle = raw_inputs.get(source_id)
    metadata = (
        bundle.get("metadata", {}).get(dataset) if isinstance(bundle, dict) else None
    )
    if (
        not isinstance(metadata, dict)
        or metadata.get("source_id") != source_id
        or not metadata.get("file")
        or not metadata.get("sha256")
    ):
        raise PipelineError(
            f"Cultural-area source metadata is missing or mismatched: {source_id}/{dataset}"
        )
    return {
        "source_id": source_id,
        "file": metadata["file"],
        "sha256": metadata["sha256"],
    }


def build_tables(source_tables, review_inputs, raw_inputs, geography):
    reviews = review_inputs["cross_source_cultural_areas/reviews.json"]
    runtime = review_inputs["cross_source_cultural_areas/runtime.json"]
    expected_counts = (
        runtime.get("expected_counts") if isinstance(runtime, dict) else None
    )
    if (
        not isinstance(runtime, dict)
        or runtime.get("schema_version") != 1
        or not isinstance(expected_counts, dict)
    ):
        raise PipelineError("Unsupported cultural-area runtime review")
    atlocal = source_tables[SOURCE_IDS["atlocal"]]
    cultural_map = source_tables[SOURCE_IDS["cultural_map"]]
    members = {}
    source_to_member = {}
    assertions = []

    def add_member(source, local_id, name, eligible, keys, classification):
        member_id = stable_id("area_member", source, local_id)
        members[member_id] = dict(
            source_member_id=member_id,
            source=source,
            local_entity_id=local_id,
            display_name=name,
            k01b_eligible=eligible,
            primary_category_codes_json=classification,
        )
        for key in keys:
            if (source, key) in source_to_member:
                raise ValueError(f"Duplicate source key: {source}/{key}")
            source_to_member[source, key] = member_id
        return member_id

    def add_assertion(
        source, member_id, observation, title, category, eligible, local_row
    ):
        assertions.append(
            dict(
                assertion_id=stable_id(
                    "area_assertion", source, observation["observation_id"]
                ),
                source_member_id=member_id,
                source=source,
                observation_id=observation["observation_id"],
                source_key=observation["source_key"],
                source_id=observation["source_id"],
                title_raw=title,
                primary_category_code=category,
                k01b_eligible=eligible,
                raw_file=observation["raw_file"],
                row_locator=observation["row_locator"],
                file_sha256=observation["file_sha256"],
                captured_at=observation["captured_at"],
                source_local_record_json=json.dumps(
                    local_row, ensure_ascii=False, sort_keys=True
                ),
                raw_record_json=json.dumps(
                    observation_record(raw_inputs, SOURCE_IDS[source], observation),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        )

    observations = {
        row["observation_id"]: row for row in atlocal["source_observations"]
    }
    for row in atlocal["areas"]:
        member = add_member(
            "atlocal", row["area_id"], row["name"], True, [row["source_key"]], "[]"
        )
        add_assertion(
            "atlocal",
            member,
            observations[row["observation_id"]],
            row["name"],
            "",
            True,
            row,
        )

    context_keys = {review["cultural_map_source_key"] for review in reviews}
    selected_subjects = set()
    for row in cultural_map["mapped_subjects"]:
        keys = json.loads(row["source_keys_json"])
        eligible = row["cultural_area_eligible"] == "True"
        if eligible or context_keys.intersection(keys):
            add_member(
                "cultural_map",
                row["subject_id"],
                row["display_title"],
                eligible,
                keys,
                row["primary_category_codes_json"],
            )
            selected_subjects.add(row["subject_id"])
    observations = {
        row["observation_id"]: row for row in cultural_map["source_observations"]
    }
    for row in cultural_map["mapped_listing_observations"]:
        if row["subject_id"] in selected_subjects:
            add_assertion(
                "cultural_map",
                source_to_member["cultural_map", row["source_key"]],
                observations[row["observation_id"]],
                row["title_raw"],
                row["primary_category_code"],
                row["primary_category_code"] == "CS",
                row,
            )

    protected = []
    for review in reviews:
        if review["decision"] in {"separate", "unresolved"}:
            protected.append(
                (
                    source_to_member["atlocal", review["atlocal_source_key"]],
                    source_to_member["cultural_map", review["cultural_map_source_key"]],
                )
            )
    components = Components(members, protected)
    find = components.find

    decisions = []
    for review in reviews:
        left = source_to_member["atlocal", review["atlocal_source_key"]]
        right = source_to_member["cultural_map", review["cultural_map_source_key"]]
        if review["decision"] == "same_subject":
            left_root, right_root = find(left), find(right)
            left_sources = {
                members[key]["source"] for key in components.members[left_root]
            }
            right_sources = {
                members[key]["source"] for key in components.members[right_root]
            }
            if left_root != right_root and left_sources.intersection(right_sources):
                raise PipelineError(
                    "Area match would collapse distinct source-local identities through a bridge"
                )
            if components.merge(left, right) == "blocked_cannot_link":
                raise PipelineError(
                    "Area match crosses a reviewed separation or unresolved boundary"
                )
        elif review["decision"] not in {"separate", "unresolved"}:
            raise ValueError("Unsupported identity decision")
        decisions.append(
            dict(
                decision_id=review["decision_id"],
                left_source_member_id=left,
                right_source_member_id=right,
                decision=review["decision"],
                evidence=review["evidence"],
                review_status="accepted_by_user",
            )
        )
    groups = defaultdict(list)
    for member in sorted(members):
        groups[find(member)].append(member)
    crosswalk = []
    global_areas = []
    global_for_member = {}
    for group in sorted(groups.values()):
        global_id = stable_id("global_cultural_area", *group)
        preferred = min(
            group, key=lambda member: (members[member]["source"] != "atlocal", member)
        )
        eligible = any(members[member]["k01b_eligible"] for member in group)
        global_areas.append(
            dict(
                global_area_id=global_id,
                display_name=members[preferred]["display_name"],
                k01b_eligible=eligible,
                source_member_count=len(group),
                identity_status="accepted_cross_source_link"
                if len(group) > 1
                else "source_local_identity",
            )
        )
        for member in group:
            global_for_member[member] = global_id
            crosswalk.append(dict(global_area_id=global_id, **members[member]))
    for assertion in assertions:
        assertion["global_area_id"] = global_for_member[assertion["source_member_id"]]
    for decision in decisions:
        decision["left_global_area_id"] = global_for_member[
            decision["left_source_member_id"]
        ]
        decision["right_global_area_id"] = global_for_member[
            decision["right_source_member_id"]
        ]
        if (decision["decision"] == "same_subject") != (
            decision["left_global_area_id"] == decision["right_global_area_id"]
        ):
            raise ValueError("Identity decision contradicts resulting components")
    contributions = [
        dict(
            measure_id="K01B_cultural_areas",
            global_area_id=row["global_area_id"],
            source_member_id=row["source_member_id"],
            source=row["source"],
            eligible=row["k01b_eligible"],
            eligibility_basis="AtLocal named area"
            if row["source"] == "atlocal"
            else (
                "Cultural Map primary CS subject"
                if row["k01b_eligible"]
                else "Non-CS context only"
            ),
        )
        for row in crosswalk
    ]
    eligible_count = sum(row["k01b_eligible"] for row in global_areas)
    counts = dict(
        atlocal_eligible_members=sum(
            row["source"] == "atlocal" and row["k01b_eligible"] for row in crosswalk
        ),
        cultural_map_eligible_members=sum(
            row["source"] == "cultural_map" and row["k01b_eligible"]
            for row in crosswalk
        ),
        eligible_cross_source_overlap=sum(row["k01b_eligible"] for row in crosswalk)
        - eligible_count,
        k01b_cultural_areas=eligible_count,
        global_subjects=len(global_areas),
        source_members=len(crosswalk),
        assertions=len(assertions),
        accepted_links=sum(row["decision"] == "same_subject" for row in decisions),
        accepted_separations=sum(row["decision"] == "separate" for row in decisions),
    )
    if counts != expected_counts:
        raise PipelineError(
            f"Cultural-area counts differ from accepted snapshot: {counts}"
        )
    if len({row["assertion_id"] for row in assertions}) != len(assertions):
        raise ValueError("Duplicate assertion ID")
    if {row["source_member_id"] for row in assertions} != set(members):
        raise ValueError("Incomplete assertion coverage")
    return {
        "global_cultural_areas": global_areas,
        "area_crosswalk": crosswalk,
        "area_assertions": assertions,
        "identity_decisions": decisions,
        "measure_contributions": contributions,
        "measure_results": [
            dict(
                measure_id="K01B_cultural_areas",
                value=eligible_count,
                unit="source_reported_cultural_area_identity",
                status="accepted_snapshot_provisional_identity_count",
            )
        ],
        "source_files": [
            source_file
            for source_id, dataset in (
                (SOURCE_IDS["atlocal"], "areas"),
                (SOURCE_IDS["cultural_map"], "map_inspiration"),
            )
            for source_file in [_source_file(raw_inputs, source_id, dataset)]
        ],
    }

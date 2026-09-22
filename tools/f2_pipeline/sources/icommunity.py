"""Build the source-local iCommunity pilot. No raw edits or cross-source merges."""

import difflib
import hashlib
import itertools
import json
import re
from collections import defaultdict
from decimal import Decimal

from ..common import (
    Components,
    matching_name,
    normalize,
    readable,
    safe_text,
    stable_id,
)

DATASET_KEYS = (
    "apptech_innovators",
    "apptech_innovations",
    "community_products",
    "activity_posts",
    "apptech_dashboard_summaries",
    "apptech_group_catalog",
    "programme_background",
    "location_assertions",
)

DIMENSIONS = [
    "technology_knowledge",
    "learning_process_management",
    "collaboration_network",
]
FILES = [
    "apptech_innovators",
    "apptech_innovations",
    "community_products",
    "activity_posts",
    "apptech_dashboard_summaries",
    "apptech_group_catalog",
    "programme_background",
]
ID_FIELDS = dict(
    zip(
        FILES,
        [
            "innovator_id",
            "innovation_id",
            "product_id",
            "post_id",
            "source_key",
            "source_key",
            "page_id",
        ],
    )
)


def sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class RoleReviews:
    """In-memory reviewed role decisions; provenance locks are checked by the caller."""

    def __init__(self, data):
        self.data = data
        self.field = data.get("role_field", "community_role_raw")
        self.by_observation = {
            item.get("row_index"): item
            for item in data.get("observation_reviews", [])
            if isinstance(item, dict)
        }
        self.by_text = {
            item.get("role_key"): item
            for item in data.get("role_reviews", [])
            if isinstance(item, dict)
        }

    def decision(self, index, value):
        return dict(
            self.by_observation.get(index)
            or self.by_text.get(sha256_text(str(value or "").strip()))
            or {
                "review_id": "",
                "status": "unreviewed"
                if str(value or "").strip()
                else "no_role_evidence",
                "reason": "No reviewed assertion for this field; no eligibility inferred.",
                "route": "",
                "review_origin": "",
            }
        )


class Pilot:
    def __init__(self, datasets, reviews, geography, input_metadata):
        if set(datasets) != set(DATASET_KEYS):
            raise ValueError(
                f"iCommunity input contract: datasets must be exactly {', '.join(DATASET_KEYS)}"
            )
        self.inputs, self.input_metadata = datasets, input_metadata
        self.role_reviews = RoleReviews(
            reviews.get(
                "business_role_reviews.json", reviews.get("business_role_reviews", {})
            )
        )
        self.tables = defaultdict(list)
        self.data = {}
        self.obs = {}
        self.sources = []
        self.decisions = reviews.get("reviewed_cases.json", reviews)
        self.excluded_person_observations = {
            str(case["source_id"]): case
            for case in self.decisions.get("excluded_person_observations", [])
        }
        self.unverified_researcher_subjects = {
            (str(case["source_id"]), case["full_name"]): case
            for case in self.decisions.get("unverified_researcher_subjects", [])
        }
        self.researcher_matching_name_corrections = {
            str(case["source_id"]): case
            for case in self.decisions.get("researcher_matching_name_corrections", [])
        }
        self.admin = {
            "province_codes": {
                r.get("provinceNameTh"): r.get("provinceCode")
                for r in geography.provinces
            },
            "district_codes": {},
        }
        for row in geography.districts:
            self.admin["district_codes"].setdefault(str(row.get("provinceCode")), {})[
                row.get("districtNameTh")
            ] = row.get("districtCode")
        self.sub = {}
        self.full_sub = geography.subdistricts

    def add(self, table, **row):
        self.tables[table].append(row)

    def issue(self, kind, observation_id, reason, entity_id="", other_entity_id=""):
        self.add(
            "review_cases",
            review_id=stable_id(
                "review", kind, observation_id, reason, entity_id, other_entity_id
            ),
            kind=kind,
            observation_id=observation_id,
            entity_id=entity_id,
            other_entity_id=other_entity_id,
            reason=reason,
            status="unresolved",
        )

    def ingest(self):
        for name in FILES:
            d, metadata = self.inputs[name], self.input_metadata.get(name)
            if not isinstance(d, dict) or not isinstance(metadata, dict):
                raise ValueError(
                    f"iCommunity input contract: missing capture or metadata for {name}"
                )
            rows = d.get("data")
            if not isinstance(rows, list) or d.get("record_count") not in (
                None,
                len(rows),
            ):
                raise ValueError(
                    f"iCommunity input contract: invalid records for {name}"
                )
            for key in (
                "source_id",
                "run_id",
                "file",
                "sha256",
                "size",
                "captured_at",
                "originating_system",
            ):
                if not metadata.get(key):
                    raise ValueError(
                        f"iCommunity input contract: incomplete metadata for {name}"
                    )
            reviewed_hash = self.decisions.get("raw_sha256", {}).get(name + ".json")
            if reviewed_hash and metadata["sha256"] != reviewed_hash:
                raise ValueError(f"iCommunity reviewed input changed: {name}")
            self.data[name] = rows
            self.sources.append(
                {
                    "file": metadata["file"],
                    "sha256": metadata["sha256"],
                    "rows": len(rows),
                }
            )
            self.add(
                "source_files",
                dataset=name,
                file=metadata["file"],
                sha256=metadata["sha256"],
                row_count=len(rows),
                envelope_json=dump({k: v for k, v in d.items() if k != "data"}),
            )
            for index, r in enumerate(rows):
                # Retain accepted source-review identity namespace; locators use the new evidence URI.
                oid = stable_id("obs", name, metadata["sha256"], index)
                self.obs[name, index] = oid
                self.add(
                    "source_observations",
                    observation_id=oid,
                    dataset=name,
                    source_id=str(r.get(ID_FIELDS[name], "")),
                    source_key=r.get("source_key"),
                    row_locator=f"evidence://{metadata['source_id']}/{metadata['run_id']}/{metadata['file']}#data/{index}",
                    file_sha256=metadata["sha256"],
                    captured_at=metadata["captured_at"],
                    raw_file=metadata["file"],
                    disposition="retained_with_lineage",
                )

    def location(self, r, oid, entity, role):
        raw = r.get("location") or {}
        if not raw:
            return ""
        p, d, t = [normalize(raw.get(k)) for k in ["province", "amphor", "tambon"]]
        pc = self.admin["province_codes"].get(p)
        known = self.admin["district_codes"].get(str(pc), {})
        d = re.sub(r"^(?:อำเภอ|อ\.)\s*", "", d)
        t = re.sub(r"^(?:ตำบล|ต\.)\s*", "", t)
        if d == "เมือง":
            d = "เมือง" + p
        dc = known.get(d)
        parents = self.sub.get(str(pc), {}).get(t, {})
        status = (
            "hierarchy_match" if dc and str(dc) in parents else "hierarchy_unresolved"
        )
        if not dc and len(parents) == 1:
            newdc, newd = next(iter(parents.items()))
            if difflib.SequenceMatcher(None, d, newd).ratio() >= 0.85 or d == p:
                dc = newdc
                d = newd
                status = "district_alias_inferred"
        geocode = str(raw.get("geocode") or "")
        candidates = [
            v
            for v in self.full_sub
            if str(v["provinceCode"]) == str(pc)
            and str(v["districtCode"]) == str(dc)
            and v["subdistrictNameTh"] == t
        ]
        subcode = str(candidates[0]["subdistrictCode"]) if len(candidates) == 1 else ""
        conflict = bool(
            re.fullmatch(r"\d{6}", geocode) and subcode and geocode != subcode
        )
        if conflict:
            status = "source_geocode_conflict"
        lid = stable_id("location", oid, role)
        self.add(
            "locations",
            location_id=lid,
            observation_id=oid,
            entity_id=entity,
            location_role=role,
            province_raw=raw.get("province"),
            district_raw=raw.get("amphor"),
            subdistrict_raw=raw.get("tambon"),
            province_normalized=p,
            province_code=str(pc or ""),
            district_normalized=d,
            district_code=str(dc or "") if not conflict else "",
            subdistrict_normalized=t,
            subdistrict_code=subcode if not conflict else "",
            source_geocode=geocode,
            geocode_validation="full_code_matches"
            if geocode and subcode == geocode
            else "conflict"
            if conflict
            else "name_hierarchy_only",
            latitude=raw.get("latitude"),
            longitude=raw.get("longitude"),
            status=status,
            raw_location_json=dump(raw),
        )
        if status not in ["hierarchy_match", "district_alias_inferred"]:
            self.issue("geography", oid, status, entity)
        return lid

    def association(self, r, oid, entity):
        project = r.get("project") or {}
        inst = r.get("institute") or {}
        researcher = r.get("researcher") or {}
        pid = stable_id("project", project.get("id")) if project.get("id") else ""
        iid = stable_id("institution", inst.get("id")) if inst.get("id") else ""
        rid = (
            stable_id("researcher", researcher.get("user_id"))
            if researcher.get("user_id")
            else ""
        )
        self.add(
            "participations",
            participation_id=stable_id("participation", oid, entity),
            observation_id=oid,
            entity_id=entity,
            project_id=pid,
            institution_id=iid,
            researcher_id=rid,
            group_id=(r.get("scope") or {}).get("group_id"),
            group_label=(r.get("scope") or {}).get("group_label_th"),
        )
        if pid:
            self.add(
                "project_assertions",
                project_id=pid,
                observation_id=oid,
                source_id=project.get("id"),
                code=project.get("code"),
                name=project.get("name"),
                year_be=project.get("year_be"),
                family_code=project.get("family_code"),
                reference_project_id=project.get("reference_project_id"),
            )
        if iid:
            self.add(
                "institution_assertions",
                institution_id=iid,
                observation_id=oid,
                source_id=inst.get("id"),
                name=inst.get("name"),
            )
        if rid:
            researcher_source_id = str(researcher.get("user_id"))
            researcher_name = researcher.get("full_name")
            matching_correction = self.researcher_matching_name_corrections.get(
                researcher_source_id
            )
            if matching_correction:
                assert researcher_name == matching_correction["full_name"]
                researcher_matching_name = matching_correction["matching_name"]
            else:
                researcher_matching_name = matching_name(researcher_name)
            subject = self.unverified_researcher_subjects.get(
                (researcher_source_id, researcher_name)
            )
            self.add(
                "researcher_assertions",
                researcher_id=rid,
                observation_id=oid,
                source_id=researcher.get("user_id"),
                full_name=researcher_name,
                matching_name=researcher_matching_name,
                role="researcher",
                community_eligible=False,
                identity_status=(
                    subject["identity_status"]
                    if subject
                    else "source_reported_researcher_assertion"
                ),
                subject_kind="account_or_coordinator_style_claim" if subject else "",
            )

    def apply(self, components, a, b, rule, observations, source_decision_id=""):
        outcome = components.merge(a, b)
        if outcome == "already_linked" and not source_decision_id:
            return
        self.add(
            "identity_decisions",
            decision_id=stable_id("decision", a, b, rule),
            source_decision_id=source_decision_id,
            left_source_id=a,
            right_source_id=b,
            rule=rule,
            outcome=outcome,
            evidence_observation_ids=observations,
        )
        if outcome.startswith("blocked"):
            self.issue("identity_conflict", observations[0], rule)

    def innovation_member_key(self, row):
        """Return the reviewed source member key for one innovation observation."""
        source_id = str(row["innovation_id"])
        split = self.innovation_context_splits.get(source_id)
        if not split:
            return source_id
        project_code = str((row.get("project") or {}).get("code") or "")
        researcher_id = str((row.get("researcher") or {}).get("user_id") or "")
        matches = [
            context
            for context in split["contexts"]
            if project_code == str(context["selector"]["project_code"])
            and researcher_id == str(context["selector"]["researcher_user_id"])
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Innovation context split {source_id} matched {len(matches)} contexts "
                f"for project={project_code}, researcher={researcher_id}"
            )
        return source_id + "::" + matches[0]["context_key"]

    def people(self):
        rows = self.data["apptech_innovators"]
        byid = defaultdict(list)
        byname = defaultdict(list)
        for i, r in enumerate(rows):
            source_id = str(r["innovator_id"])
            excluded = self.excluded_person_observations.get(source_id)
            if excluded:
                assert (
                    r["innovator_name"] == excluded["name"]
                    and r["project"]["code"] == excluded["project_code"]
                    and r.get("community_role_raw") is None
                    and r.get("detail") is None
                )
                continue
            byid[source_id].append(i)
            byname[matching_name(r["innovator_name"])].append(i)
        assert set(self.excluded_person_observations) <= {
            str(r["innovator_id"]) for r in rows
        }
        components = Components(byid, [("1630", "4947")])
        for name, indices in byname.items():
            if len(name.split()) < 2:
                continue
            for i, j in itertools.combinations(indices, 2):
                a, b = rows[i], rows[j]
                if a["innovator_id"] == b["innovator_id"]:
                    continue
                inst = a["institute"]["id"] == b["institute"]["id"]
                research = a["researcher"]["user_id"] == b["researcher"]["user_id"]
                place = all(
                    a["location"].get(k) == b["location"].get(k)
                    and a["location"].get(k)
                    for k in ["province", "amphor", "tambon"]
                )
                pa, pb = a["project"]["code"], b["project"]["code"]
                family = pa and pb and pa.split("-")[0] == pb.split("-")[0]
                rule = ""
                if inst and place:
                    rule = "accepted_name_institution_locality"
                elif inst and research and family:
                    rule = "accepted_name_institution_researcher_project_family"
                elif name in self.decisions["cross_institution_people"]:
                    rule = "accepted_named_cross_institution_case"
                if rule:
                    self.apply(
                        components,
                        a["innovator_id"],
                        b["innovator_id"],
                        rule,
                        [
                            self.obs["apptech_innovators", i],
                            self.obs["apptech_innovators", j],
                        ],
                    )
        for case in self.decisions["person_typo_pairs"]:
            a, b = [rows[byid[k][0]] for k in case["source_ids"]]
            assert (
                all(a[k]["id"] == b[k]["id"] for k in ["project", "institute"])
                and a["researcher"]["user_id"] == b["researcher"]["user_id"]
                and a["location"]["geocode"] == b["location"]["geocode"]
            )
            self.apply(
                components,
                *case["source_ids"],
                "reviewed_obvious_typo",
                [
                    self.obs["apptech_innovators", byid[k][0]]
                    for k in case["source_ids"]
                ],
            )
        correction_groups = self.decisions.get("source_identity_corrections", [])
        correction_ids = []
        for group in correction_groups:
            links = group.get("links", [group])
            expected_ids = group.get("candidate_ids", [group.get("candidate_id")])
            assert len(expected_ids) == len(links)
            for link in links:
                left = [str(value) for value in link["left_source_ids"]]
                right = [str(value) for value in link["right_source_ids"]]
                assert left and right and set(left + right) <= set(byid)
                correction_ids.append(link["candidate_id"])
                for source_ids in [left, right]:
                    for source_id in source_ids[1:]:
                        self.apply(
                            components,
                            source_ids[0],
                            source_id,
                            "retained_source_local_identity",
                            [
                                self.obs["apptech_innovators", byid[source_ids[0]][0]],
                                self.obs["apptech_innovators", byid[source_id][0]],
                            ],
                        )
                evidence = [
                    self.obs["apptech_innovators", index]
                    for source_id in left + right
                    for index in byid[source_id]
                ]
                self.apply(
                    components,
                    left[0],
                    right[0],
                    "audited_source_identity_correction",
                    evidence,
                    link["candidate_id"],
                )
                assert (
                    len({components.find(source_id) for source_id in left + right}) == 1
                )
        assert len(correction_ids) == len(set(correction_ids))
        ids = {k: stable_id("person", components.find(k)) for k in byid}
        self.person_ids = ids
        self.subject_ids = {
            source_id: stable_id("non_person_subject", source_id)
            for source_id in self.excluded_person_observations
        }
        self.entity_ids = {**self.person_ids, **self.subject_ids}
        for source_id, case in self.excluded_person_observations.items():
            source_rows = [r for r in rows if str(r["innovator_id"]) == source_id]
            assert len(source_rows) == 1
            self.add(
                "non_person_subjects",
                subject_id=self.subject_ids[source_id],
                display_name=source_rows[0]["innovator_name"],
                source_ids_json=[source_id],
                identity_status="excluded_apparent_test_subject",
                exclusion_reason=case["reason"],
            )
        for root, members in components.members.items():
            indices = [i for k in members for i in byid[k]]
            names = sorted({normalize(rows[i]["innovator_name"]) for i in indices})
            eid = ids[root]
            quality = (
                "incomplete_or_ambiguous_name"
                if any(
                    len(matching_name(n).split()) < 2 or n.startswith("นางนาง ")
                    for n in names
                )
                else "source_reported_person"
            )
            self.add(
                "people",
                person_id=eid,
                display_name=names[0],
                aliases_json=names,
                source_ids_json=sorted(members),
                community_eligible=True,
                identity_status="supported_source_local",
                name_quality=quality,
            )
            if quality != "source_reported_person":
                self.issue(
                    "name_quality",
                    self.obs["apptech_innovators", indices[0]],
                    quality,
                    eid,
                )
        fuzzy_context = defaultdict(dict)
        for i, r in enumerate(rows):
            if str(r["innovator_id"]) in self.subject_ids:
                continue
            fuzzy_context[
                (
                    r["institute"]["id"],
                    r["project"]["id"],
                    r["researcher"]["user_id"],
                    r["location"]["geocode"],
                )
            ][r["innovator_id"]] = i
        for group in fuzzy_context.values():
            for i, j in itertools.combinations(group.values(), 2):
                a, b = rows[i], rows[j]
                na, nb = (
                    matching_name(a["innovator_name"]),
                    matching_name(b["innovator_name"]),
                )
                if (
                    ids[a["innovator_id"]] != ids[b["innovator_id"]]
                    and na != nb
                    and difflib.SequenceMatcher(
                        None, na.replace(" ", ""), nb.replace(" ", "")
                    ).ratio()
                    >= 0.88
                ):
                    self.issue(
                        "possible_person_spelling_duplicate",
                        self.obs["apptech_innovators", i],
                        "Near name in agreeing context; no automatic fuzzy merge",
                        ids[a["innovator_id"]],
                        ids[b["innovator_id"]],
                    )
        for i, r in enumerate(rows):
            oid = self.obs["apptech_innovators", i]
            source_id = str(r["innovator_id"])
            eid = self.entity_ids[source_id]
            is_non_person_subject = source_id in self.subject_ids
            decision = self.role_reviews.decision(i, r.get("community_role_raw"))
            role_locator = (
                f"data/icommunity/apptech_innovators.json#data/{i}/community_role_raw"
            )
            name_locator = (
                f"data/icommunity/apptech_innovators.json#data/{i}/innovator_name"
            )
            role_review = dict(
                review_id=decision["review_id"],
                person_id="" if is_non_person_subject else eid,
                subject_id=eid if is_non_person_subject else "",
                observation_id=oid,
                source_id=source_id,
                role_passage=safe_text(r.get("community_role_raw")),
                source_locator=role_locator,
                name_source_locator=name_locator,
                status="non_person_subject"
                if is_non_person_subject
                else decision["status"],
                evidence_route=decision.get("route", ""),
                business_name=decision.get("business_name", ""),
                reason=decision["reason"],
                review_origin=decision.get("review_origin")
                or (
                    f"review://business_role_reviews.json#role_reviews/{decision['review_id']}"
                    if decision.get("review_id")
                    else ""
                ),
                supporting_evidence_json=decision.get("supporting_evidence", []),
            )
            self.add("business_role_reviews", **role_review)
            self.add(
                "entity_observations",
                entity_id=eid,
                entity_type="non_person_subject" if is_non_person_subject else "person",
                observation_id=oid,
                source_id=r["innovator_id"],
            )
            if is_non_person_subject:
                self.association(r, oid, eid)
                self.location(r, oid, eid, "source_test_subject_location")
                continue
            self.add(
                "person_roles",
                role_id=stable_id("role", oid),
                person_id=eid,
                observation_id=oid,
                role="community_innovator",
                evidence="accepted innovator dataset membership",
                role_text=safe_text(r.get("community_role_raw")),
            )
            self.association(r, oid, eid)
            self.location(r, oid, eid, "source_person_location")
            if decision["status"] == "supported":
                self.add(
                    "entrepreneur_evidence",
                    person_id=eid,
                    observation_id=oid,
                    role_passage=role_review["role_passage"],
                    eligibility="reviewed_" + decision["route"],
                    review_id=decision["review_id"],
                    source_locator=role_locator,
                    name_source_locator=name_locator,
                    business_name=decision.get("business_name", ""),
                    reason=decision["reason"],
                    supporting_evidence_json=decision.get("supporting_evidence", []),
                )
            elif decision["status"] in {"unresolved", "unreviewed"}:
                self.add(
                    "role_review",
                    person_id=eid,
                    observation_id=oid,
                    role_passage=role_review["role_passage"],
                    reason=decision["reason"],
                    review_id=decision["review_id"],
                    status=decision["status"],
                    source_locator=role_locator,
                )
            detail = r.get("detail")
            if detail:
                aid = stable_id(
                    "assessment",
                    eid,
                    r["project"]["id"],
                    {k: detail[k] for k in DIMENSIONS},
                )
                self.add(
                    "assessment_observations",
                    assessment_id=aid,
                    person_id=eid,
                    observation_id=oid,
                    project_id=stable_id("project", r["project"]["id"]),
                )
                for dim in DIMENSIONS:
                    start, end = (
                        detail[dim]["start_level"],
                        detail[dim]["current_level"],
                    )
                    assert start in range(1, 5) and end in range(1, 5)
                    self.add(
                        "development_scores",
                        assessment_id=aid,
                        person_id=eid,
                        dimension=dim,
                        start_score=start,
                        current_score=end,
                        delta=end - start,
                    )
        for name, indices in byname.items():
            entities = sorted({ids[rows[i]["innovator_id"]] for i in indices})
            if len(entities) > 1:
                for left, right in itertools.combinations(entities, 2):
                    self.issue(
                        "possible_person_duplicate",
                        self.obs["apptech_innovators", indices[0]],
                        "same matching name; insufficient accepted context",
                        left,
                        right,
                    )

    def innovations(self):
        rows = self.data["apptech_innovations"]
        self.innovation_context_splits = {
            str(row["source_id"]): row
            for row in self.decisions.get("innovation_context_splits", [])
        }
        if len(self.innovation_context_splits) != len(
            self.decisions.get("innovation_context_splits", [])
        ):
            raise ValueError("Duplicate innovation context-split source_id")
        self.innovation_member_keys = [self.innovation_member_key(row) for row in rows]
        byid = defaultdict(list)
        for i, r in enumerate(rows):
            byid[self.innovation_member_keys[i]].append(i)
        repeated_raw = defaultdict(list)
        for i, r in enumerate(rows):
            repeated_raw[str(r["innovation_id"])].append(i)
        for source_id, indices in sorted(repeated_raw.items()):
            if len(indices) < 2:
                continue
            split = self.innovation_context_splits.get(source_id)
            member_keys = sorted({self.innovation_member_keys[i] for i in indices})
            titles = sorted({normalize(rows[i]["innovation_name"]) for i in indices})
            descriptions = sorted(
                {
                    sha256_text(
                        normalize(
                            readable(
                                (rows[i].get("detail") or {}).get(
                                    "short_description_html"
                                )
                                or (rows[i].get("detail") or {}).get(
                                    "short_description_text"
                                )
                            )
                        )
                    )
                    for i in indices
                }
            )
            if split:
                expected = {
                    source_id + "::" + row["context_key"] for row in split["contexts"]
                }
                if set(member_keys) != expected:
                    raise ValueError(
                        f"Innovation context split {source_id} does not cover every configured context"
                    )
                disposition = "reviewed_context_split"
                reason = split["reason"]
            else:
                if len(titles) != 1 or len(descriptions) != 1:
                    raise ValueError(
                        f"Repeated innovation ID {source_id} changed title or description; review required"
                    )
                disposition = "retained_one_identity"
                reason = (
                    "Repeated source ID has the same title and technical description. "
                    "Project, team or location changes alone do not establish a different output."
                )
            self.add(
                "reused_innovation_id_audit",
                raw_source_id=source_id,
                occurrence_count=len(indices),
                source_member_count=len(member_keys),
                source_member_keys_json=member_keys,
                disposition=disposition,
                project_codes_json=sorted(
                    {
                        str((rows[i].get("project") or {}).get("code") or "")
                        for i in indices
                    }
                ),
                researcher_user_ids_json=sorted(
                    {
                        str((rows[i].get("researcher") or {}).get("user_id") or "")
                        for i in indices
                    }
                ),
                institute_ids_json=sorted(
                    {
                        str((rows[i].get("institute") or {}).get("id") or "")
                        for i in indices
                    }
                ),
                titles_json=titles,
                description_sha256_json=descriptions,
                observation_ids_json=[
                    self.obs["apptech_innovations", i] for i in indices
                ],
                reason=reason,
            )
        prior = self.decisions["prior_innovation_decisions"]
        cannot = []
        keymap = {
            r["source_key"]: self.innovation_member_keys[i] for i, r in enumerate(rows)
        }
        for d in prior:
            self.add("prior_decision_mapping", **d)
            if not d["all_local_endpoints_validated"]:
                self.issue(
                    "prior_decision_endpoint",
                    "",
                    "Prior decision "
                    + d["candidate_id"]
                    + " has a local endpoint not present; retained without invented join",
                )
            if (
                d["decision"] == "cannot_link"
                and d["all_local_endpoints_validated"]
                and d["left_key"] in keymap
                and d["right_key"] in keymap
            ):
                left = keymap[d["left_key"]]
                right = keymap[d["right_key"]]
                cannot.append((left, right))
                evidence = [
                    self.obs["apptech_innovations", i]
                    for member in (left, right)
                    for i in byid[member]
                ]
                self.add(
                    "identity_decisions",
                    decision_id=stable_id(
                        "decision",
                        left,
                        right,
                        "prior_reviewed_cannot_link",
                        d["candidate_id"],
                    ),
                    source_decision_id=d["candidate_id"],
                    left_source_id=left,
                    right_source_id=right,
                    rule="prior_reviewed_cannot_link",
                    outcome="cannot_link_prior_reviewed",
                    evidence_observation_ids=evidence,
                )
        for split in self.innovation_context_splits.values():
            members = [
                str(split["source_id"]) + "::" + context["context_key"]
                for context in split["contexts"]
            ]
            cannot.extend(itertools.combinations(members, 2))
        c = Components(byid, cannot)
        for i, a in enumerate(rows):
            for j in range(i):
                b = rows[j]
                a_member = self.innovation_member_keys[i]
                b_member = self.innovation_member_keys[j]
                same = normalize(a["innovation_name"]) == normalize(
                    b["innovation_name"]
                )
                rule = ""
                if (
                    same
                    and a["project"]["id"] == b["project"]["id"]
                    and a["researcher"]["user_id"] == b["researcher"]["user_id"]
                ):
                    rule = "accepted_full_title_project_researcher"
                if a["project"]["code"] == b["project"]["code"] == "A11F670112-00":
                    rule = "accepted_forest_case"
                if (
                    same
                    and a["project"]["code"].split("-")[0]
                    == b["project"]["code"].split("-")[0]
                    and a["institute"]["id"] == b["institute"]["id"]
                    and a["innovation_name"]
                    in self.decisions["cross_suffix_innovation_titles"]
                ):
                    rule = "accepted_cross_suffix_case"
                if rule:
                    self.apply(
                        c,
                        a_member,
                        b_member,
                        rule,
                        [
                            self.obs["apptech_innovations", i],
                            self.obs["apptech_innovations", j],
                        ],
                    )
        for d in prior:
            if (
                d["decision"] == "must_link"
                and d["left_key"] in keymap
                and d["right_key"] in keymap
            ):
                self.apply(
                    c,
                    keymap[d["left_key"]],
                    keymap[d["right_key"]],
                    "prior_reviewed_must_link",
                    [self.obs["apptech_innovations", byid[keymap[d["left_key"]]][0]]],
                )
        self.innovation_ids = {k: stable_id("innovation", c.find(k)) for k in byid}
        for split in self.innovation_context_splits.values():
            members = [
                str(split["source_id"]) + "::" + context["context_key"]
                for context in split["contexts"]
            ]
            for left, right in itertools.combinations(members, 2):
                left_observations = [
                    self.obs["apptech_innovations", i]
                    for i, member in enumerate(self.innovation_member_keys)
                    if member == left
                ]
                right_observations = [
                    self.obs["apptech_innovations", i]
                    for i, member in enumerate(self.innovation_member_keys)
                    if member == right
                ]
                self.add(
                    "identity_decisions",
                    decision_id=stable_id(
                        "decision", left, right, "reviewed_context_split"
                    ),
                    source_decision_id="",
                    left_source_id=left,
                    right_source_id=right,
                    rule="reviewed_context_split",
                    outcome="cannot_link_context_split",
                    evidence_observation_ids=left_observations + right_observations,
                )
            for context in split["contexts"]:
                member_key = str(split["source_id"]) + "::" + context["context_key"]
                indices = [
                    i
                    for i, current_member in enumerate(self.innovation_member_keys)
                    if current_member == member_key
                ]
                expected_count = int(
                    context.get("expected_observation_count", len(indices))
                )
                if len(indices) != expected_count:
                    raise ValueError(
                        f"Innovation context {member_key} expected {expected_count} observations, "
                        f"found {len(indices)}"
                    )
                self.add(
                    "innovation_context_splits",
                    raw_source_id=str(split["source_id"]),
                    source_member_key=member_key,
                    context_key=context["context_key"],
                    innovation_id=self.innovation_ids[member_key],
                    project_code=context["selector"]["project_code"],
                    researcher_user_id=context["selector"]["researcher_user_id"],
                    observation_ids_json=[
                        self.obs["apptech_innovations", i] for i in indices
                    ],
                    reason=split["reason"],
                )
        reviewed_split_entity_pairs = {
            frozenset(
                (
                    self.innovation_ids[
                        str(split["source_id"]) + "::" + left["context_key"]
                    ],
                    self.innovation_ids[
                        str(split["source_id"]) + "::" + right["context_key"]
                    ],
                )
            )
            for split in self.innovation_context_splits.values()
            for left, right in itertools.combinations(split["contexts"], 2)
        }
        for root, members in c.members.items():
            names = sorted(
                {rows[i]["innovation_name"] for k in members for i in byid[k]}
            )
            raw_source_ids = sorted(
                {str(rows[i]["innovation_id"]) for k in members for i in byid[k]}
            )
            context_keys = sorted(
                {key.split("::", 1)[1] for key in members if "::" in key}
            )
            self.add(
                "innovations",
                innovation_id=self.innovation_ids[root],
                display_name=normalize(names[0]),
                aliases_json=names,
                source_ids_json=raw_source_ids,
                source_member_keys_json=sorted(members),
                context_keys_json=context_keys,
                identity_status=(
                    "reviewed_context_split"
                    if context_keys
                    else "supported_source_local"
                ),
            )
        for i, r in enumerate(rows):
            oid = self.obs["apptech_innovations", i]
            member_key = self.innovation_member_keys[i]
            eid = self.innovation_ids[member_key]
            self.add(
                "entity_observations",
                entity_id=eid,
                entity_type="innovation",
                observation_id=oid,
                source_id=r["innovation_id"],
                source_member_key=member_key,
            )
            self.association(r, oid, eid)
            self.location(r, oid, eid, "declared_innovation_use")
            detail = r.get("detail") or {}
            self.add(
                "innovation_details",
                innovation_id=eid,
                observation_id=oid,
                description=safe_text(
                    readable(
                        detail.get("short_description_html")
                        or detail.get("short_description_text")
                    )
                ),
                technology_group=r.get("technology_group_raw"),
                innovation_type=detail.get("innovation_type"),
                usage_cost_raw=detail.get("usage_cost_thb_raw"),
                cover_image=r.get("cover_image_path"),
            )
            for scale, field in [
                ("TRL", "latest_readiness_level_raw"),
                ("SRL", "latest_social_readiness_level_raw"),
            ]:
                raw = r.get(field)
                match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", str(raw or ""))
                start, end = (int(match[1]), int(match[2])) if match else (None, None)
                valid = end is not None and 1 <= end <= 9
                self.add(
                    "readiness",
                    assessment_id=stable_id("readiness", oid, scale),
                    innovation_id=eid,
                    observation_id=oid,
                    scale=scale,
                    export_raw=raw,
                    start_level=start,
                    end_level=end if valid else None,
                    qualifies=scale == "TRL" and valid and end >= 8,
                    basis="export_project_end"
                    if valid
                    else "unknown_export_no_detail_default",
                    saved_detail_json=detail.get(
                        "technology_readiness" if scale == "TRL" else "social_readiness"
                    ),
                )
        bytitle = defaultdict(list)
        for i, r in enumerate(rows):
            bytitle[normalize(r["innovation_name"])].append(i)
        for indices in bytitle.values():
            entities = sorted(
                {self.innovation_ids[self.innovation_member_keys[i]] for i in indices}
            )
            for a, b in itertools.combinations(entities, 2):
                if frozenset((a, b)) in reviewed_split_entity_pairs:
                    continue
                self.issue(
                    "possible_innovation_duplicate",
                    self.obs["apptech_innovations", indices[0]],
                    "Same title across unsupported context; remains separate",
                    a,
                    b,
                )
        catalogue = defaultdict(set)
        for i, r in enumerate(rows):
            catalogue[(r["project"]["code"], normalize(r["innovation_name"]))].add(
                self.innovation_ids[self.innovation_member_keys[i]]
            )
        for i, r in enumerate(self.data["apptech_innovators"]):
            title = normalize(r.get("linked_innovation_name"))
            project = r["project"]["code"]
            oid = self.obs["apptech_innovators", i]
            if not title:
                continue
            target = self.decisions["work_aliases"].get(project + "|" + title, title)
            found = catalogue[project, target]
            eid = next(iter(found)) if len(found) == 1 else ""
            self.add(
                "work_mentions",
                mention_id=stable_id("mention", oid),
                observation_id=oid,
                person_id=(
                    ""
                    if str(r["innovator_id"]) in self.subject_ids
                    else self.person_ids[str(r["innovator_id"])]
                ),
                subject_id=self.subject_ids.get(str(r["innovator_id"]), ""),
                project_id=stable_id("project", r["project"]["id"]),
                mention_text=title,
                innovation_id=eid,
                link_status="supported_catalogue_match"
                if eid
                else "unresolved_mention_not_counted",
            )

    def other_sources(self):
        for name in ["community_products", "activity_posts", "programme_background"]:
            for i, r in enumerate(self.data[name]):
                oid = self.obs[name, i]
                text = safe_text(
                    readable(
                        (r.get("description_html") or "")
                        + "\n"
                        + (r.get("short_description_html") or "")
                        if name == "community_products"
                        else r.get("content_html") or r.get("content_text")
                    )
                )
                if name == "community_products":
                    eid = stable_id("product", str(r["product_id"]))
                    self.add(
                        "products",
                        product_id=eid,
                        observation_id=oid,
                        source_id=str(r["product_id"]),
                        name=normalize(r["name"]),
                        description=text,
                        permalink=r.get("permalink"),
                        categories_json=r["categories"],
                        attributes_json=r["attributes"],
                        images_json=r["images"],
                        stock_status=r.get("stock_status"),
                        is_purchasable=r["is_purchasable"],
                        is_in_stock=r.get("is_in_stock"),
                        on_sale=r["on_sale"],
                        identity_status="source_listing_provisional",
                    )
                    for field in ["price", "regular_price", "sale_price"]:
                        amount = r["prices"].get(field)
                        value = (
                            str(
                                Decimal(amount)
                                / (
                                    Decimal(10)
                                    ** int(r["prices"]["currency_minor_unit"])
                                )
                            )
                            if amount not in ("", None)
                            else None
                        )
                        self.add(
                            "product_prices",
                            product_id=eid,
                            observation_id=oid,
                            price_kind=field,
                            amount_raw=amount,
                            minor_unit=r["prices"]["currency_minor_unit"],
                            currency=r["prices"]["currency_code"],
                            amount_thb=value,
                        )
                    self.add(
                        "narrative_evidence",
                        observation_id=oid,
                        entity_id=eid,
                        kind="product_description",
                        text=text,
                    )
                    match = re.search(r"พื้นที่\s*:?\s*([^\n]+)", text)
                    area = match[1] if match else ""
                    vendor = re.split(r"ตำบล|ต\.|ที่อยู่|บ้านแม่อิงหลวง", area)[0].strip()
                    if "กลุ่มห้อมบ้านนาคูหา" in text.replace(" ", ""):
                        vendor = "เครือข่ายวิสาหกิจชุมชนกลุ่มห้อมบ้านนาคูหา"
                    if "ทอผ้าย้อมครามบ้านอูนดง" in text:
                        vendor = "กลุ่มวิสาหกิจชุมชนทอผ้าย้อมครามบ้านอูนดง"
                    good = bool(
                        vendor and vendor not in ["วิสาหกิจชุมชน", "บ้านอูนดง-หนองไชยวาลย์"]
                    )
                    province = re.search(r"(?:จังหวัด|จ\.)\s*([^\s.]+)", area)
                    district = re.search(r"(?:อำเภอ|อ\.)\s*(.*?)(?=จังหวัด|จ\.|$)", area)
                    tambon = re.search(r"(?:ตำบล|ต\.)\s*(.*?)(?=อำเภอ|อ\.|$)", area)
                    loc = {
                        "province": province[1] if province else "",
                        "amphor": district[1].strip() if district else "",
                        "tambon": tambon[1].strip() if tambon else "",
                    }
                    self.location({"location": loc}, oid, eid, "cultural_product_area")
                    if good:
                        sid = stable_id(
                            "seller",
                            normalize(vendor),
                            loc["province"],
                            loc["amphor"],
                            loc["tambon"],
                        )
                        self.add(
                            "sellers",
                            seller_id=sid,
                            name=vendor,
                            province=loc["province"],
                            identity_status="source_listed_operator_provisional",
                        )
                        self.add(
                            "product_sellers",
                            product_id=eid,
                            seller_id=sid,
                            observation_id=oid,
                            evidence_passage=area
                            if vendor in area
                            else next(
                                (
                                    line
                                    for line in text.splitlines()
                                    if "ห้อมบ้านนาคูหา" in line.replace(" ", "")
                                    or "ทอผ้าย้อมครามบ้านอูนดง" in line
                                ),
                                "",
                            ),
                            relationship="source_listed_product_operator",
                        )
                    else:
                        self.issue(
                            "seller_extraction",
                            oid,
                            "Generic enterprise/location wording does not identify a named seller",
                            eid,
                        )
                else:
                    pubid = stable_id(
                        "publication", name, str(r.get("post_id", r.get("page_id")))
                    )
                    self.add(
                        "publications",
                        publication_id=pubid,
                        observation_id=oid,
                        source_id=str(r.get("post_id", r.get("page_id"))),
                        title=normalize(r.get("title_html") or r.get("title")),
                        content=text,
                        published_at=r.get("published_at"),
                        modified_at=r.get("modified_at"),
                        source_url=r.get("source_url"),
                    )
                    case = self.decisions["activities"].get(str(r.get("post_id")))
                    if case and case["counted"]:
                        eventid = stable_id("activity", str(r["post_id"]))
                        self.add(
                            "activities",
                            activity_id=eventid,
                            publication_id=pubid,
                            observation_id=oid,
                            name=normalize(case["name"]),
                            start_date=case.get("start_date"),
                            end_date=case.get("end_date"),
                            status=case["status"],
                            evidence_excerpt=safe_text(case["evidence"]),
                            province=case.get("province"),
                            identity_status="reported_occurrence_provisional",
                        )
                        venue = case.get("venue_review")
                        if venue:
                            expected_locator = f"data/{i}/content_html"
                            assert venue["raw_locator"] == expected_locator, (
                                "Activity venue review must cite the current raw activity field"
                            )
                            assert venue["province"] == case.get("province"), (
                                "Activity venue province must agree with the reviewed activity province"
                            )
                            assert venue["raw_text_marker"] in r.get(
                                "content_html", ""
                            ), "Activity venue review marker is stale"
                            self.add(
                                "activity_venue_evidence",
                                venue_evidence_id=stable_id(
                                    "activity_venue", eventid, venue["raw_locator"]
                                ),
                                activity_id=eventid,
                                publication_id=pubid,
                                observation_id=oid,
                                venue_name_raw=venue["venue_name"],
                                province_raw=venue["province"],
                                location_role=venue["location_role"],
                                status="reviewed_explicit_activity_venue",
                                raw_locator=venue["raw_locator"],
                                evidence_marker=venue["raw_text_marker"],
                                reason=venue["reason"],
                            )
                        if str(r["post_id"]) == "361":
                            self.issue(
                                "possible_event_duplicate",
                                oid,
                                "Unresolved announcement/report pair 361/270",
                                eventid,
                                stable_id("activity", "270"),
                            )
        for i, r in enumerate(self.data["apptech_dashboard_summaries"]):
            oid = self.obs["apptech_dashboard_summaries", i]
            aid = stable_id("aggregate", oid)
            self.add(
                "aggregate_summaries",
                aggregate_id=aid,
                observation_id=oid,
                entity_type=r["dashboard_entity"],
                scope_json=r["scope"],
                reported_count_raw=r["reported_count_raw"],
                reported_count=int(str(r["reported_count_raw"]).replace(",", "")),
                retrieved_at=r["retrieved_at"],
                status="source_reported_nonadditive",
            )
            for n, g in enumerate(r["geographic_rows"]):
                self.add(
                    "aggregate_geography",
                    aggregate_id=aid,
                    row_index=n,
                    observation_id=oid,
                    area_label=g.get("area"),
                    source_tambon_id=g.get("tambon"),
                    latitude=g.get("lat"),
                    longitude=g.get("long"),
                    count_innovation=g.get("count_innovation"),
                    count_innovator=g.get("count_innovator"),
                )
        for i, r in enumerate(self.data["apptech_group_catalog"]):
            self.add(
                "group_catalog",
                observation_id=self.obs["apptech_group_catalog", i],
                entity_type=r["dashboard_entity"],
                group_id=r["group_id"],
                label=r["group_label_th"],
            )

    def finish(self):
        metadata = self.input_metadata["location_assertions"]
        for index, assertion in enumerate(self.inputs["location_assertions"]):
            self.add(
                "supplemental_location_lineage",
                parent_observation_id=self.obs.get(
                    ("apptech_dashboard_summaries", 0), ""
                ),
                parent_locator=f"evidence://{metadata['source_id']}/{metadata['run_id']}/{metadata['file']}#data/{index}",
                assertion_json=assertion,
                assertion_sha256=metadata["sha256"],
                counted_separately=False,
            )
        products = defaultdict(list)
        for r in self.tables["products"]:
            products[normalize(r["name"]).replace(" ", "")].append(r)
        for group in products.values():
            for a, b in itertools.combinations(group, 2):
                self.issue(
                    "possible_product_duplicate",
                    a["observation_id"],
                    "Same normalized title; retain separate offerings without variant/seller identity proof",
                    a["product_id"],
                    b["product_id"],
                )
        assessments = defaultdict(list)
        for r in self.tables["development_scores"]:
            assessments[r["assessment_id"]].append(r)
        for aid, score_rows in assessments.items():
            unique = {r["dimension"]: r for r in score_rows}
            person = score_rows[0]["person_id"]
            self.add(
                "development_assessments",
                assessment_id=aid,
                person_id=person,
                any_increase=any(r["delta"] > 0 for r in unique.values()),
                mixed_change=any(r["delta"] > 0 for r in unique.values())
                and any(r["delta"] < 0 for r in unique.values()),
                assessment_period="source start/current; undated",
                complete=len(unique) == 3,
            )
        context = defaultdict(set)
        for r in self.tables["assessment_observations"]:
            context[r["person_id"], r["project_id"]].add(r["assessment_id"])
        for (person, project), aids in context.items():
            if len(aids) > 1:
                self.issue(
                    "assessment_conflict",
                    "",
                    "Competing score pairs in "
                    + project
                    + "; no inferred supersession",
                    person,
                )
        levels = defaultdict(set)
        for r in self.tables["readiness"]:
            if r["scale"] == "TRL" and r["end_level"] is not None:
                levels[r["innovation_id"]].add(r["end_level"])
        for eid, values in levels.items():
            if len(values) > 1:
                self.issue(
                    "readiness_conflict",
                    "",
                    "Competing export TRL values "
                    + str(sorted(values))
                    + "; any eligible 8-9 still qualifies",
                    eid,
                )
        # Remove identical facts only; evidence bridges preserve every source observation.
        for name, rows in self.tables.items():
            self.tables[name] = list({dump(r): r for r in rows}.values())
        qualifying = {
            r["innovation_id"] for r in self.tables["readiness"] if r["qualifies"]
        }
        increased = {
            r["person_id"] for r in self.tables["development_scores"] if r["delta"] > 0
        }
        for measure, entities in [
            ("community_innovators", {r["person_id"] for r in self.tables["people"]}),
            ("broader_innovators", {r["person_id"] for r in self.tables["people"]}),
            ("ready_innovations", qualifying),
            (
                "listed_innovations",
                {r["innovation_id"] for r in self.tables["innovations"]},
            ),
            ("person_dimension_increase", increased),
            ("cultural_products", {r["product_id"] for r in self.tables["products"]}),
            (
                "reported_activities",
                {r["activity_id"] for r in self.tables["activities"]},
            ),
            ("cultural_sellers", {r["seller_id"] for r in self.tables["sellers"]}),
            (
                "cultural_entrepreneurs",
                {r["person_id"] for r in self.tables["entrepreneur_evidence"]},
            ),
        ]:
            for eid in sorted(entities):
                self.add(
                    "measure_contributions",
                    measure=measure,
                    entity_id=eid,
                    scope="icommunity_only",
                    status="provisional_source_local",
                )
            self.add(
                "measure_results",
                measure=measure,
                value=len(entities),
                scope="icommunity_only",
                status="provisional_source_local",
                note="Not final cross-source KPI; K02 PMUA headline remains 12251",
            )
        labels = {}
        for table, key, label in [
            ("people", "person_id", "display_name"),
            ("non_person_subjects", "subject_id", "display_name"),
            ("innovations", "innovation_id", "display_name"),
            ("products", "product_id", "name"),
            ("activities", "activity_id", "name"),
            ("sellers", "seller_id", "name"),
        ]:
            labels.update({r[key]: r[label] for r in self.tables[table]})
        review_outcomes = self.decisions.get("pilot_review_outcomes", {})
        case_ids = {r["review_id"] for r in self.tables["review_cases"]}
        assert review_outcomes.keys() <= case_ids, (
            "Reviewed case no longer matches: inspect before rebuilding"
        )
        for r in self.tables["review_cases"]:
            r["entity_name"] = labels.get(r["entity_id"], "")
            r["other_entity_name"] = labels.get(r["other_entity_id"], "")
            outcome = review_outcomes.get(r["review_id"], {})
            r["status"] = outcome.get("status", "unresolved")
            r["user_decision"] = outcome.get("user_decision", "")
        raw_names = {
            r["innovator_id"]: r["innovator_name"]
            for r in self.data["apptech_innovators"]
        }
        raw_names.update(
            {
                r["innovation_id"]: r["innovation_name"]
                for r in self.data["apptech_innovations"]
            }
        )
        raw_names.update(
            {
                self.innovation_member_keys[i]: r["innovation_name"]
                for i, r in enumerate(self.data["apptech_innovations"])
            }
        )
        for r in self.tables["identity_decisions"]:
            r["left_name"] = raw_names.get(r["left_source_id"], "")
            r["right_name"] = raw_names.get(r["right_source_id"], "")
        for r in self.tables["measure_results"]:
            if r["measure"] == "cultural_entrepreneurs":
                r["note"] = (
                    "Reviewed role evidence under accepted project scope; unresolved relationships retained. Not a final cross-source KPI."
                )
        self.add(
            "measure_results",
            measure="participating_businesses",
            value=None,
            scope="icommunity_only",
            status="not_constructed_from_person_or_product_membership",
            note="No invented business count from people or products; explicit business participation identities require further supported links.",
        )
        self.add(
            "measure_results",
            measure="K02_headline_reference",
            value=12251,
            scope="PMUA_aggregate_reference_only",
            status="not_an_icommunity_result",
            note="Accepted headline, kept separate; not added to named people.",
        )
        obsids = {r["observation_id"] for r in self.tables["source_observations"]}
        for table, rows in self.tables.items():
            for r in rows:
                if r.get("observation_id"):
                    assert r["observation_id"] in obsids, (table, r)
        entityids = set(labels)
        for table in [
            "entity_observations",
            "locations",
            "participations",
            "measure_contributions",
        ]:
            for r in self.tables[table]:
                assert r["entity_id"] in entityids, (table, r["entity_id"])
        person_ids = {r["person_id"] for r in self.tables["people"]}
        subject_ids = {r["subject_id"] for r in self.tables["non_person_subjects"]}
        for r in self.tables["work_mentions"]:
            assert (bool(r["person_id"]) + bool(r["subject_id"])) == 1
            assert (
                r["person_id"] in person_ids
                if r["person_id"]
                else r["subject_id"] in subject_ids
            )
            assert not r["innovation_id"] or r["innovation_id"] in entityids
        for r in self.tables["product_sellers"]:
            assert r["product_id"] in entityids and r["seller_id"] in entityids
        if len(obsids) != len(self.tables["source_observations"]):
            raise ValueError("iCommunity observation accounting failed")

    def run(self):
        self.ingest()
        self.people()
        self.innovations()
        self.other_sources()
        self.finish()
        return {name: list(rows) for name, rows in self.tables.items()}


def build_tables(datasets, reviews, geography, input_metadata):
    """Build all iCommunity source-local legacy tables from declared captures."""
    return Pilot(datasets, reviews, geography, input_metadata).run()

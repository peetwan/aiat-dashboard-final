from __future__ import annotations

from collections import Counter
from functools import lru_cache
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from f2_candidate_adapter import DEFAULT_CANDIDATE_ROOT, VerifiedF2Candidate


C02 = "C02_COMMUNITY"
ALLOWED_ROLES = {"community_innovator", "inventor"}
ALLOWED_IDENTITIES = {"source_supported", "reviewed_cross_source"}
FORBIDDEN_PERSON_KEYS = {
    "account_id",
    "address",
    "coordinates",
    "email",
    "latitude",
    "longitude",
    "phone",
    "profile_id",
    "street_address",
    "telephone",
    "token",
}


@lru_cache(maxsize=1)
def _verified_candidate() -> VerifiedF2Candidate:
    return VerifiedF2Candidate.open()


@pytest.fixture
def staged_c02_candidate(monkeypatch) -> VerifiedF2Candidate:
    if not DEFAULT_CANDIDATE_ROOT.is_dir():
        pytest.skip("private staged C02 candidate is not present")
    candidate = _verified_candidate()
    candidate.install(monkeypatch)
    return candidate


def _walk_keys(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key).casefold()
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _topic(candidate: VerifiedF2Candidate, topic_id: str) -> dict[str, Any]:
    return candidate.load_artifact(candidate.snapshot, f"f2/topic/{topic_id}")


def _all_c02_details(
    candidate: VerifiedF2Candidate, topic: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    details: dict[str, dict[str, Any]] = {}
    for artifact_key in sorted(set(topic["detail_artifacts"].values())):
        shard = candidate.load_artifact(candidate.snapshot, artifact_key)
        for entity_id, detail in shard["details_by_id"].items():
            assert entity_id not in details
            details[entity_id] = detail
    return details


def test_staged_candidate_community_api_search_paging_etag_and_no_map(
    staged_c02_candidate: VerifiedF2Candidate,
) -> None:
    candidate = staged_c02_candidate
    client = TestClient(app)

    first = client.get(
        "/api/public/v1/f2/topics/k02",
        params={"measure": C02, "limit": 25},
    )
    assert first.status_code == 200
    assert len(first.content) < 16 * 1024
    payload = first.json()
    assert payload["revision"] == candidate.snapshot.revision
    assert payload["result"]["value"] == 4640
    assert payload["list"]["scoped_item_count"] == 4640
    assert payload["list"]["matching_item_count"] == 4640
    assert payload["list"]["returned_count"] == 25
    assert payload["filter_contract"]["supported_filters"] == []
    assert payload["filter_contract"]["map_availability"] == "unavailable"
    assert not any("/detail/" in key for key in candidate.reads)

    not_modified = client.get(
        "/api/public/v1/f2/topics/k02",
        params={"measure": C02, "limit": 25},
        headers={"If-None-Match": first.headers["etag"]},
    )
    assert not_modified.status_code == 304
    assert not not_modified.content

    final_page = client.get(
        "/api/public/v1/f2/topics/k02",
        params={"measure": C02, "limit": 25, "offset": 4625},
    ).json()
    assert final_page["list"]["returned_count"] == 15

    first_item = payload["list"]["items"][0]
    search = client.get(
        "/api/public/v1/f2/topics/k02",
        params={"measure": C02, "q": first_item["label"]},
    ).json()
    assert search["result"]["value"] == 4640
    assert search["list"]["matching_item_count"] >= 1
    assert first_item["entity_id"] in {
        item["entity_id"] for item in search["list"]["items"]
    }
    unmatched = client.get(
        "/api/public/v1/f2/topics/k02",
        params={"measure": C02, "q": "not-an-admitted-c02-label"},
    ).json()
    assert unmatched["result"]["value"] == 4640
    assert unmatched["list"]["matching_item_count"] == 0

    for name, value in (
        ("province", "10"),
        ("year", "2026"),
        ("role", "inventor"),
        ("organization", "example"),
    ):
        response = client.get(
            "/api/public/v1/f2/topics/k02",
            params={"measure": C02, name: value},
        )
        assert response.status_code == 422
    assert client.get(f"/api/public/v1/f2/map?measure={C02}").status_code == 422
    assert (
        client.get("/api/public/v1/f2/topics/k02", params={"measure": "K02"})
        .json()["result"]["value"]
        == 12251
    )
    assert (
        client.get(
            "/api/public/v1/f2/topics/k02",
            params={"measure": C02, "revision": "0" * 64},
        ).status_code
        == 409
    )


def test_staged_candidate_has_one_c02_population_and_no_withheld_titles(
    staged_c02_candidate: VerifiedF2Candidate,
) -> None:
    candidate = staged_c02_candidate
    client = TestClient(app)
    topic = _topic(candidate, "k02")
    c02_ids = topic["item_ids_by_measure_and_scope"][C02]["national"]

    assert len(c02_ids) == 4640
    assert "C02_BROADER" not in topic["measure_ids"]
    assert "C02_BROADER" not in topic["filter_contracts"]
    assert "C02_BROADER" not in topic["item_ids_by_measure_and_scope"]

    response = client.get(
        "/api/public/v1/f2/topics/k02",
        params={"measure": C02, "limit": 25},
    )
    assert response.status_code == 200
    assert len(response.content) < 16 * 1024
    assert response.json()["result"]["value"] == 4640
    assert response.json()["list"]["scoped_item_count"] == 4640

    removed = client.get(
        "/api/public/v1/f2/topics/k02",
        params={"measure": "C02_BROADER"},
    )
    assert removed.status_code == 404

    former_placeholder = client.get(
        "/api/public/v1/f2/topics/k02",
        params={"measure": C02, "q": "ชื่ออยู่ระหว่างการตรวจสอบ"},
    )
    assert former_placeholder.status_code == 200
    assert former_placeholder.json()["list"]["matching_item_count"] == 0
    assert not (set(_walk_keys(former_placeholder.json())) & FORBIDDEN_PERSON_KEYS)


def test_staged_candidate_person_to_innovation_navigation_stays_in_revision(
    staged_c02_candidate: VerifiedF2Candidate,
) -> None:
    candidate = staged_c02_candidate
    client = TestClient(app)
    topic = _topic(candidate, "k02")
    person_id = next(
        entity_id
        for entity_id in topic["item_ids_by_measure_and_scope"][C02]["national"]
        if topic["items_by_id"][entity_id]["related_work_count"] > 0
    )

    person_response = client.get(
        f"/api/public/v1/f2/topics/k02/details/{person_id}",
        params={"measure": C02, "revision": candidate.snapshot.revision},
    )
    assert person_response.status_code == 200
    person_payload = person_response.json()
    relationships = person_payload["detail"]["relationships"]
    assert relationships
    target = relationships[0]["target_detail"]
    assert target["topic_id"] == "k04"
    assert target["measure_id"] in {"K04", "C04_LISTED"}

    target_response = client.get(
        f"/api/public/v1/f2/topics/{target['topic_id']}/details/{target['entity_id']}",
        params={
            "measure": target["measure_id"],
            "revision": person_payload["revision"],
        },
    )
    assert target_response.status_code == 200
    target_payload = target_response.json()
    assert target_payload["revision"] == person_payload["revision"]
    assert target_payload["measure_id"] == target["measure_id"]
    assert target_payload["detail"]["entity_id"] == target["entity_id"]


def test_staged_candidate_identity_privacy_and_relationship_integrity(
    staged_c02_candidate: VerifiedF2Candidate,
) -> None:
    candidate = staged_c02_candidate
    topic = _topic(candidate, "k02")
    details = _all_c02_details(candidate, topic)
    c02 = set(topic["item_ids_by_measure_and_scope"][C02]["national"])

    assert set(topic["items_by_id"]) == c02
    assert set(topic["detail_artifacts"]) == c02
    assert set(details) == c02

    identity_counts = Counter()
    relationship_count = 0
    k04_topic = _topic(candidate, "k04")
    k04_memberships = {
        measure: set(scopes["national"])
        for measure, scopes in k04_topic["item_ids_by_measure_and_scope"].items()
        if measure in {"K04", "C04_LISTED"}
    }
    target_ids_by_artifact: dict[str, set[str]] = {}

    for entity_id, detail in details.items():
        compact = topic["items_by_id"][entity_id]
        assert compact["identity_status"] in ALLOWED_IDENTITIES
        assert detail["identity_status"] == compact["identity_status"]
        identity_counts[detail["identity_status"]] += 1
        assert set(compact["role_codes"]) <= ALLOWED_ROLES
        assert detail["entity_id"] == entity_id
        assert detail["detail_availability"] == "available"
        assert detail["locations"] == []
        assert detail["province_codes"] == []
        assert not (set(_walk_keys(detail)) & FORBIDDEN_PERSON_KEYS)

        assert detail["label_availability"] == "available"
        assert detail["label"] != "ชื่ออยู่ระหว่างการตรวจสอบ"
        roles = detail["children"]["qualifying_roles"]
        assert roles
        assert any(C02 in role["qualifies_for"] for role in roles)
        for role in roles:
            assert role["role_code"] in ALLOWED_ROLES
            assert role["evidence_basis"] == "source_supported_person_role"
            assert role["source_id"] in detail["source_ids"]

        relationships = detail["relationships"]
        relationship_count += len(relationships)
        assert compact["related_work_count"] == len(
            {relationship["entity_id"] for relationship in relationships}
        )
        assert detail["related_work_count"] == compact["related_work_count"]
        for relationship in relationships:
            assert relationship["kind"] in {
                "contributed_to_innovation",
                "invented_innovation",
            }
            assert relationship["role_code"] in ALLOWED_ROLES
            assert relationship["source_id"] in detail["source_ids"]
            target = relationship["target_detail"]
            assert target["topic_id"] == "k04"
            assert target["measure_id"] in {"K04", "C04_LISTED"}
            assert target["entity_id"] in k04_memberships[target["measure_id"]]
            artifact_key = k04_topic["detail_artifacts"][target["entity_id"]]
            assert artifact_key in candidate.snapshot.files
            target_ids_by_artifact.setdefault(artifact_key, set()).add(
                target["entity_id"]
            )

    assert identity_counts == {"source_supported": 4604, "reviewed_cross_source": 36}
    assert relationship_count == 5125
    assert candidate.verification["unlinked_relationships"] == 0

    for artifact_key, expected_ids in target_ids_by_artifact.items():
        target_shard = candidate.load_artifact(candidate.snapshot, artifact_key)
        assert expected_ids <= set(target_shard["details_by_id"])

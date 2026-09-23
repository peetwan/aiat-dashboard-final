from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app import f2_data
from app.main import app


@pytest.fixture
def c02_publication(monkeypatch):
    """Synthetic reviewed payloads; no active candidate or database is read."""
    community_id = "global_person_community_example"
    inventor_id = "global_person_inventor_example"
    topic_key = "f2/topic/k02"
    child_key = "f2/topic/k02/detail/000"
    c02 = "C02_COMMUNITY"
    items = {
        community_id: {
            "label": "ชุมชน ตัวอย่าง",
            "label_availability": "available",
            "identity_status": "source_supported",
            "source_ids": ["f2_icommunity"],
            "role_codes": ["community_innovator"],
            "role_labels_th": ["นวัตกรชุมชน"],
            "related_work_count": 1,
        },
        inventor_id: {
            "label": "ผู้ประดิษฐ์ ตัวอย่าง",
            "label_availability": "available",
            "identity_status": "reviewed_cross_source",
            "source_ids": ["f2_apptech_mru"],
            "role_codes": ["inventor"],
            "role_labels_th": ["ผู้ประดิษฐ์"],
            "related_work_count": 0,
        },
    }
    contracts = {
        c02: {
            "detail_availability": "available",
            "map_availability": "unavailable",
            "supported_filters": [],
            "permitted_combinations": [[]],
        }
    }
    contracts["K02"] = {
        **contracts[c02],
        "detail_availability": "not_applicable",
    }
    membership = {c02: [community_id, inventor_id]}
    prepared = {}
    for measure, counted in (("K02", 12251), (c02, 3)):
        prepared[measure] = {
            "default": {
                "result": {
                    "measure_id": measure,
                    "scope_key": "national",
                    "value": counted,
                    "unit": "person",
                    "availability": "available",
                    "requested_filters": {},
                    "applied_filters": {},
                },
                "item_ids": membership.get(measure, []),
            },
            "selections": {},
            "choices": {},
        }
    topic = {
        "topic_id": "k02",
        "measure_ids": ["K02", c02],
        "filter_contracts": contracts,
        "scopes": {"national": {"prepared_filters": prepared}},
        "items_by_id": items,
        "item_ids_by_measure_and_scope": {
            measure: {"national": ids} for measure, ids in membership.items()
        },
        "details_by_id": {},
        "detail_artifacts": {item_id: child_key for item_id in items},
        "sources": [{"source_id": "f2_icommunity"}],
    }
    details = {
        item_id: {
            **item,
            "entity_id": item_id,
            "detail_availability": "available",
            "locations": [],
            "province_codes": [],
            "children": {
                "qualifying_roles": [
                    {
                        "assertion_id": f"role_{index}",
                        "role_code": item["role_codes"][0],
                        "qualifies_for": [c02],
                        "source_id": item["source_ids"][0],
                    }
                ]
            },
        }
        for index, (item_id, item) in enumerate(items.items())
    }
    payloads = {
        "f2/geography": {"provinces": {"10": {"province_name_th": "กรุงเทพมหานคร"}}},
        topic_key: topic,
        child_key: {"details_by_id": details},
        "f2/overview": {
            "headlines": [
                {
                    "measure_id": "K02",
                    "companions": [
                        {"measure_id": c02, "map_availability": "unavailable"}
                    ],
                }
            ]
        },
    }
    revision = f2_data.RevisionSnapshot(
        revision="a" * 64,
        release_id="synthetic-c02-release",
        release_date="2026-09-17",
        files={key: {} for key in payloads},
        source_ids=["f2_icommunity", "f2_apptech_mru"],
    )
    reads = []

    def load(snapshot, artifact_key):
        assert snapshot == revision
        reads.append(artifact_key)
        return deepcopy(payloads[artifact_key])

    monkeypatch.setattr(f2_data, "_active_revision", lambda: revision)
    monkeypatch.setattr(f2_data, "_load_artifact", load)
    return community_id, inventor_id, child_key, reads


def test_c02_api_keeps_counted_population_separate_from_admitted_search(
    c02_publication,
):
    community_id, _, child_key, reads = c02_publication
    client = TestClient(app)
    response = client.get(
        "/api/public/v1/f2/topics/k02",
        params={"measure": "C02_COMMUNITY", "q": "ชุมชน", "limit": 1},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["value"] == 3
    assert payload["list"]["scoped_item_count"] == 2
    assert payload["list"]["matching_item_count"] == 1
    assert payload["list"]["items"][0]["entity_id"] == community_id
    assert payload["list"]["items"][0]["role_codes"] == ["community_innovator"]
    assert child_key not in reads
    etag_response = client.get(
        "/api/public/v1/f2/topics/k02",
        params={"measure": "C02_COMMUNITY", "q": "ชุมชน", "limit": 1},
        headers={"If-None-Match": response.headers["etag"]},
    )
    assert etag_response.status_code == 304
    assert not etag_response.content
    unmatched = client.get(
        "/api/public/v1/f2/topics/k02",
        params={"measure": "C02_COMMUNITY", "q": "not-an-admitted-label"},
    ).json()
    assert unmatched["result"]["value"] == 3
    assert unmatched["list"]["matching_item_count"] == 0
    assert (
        client.get("/api/public/v1/f2/topics/k02?measure=K02").json()["result"]["value"]
        == 12251
    )


def test_c02_detail_serves_both_actual_roles_from_one_population(
    c02_publication,
):
    community_id, inventor_id, child_key, reads = c02_publication
    client = TestClient(app)
    details = []
    for person_id in (community_id, inventor_id):
        response = client.get(
            f"/api/public/v1/f2/topics/k02/details/{person_id}",
            params={"measure": "C02_COMMUNITY", "revision": "a" * 64},
        )
        assert response.status_code == 200
        details.append(response.json()["detail"])
        assert response.json()["provenance"]["artifact_keys"] == [
            "f2/topic/k02",
            child_key,
        ]
    assert details[0]["role_codes"] == ["community_innovator"]
    assert details[1]["role_codes"] == ["inventor"]
    assert child_key in reads
    assert (
        client.get(
            f"/api/public/v1/f2/topics/k02/details/{inventor_id}",
            params={"measure": "C02_BROADER"},
        ).status_code
        == 404
    )
    assert (
        client.get(
            "/api/public/v1/f2/topics/k02/details/global_person_wholly_withheld",
            params={"measure": "C02_COMMUNITY"},
        ).status_code
        == 404
    )

def test_c02_api_rejects_unsupported_filters_and_stale_revision(c02_publication):
    common_id, _, _, _ = c02_publication
    client = TestClient(app)
    for name, value in (
        ("province", "10"),
        ("year", "2026"),
        ("role", "inventor"),
        ("organization", "example"),
    ):
        response = client.get(
            "/api/public/v1/f2/topics/k02",
            params={"measure": "C02_COMMUNITY", name: value},
        )
        assert response.status_code == 422
    assert client.get("/api/public/v1/f2/map?measure=C02_COMMUNITY").status_code == 422
    assert (
        client.get(
            f"/api/public/v1/f2/topics/k02/details/{common_id}",
            params={"measure": "C02_COMMUNITY", "revision": "b" * 64},
        ).status_code
        == 409
    )
    assert (
        client.get("/api/public/v1/f2/topics/k02?measure=K02&q=example").status_code
        == 422
    )


def test_c02_accepted_province_scope_reuses_generic_api_and_map(
    c02_publication, monkeypatch
):
    community_id, _, child_key, _ = c02_publication
    original_load = f2_data._load_artifact

    def load_with_province(snapshot, artifact_key):
        payload = original_load(snapshot, artifact_key)
        if artifact_key == "f2/topic/k02":
            contract = payload["filter_contracts"]["C02_COMMUNITY"]
            contract["supported_filters"] = ["province"]
            contract["permitted_combinations"] = [[], ["province"]]
            contract["map_availability"] = "province"
            payload["scopes"]["province/10"] = {
                "scope_key": "province/10",
                "prepared_filters": {
                    "C02_COMMUNITY": {
                        "default": {
                            "result": {
                                "measure_id": "C02_COMMUNITY",
                                "scope_key": "province/10",
                                "value": 1,
                                "unit": "person",
                                "availability": "available",
                                "requested_filters": {"province": ["10"]},
                                "applied_filters": {"province": ["10"]},
                            },
                            "item_ids": [community_id],
                        },
                        "selections": {},
                        "choices": {},
                    }
                },
            }
            payload["item_ids_by_measure_and_scope"]["C02_COMMUNITY"][
                "province/10"
            ] = [community_id]
        elif artifact_key == child_key:
            detail = payload["details_by_id"][community_id]
            detail["province_codes"] = ["10"]
            detail["locations"] = [
                {
                    "province_code": "10",
                    "province": "กรุงเทพมหานคร",
                    "location_role": "source_reported_innovator_location",
                    "source_id": "f2_icommunity",
                }
            ]
        elif artifact_key == "f2/overview":
            payload["headlines"][0]["companions"][0].update(
                {
                    "topic_id": "k02",
                    "map_availability": "province",
                    "map_legend_th": "สีแสดงจำนวนบุคคลไม่ซ้ำรายจังหวัด",
                }
            )
        return payload

    monkeypatch.setattr(f2_data, "_load_artifact", load_with_province)
    client = TestClient(app)
    response = client.get(
        "/api/public/v1/f2/topics/k02",
        params={"measure": "C02_COMMUNITY", "province": "10", "q": "ชุมชน"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["value"] == 1
    assert payload["list"]["scoped_item_count"] == 1
    assert payload["list"]["matching_item_count"] == 1
    assert payload["list"]["items"][0]["entity_id"] == community_id
    detail = client.get(
        f"/api/public/v1/f2/topics/k02/details/{community_id}",
        params={
            "measure": "C02_COMMUNITY",
            "province": "10",
            "revision": "a" * 64,
        },
    )
    assert detail.status_code == 200
    assert detail.json()["detail"]["locations"] == [
        {
            "province_code": "10",
            "province": "กรุงเทพมหานคร",
            "location_role": "source_reported_innovator_location",
            "source_id": "f2_icommunity",
        }
    ]
    map_response = client.get(
        "/api/public/v1/f2/map", params={"measure": "C02_COMMUNITY"}
    )
    assert map_response.status_code == 200
    map_payload = map_response.json()
    assert map_payload["legend"]["meaning_th"] == "สีแสดงจำนวนบุคคลไม่ซ้ำรายจังหวัด"
    assert len(map_payload["cells"]) == 1
    cell = map_payload["cells"][0]
    assert cell["province_code"] == "10"
    assert cell["province_name_th"] == "กรุงเทพมหานคร"
    assert cell["result"]["value"] == 1
    assert cell["result"]["unit"] == "คน"
    assert cell["result"]["requested_filters"] == {"province": ["10"]}
    assert client.get(
        "/api/public/v1/f2/topics/k02",
        params={"measure": "C02_COMMUNITY", "region": "central"},
    ).status_code == 422


@pytest.mark.parametrize("failure", ["undeclared_shard", "missing_detail"])
def test_c02_detail_fails_closed_for_inconsistent_shards(
    c02_publication, monkeypatch, failure
):
    common_id, _, child_key, _ = c02_publication
    if failure == "undeclared_shard":
        f2_data._active_revision().files.pop(child_key)
    else:
        original_load = f2_data._load_artifact

        def load(snapshot, artifact_key):
            payload = original_load(snapshot, artifact_key)
            if artifact_key == child_key:
                payload["details_by_id"].pop(common_id)
            return payload

        monkeypatch.setattr(f2_data, "_load_artifact", load)
    response = TestClient(app).get(
        f"/api/public/v1/f2/topics/k02/details/{common_id}",
        params={"measure": "C02_COMMUNITY"},
    )
    assert response.status_code == 503
    assert "ชุมชน ตัวอย่าง" not in response.text

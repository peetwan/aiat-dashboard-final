from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.f2_data import f2_cache_stats, reset_f2_cache
from app.main import app
from app.models import PublicArtifact


def _measure(overview: dict, measure_id: str) -> dict:
    for headline in overview["headlines"]:
        if headline["measure_id"] == measure_id:
            return headline
        for companion in headline.get("companions", []):
            if companion["measure_id"] == measure_id:
                return companion
    raise AssertionError(f"missing measure {measure_id}")


def test_f2_api_contract_selective_reads_and_semantic_regressions():
    reset_f2_cache()
    with TestClient(app) as client:
        overview_response = client.get("/api/public/v1/f2/overview")
        assert overview_response.status_code == 200
        overview = overview_response.json()
        assert len(overview["headlines"]) == 14
        assert sum(len(row["companions"]) for row in overview["headlines"]) == 7
        expected_units = {
            "K01A": "จังหวัด",
            "K01B": "แห่ง",
            "K02": "คน",
            "C02_COMMUNITY": "คน",
            "K03": "ครั้ง",
            "K04": "นวัตกรรม",
            "C04_LISTED": "นวัตกรรม",
            "K05": "ร้านค้า",
            "K06": "คน",
            "K07": "รายการ",
            "K08": "ธุรกิจชุมชน",
            "C08_PARTICIPATING": "ธุรกิจชุมชน",
            "C08_REPORTED_BUSINESSES": "ธุรกิจชุมชน",
            "C08_ASSESSED_PEOPLE": "คน",
            "C08_INCREASED_PEOPLE": "คน",
            "K09": "คนต่อเดือน",
            "K10": "ล้านบาทต่อเดือน",
            "C10_ALTERNATIVE": "ล้านบาทต่อเดือน",
            "K11A": "คลัสเตอร์",
            "K11B": "จังหวัด",
            "K12": "รายการ",
        }
        for measure_id, expected_unit in expected_units.items():
            measure = _measure(overview, measure_id)
            assert measure["unit"] == expected_unit
            assert measure["result"]["unit"] == expected_unit
        assert "C02_BROADER" not in expected_units
        assert _measure(overview, "C02_COMMUNITY")["result"]["value"] == 4640
        assert len(overview_response.content) <= 256 * 1024
        assert overview["revision"] != overview["release_id"]
        assert len(overview["revision"]) == 64
        assert overview_response.headers["cache-control"] == "public, max-age=0, must-revalidate"

        not_modified = client.get(
            "/api/public/v1/f2/overview",
            headers={"If-None-Match": overview_response.headers["etag"]},
        )
        assert not_modified.status_code == 304
        assert not not_modified.content

        province = client.get("/api/public/v1/f2/overview?province=10").json()
        assert province["scope"] == "province/10"
        assert _measure(overview, "K02")["result"] != _measure(province, "K02")["result"]
        assert _measure(province, "K09")["result"]["availability"] == "unavailable"
        assert _measure(province, "K09")["national_context"]["relationship"] == "independent_source_region_not_mapped_to_selected_dashboard_geography"
        assert _measure(overview, "K08")["result"] != _measure(overview, "C08_PARTICIPATING")["result"]

        map_response = client.get("/api/public/v1/f2/map?measure=K01B")
        assert map_response.status_code == 200
        map_payload = map_response.json()
        assert len(map_payload["cells"]) == 77
        assert {cell["province_code"] for cell in map_payload["cells"]} >= {"10", "96"}
        assert len(map_response.content) <= 256 * 1024
        assert map_payload["unit"] == "แห่ง"
        assert {
            cell["result"]["unit"] for cell in map_payload["cells"]
        } == {"แห่ง"}
        c02_map_response = client.get("/api/public/v1/f2/map?measure=C02_COMMUNITY")
        assert c02_map_response.status_code == 200
        c02_map = c02_map_response.json()
        assert len(c02_map["cells"]) == 77
        c02_values = [cell["result"]["value"] for cell in c02_map["cells"]]
        assert sum(value > 0 for value in c02_values) == 37
        assert sum(value == 0 for value in c02_values) == 40
        assert sum(c02_values) == 4418
        assert max(c02_values) == 490
        assert c02_map["coverage"] == {
            "national_total": 4640,
            "province_sum_is_additive": False,
            "selected_count": 4640,
            "with_province": 4415,
            "without_province": 225,
        }
        assert "บุคคลไม่ซ้ำ" in c02_map["legend"]["meaning_th"]

        list_response = client.get("/api/public/v1/f2/topics/k12?measure=K12&limit=25")
        assert list_response.status_code == 200
        topic_page = list_response.json()
        assert topic_page["result"]["value"] == 5141
        assert topic_page["list"]["scoped_item_count"] == 5141
        assert topic_page["list"]["matching_item_count"] == 5141
        assert topic_page["list"]["returned_count"] == 25
        assert len(list_response.content) <= 256 * 1024
        assert topic_page["result"]["unit"] == "รายการ"

        first_item = topic_page["list"]["items"][0]
        assert first_item["province_names_th"] == ["สงขลา"]
        query = first_item["label"][:4]
        searched = client.get(
            "/api/public/v1/f2/topics/k12",
            params={"measure": "K12", "q": query, "limit": 25},
        ).json()
        assert searched["result"] == topic_page["result"]
        assert searched["list"]["matching_item_count"] <= 5141
        assert all(
            query.casefold() in item["label"].casefold()
            for item in searched["list"]["items"]
        )

        filtered = client.get(
            "/api/public/v1/f2/topics/k12",
            params={"measure": "K12", "province": "10", "category": "AA"},
        )
        assert filtered.status_code == 200
        assert filtered.json()["result"]["requested_filters"] == {
            "category": ["AA"],
            "province": ["10"],
        }

        detail_response = client.get(
            f"/api/public/v1/f2/topics/k12/details/{first_item['entity_id']}",
            params={"measure": "K12", "revision": overview["revision"]},
        )
        assert detail_response.status_code == 200
        detail = detail_response.json()["detail"]
        assert detail["entity_id"] == first_item["entity_id"]
        assert detail["detail_availability"] == "available"
        assert len(detail_response.json()["provenance"]["artifact_keys"]) == 2

        inline_page = client.get(
            "/api/public/v1/f2/topics/k01b?measure=K01B&limit=1"
        ).json()
        inline_id = inline_page["list"]["items"][0]["entity_id"]
        inline_detail = client.get(
            f"/api/public/v1/f2/topics/k01b/details/{inline_id}?measure=K01B"
        )
        assert inline_detail.status_code == 200
        assert inline_detail.json()["provenance"]["artifact_keys"] == ["f2/topic/k01b"]

        reads = f2_cache_stats()["database_reads"]
        detail_reads = [key for key in reads if "/detail/" in key]
        assert detail_reads == [
            detail_response.json()["provenance"]["artifact_keys"][-1]
        ]

        k04 = client.get("/api/public/v1/f2/topics/k04?measure=K04").json()
        c04 = client.get("/api/public/v1/f2/topics/k04?measure=C04_LISTED").json()
        assert k04["result"]["value"] == 514
        assert c04["result"]["value"] == 2399

        source_regions = client.get("/api/public/v1/f2/topics/k09?measure=K09")
        assert source_regions.status_code == 200
        assert len(source_regions.json()["source_region_results"]) == 6
        assert all(
            row["result"]["scope_key"].startswith("source_region/")
            for row in source_regions.json()["source_region_results"]
        )
        assert {
            row["result"]["unit"]
            for row in source_regions.json()["source_region_results"]
        } == {"คนต่อเดือน"}

        zero_price = client.get(
            "/api/public/v1/f2/topics/k07/details/offering_family_002dfbc09f8c360f3395?measure=K07"
        )
        assert zero_price.status_code == 200
        assert "price unspecified/source reports 0" in json.dumps(
            zero_price.json()["detail"], ensure_ascii=False
        )

        withheld = client.get(
            "/api/public/v1/f2/topics/k12/details/cultural_map_subject_c8aca030751e9a4d6c32?measure=K12"
        )
        assert withheld.status_code == 200
        assert withheld.json()["detail"]["label"] == "Title withheld pending review"

        assert client.get("/api/public/v1/f2/topics/nope?measure=K12").status_code == 404
        assert client.get("/api/public/v1/f2/topics/k12?measure=K09").status_code == 404
        assert client.get("/api/public/v1/f2/overview?province=99").status_code == 422
        assert client.get("/api/public/v1/f2/overview?year=2025").status_code == 422
        assert client.get("/api/public/v1/f2/map?measure=K09").status_code == 422
        assert client.get("/api/public/v1/f2/topics/k01b?measure=K01B&category=AA").status_code == 422
        assert client.get("/api/public/v1/f2/topics/k06?measure=K06&q=x").status_code == 422
        assert client.get(
            "/api/public/v1/f2/topics/k12/details/not-a-member?measure=K12"
        ).status_code == 404
        assert client.get(
            "/api/public/v1/f2/overview",
            params={"revision": "0" * 64},
        ).status_code == 409

        with SessionLocal() as session:
            artifact = session.get(PublicArtifact, "f2/overview")
            assert artifact is not None
            artifact.content_hash = "0" * 64
            session.commit()
        reset_f2_cache()
        inconsistent = client.get("/api/public/v1/f2/overview")
        assert inconsistent.status_code == 503
        assert "hash" in inconsistent.json()["detail"]


def test_f2_public_responses_do_not_contain_runtime_paths():
    with TestClient(app) as client:
        payload = client.get("/api/public/v1/f2/overview").json()
    encoded = json.dumps(payload, ensure_ascii=False)
    assert "data/runtime" not in encoded
    assert "raw/" not in encoded

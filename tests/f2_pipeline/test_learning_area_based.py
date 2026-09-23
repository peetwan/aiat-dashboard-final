from tools.f2_pipeline.sources.learning_area_based import TABLE_COLUMNS, build_tables


class Geography:
    reference_version = "geo-v1"
    provinces = [{"provinceCode": 10, "provinceNameTh": "ทดสอบ"}]
    districts = [
        {"provinceCode": 10, "districtCode": 1001, "districtNameTh": "เมืองทดสอบ"}
    ]
    subdistricts = [
        {
            "provinceCode": 10,
            "districtCode": 1001,
            "subdistrictCode": 100101,
            "subdistrictNameTh": "ตัวอย่าง",
        }
    ]


def row(source_id, sequence, district="เมือง", subdistrict="ตัวอย่าง"):
    return {
        "id": source_id,
        "sequence": sequence,
        "businessName": "วิสาหกิจตัวอย่าง",
        "projectName": "โครงการทดสอบ",
        "researchUnit": "มหาวิทยาลัยทดสอบ",
        "fiscalYear": "2568",
        "createdAt": "2025-01-01T00:00:00Z",
        "updatedAt": "2025-01-02T00:00:00Z",
        "region": "ภาคกลาง",
        "province": "ทดสอบ",
        "district": district,
        "subDistrict": subdistrict,
    }


def metadata():
    files = {
        "area_based_response": "area_based.json",
        "area_based_rows": "area_based_rows.jsonl",
        "area_based_stats": "area_based_stats.json",
        "refresh_summary": "complete_refresh_summary.json",
        "capture_manifest": "manifest.json",
    }
    result = {
        key: {
            "source_id": "f2_learning_area_based",
            "run_id": "run-1",
            "file": file,
            "sha256": f"sha-{key}",
            "size": 1,
            "captured_at": "2026-01-01T00:00:00Z",
            "originating_system": "synthetic",
        }
        for key, file in files.items()
    }
    result["area_based_rows"]["canonical_evidence_path"] = "area_based_rows.jsonl.gz"
    return result


def test_reviewed_component_swap_participations_and_audit_coverage():
    rows = [row("one", 1), row("two", 2, district="ตัวอย่าง", subdistrict="เมือง")]
    stats = {
        "totalRecords": 2,
        "byRegion": {"ภาคกลาง": 2},
        "byProvince": {"ทดสอบ": 2},
        "byDistrict": {"เมือง": 1, "ตัวอย่าง": 1},
        "bySubDistrict": {"ตัวอย่าง": 1, "เมือง": 1},
        "byResearchUnit": {"มหาวิทยาลัยทดสอบ": 2},
        "byFiscalYear": {"2568": 2},
        "byBusinessType": {"ไม่ระบุ": 2},
    }
    meta = metadata()
    manifest = {
        "source_id": "f2_learning_area_based",
        "run_id": "run-1",
        "datasets": [{"file": "area_based_rows.jsonl.gz", "sha256": "sha-gzip"}],
        "extra_files": [
            {
                "file": "area_based.json",
                "sha256": meta["area_based_response"]["sha256"],
            },
            {
                "file": "area_based_stats.json",
                "sha256": meta["area_based_stats"]["sha256"],
            },
            {
                "file": "complete_refresh_summary.json",
                "sha256": meta["refresh_summary"]["sha256"],
            },
        ],
    }
    datasets = {
        "area_based_response": {"data": rows, "stats": stats},
        "area_based_rows": rows,
        "area_based_stats": stats,
        "refresh_summary": {"row_count": 2, "stats": stats},
        "capture_manifest": manifest,
    }
    reviews = {
        "reviewed_cases.json": {
            "exact_name_groups": [
                {
                    "group": 1,
                    "source_ids": ["one", "two"],
                    "treatment": "merge_supported",
                    "evidence": "semantic://synthetic/exact-name",
                }
            ],
            "near_name_pairs": [],
            "cannot_links": [],
            "location_overrides": {
                "swaps": ["two"],
                "district_aliases": {},
                "subdistrict_aliases": [],
            },
        },
        "geography_review.json": {
            "origin_sha256": meta["area_based_response"]["sha256"],
            "area": {
                "full_hierarchy_review": [
                    {"id": "one", "status": "hierarchy_match"},
                    {"id": "two", "status": "district_subdistrict_swapped"},
                ]
            },
        },
    }

    tables = build_tables(datasets, reviews, Geography(), meta)

    assert len(tables["businesses"]) == 1
    assert len(tables["participations"]) == 2
    assert {row["business_id"] for row in tables["participations"]} == {
        tables["businesses"][0]["business_id"]
    }
    second_observation = next(
        row["observation_id"]
        for row in tables["source_observations"]
        if row["source_id"] == "two"
    )
    swapped = next(
        row
        for row in tables["locations"]
        if row["observation_id"] == second_observation
    )
    assert swapped["resolution_method"] == "reviewed_district_subdistrict_swap"
    assert (
        swapped["district_code"] == "1001" and swapped["subdistrict_code"] == "100101"
    )
    assert len(tables["review_cases"]) == 2
    assert isinstance(tables["identity_decisions"][0]["source_ids_json"], list)
    assert all(
        set(row) == set(TABLE_COLUMNS[name])
        for name, rows in tables.items()
        for row in rows
    )

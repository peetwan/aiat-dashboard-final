from tools.f2_pipeline.sources.learning_dashboard import TABLE_COLUMNS, build_tables


class Geography:
    reference_version = "geo-v1"
    provinces = [{"provinceCode": 10, "provinceNameTh": "ทดสอบ"}]

    def resolve(self, province, district):
        return {"province_normalized": province, "province_code": "10"}


def metadata():
    files = {
        "learning_dashboard_response": "learning_dashboard.json",
        "dashboard_keys": "dashboard_keys.jsonl",
        "refresh_summary": "complete_refresh_summary.json",
        "capture_manifest": "manifest.json",
    }
    result = {
        key: {
            "source_id": "f2_learning_dashboard",
            "run_id": "run-1",
            "file": file,
            "sha256": f"sha-{key}",
            "size": 1,
            "captured_at": "2026-01-01T00:00:00Z",
            "originating_system": "synthetic",
        }
        for key, file in files.items()
    }
    result["dashboard_keys"]["canonical_evidence_path"] = "dashboard_keys.jsonl.gz"
    return result


def test_marginals_positional_impacts_reconciliation_and_coverage_are_preserved():
    regions = ["เหนือ", "กลาง", "อีสาน", "ตะวันตก", "ตะวันออก", "ใต้"]
    raw = {
        "provinces": [["จังหวัด", "จำนวน"], ["ทดสอบ", 6]],
        "entityTypes": [["รูปแบบ", "จำนวน"], ["ชุมชน", 6]],
        "categories": [["ประเภท", "จำนวน"], ["อาหาร", 6]],
        "geography": [["ภูมิภาค", "จำนวน"], *[[region, 1] for region in regions]],
        "geographyImpact": [
            {
                "localEmployeeAmount": 1,
                "localEmployeeExpense": 2,
                "localResourceConsumption": 3,
                "localResourceExpense": 4,
            }
            for _ in regions
        ],
        "impactSummary": {
            "totalEmplyeeAmount": 6,
            "totalEmployeeExpense": 12,
            "totalResourceConsumption": 18,
            "totalResourceExpense": 24,
        },
        "excludedResourceExpense": {"region": "กลาง", "amount": 10},
    }
    meta = metadata()
    manifest = {
        "source_id": "f2_learning_dashboard",
        "run_id": "run-1",
        "datasets": [{"file": "dashboard_keys.jsonl.gz", "sha256": "sha-gzip"}],
        "extra_files": [
            {
                "file": "learning_dashboard.json",
                "sha256": meta["learning_dashboard_response"]["sha256"],
            },
            {
                "file": "complete_refresh_summary.json",
                "sha256": meta["refresh_summary"]["sha256"],
            },
        ],
    }
    keys = sorted(raw)
    datasets = {
        "learning_dashboard_response": raw,
        "dashboard_keys": [
            {"key": key, "value_type": type(raw[key]).__name__} for key in keys
        ],
        "refresh_summary": {"keys": keys, "province_rows": len(raw["provinces"])},
        "capture_manifest": manifest,
    }
    reviews = {
        "reviewed_cases.json": {
            "source_files": {
                "learning_dashboard.json": meta["learning_dashboard_response"]["sha256"]
            },
            "allowed_declared_hash_discrepancies": [],
            "count_dimensions": ["provinces", "entityTypes", "categories", "geography"],
            "regional_impact_position_order": regions,
            "regional_impact_mapping_basis": "reviewed synthetic position order",
            "k10_versions": {
                "K10A_reported_monthly_income_to_local_workers_and_suppliers_v1": {
                    "components": ["localEmployeeExpense", "localResourceExpense"],
                    "assumption": "synthetic additive components",
                },
                "K10B_assumed_historical_local_income_reconstruction_v1": {
                    "components": [
                        "localResourceExpense",
                        "excludedResourceExpense.amount",
                    ],
                    "assumption": "synthetic reconstruction",
                },
            },
        }
    }

    tables = build_tables(datasets, reviews, Geography(), meta)

    assert len(tables["count_dimension_headers"]) == 4
    assert len(tables["count_members"]) == 9
    assert [row["region_raw"] for row in tables["regional_impacts"]] == regions
    assert len(tables["impact_components"]) == 24
    assert len(tables["reconciliation_links"]) == 24
    results = {row["measure"]: row for row in tables["measure_results"]}
    assert results["K09_source_reported_monthly_employment_v1"]["value"] == "6"
    assert (
        results["K10A_reported_monthly_income_to_local_workers_and_suppliers_v1"][
            "value"
        ]
        == "0.000036"
    )
    assert (
        results["K10B_assumed_historical_local_income_reconstruction_v1"]["value"]
        == "0.000034"
    )
    assert tables["coverage_assertions"][0]["province_code"] == "10"
    assert isinstance(
        results["K09_source_reported_monthly_employment_v1"]["filter_metadata_json"],
        dict,
    )
    assert all(
        set(row) == set(TABLE_COLUMNS[name])
        for name, rows in tables.items()
        for row in rows
    )

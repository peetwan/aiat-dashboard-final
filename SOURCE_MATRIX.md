# Source matrix

Catalog ครบ 28 source: public candidate 11, metadata-only 12, restricted local-only 5. Publication permission ไม่ใช่ fact acceptance; ทุก public value ยัง needs_review

| # | source_id | วิธีหลัก | Visibility | records อ้างอิง | endpoints | safe runtime |
|---:|---|---|---|---:|---:|---:|
| 1 | f1_sradss_ppaos | api_first | public_candidate | 1,083,458 | 44 | 28 |
| 2 | f1_pppconnext | snapshot_only | public_candidate | 997,293 | 1 | 0 |
| 3 | f2_culturalmap_university | snapshot_only | public_candidate | 5,619 | 6 | 0 |
| 4 | f2_cultural_market_civil | metadata_only | metadata_only | 0 | 0 | 0 |
| 5 | f2_icommunity | metadata_only | metadata_only | 0 | 0 | 0 |
| 6 | f2_rmutdb | snapshot_only | public_candidate | 2,001 | 14 | 0 |
| 7 | f2_apptech_mtr | api_first | public_candidate | 621 | 6 | 6 |
| 8 | f2_apptech_mru | api_first | public_candidate | 503 | 8 | 5 |
| 9 | f2_target_household | blocked | restricted_local_only | 0 | 0 | 0 |
| 10 | f2_learning_dashboard | api_first | public_candidate | 66 | 1 | 1 |
| 11 | f2_learning_area_based | api_first | public_candidate | 1,002 | 1 | 1 |
| 12 | f2_wallet_all_realtime | blocked | restricted_local_only | 0 | 2 | 0 |
| 13 | f2_wallet_cluster_realtime | blocked | restricted_local_only | 0 | 2 | 0 |
| 14 | f3_city_capital_open_data | snapshot_only | public_candidate | 702 | 1 | 0 |
| 15 | f3_nonthaburi_city_learning | blocked | restricted_local_only | 0 | 0 | 0 |
| 16 | f3_ruamthiao_lamphun | snapshot_only | public_candidate | 54 | 5 | 0 |
| 17 | f3_ruamrian | metadata_only | metadata_only | 0 | 0 | 0 |
| 18 | f3_ruamkhai | metadata_only | metadata_only | 0 | 0 | 0 |
| 19 | f3_ruamjai_thungsong | metadata_only | metadata_only | 0 | 0 | 0 |
| 20 | f3_healthcare_nonthaburi | blocked | restricted_local_only | 0 | 0 | 0 |
| 21 | f3_ciap_smartcity | metadata_only | metadata_only | 0 | 0 | 0 |
| 22 | f3_learning_city_platform | metadata_only | metadata_only | 0 | 0 | 0 |
| 23 | f3_housing_portal | api_first | public_candidate | 7,259 | 50 | 49 |
| 24 | f4_research_dashboard_psu | metadata_only | metadata_only | 0 | 0 | 0 |
| 25 | spu_sukhothai_care | metadata_only | metadata_only | 0 | 0 | 0 |
| 26 | spu_sukhothai_water | metadata_only | metadata_only | 0 | 0 | 0 |
| 27 | spu_nsn_flood | metadata_only | metadata_only | 0 | 0 | 0 |
| 28 | spu_rawangphai_uru | metadata_only | metadata_only | 0 | 0 | 0 |

หมายเหตุ:

- safe runtime คือ technical allowlist ไม่ใช่การรับรองความหมายหรือ freshness
- restricted source มี metadata เท่านั้น; endpoint payload และค่าข้อมูลไม่เข้า Cloud
- metadata-only source ใช้เพื่อ discovery/catalog และไม่มี endpoint ที่สร้างขึ้นเอง
- f2_learning_dashboard อนุญาต candidate 66 province rows แต่ยังขาด raw manifest และ selected-project scope review
- จำนวน raw/index rows ไม่ใช่จำนวนที่ต้องแสดงทั้งหมดใน serving UI

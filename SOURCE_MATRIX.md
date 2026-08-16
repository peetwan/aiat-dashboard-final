# Source matrix

10 source ได้รับ project-owner publication approval แล้ว แต่ทุกข้อมูลยังเป็น candidate/needs_review จนกว่า semantic และ freshness gate จะผ่าน; wallet 2 source คง restricted local-only

| # | source_id | วิธีหลัก | Cloud policy | records อ้างอิง | endpoints | safe runtime |
|---:|---|---|---|---:|---:|---:|
| 1 | f1_sradss_ppaos | api_first | project_owner_approved_public | 1,083,458 | 44 | 28 |
| 2 | f1_pppconnext | snapshot_only | project_owner_approved_public | 997,293 | 1 | 0 |
| 3 | f2_culturalmap_university | snapshot_only | project_owner_approved_public | 5,619 | 6 | 0 |
| 6 | f2_rmutdb | snapshot_only | project_owner_approved_public | 2,001 | 14 | 0 |
| 7 | f2_apptech_mtr | api_first | project_owner_approved_public | 621 | 6 | 6 |
| 8 | f2_apptech_mru | api_first | project_owner_approved_public | 503 | 8 | 5 |
| 11 | f2_learning_area_based | api_first | project_owner_approved_public | 1,002 | 1 | 1 |
| 12 | f2_wallet_all_realtime | blocked | restricted_local_only | 934 | 2 | 0 |
| 13 | f2_wallet_cluster_realtime | blocked | restricted_local_only | 140 | 2 | 0 |
| 14 | f3_city_capital_open_data | snapshot_only | project_owner_approved_public | 702 | 1 | 0 |
| 16 | f3_ruamthiao_lamphun | snapshot_only | project_owner_approved_public | 54 | 5 | 0 |
| 23 | f3_housing_portal | api_first | project_owner_approved_public | 7,259 | 50 | 49 |

หมายเหตุ:

- safe runtime หมายถึง endpoint ที่ผ่าน technical allowlist เท่านั้น ไม่ได้แปลว่าอนุญาต publish
- f2_wallet_all_realtime และ f2_wallet_cluster_realtime ถูกบล็อกทั้ง endpoint และ data บน Cloud
- Source สาธารณะ 10 แหล่งได้รับ project-owner approval เมื่อ 2026-08-16 แต่ยังคงป้าย needs_review
- Source จากทีมเพื่อน 3, 14 และ 16 ต้องคง provenance ของ external-team scraper
- Housing demand แสดง schema เท่านั้น และ policy-assessment ถูกบล็อกค่ารายแถว

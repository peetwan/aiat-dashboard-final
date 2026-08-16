# Geo Linkage Audit

อัปเดต: 2026-08-16

| Source | ผลตรวจ | การใช้งานใน dashboard |
|---|---|---|
| PPPConnext | aggregate 660 แถว; province rows 307; เชื่อมได้ 21 จังหวัด | แสดงค่าครัวเรือน/ทุนดำรงชีพแยก metric |
| AppTech MTR | API 77 จังหวัด; ผู้ใช้ 2,356; interaction 371 | แสดง aggregate จังหวัดและภาพรวมทะเบียน 621 รายการแยกกัน |
| City Capital | 18 เมือง × 39 metric; exact DLA match 18/18 | แสดงระดับเทศบาลใน 16 จังหวัด; เทียบ median 18 เมือง |
| RMUTDB | 2,001 records; ไม่มี location ระดับ record | หน้า non-map ระดับประเทศเท่านั้น |

## หลักฐาน

- PPPConnext: `data/staged/f1_pppconnext/20260804T_pppconnext_bi_silver_01/manifest.json`
- AppTech MTR: `data/raw/network/f2_apptech_mtr/20260816T_geo_link_audit_07/manifest.json`
- City Capital crosswalk: `data/raw/ckan/f3_city_capital_open_data/20260816T_dla_city_crosswalk_14b/manifest.json`
- RMUTDB: `data/staged/silver/f2_rmutdb/20260805T_ebook_silver_01/summary.json`

## Serving outputs

- `data/public/source_insights.json`
- `data/public/provincial_briefings/{province_code}.json`
- `data/public/executive_summaries/{province_code}.json`
- `/api/public/v1/source-insights`
- `/api/public/v1/provinces/{province_code}/summary`

ตัวเลขทุกชุดยังเป็น candidate/needs_review และไม่ถูกนำมารวมเป็นคะแนนจัดสรรงบ

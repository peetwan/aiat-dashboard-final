# Add Country And Province Overview Guidelines To `dashboard_f4.md`

## Summary

- Create `/Users/mister1st/Documents/Dashboard/aiat-dashboard-final/dashboard_f4.md`.
- Keep the existing country-level overview and country-level click behavior.
- Add province-level overview as an additional flow after the country section.
- Detail clicks show filtered lists, not raw files.
- Do not commit until user approves the final diff.

## Country-Level Overview

| KPI | Dashboard display | Source behavior | Evidence |
| --- | ---: | --- | --- |
| พื้นที่เป้าหมาย | `67 จังหวัด` | Dynamic from R2 | Count from `raw/f2/f2_learning_dashboard/20260820T134600Z/complete_refresh_summary.json`, field `province_rows`. |
| เทคโนโลยี/นวัตกรรม | `1,172 นวัตกรรม` | Static headline for now | Live PMUA AppTech `/propose` and `/dashboard` currently show `1,172`; older R2 `/propose` page snapshot has `1,161`. |
| นวัตกรรมเชิงนโยบาย | `107 โครงการวิจัย` | Dynamic from R2 | Count from `raw/f4/clig_projects/20260823T072251Z/manifest.json`, dataset `clig.projects.row_count`. |
| นวัตกรท้องถิ่น/นวัตกร | `12,059 คน` | Static headline for now | Static/manual until PMUA AppTech R2 contains a clean metric snapshot. |

## Country-Level Click Details

| Clicked card | Detail view content | R2 source |
| --- | --- | --- |
| เทคโนโลยี/นวัตกรรม | Show a searchable/table list of PMUA AppTech products/innovations. Use parsed records, not raw HTML. Show title, product id, provinces, districts, subdistricts, source URL, and fetched timestamp where available. Show evidence note: older R2 `/propose` snapshot headline was `1,161`; structured product list has `1,160` parsed rows. | `raw/f2/f2_target_household/20260818T163603Z/products_redacted.jsonl.gz`; headline evidence from `raw/f2/f2_target_household/20260820T134640Z/public_pages/propose.html`. |
| นวัตกรรมเชิงนโยบาย | Show a searchable/table list of all CLIG research projects behind the `107` count. Use project rows, not only policy candidates. | `raw/f4/clig_projects/20260823T072251Z/projects.jsonl.gz`; count comes from `manifest.json` dataset `clig.projects.row_count = 107`. |

## Province-Level Overview

- Province level is an addition after country level, not a replacement.
- User can zoom/select a province from the country overview.
- Backend filters each province-level KPI using the selected province.

| Province-level item | Display | Filter logic | Source |
| --- | ---: | --- | --- |
| Province name | `{province_name_th}` | Resolve from selected province code/name | Shared province lookup |
| เทคโนโลยี/นวัตกรรม | `{n} นวัตกรรม` | Count PMUA product rows where selected province code is in `provinces` | `raw/f2/f2_target_household/20260818T163603Z/products_redacted.jsonl.gz` |
| นวัตกรรมเชิงนโยบาย | `{n} โครงการวิจัย` | Count CLIG project rows whose title/detail/abstract/organization text contains the selected Thai province name | `raw/f4/clig_projects/20260823T072251Z/projects.jsonl.gz` |

## Province-Level Click Details

| Clicked province card | Detail view content |
| --- | --- |
| เทคโนโลยี/นวัตกรรม | Show PMUA product/innovation list filtered to selected province. Columns: `title`, `product_id`, province, districts, subdistricts, `source_url`, `fetched_at`, `section_labels`. |
| นวัตกรรมเชิงนโยบาย | Show CLIG project list filtered to selected province. Columns: project title, `project_id`, `contract_no`, fiscal year, status, `lead_organization`, budget if available, `detail_url`. |

## Evidence Notes

- PMUA product rows have explicit province codes. Current R2 parsed list has `1,160` rows and `74` distinct province codes.
- CLIG rows do not have a structured province field. For v1, province filtering is derived by matching Thai province names in `project_title`, `detail_title`, `abstract_th`, `abstract_en`, and `lead_organization`.
- Initial CLIG text-derived mapping finds `78 / 107` projects mapped to at least one province, with `29` unmapped. Province counts should be labeled as evidence-matched, not complete geographic coverage.
- Both country and province detail lists are evidence drilldowns, not certified final KPI facts.

## Verification

- After execution, show `git status --short`.
- Show the diff for `dashboard_f4.md`.
- No `git commit` unless explicitly approved.

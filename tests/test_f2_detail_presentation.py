from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_f2_detail_presenters_create_human_readable_models_for_every_measure() -> None:
    assert NODE is not None
    samples = {
        "K01B": {
            "label": "พื้นที่วัฒนธรรมตัวอย่าง",
            "identity_status": "source_local_identity",
            "category_codes": ["CS", "CS1"],
            "descriptions": [{"kind": "history", "text": "เรื่องราวของพื้นที่"}],
            "locations": [
                {"subdistrict": "ทดสอบ", "district": "เมือง", "province": "สงขลา"}
            ],
            "listings": [
                {
                    "label": "รายการต้นทาง",
                    "source_id": "f2_culturalmap_university",
                    "source_url": "https://example.org/culture",
                }
            ],
            "flags": {},
        },
        "K12": {
            "label": "Title withheld pending review",
            "identity_status": "source_listing_identity",
            "category_codes": ["PA", "PA1"],
            "locations": [{"province": "สงขลา"}],
            "flags": {
                "label_withholding_reason": "source_title_failed_public_scalar_admission"
            },
        },
        "K03": {
            "label": "กิจกรรมตัวอย่าง",
            "identity_status": "provisional_reported_activity",
            "descriptions": [{"kind": "description", "text": "รายละเอียดกิจกรรม"}],
            "locations": [{"province": "เชียงใหม่"}],
            "children": {
                "dates": [
                    {
                        "start_date": "2024-02-10",
                        "end_date": "2024-02-10",
                        "has_conflict": False,
                    }
                ]
            },
            "flags": {},
        },
        "K04": {
            "label": "นวัตกรรมตัวอย่าง",
            "identity_status": "reviewed_cross_source",
            "source_ids": ["f2_target_household"],
            "descriptions": [
                {"kind": "ปัญหา (Pain Points)", "text": "ปัญหาที่พบ"},
                {"kind": "ประโยชน์ (Gain Points)", "text": "ประโยชน์ที่ได้รับ"},
            ],
            "locations": [{"province": "ปัตตานี"}],
            "children": {
                "readiness": [
                    {
                        "scale": "TRL",
                        "numeric_level": 8,
                        "qualifies": True,
                        "source_id": "f2_target_household",
                    }
                ],
                "organizations": [
                    {"organization": "มหาวิทยาลัยตัวอย่าง", "role": "university"}
                ],
                "work_attributions": [
                    {"attribution": "นักวิจัยตัวอย่าง", "role": "researcher"}
                ],
            },
            "flags": {
                "identity_review": {
                    "outcome": "merged",
                    "merge_scope": "cross_source",
                    "counting": "merged",
                    "name_quality": "supported",
                }
            },
        },
        "C04_LISTED": {
            "label": "นวัตกรรมในรายการ",
            "identity_status": "source_local_only",
            "children": {
                "readiness": [
                    {
                        "scale": "ATL",
                        "numeric_level": 7,
                        "qualifies": False,
                        "source_id": "f2_apptech_mtr",
                    }
                ]
            },
            "flags": {},
        },
        "K05": {
            "label": "ร้านตัวอย่าง",
            "identity_status": "reviewed_provisional_identity",
            "descriptions": [
                {"kind": "source_reported_business", "text": "ข้อมูลร้านตามแหล่งต้นทาง"}
            ],
            "children": {
                "source_memberships": [
                    {"label": "ร้านตัวอย่าง", "source_id": "f2_cultural_market_civil"}
                ]
            },
            "relationships": [
                {"label": "สินค้าตัวอย่าง", "kind": "source_reported_operator"}
            ],
            "flags": {
                "geography_not_borrowed_from_offerings": True,
                "identity_review": {
                    "outcome": "kept_separate",
                    "merge_scope": None,
                    "counting": "separate",
                    "name_quality": "supported",
                },
            },
        },
        "K07": {
            "label": "กลุ่มผลิตภัณฑ์ตัวอย่าง",
            "identity_status": "reviewed_product_family",
            "children": {
                "offerings": [
                    {
                        "label": "สินค้ารุ่นสีแดง",
                        "membership_role": "variant",
                        "children": {
                            "prices": [
                                {
                                    "currency": "THB",
                                    "amounts": [
                                        {
                                            "status": "unspecified",
                                            "value": 0,
                                            "display_label": "price unspecified/source reports 0",
                                        }
                                    ],
                                }
                            ]
                        },
                        "relationships": [{"label": "ร้านตัวอย่าง"}],
                        "locations": [{"province": "สระบุรี"}],
                    }
                ]
            },
            "flags": {
                "variants_are_children_not_entities": True,
                "identity_review": {
                    "outcome": "grouped_family",
                    "merge_scope": None,
                    "counting": "grouped",
                    "name_quality": "supported",
                },
            },
        },
        "C08_PARTICIPATING": {
            "label": "ธุรกิจชุมชนตัวอย่าง",
            "identity_status": "provisional_source_unit",
            "locations": [{"district": "เมือง", "province": "นราธิวาส"}],
            "children": {
                "participations": [
                    {
                        "fiscal_year_be": 2567,
                        "project": "โครงการตัวอย่าง",
                        "research_unit": "มหาวิทยาลัยตัวอย่าง",
                        "source_id": "f2_learning_area_based",
                    }
                ]
            },
            "flags": {
                "participation_not_improvement": True,
                "person_assessments_withheld": True,
            },
        },
    }
    script = r"""
const assert = require('node:assert/strict');
const presenter = require('./app/static/f2-detail.js');
const samples = JSON.parse(process.env.SAMPLES);
const provenance = {sources: [
  {source_id: 'f2_target_household', public_url: 'https://pmua-apptech.com/'},
  {source_id: 'f2_apptech_mtr', public_url: 'https://rinmp.com/'},
]};
const models = Object.fromEntries(Object.entries(samples).map(([measure, detail]) => [measure, presenter.present(measure, detail, provenance)]));
const listK12 = presenter.presentListItem('K12', {
  label: 'โนราสมาน สืบสานศิลป์',
  entity_id: 'cultural_map_subject_internal',
  identity_status: 'source_listing_identity',
  category_codes: ['PA', 'PA2'],
  province_names_th: ['สงขลา'],
});
assert.deepEqual(listK12.context, ['รายการทุนวัฒนธรรม', 'ศิลปะการแสดง', 'จังหวัดสงขลา']);
assert.equal(listK12.warning, '');
assert.equal(JSON.stringify(listK12).includes('entity_id'), false);
assert.equal(JSON.stringify(listK12).includes('source_listing_identity'), false);
const sourceRecord = presenter.presentListItem('K05', {
  label: 'ร้านตามข้อมูลต้นทาง',
  identity_review: {outcome: 'source_record_only'},
});
assert.equal(sourceRecord.warning, '');
const keptSeparate = presenter.presentListItem('K05', {
  label: 'ร้านที่ตรวจสอบแล้ว',
  identity_review: {outcome: 'kept_separate'},
});
assert.equal(keptSeparate.warning, '');
const malformedName = presenter.presentListItem('C08_PARTICIPATING', {
  label: 'Name unavailable',
  identity_review: {outcome: 'malformed_name'},
});
assert.equal(malformedName.title, 'ไม่พบชื่อจากแหล่งข้อมูล');
assert.equal(malformedName.warning, 'ไม่มีชื่อรายการจากแหล่งข้อมูล');
const uncertainInnovation = presenter.presentListItem('K04', {
  label: 'นวัตกรรมตัวอย่าง',
  identity_status: 'provisional_unresolved_candidates',
  province_names_th: ['ปัตตานี'],
});
assert.equal(uncertainInnovation.warning, 'อาจซ้ำกับรายการอื่น — ยังนับแยก');
for (const [measure, model] of Object.entries(models)) {
  assert.ok(model.title, `${measure} title`);
  assert.ok(model.eyebrow, `${measure} eyebrow`);
  assert.ok(Array.isArray(model.sections), `${measure} sections`);
  assert.ok(Array.isArray(model.notices), `${measure} notices`);
  assert.ok(model.technical, `${measure} technical disclosure`);
  const visible = JSON.stringify({...model, technical: undefined});
  assert.equal(visible.includes('entity_id'), false, `${measure} hides entity id from primary view`);
  assert.equal(visible.includes('source_id'), false, `${measure} hides source id from primary view`);
}
assert.ok(models.K01B.sections.some((section) => section.title === 'เรื่องราวและความสำคัญ'));
assert.ok(JSON.stringify(models.K01B).includes('ประวัติและความเป็นมา'));
assert.equal(models.K12.title, 'ชื่อรายการอยู่ระหว่างการตรวจสอบ');
assert.ok(models.K12.notices.some((notice) => notice.text.includes('อยู่ระหว่างการตรวจสอบ')));
assert.ok(JSON.stringify(models.K12).includes('ศิลปะการแสดง'));
assert.ok(models.K03.notices.some((notice) => notice.text.includes('ไม่ได้ยืนยันว่าโครงการทั้งหมดเสร็จสมบูรณ์')));
assert.ok(models.K04.sections.some((section) => section.title === 'ระดับความพร้อมตามแหล่งข้อมูล'));
assert.ok(JSON.stringify(models.K04).includes('ระดับความพร้อมเทคโนโลยี (TRL) 8'));
assert.ok(JSON.stringify(models.K04.sources).includes('ระบบฐานข้อมูลครัวเรือนมุ่งเป้า'));
assert.equal(JSON.stringify(models.K04.sources).includes('RinMP'), false);
assert.ok(models.C04_LISTED.notices.some((notice) => notice.text.includes('ไม่ใช่การประเมินสถานะปัจจุบัน')));
assert.ok(models.K04.badges.includes('เชื่อมโยงข้ามแหล่งข้อมูลแล้ว'));
assert.ok(models.K05.sections.some((section) => section.title === 'สินค้าและบริการที่เกี่ยวข้อง'));
assert.ok(JSON.stringify(models.K05).includes('แผนที่ตลาดวัฒนธรรม'));
assert.ok(models.K05.badges.includes('ตรวจสอบแล้วว่าเป็นคนละรายการ'));
assert.ok(JSON.stringify(models.K07).includes('ไม่ระบุราคา — แหล่งข้อมูลรายงานค่า 0'));
assert.ok(models.K07.notices.some((notice) => notice.text.includes('ไม่ใช่หน่วยนับเพิ่มเติม')));
assert.ok(models.K07.badges.includes('จัดกลุ่มสินค้าและบริการแล้ว'));
assert.ok(models.C08_PARTICIPATING.notices.some((notice) => notice.text.includes('ไม่ได้ยืนยันว่าธุรกิจมีผลประกอบการ')));
const unnamedBusiness = presenter.present('C08_PARTICIPATING', {...samples.C08_PARTICIPATING, label: 'Name unavailable'}, provenance);
assert.equal(unnamedBusiness.title, 'ไม่พบชื่อธุรกิจจากแหล่งข้อมูล');
console.log(JSON.stringify(Object.fromEntries(Object.entries(models).map(([key, value]) => [key, {title: value.title, sections: value.sections.length}]))));
"""
    result = subprocess.run(
        [NODE, "-"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=30,
        input=script,
        env={"SAMPLES": json.dumps(samples, ensure_ascii=False)},
    )
    assert result.returncode == 0, result.stderr
    rendered = json.loads(result.stdout)
    assert set(rendered) == set(samples)


def test_f2_detail_ui_uses_presenter_instead_of_raw_schema_as_primary_view() -> None:
    template = (ROOT / "app/templates/index.html").read_text(encoding="utf-8")
    script = (ROOT / "app/static/f2.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "app/static/f2.css").read_text(encoding="utf-8")

    assert "/static/f2-detail.js" in template
    assert "F2DetailPresenter.present" in script
    assert "renderDetailPresentation(model)" in script
    assert "รายละเอียดทางเทคนิคและการตรวจสอบย้อนกลับ" in script
    assert ".f2-detail-notice--warning" in stylesheet
    assert ".f2-detail-section--timeline" in stylesheet


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_c02_person_presenters_only_show_admitted_public_person_context() -> None:
    assert NODE is not None
    samples = {
        "C02_COMMUNITY": {
            "label": "บุคคลสาธารณะ",
            "label_availability": "available",
            "identity_status": "reviewed_cross_source",
            "source_ids": ["f2_icommunity", "f2_apptech_mru"],
            "locations": [
                {
                    "province_code": "10",
                    "province": "กรุงเทพมหานคร",
                    "location_role": "source_reported_innovator_location",
                    "source_id": "f2_icommunity",
                }
            ],
            "province_codes": ["10"],
            "children": {
                "qualifying_roles": [
                    {
                        "role_code": "community_innovator",
                        "qualifies_for": ["C02_COMMUNITY"],
                        "source_id": "f2_icommunity",
                    },
                    {
                        "role_code": "inventor",
                        "qualifies_for": ["C02_COMMUNITY"],
                        "source_id": "f2_apptech_mru",
                    },
                    {
                        "role_code": "researcher",
                        "qualifies_for": ["C02_COMMUNITY"],
                        "source_id": "f2_icommunity",
                    },
                ],
                "organizations": [
                    {
                        "organization": "หน่วยงานที่อนุมัติ",
                        "role": "affiliated_organization",
                        "source_id": "f2_icommunity",
                    }
                ],
            },
            "relationships": [
                {
                    "entity_id": "work-1",
                    "label": "ผลงานที่เชื่อมโยง",
                    "role_code": "community_innovator",
                    "source_id": "f2_icommunity",
                    "target_detail": {
                        "topic_id": "k04",
                        "measure_id": "K04",
                        "entity_id": "work-1",
                    },
                },
                {
                    "entity_id": "work-1",
                    "label": "ผลงานที่เชื่อมโยง",
                    "role_code": "inventor",
                    "source_id": "f2_icommunity",
                    "target_detail": {
                        "topic_id": "k04",
                        "measure_id": "K04",
                        "entity_id": "work-1",
                    },
                },
                {
                    "entity_id": "work-3",
                    "label": "ผลงานที่เชื่อมโยง",
                    "source_id": "f2_icommunity",
                    "target_detail": {
                        "topic_id": "k04",
                        "measure_id": "K04",
                        "entity_id": "work-3",
                    },
                },
                {
                    "entity_id": "public_work_unlinked",
                    "label": "ผลงานที่ไม่มีหน้าสาธารณะ",
                    "source_id": "f2_icommunity",
                },
                {
                    "entity_id": "public_work_invalid_link",
                    "label": "ผลงานที่ลิงก์ไม่ครบ",
                    "source_id": "f2_icommunity",
                    "target_detail": {"topic_id": "k04", "measure_id": "K04"},
                },
            ],
            "flags": {
                "k02_relationship": "not_established",
                "missing_public_detail_fields": ["organizations"],
                "geography_not_published": False,
                "person_province_basis": "source_reported_innovator_location",
                "province_memberships_overlap": False,
            },
            "private_profile_url": "https://private.example.invalid/",
            "raw_status": "internal",
        },
    }
    script = r"""
const assert = require('node:assert/strict');
const presenter = require('./app/static/f2-detail.js');
const samples = JSON.parse(process.env.SAMPLES);
const provenance = {sources: [{source_id: 'f2_icommunity', public_url: 'https://example.org/public'}, {source_id: 'f2_apptech_mru', public_url: 'https://example.org/mru'}]};
const community = presenter.present('C02_COMMUNITY', samples.C02_COMMUNITY, provenance);
const visibleCommunity = JSON.stringify({...community, technical: undefined});
assert.equal(community.title, 'บุคคลสาธารณะ');
assert.deepEqual(community.sections[0].items.map((item) => item.title), ['นวัตกรชุมชน', 'ผู้ประดิษฐ์']);
assert.ok(community.sections.some((section) => section.title === 'หน่วยงานที่ระบุ' && JSON.stringify(section).includes('หน่วยงานที่อนุมัติ')));
assert.equal(community.sections.find((section) => section.title === 'ผลงานหรือโครงการที่เกี่ยวข้อง').items.length, 4);
const linked = community.sections.find((section) => section.title === 'ผลงานหรือโครงการที่เกี่ยวข้อง').items[0];
assert.deepEqual(linked.targetDetail, {topicId: 'k04', measureId: 'K04', entityId: 'work-1'});
assert.ok(community.notices.some((notice) => notice.text.includes('K02')));
assert.ok(community.badges.includes('ทะเบียนนวัตกรชุมชนและผู้ประดิษฐ์'));
assert.ok(community.sections.some((section) => section.title === 'จังหวัดที่ต้นทางระบุสำหรับนวัตกร' && JSON.stringify(section).includes('จังหวัดกรุงเทพมหานคร')));
assert.ok(community.notices.some((notice) => notice.text === 'จังหวัดนี้เป็นข้อมูลที่ต้นทางผูกกับระเบียนนวัตกร ไม่ได้หมายถึงจังหวัดที่อยู่อาศัยหรือสถานที่ทำงานปัจจุบัน'));
const incorrectDatasetFlag = presenter.present('C02_COMMUNITY', {...samples.C02_COMMUNITY, flags: {...samples.C02_COMMUNITY.flags, province_memberships_overlap: true}}, provenance);
assert.equal(incorrectDatasetFlag.notices.some((notice) => notice.text.includes('บุคคลนี้มีจังหวัด')), false);
const actualMultipleProvinces = presenter.present('C02_COMMUNITY', {
  ...samples.C02_COMMUNITY,
  province_codes: ['10', '80'],
  locations: [...samples.C02_COMMUNITY.locations, {province_code: '80', province: 'นครศรีธรรมราช', location_role: 'source_reported_innovator_location', source_id: 'f2_icommunity'}],
}, provenance);
assert.ok(actualMultipleProvinces.notices.some((notice) => notice.text.includes('บุคคลนี้มีจังหวัด')));
const unavailable = presenter.present('C02_COMMUNITY', {...samples.C02_COMMUNITY, locations: [], province_codes: [], flags: {...samples.C02_COMMUNITY.flags, geography_not_published: true, person_province_basis: 'unavailable'}}, provenance);
assert.ok(unavailable.notices.some((notice) => notice.text.includes('บุคคลยังคงอยู่ในยอดระดับประเทศ')));
const sourceSupported = presenter.present('C02_COMMUNITY', {
  ...samples.C02_COMMUNITY,
  identity_status: 'source_supported',
  source_ids: ['f2_icommunity'],
  flags: {
    ...samples.C02_COMMUNITY.flags,
    unresolved_identity: true,
    possible_duplicate: false,
    source_quality_flags: ['source_reported_person'],
  },
}, provenance);
assert.equal(sourceSupported.notices.some((notice) => notice.text.includes('ซ้ำ')), false);
assert.equal(visibleCommunity.includes('private_profile_url'), false);
assert.equal(visibleCommunity.includes('raw_status'), false);
assert.equal(visibleCommunity.includes('entity_id'), false);
const compact = presenter.presentListItem('C02_COMMUNITY', {label: 'ผู้ประดิษฐ์สาธารณะ', label_availability: 'available', role_codes: ['inventor'], organization_labels: ['หน่วยงานที่อนุมัติ'], related_work_count: 2, related_work_count_unavailable: false, identity_status: 'source_supported', source_ids: ['f2_apptech_mru']});
assert.equal(compact.title, 'ผู้ประดิษฐ์สาธารณะ');
assert.ok(compact.context.includes('ผลงานที่แสดงในฉบับเผยแพร่นี้ 2 รายการ'));
assert.equal(JSON.stringify(compact).includes('source_supported'), false);
assert.equal(compact.warning, '');
const uncertainCompact = presenter.presentListItem('C02_COMMUNITY', {
  ...compact,
  label: 'บุคคลที่อาจซ้ำ',
  identity_review: {outcome: 'unresolved'},
});
assert.equal(uncertainCompact.warning, 'อาจซ้ำกับรายการอื่น — ยังนับแยก');
console.log(JSON.stringify({community: community.sections.length}));
"""
    result = subprocess.run(
        [NODE, "-"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=30,
        input=script,
        env={"SAMPLES": json.dumps(samples, ensure_ascii=False)},
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_f2_sources_recover_unsupported_province_and_preserve_other_errors() -> None:
    """Exercise source loading with fake responses, without upstream requests."""
    assert NODE is not None
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/f2.js', 'utf8');
// Evaluate the production functions against controlled I/O and view seams.
function functionSource(name) {
  const match = new RegExp('^  (?:async )?function ' + name + '\\(', 'm').exec(source);
  assert.ok(match, name);
  const next = source.indexOf('\n  function ', match.index + 1);
  const nextAsync = source.indexOf('\n  async function ', match.index + 1);
  const end = Math.min(...[next, nextAsync].filter(index => index >= 0));
  return source.slice(match.index, end);
}
(async () => {
  for (const failure of ['unsupported filter combination for measure', 'HTTP 503', 'AbortError', 'stale']) {
    const calls = [], notices = [], errors = [], restored = [], urls = [];
    const state = {topic: 'k09', measure: 'K09', province: '90', topicData: null, scopeNotice: '', callbacks: {
      getProvinces: () => [{province_code: '90', province_name_th: 'สงขลา'}],
      onProvinceRestore: province => restored.push(province),
    }};
    let recovery;
    const context = vm.createContext({
      state, text: String, views: {sources: {}},
      selectedMeasureDefinition: () => ({label_th: 'การจ้างงาน'}),
      detailScope: () => ({measure: state.measure, province: state.province}),
      query: params => '?' + new URLSearchParams(params),
      request: async path => {
        calls.push(path);
        if (state.province) {
          const error = new Error(failure);
          if (failure === 'AbortError') error.name = 'AbortError';
          if (failure === 'stale') error.stale = true;
          throw error;
        }
        return {topic_id: 'k09', measure_id: 'K09', scope: 'national'};
      },
      status: (_view, heading, message) => {
        if (heading === 'เปิดที่มาไม่ได้') errors.push(message);
      },
      el: (_tag, attrs, ...children) => [attrs?.text, ...children],
      writeUrl: push => urls.push({push, province: state.province}),
      loadOverview: () => { recovery = context.loadSources(); },
      renderSources: () => context.renderScopeNotice({append: node => notices.push(node)}),
    });
    vm.runInContext(['renderScopeNotice', 'recoverUnsupportedProvince', 'loadSources'].map(functionSource).join('\n'), context);
    await context.loadSources();
    if (recovery) await recovery;
    if (failure.startsWith('unsupported')) {
      assert.equal(calls.length, 2);
      assert.equal(new URLSearchParams(calls[0].split('?')[1]).get('province'), '90');
      assert.equal(new URLSearchParams(calls[1].split('?')[1]).get('province'), '');
      assert.equal(state.topicData.scope, 'national');
      assert.deepEqual(restored, ['']);
      assert.deepEqual(urls, [{push: false, province: ''}]);
      assert.ok(JSON.stringify(notices).includes('สงขลา'));
      assert.ok(JSON.stringify(notices).includes('มุมมองประเทศไทย'));
      assert.equal(errors.length, 0);
    } else {
      assert.equal(calls.length, 1);
      assert.equal(state.province, '90');
      assert.equal(restored.length, 0);
      assert.equal(notices.length, 0);
      assert.equal(errors.length, failure === 'HTTP 503' ? 1 : 0);
      assert.ok(errors.every(message => !message.includes('HTTP')));
    }
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        [NODE, "-"], cwd=ROOT, text=True, encoding="utf-8",
        capture_output=True, timeout=30, input=script,
    )
    assert result.returncode == 0, result.stderr

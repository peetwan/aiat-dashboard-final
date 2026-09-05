"""ตรวจคำขอหน้าจังหวัดแบบ offline โดยจำลองลำดับการตอบกลับของ API"""

from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="ต้องมี Node.js สำหรับทดสอบ JavaScript")
def test_province_research_attribution_keeps_name_and_affiliations():
    result = subprocess.run(
        [NODE, "-"], cwd=ROOT, text=True, encoding="utf-8", capture_output=True, timeout=15,
        input=r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/province.js', 'utf8');
const context = vm.createContext({});
vm.runInContext(source.slice(0, source.lastIndexOf('document.getElementById("retryDetail")')), context);
const render = leads => vm.runInContext(`humanValue(${JSON.stringify(leads)})`, context);
for (const lead of [
  {name: 'ผู้วิจัยตัวอย่าง', faculty: 'คณะวิทยาศาสตร์', institute: 'มหาวิทยาลัยตัวอย่าง'},
  {faculty: 'คณะวิทยาศาสตร์', institute: 'มหาวิทยาลัยตัวอย่าง'},
]) {
  const rendered = render([lead]);
  for (const value of Object.values(lead)) assert.ok(rendered.includes(value));
  assert.ok(!rendered.includes('undefined'));
}
""",
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(NODE is None, reason="ต้องมี Node.js สำหรับทดสอบ JavaScript")
def test_tourism_card_renders_hours_separately_from_phone():
    result = subprocess.run(
        [NODE, "-"], cwd=ROOT, text=True, encoding="utf-8", capture_output=True, timeout=15,
        input=r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const elements = {};
const context = vm.createContext({document: {getElementById: id => elements[id] ||= {}}});
vm.runInContext(fs.readFileSync('app/static/app.js', 'utf8').replace(/loadDashboard\(\);\s*$/, ''), context);
vm.runInContext(`renderTourism({status:'available', items:[{page_id:'contact', data:{service_centres:[{
  name:{TH:'ศูนย์บริการตัวอย่าง'}, opening_hours:'07.30 - 18.00 น.', phones:[{phone:'053-569100'}]
}]}}]})`, context);
const html = elements.tourismItems.innerHTML;
assert.ok(html.includes('<p>053-569100</p>'));
assert.ok(html.includes('<p>เวลาทำการ: 07.30 - 18.00 น.</p>'));
assert.equal(html.split('07.30 - 18.00 น.').length - 1, 1);
""",
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(NODE is None, reason="ต้องมี Node.js สำหรับทดสอบ JavaScript")
def test_f4_requests_deduplicate_ignore_stale_results_and_allow_retry() -> None:
    result = subprocess.run(
        [NODE, "-"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=15,
        input=r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/app.js', 'utf8');
const context = vm.createContext({console: {error() {}}});
// ทดสอบ request functions จริง โดยไม่เปิดแผนที่หรือเรียก network
vm.runInContext(source.replace(/loadDashboard\(\);\s*$/, ''), context);
vm.runInContext(`
  renderF4CountryPanel = () => {};
  const pending = new Map();
  let requestCount = 0;
  fetchPublicJson = endpoint => new Promise((resolve, reject) => {
    requestCount++;
    pending.set(endpoint, {resolve, reject});
  });
  state.mapMode = 'f4';
  state.selectedCode = '40';
`, context);
const run = code => vm.runInContext(code, context);
(async () => {
  const oldRequest = run(`loadF4ProvinceOverview('40')`);
  await run(`loadF4ProvinceOverview('40')`);
  assert.equal(run('requestCount'), 1, 'duplicate requests share one in-flight fetch');
  run(`state.selectedCode = '46'`);
  const currentRequest = run(`loadF4ProvinceOverview('46')`);
  run(`pending.get('/api/public/v1/f4/provinces/46').resolve({province_code:'46'})`);
  await currentRequest;
  run(`pending.get('/api/public/v1/f4/provinces/40').resolve({province_code:'40'})`);
  await oldRequest;
  assert.equal(run('state.f4Province.province_code'), '46', 'late response cannot replace the selected province');

  run(`state.selectedCode = '41'; state.f4Province = null`);
  const failedRequest = run(`loadF4ProvinceOverview('41')`);
  run(`pending.get('/api/public/v1/f4/provinces/41').reject(new Error('unavailable'))`);
  assert.equal(await failedRequest, null);
  assert.equal(run(`state.f4Errors.has('province:41')`), true);
  assert.equal(run(`state.f4Loading.has('province:41')`), false);
  assert.equal(run('requestCount'), 3, 'failure must not automatically retry');

  const retriedRequest = run(`loadF4ProvinceOverview('41')`);
  assert.equal(run(`state.f4Errors.has('province:41')`), false);
  run(`pending.get('/api/public/v1/f4/provinces/41').resolve({province_code:'41'})`);
  await retriedRequest;
  assert.equal(run('state.f4Province.province_code'), '41');
  assert.equal(run('state.f4Loading.size'), 0);

  run(`state.selectedCode = '40'; state.f4Province = null`);
  const abandonedRequest = run(`loadF4ProvinceOverview('40')`);
  run(`state.mapMode = 'f1'; pending.get('/api/public/v1/f4/provinces/40').resolve({province_code:'40'})`);
  await abandonedRequest;
  assert.equal(run('state.f4Province'), null, 'leaving F4 ignores its pending province result');
})().catch(error => { console.error(error); process.exitCode = 1; });
""",
    )
    assert result.returncode == 0, result.stdout + result.stderr

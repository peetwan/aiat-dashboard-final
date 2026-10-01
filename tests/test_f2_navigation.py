"""Exercise F2 scope and filter transitions without a browser or upstream calls."""
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_province_memory_and_mobile_filter_transactions():
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/f2.js', 'utf8');
function extract(name) {
  const start = source.indexOf('  function ' + name + '(');
  const candidates = ['\n  function ', '\n  async function '].map(marker => source.indexOf(marker, start + 1)).filter(index => index >= 0);
  return source.slice(start, Math.min(...candidates));
}
const definitions = [{measure_id:'K04', topic_id:'k04', filter_contract:{supported_filters:['province']}}, {measure_id:'K09', topic_id:'k09', filter_contract:{supported_filters:[]}}];
const restored = [], history = [];
const state = {province:'50', rememberedProvince:'50', measure:'K04', topic:'k04', filters:{q:'old'}, searchDraft:'old', sort:'source', offset:25, scopeNotice:'', filterDraft:null, callbacks:{
  getProvinces: () => [{province_code:'50', province_name_th:'เชียงใหม่'}],
  onProvinceRestore: code => restored.push(code),
}};
const element = {append(){}, setAttribute(){}, showModal(){}, close(){}, after(){}, focus(){}};
const context = vm.createContext({state, structuredClone, clearTimeout, text:String,
  $: () => element, abort(){}, loadOverview(){},
  allMeasureDefinitions: () => definitions,
  selectedMeasureDefinition: () => definitions.find(row => row.measure_id === state.measure),
  measureDisplayLabel: row => row?.label_th || '',
  supportsProvince: row => row.filter_contract.supported_filters.includes('province'),
  writeUrl: push => { if (!state.filterDraft) history.push(push); },
});
vm.runInContext(['selectMeasure', 'changeMeasure', 'handleProvince', 'openFilters', 'finishFilters'].map(extract).join('\n'), context);
context.changeMeasure('K09');
assert.equal(state.province, '');
assert.equal(state.rememberedProvince, '50');
context.changeMeasure('K04');
assert.equal(state.province, '50');
assert.deepEqual(restored, ['', '50']);
context.handleProvince('');
context.changeMeasure('K09');
context.changeMeasure('K04');
assert.equal(state.province, ''); // Explicit national selection clears remembered province.
state.province = state.rememberedProvince = '50';
state.filters = {q:'original'}; state.searchDraft = 'original'; state.offset = 25;
const before = history.length;
context.openFilters();
context.changeMeasure('K09');
assert.equal(history.length, before); // Preview never adds browser history.
context.finishFilters(false);
assert.equal(state.province, '50');
assert.equal(state.measure, 'K04');
assert.equal(state.filters.q, 'original');
assert.equal(state.offset, 25);
context.openFilters();
context.changeMeasure('K09');
context.finishFilters(true);
assert.equal(state.province, '');
assert.equal(state.rememberedProvince, '50');
assert.equal(state.filterDraft, null);
assert.equal(history.at(-1), true);
state.offset = 25;
context.openFilters();
state.searchDraft = 'new search'; // Apply before the search debounce fires.
context.finishFilters(true);
assert.equal(state.offset, 0);
assert.equal(state.filters.q, 'new search');
const integration = fs.readFileSync('app/static/app.js', 'utf8');
const resizeStart = integration.indexOf('function syncResponsiveWorkspace()');
const resizeEnd = integration.indexOf('\nfunction ', resizeStart + 1);
state.catalog = {}; state.mapMode = 'f2'; state.selectedCode = '';
context.window = {F2Dashboard:{isOpen: () => true}};
context.usesMobileMapFirst = () => true;
context.hideWorkspacePanel = () => assert.fail('Resize must not hide an active F2 lookup');
vm.runInContext(integration.slice(resizeStart, resizeEnd), context);
context.syncResponsiveWorkspace();
// Historical income reconstruction must not be selectable, even through an old URL.
vm.runInContext(source.split('\n').find(line => line.startsWith('  const visibleMeasures =')), context);
assert.equal(vm.runInContext("visibleMeasures([{measure_id:'K10'},{measure_id:'C10_ALTERNATIVE'}]).length", context), 1);
assert.equal(vm.runInContext("visibleMeasures([{value:'K10'},{value:'C10_ALTERNATIVE'}])[0].value", context), 'K10');
context.URLSearchParams = URLSearchParams;
context.location = {search:'?f2tab=list&f2measure=C10_ALTERNATIVE&f2component=excludedResourceExpense&f2offset=25'};
vm.runInContext(extract('restoreUrl'), context);
context.restoreUrl();
assert.equal(state.measure, 'K10');
assert.equal(Object.keys(state.filters).length, 0);
assert.equal(state.offset, 0);
context.selectMeasure('C10_ALTERNATIVE');
assert.equal(state.measure, 'K10');
// Coverage remains national context and cannot return as a selectable map metric.
definitions.push({measure_id:'K12', topic_id:'k12', filter_contract:{supported_filters:['province']}});
assert.equal(vm.runInContext("visibleMeasures([{value:'K01A'},{value:'K12'}])[0].value", context), 'K12');
context.selectMeasure('');
assert.equal(state.measure, 'K12');
assert.equal(state.topic, 'k12');
context.location.search = '?f2tab=list&f2measure=K01A&province=50&f2offset=25&f2detail=old';
context.restoreUrl();
assert.equal(state.measure, 'K12');
assert.equal(state.topic, 'k12');
assert.equal(state.province, '50');
assert.equal(state.offset, 0);
assert.equal(state.detail, '');
context.selectMeasure('K01A');
assert.equal(state.measure, 'K12');
vm.runInContext(extract('datasetCoverageCount'), context);
assert.equal(context.datasetCoverageCount({headlines:[{measure_id:'K01A', result:{value:1}, coverage:{national_total:77, selected_count:1}}]}), 77);
assert.equal(context.datasetCoverageCount({headlines:[]}), null);

"""
    result = subprocess.run(
        [shutil.which("node"), "-"], input=script, text=True, capture_output=True,
        cwd=Path(__file__).resolve().parents[1], timeout=30,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_metric_explanations_follow_responsive_rows():
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/f2.js', 'utf8');
const start = source.indexOf('  function metricRows(');
const end = source.indexOf('  function backToOverview(', start);
let columns = '200px 200px';
const panels = new Map();
function card(id) {
  const attributes = {'aria-expanded':'false', 'aria-controls':id};
  const button = {getAttribute:key=>attributes[key], setAttribute:(key,value)=>{attributes[key]=value;}};
  panels.set(id, {hidden:true, afterCard:null});
  return {id, button, classList:{contains:name=>name==='f2-metric-wrap'},
    querySelector:()=>button, after:panel=>{panel.afterCard=id;}};
}
const [a,b,c,d] = ['a','b','c','d'].map(card);
const note = {classList:{contains:()=>false}};
const panelNode = {classList:{contains:name=>name==='f2-metric-explanation'}};
const group = {children:[a,panelNode,b,note,c,d]};
const context = vm.createContext({getComputedStyle:()=>({gridTemplateColumns:columns}), $:id=>panels.get(id)});
vm.runInContext(source.slice(start,end),context);
function open(card) {
  card.button.setAttribute('aria-expanded','true');
  context.layoutMetricExplanations(group,card.button);
}
open(a);
assert.equal(panels.get('a').afterCard,'b'); // Full width beneath both cards.
open(b);
assert.equal(panels.get('a').hidden,true);
assert.equal(a.button.getAttribute('aria-expanded'),'false');
assert.equal(panels.get('b').hidden,false);
open(c);
assert.equal(panels.get('b').hidden,false); // A different row stays open.
assert.equal(panels.get('c').afterCard,'d');
b.button.setAttribute('aria-expanded','false');
context.layoutMetricExplanations(group,b.button);
assert.equal(panels.get('b').hidden,true);
columns = '400px';
context.layoutMetricExplanations(group);
assert.equal(panels.get('c').afterCard,'c'); // Mobile: beneath its own card.
open(d);
columns = '200px 200px';
context.layoutMetricExplanations(group);
assert.equal(panels.get('c').hidden,false);
assert.equal(panels.get('d').hidden,true); // Resize merges rows without two open panels.
group.children = [a,b,c,d];
columns = '200px 200px 200px';
open(a);
assert.equal(panels.get('a').afterCard,'c'); // Expanded desktop has three columns.
assert.equal(panels.get('c').hidden,true);
"""
    result = subprocess.run(
        [shutil.which("node"), "-"], input=script, text=True, capture_output=True,
        cwd=Path(__file__).resolve().parents[1], timeout=30,
    )
    assert result.returncode == 0, result.stderr

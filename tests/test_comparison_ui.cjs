const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor() { this.children = []; this.style = {}; this.value = '65'; this.dataset = {}; this.textContent = ''; }
  append(...nodes) { this.children.push(...nodes); }
  prepend(...nodes) { this.children.unshift(...nodes); }
  addEventListener() {}
  setAttribute(name, value) { this[name] = value; }
  replaceChildren(...nodes) { this.children = nodes; }
  get text() { return this.textContent + this.children.map(node => node.text).join(' '); }
}

function harness(data) {
  const elements = new Map();
  const document = {
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, new Element());
      return elements.get(id);
    },
    createElement() { return new Element(); },
  };
  const context = vm.createContext({ document, console, AbortController, setTimeout, clearTimeout,
    fetch: async () => ({ ok: true, json: async () => data }) });
  // Load the application's functions without registering page events or starting timers.
  const code = fs.readFileSync(require.resolve('../app/static/app.js'), 'utf8');
  vm.runInContext(code.slice(0, code.indexOf('// EVENT LISTENERS')), context);
  return { context, elements };
}

test('missing rolling cache clears previous metrics without displaying an error or training claim', async () => {
  const { context, elements } = harness({ status: 'not_ready', message: 'Báo cáo được tính riêng trên máy chủ.' });
  for (const id of ['fortune-historical-summary', 'fortune-historical-daily-body', 'fortune-historical-daily-stats']) {
    vm.runInContext(`el('${id}').append(cell('old report'));`, context);
  }
  await context.loadRollingModelComparison();
  for (const id of ['fortune-historical-summary', 'fortune-historical-daily-body', 'fortune-historical-daily-stats']) {
    assert.equal(elements.get(id).children.length, 0);
  }
  assert.equal(elements.get('fortune-rolling-window-badge').text, 'Chờ báo cáo');
  assert.match(elements.get('fortune-historical-note').text, /tính riêng/);
});

test('dashboard loads only the selected page, including after navigation', async () => {
  const { context } = harness({});
  const names = ['loadMetrics', 'loadLatestResult', 'loadLatestPrediction', 'loadLatestLogisticPrediction',
    'loadLatestCatBoostPrediction', 'loadPredictionHistory', 'loadLogisticPredictionHistory',
    'loadModelComparison', 'loadRollingModelComparison', 'loadCatBoostHistory',
    'loadCatBoostComparison', 'loadCatBoostRecentNumbers', 'loadResults', 'loadBacktests', 'loadDigitBacktests'];
  context.loaded = [];
  for (const name of names) vm.runInContext(`${name} = async () => loaded.push('${name}');`, context);
  vm.runInContext('renderCatBoostPrediction = () => {};', context);
  await context.refreshDashboard();
  assert.deepEqual(context.loaded, ['loadMetrics', 'loadLatestResult']);
  context.loaded.length = 0;
  vm.runInContext("state.currentPage = 'one-digit';", context);
  await context.refreshDashboard();
  assert.deepEqual(context.loaded, ['loadLatestCatBoostPrediction', 'loadCatBoostHistory',
    'loadCatBoostComparison', 'loadCatBoostRecentNumbers']);
});

test('unchanged result avoids dashboard reload; corrections and five-minute refresh still load', async () => {
  const { context } = harness({});
  context.reloads = 0;
  vm.runInContext('renderLatestResult = () => {}; toast = () => {}; refreshDashboard = async () => { reloads++; };', context);
  const result = { draw_date: '2026-10-16', special_prize: '00059', last_two: '59', status: 'observed' };
  await context.handlePolledResult(result, result.draw_date);
  await context.handlePolledResult(result, result.draw_date);
  assert.equal(context.reloads, 1);
  await context.handlePolledResult({ ...result, status: 'conflict' }, result.draw_date);
  assert.equal(context.reloads, 2);
  vm.runInContext('state.smartRefreshAt -= 300001;', context);
  await context.handlePolledResult({ ...result, status: 'conflict' }, result.draw_date);
  assert.equal(context.reloads, 3);
});

test('live A/B displays uncertainty and exclusion reasons, including an empty sample', async () => {
  const model = { hit_rate: null, hits: 0, confidence_interval_95: null };
  const { context, elements } = harness({ paired_predictions: 0, frequency_model: model, logistic_model: model,
    lift_logistic_vs_frequency: null, mcnemar_exact_p: null, baseline: 0.65, recent_pairs: [],
    note: 'Loại dự đoán khóa muộn. Chưa đủ bằng chứng.' });
  await context.loadModelComparison();
  assert.match(elements.get('fortune-comparison-summary').text, /Chưa có khoảng tin cậy/);
  assert.match(elements.get('fortune-comparison-note').text, /khóa muộn/);
  assert.match(elements.get('fortune-comparison-history').text, /Chưa có đủ cặp/);
});

test('three-way comparison renders CI and paired adjusted statistics', async () => {
  const model = { model_version: 'A', hit_rate: 15/19, hits: 15, confidence_interval_95: [0.566657, 0.914923] };
  const { context, elements } = harness({ selected_count: 65, paired_predictions: 19, baseline: 0.65,
    frequency_model: model, logistic_model: { ...model, model_version: 'B' },
    catboost_model: { ...model, model_version: 'C' }, note: 'Chưa đủ bằng chứng.', recent_pairs: [],
    comparisons: [{ model_a: 'A', model_b: 'C', mcnemar_exact_p: 1, mcnemar_holm_p: 1 }] });
  await context.loadCatBoostComparison();
  assert.match(elements.get('catboost-comparison-cards').text, /15\/19 HIT · CI 95% 56\.67% – 91\.49%/);
  assert.match(elements.get('catboost-comparison-note').text, /sau Holm=1/);
});

test('latest prediction renders invalidation without retaining HIT or MISS', async () => {
  const { context, elements } = harness({ prediction_date: '2026-10-13', selected_count: 65,
    trained_through: '2026-10-12', coverage_probability: 0.7, numbers: [], scores: [],
    evaluation: { status: 'invalidated' } });
  vm.runInContext('renderNumberGrid = () => {}; updateSelectedExport = () => {};', context);
  await context.loadLatestPrediction();
  const text = elements.get('prediction-meta').text;
  assert.match(text, /Kết quả cần xác minh/);
  assert.doesNotMatch(text, /HIT|MISS/);
});

test('all three histories clearly label retrospective predictions', async () => {
  const { context, elements } = harness([{ _id: 'replay', prediction_date: '2026-10-14',
    selected_count: 65, trained_through: '2026-10-13', prediction_kind: 'retrospective',
    model_version: 'test-model', evaluation: { status: 'evaluated', actual_last_two: '59', hit: true } }]);
  await context.loadPredictionHistory();
  await context.loadLogisticPredictionHistory();
  await context.loadCatBoostHistory();
  for (const id of ['prediction-history', 'fortune-prediction-history', 'catboost-prediction-history']) {
    assert.match(elements.get(id).text, /2026-10-14.*HỒI KIỂM/);
    assert.match(elements.get(id).text, /59/);
  }
});

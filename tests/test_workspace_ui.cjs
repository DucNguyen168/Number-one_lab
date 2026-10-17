const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function element() {
  const classes = new Set();
  return {
    textContent: '', innerHTML: 'Refresh', hidden: false, open: false, dataset: {}, isConnected: true,
    attributes: {}, handlers: {}, focused: false, children: [],
    append(...nodes) { this.children.push(...nodes); },
    replaceChildren(...nodes) { this.children = nodes; },
    classList: { contains: key => classes.has(key), toggle(key, on) { on ? classes.add(key) : classes.delete(key); } },
    setAttribute(key, value) { this.attributes[key] = value; },
    removeAttribute(key) { delete this.attributes[key]; },
    addEventListener(name, callback) { (this.handlers[name] ||= []).push(callback); },
    emit(name, event = {}) { this.handlers[name]?.forEach(callback => callback(event)); },
    focus() { this.focused = true; },
    showModal() { this.open = true; },
    close() { this.open = false; this.emit('close'); },
    getBoundingClientRect: () => ({ left: 20, top: 20, right: 200, bottom: 200 }),
  };
}

function harness(fetcher = async () => ({ ok: true, json: async () => ({}) })) {
  const nodes = new Map();
  const get = id => { if (!nodes.has(id)) nodes.set(id, element()); return nodes.get(id); };
  const dialogs = ['usage-rules', 'automation-dialog', 'prediction-detail-modal'].map(get);
  dialogs.slice(1).forEach(node => { node.dataset.dismissible = 'true'; });
  const body = element();
  const opener = element();
  const document = {
    body, activeElement: opener, getElementById: get, createElement: element,
    querySelectorAll: selector => selector === 'dialog' ? dialogs : [],
    querySelector: selector => selector === 'dialog[open]' ? dialogs.find(node => node.open) : null,
  };
  const window = { matchMedia: () => ({ matches: true }) };
  const context = vm.createContext({ document, window, console, AbortController, setTimeout, clearTimeout, fetch: fetcher });
  vm.runInContext(fs.readFileSync(require.resolve('../app/static/ui.js'), 'utf8'), context);
  const app = fs.readFileSync(require.resolve('../app/static/app.js'), 'utf8');
  vm.runInContext(app.slice(0, app.indexOf('// EVENT LISTENERS')), context);
  const run = code => vm.runInContext(code, context);
  return { get, context, run, body, opener, window };
}

test('concurrent GETs share one request; completed reads and POSTs are never cached', async () => {
  let calls = 0;
  const pending = deferred();
  const h = harness(async () => { calls++; await pending.promise; return { ok: true, json: async () => ({ ok: true }) }; });
  const a = h.context.api('/api/results');
  const b = h.context.api('/api/results');
  assert.equal(calls, 1);
  pending.resolve();
  await Promise.all([a, b]);
  await h.context.api('/api/results');
  assert.equal(calls, 2);
  await Promise.all([h.context.api('/api/run', { method: 'POST' }), h.context.api('/api/run', { method: 'POST' })]);
  assert.equal(calls, 4);
});

test('a rejected read can be retried without reusing a failed request', async () => {
  let calls = 0;
  const h = harness(async () => {
    if (++calls === 1) throw new Error('offline');
    return { ok: true, json: async () => ({ recovered: true }) };
  });
  await assert.rejects(h.context.api('/api/results'), /offline/);
  assert.equal((await h.context.api('/api/results')).recovered, true);
});

test('timeouts while reading a response and invalid JSON surface as errors', async () => {
  const h = harness(async () => ({ ok: true, json: async () => { throw Object.assign(new Error('aborted'), { name: 'AbortError' }); } }));
  await assert.rejects(h.context.api('/api/results'), /quá thời gian/);
  h.context.fetch = async () => ({ ok: true, json: async () => { throw new SyntaxError('bad json'); } });
  await assert.rejects(h.context.api('/api/results'), /không hợp lệ/);
});

test('navigation preserves modified clicks, changes route once and restores history scroll position', () => {
  const h = harness();
  const link = element();
  link.dataset.pageLink = 'results';
  const section = element();
  section.dataset.pageView = 'results';
  const listeners = {};
  let pushes = 0;
  let refreshes = 0;
  h.context.document.querySelectorAll = selector => selector === '[data-page-view]' ? [section] : [link];
  h.window.location = { pathname: '/', href: 'http://local/' };
  h.window.history = {
    state: {},
    replaceState(value) { this.state = value; },
    pushState(value, unused, path) { this.state = value; h.window.location.pathname = path; pushes++; },
  };
  h.window.scrollY = 420;
  h.window.scrollTo = options => { h.window.scrollY = options.top; };
  h.window.addEventListener = (name, callback) => { listeners[name] = callback; };
  h.context.refreshDashboard = () => { refreshes++; };
  h.context.initPageNavigation();
  let prevented = 0;
  link.emit('click', { button: 0, ctrlKey: true, preventDefault() { prevented++; } });
  assert.equal(pushes, 0);
  assert.equal(prevented, 0);
  link.emit('click', { button: 0, preventDefault() { prevented++; } });
  assert.equal(pushes, 1);
  assert.equal(h.window.scrollY, 0);
  assert.equal(link.attributes['aria-current'], 'page');
  assert.equal(h.get('page-title').focused, true);
  link.emit('click', { button: 0, preventDefault() {} });
  assert.equal(pushes, 1);
  assert.equal(refreshes, 1);
  h.window.location.pathname = '/';
  listeners.popstate({ state: { scrollY: 420 } });
  assert.equal(h.window.scrollY, 420);
  assert.equal(pushes, 1);
  assert.equal(link.attributes['aria-current'], undefined);
});

test('blocked local storage does not prevent theme initialization or switching', () => {
  const h = harness();
  const root = element();
  root.dataset.theme = 'dark';
  h.context.document.documentElement = root;
  h.context.document.querySelector = () => ({});
  h.context.localStorage = { setItem() { throw new Error('storage blocked'); } };
  h.context.initThemeToggle();
  assert.equal(h.get('sky-toggle').attributes['aria-pressed'], 'true');
  h.get('sky-toggle').emit('click');
  assert.equal(root.dataset.theme, 'light');
  assert.equal(h.get('sky-toggle').attributes['aria-pressed'], 'false');
});

test('partial refresh reports failure, then retry clears feedback and busy state', async () => {
  const h = harness();
  h.run('loadMetrics = async () => { throw new Error("offline"); }; loadLatestResult = async () => {};');
  await h.context.refreshDashboard();
  assert.equal(h.get('page-feedback').hidden, false);
  assert.match(h.get('page-feedback-message').textContent, /Một phần/);
  assert.equal(h.get('page-progress').hidden, true);
  assert.equal(h.get('main-content').attributes['aria-busy'], 'false');
  assert.equal(h.get('refresh-page-btn').disabled, false);
  h.run('loadMetrics = async () => {};');
  await h.context.refreshDashboard();
  assert.equal(h.get('page-feedback').hidden, true);
  assert.match(h.get('page-update-status').textContent, /Cập nhật lúc/);
});

test('slow previous page cannot replace the new page loading status or error message', async () => {
  const h = harness();
  const pending = deferred();
  h.context.pending = pending.promise;
  h.run('loadMetrics = async () => pending; loadLatestResult = async () => pending; loadResults = async () => {};');
  const oldRefresh = h.context.refreshDashboard();
  assert.equal(h.get('page-progress').hidden, false);
  h.run('state.currentPage = "results";');
  await h.context.refreshDashboard();
  const currentStatus = h.get('page-update-status').textContent;
  pending.reject(new Error('old request failed'));
  await oldRefresh;
  assert.equal(h.get('page-update-status').textContent, currentStatus);
  assert.equal(h.get('page-feedback').hidden, true);
  assert.equal(h.get('page-progress').hidden, true);
});

test('opening another prediction ignores a late response from the first one', async () => {
  const first = deferred();
  const h = harness(async path => {
    if (path.endsWith('/first')) await first.promise;
    return { ok: true, json: async () => ({ id: path.split('/').pop() }) };
  });
  h.run('rendered = []; renderPredictionDetail = prediction => rendered.push(prediction.id);');
  const oldDetail = h.context.openPredictionDetail('first');
  await h.context.openPredictionDetail('second');
  first.resolve();
  await oldDetail;
  assert.deepEqual([...h.context.rendered], ['second']);
});

test('closing a loading prediction does not render it after its response arrives', async () => {
  const pending = deferred();
  const h = harness(async () => { await pending.promise; return { ok: true, json: async () => ({}) }; });
  h.run('renderCount = 0; renderPredictionDetail = () => renderCount++;');
  const detail = h.context.openPredictionDetail('first');
  h.context.closePredictionDetail();
  pending.resolve();
  await detail;
  assert.equal(h.context.renderCount, 0);
  assert.equal(h.get('prediction-detail-modal').open, false);
});

test('native popup lifecycle locks scroll, restores focus and keeps lock for another open popup', () => {
  const h = harness();
  const ui = h.window.DashboardUI;
  ui.openDialog(h.get('automation-dialog'));
  assert.equal(h.body.classList.contains('dialog-open'), true);
  ui.openDialog(h.get('prediction-detail-modal'));
  ui.closeDialog(h.get('prediction-detail-modal'));
  assert.equal(h.body.classList.contains('dialog-open'), true);
  ui.closeDialog(h.get('automation-dialog'));
  assert.equal(h.body.classList.contains('dialog-open'), false);
  assert.equal(h.opener.focused, true);
});

test('Escape is handled for dismissible popups while the entry notice remains mandatory', () => {
  const h = harness();
  const dialog = h.get('automation-dialog');
  h.window.DashboardUI.openDialog(dialog);
  let prevented = false;
  dialog.emit('cancel', { preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
  assert.equal(dialog.open, false);
  assert.equal(h.get('usage-rules').handlers.cancel, undefined);
});

test('a press that starts inside the popup cannot dismiss it by releasing outside', () => {
  const h = harness();
  const dialog = h.get('automation-dialog');
  h.window.DashboardUI.openDialog(dialog);
  dialog.emit('pointerdown', { target: dialog, clientX: 50, clientY: 50 });
  dialog.emit('click', { target: dialog, clientX: 0, clientY: 0 });
  assert.equal(dialog.open, true);
  dialog.emit('pointerdown', { target: dialog, clientX: 0, clientY: 0 });
  dialog.emit('click', { target: dialog, clientX: 0, clientY: 0 });
  assert.equal(dialog.open, false);
});

test('reopening during close animation cancels the pending close', async () => {
  const h = harness();
  h.window.matchMedia = () => ({ matches: false });
  const dialog = h.get('automation-dialog');
  const pending = deferred();
  let canceled = false;
  h.window.DashboardUI.openDialog(dialog);
  dialog.animate = () => ({ finished: pending.promise, cancel() { canceled = true; pending.reject(new Error('canceled')); } });
  h.window.DashboardUI.closeDialog(dialog);
  h.window.DashboardUI.openDialog(dialog);
  await Promise.resolve();
  assert.equal(canceled, true);
  assert.equal(dialog.open, true);
  assert.equal(h.body.classList.contains('dialog-open'), true);
});

function resultRows(count = 15) {
  return Array.from({ length: count }, (_, index) => ({
    draw_date: `2026-10-${String(20 - index).padStart(2, '0')}`,
    special_prize: '00100', last_two: '00', status: 'observed', sources: { first: { name: 'Source A' } },
  }));
}

function resultsFetcher(rows, calls) {
  return async path => {
    calls.push(path);
    const params = new URL(path, 'http://local').searchParams;
    const before = params.get('before');
    return { ok: true, json: async () => rows.filter(row => !before || row.draw_date < before).slice(0, Number(params.get('limit'))) };
  };
}

test('results initially show six days and preserve leading zeros', async () => {
  const calls = [];
  const h = harness(resultsFetcher(resultRows(), calls));
  await h.context.loadResults();
  assert.deepEqual(calls, ['/api/results?limit=7&include_models=true']);
  const rows = h.get('result-history').children;
  assert.equal(rows.length, 6);
  assert.equal(rows[0].children[0].textContent, '20/10/2026');
  assert.equal(rows[0].children[1].textContent, '00100');
  assert.equal(rows[0].children[2].children[0].textContent, '00');
  assert.equal(h.get('results-more-btn').hidden, false);
});

test('show more appends six older days without repeats and hides at the end', async () => {
  const calls = [];
  const h = harness(resultsFetcher(resultRows(), calls));
  await h.context.loadResults();
  await h.context.loadResults({ append: true });
  assert.equal(h.get('result-history').children.length, 12);
  assert.equal(calls[1], '/api/results?limit=7&include_models=true&before=2026-10-15');
  await h.context.loadResults({ append: true });
  const dates = h.get('result-history').children.map(row => row.children[0].textContent);
  assert.equal(dates.length, 15);
  assert.equal(new Set(dates).size, 15);
  assert.equal(h.get('results-more-btn').hidden, true);
  await h.context.loadResults({ append: true });
  assert.equal(calls.length, 3);
});

test('refresh keeps the expanded row count and includes a new latest result', async () => {
  const rows = resultRows();
  const calls = [];
  const h = harness(resultsFetcher(rows, calls));
  await h.context.loadResults();
  await h.context.loadResults({ append: true });
  rows.unshift({ ...rows[0], draw_date: '2026-10-21' });
  await h.context.loadResults();
  assert.equal(calls[2], '/api/results?limit=13&include_models=true');
  assert.equal(h.get('result-history').children.length, 12);
  assert.equal(h.get('result-history').children[0].children[0].textContent, '21/10/2026');
});

test('a failed show-more request keeps existing rows and can retry the same cursor', async () => {
  const rows = resultRows();
  const calls = [];
  const h = harness(resultsFetcher(rows, calls));
  await h.context.loadResults();
  h.context.fetch = async () => { throw new Error('offline'); };
  await assert.rejects(h.context.loadResults({ append: true }), /offline/);
  assert.equal(h.get('result-history').children.length, 6);
  assert.equal(h.get('results-more-btn').disabled, false);
  assert.equal(h.get('results-more-btn').hidden, false);
  assert.match(h.get('results-range').textContent, /thử lại/);
  h.context.fetch = resultsFetcher(rows, calls);
  await h.context.loadResults({ append: true });
  assert.equal(calls[1], '/api/results?limit=7&include_models=true&before=2026-10-15');
  assert.equal(h.get('result-history').children.length, 12);
});

test('repeated show-more clicks and an overlapping refresh share a single request', async () => {
  const rows = resultRows();
  const calls = [];
  const h = harness(resultsFetcher(rows, calls));
  await h.context.loadResults();
  const gate = deferred();
  const fetcher = resultsFetcher(rows, calls);
  h.context.fetch = async path => { await gate.promise; return fetcher(path); };
  const first = h.context.loadResults({ append: true });
  const second = h.context.loadResults({ append: true });
  const refresh = h.context.loadResults();
  assert.equal(h.get('results-more-btn').disabled, true);
  gate.resolve();
  await Promise.all([first, second, refresh]);
  assert.equal(calls.length, 2);
  assert.equal(h.get('result-history').children.length, 12);
  assert.equal(h.get('result-history').attributes['aria-busy'], 'false');
});

test('empty results render a clear message and no show-more button', async () => {
  const h = harness(resultsFetcher([], []));
  await h.context.loadResults();
  assert.match(h.get('result-history').children[0].children[0].textContent, /Chưa có kết quả/);
  assert.equal(h.get('results-more-btn').hidden, true);
});

test('results replace sources with accessible A/B/C outcomes and disclose retrospective results', async () => {
  const rows = resultRows(1);
  rows[0].model_selected_count = 65;
  rows[0].model_outcomes = {
    A: { status: 'hit', prediction_kind: 'live' },
    B: { status: 'miss', prediction_kind: 'retrospective' },
    C: { status: 'pending', prediction_kind: 'live' },
  };
  const h = harness(resultsFetcher(rows, []));
  await h.context.loadResults();
  const cells = h.get('result-history').children[0].children;
  assert.equal(cells.length, 5);
  assert.equal(cells[4].className, 'results-models-cell');
  const markers = cells[4].children[0].children;
  assert.deepEqual(markers.map(node => node.children[0].textContent), ['A', 'B', 'C']);
  assert.deepEqual(markers.map(node => node.children[1].textContent), ['✓', '×', '—']);
  assert.match(markers[0].className, /result-model-hit$/);
  assert.match(markers[1].className, /result-model-miss$/);
  assert.match(markers[2].className, /result-model-neutral$/);
  assert.match(markers[0].attributes['aria-label'], /Dự đoán N-1: Đúng · Top 65/);
  assert.match(markers[1].attributes['aria-label'], /Thần Tài: Sai.*Hồi kiểm/);
  assert.equal(markers[1].children[2].textContent, 'HK');
  assert.equal(h.get('results-model-count').textContent, 'Đối chiếu Top 65');
});

test('missing, invalidated and unknown model outcomes stay neutral', () => {
  const h = harness();
  const cell = h.context.resultModelCell({ model_outcomes: {
    B: { status: 'invalidated' }, C: { status: 'unexpected' },
  } });
  for (const marker of cell.children[0].children) {
    assert.match(marker.className, /result-model-neutral$/);
    assert.equal(marker.children[1].textContent, '—');
  }
  assert.match(cell.children[0].children[1].attributes['aria-label'], /Cần đối chiếu lại/);
});

test('N-1 route and legacy bookmarks open the same model with its new title', () => {
  const h = harness();
  for (const path of ['/du-doan-n-1', '/du-doan-n-1/', '/du-doan-2-so', '/du-doan-2-so/']) {
    assert.equal(h.context.pageFromPath(path), 'two-digit');
  }
  h.context.showPage('two-digit');
  assert.equal(h.get('page-title').textContent, 'Dự đoán N-1');
  assert.equal(h.context.document.title, 'Dự đoán N-1 · XSMB Research Lab');
});

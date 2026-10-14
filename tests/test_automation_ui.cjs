const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function harness(handler = () => ({ ok: true, data: {} })) {
  const elements = new Map();
  const calls = [];
  const document = {
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, {
        textContent: '', hidden: false, open: false, value: '', dataset: {},
        showModal() { this.open = true; }, focus() {}, close() { this.open = false; },
      });
      return elements.get(id);
    },
  };
  const context = vm.createContext({ document, console, fetch: async (path, options) => {
    calls.push({ path, options });
    const reply = handler(path, options);
    return { ok: reply.ok, status: reply.status || 200, json: async () => reply.data };
  } });
  const code = fs.readFileSync(require.resolve('../app/static/app.js'), 'utf8');
  vm.runInContext(code.slice(0, code.indexOf('// EVENT LISTENERS')), context);
  return { context, calls, element: document.getElementById };
}

test('manual generation and automatic recovery do not send credentials or open login', async () => {
  const { context, calls } = harness();
  for (const path of ['/api/predictions/generate', '/api/logistic-predictions/generate', '/api/catboost-predictions/generate', '/api/auto-daily']) {
    await context.api(path, { method: 'POST', headers: { Accept: 'application/json' } });
  }
  calls.forEach(call => {
    assert.equal(call.options.headers['X-Admin-Key'], undefined);
    assert.equal(call.options.headers.Authorization, undefined);
    assert.equal(call.options.headers['Content-Type'], 'application/json');
    assert.equal(call.options.headers.Accept, 'application/json');
  });
});

test('Vercel mode shows Cron without claiming an in-process scheduler or requiring keys', () => {
  const { context, element } = harness();
  const health = { scheduler_enabled: false, automation: { mode: 'vercel_cron', configured: true, auto_prediction: true } };
  context.renderAutomationStatus(health);
  assert.equal(element('scheduler-pill').textContent, 'Vercel Cron');
  assert.doesNotMatch(element('automation-status').textContent, /SECRET|API_KEY/);
  health.automation.last_run = { status: 'interrupted', trigger: 'cron', started_at: '2026-10-14T12:00:00Z' };
  context.renderAutomationStatus(health);
  assert.equal(element('scheduler-pill').textContent, 'Tự động: có lỗi');
});

test('recovery outcome remains visible inside modal instead of only in toast behind it', async () => {
  const { context, element } = harness();
  vm.runInContext('toast = () => {}; refreshDashboard = async () => {};', context);
  element('automation-dialog').open = true;
  await context.runAction(element('automation-run-btn'), 'Đang chạy', async () => ({}), () => 'Đã bổ sung dự đoán');
  assert.equal(element('automation-message').textContent, 'Đã bổ sung dự đoán');
  await context.runAction(element('automation-run-btn'), 'Đang chạy', async () => { throw new Error('Nguồn chưa có kết quả'); }, () => '');
  assert.equal(element('automation-message').textContent, 'Nguồn chưa có kết quả');
  assert.equal(element('automation-run-btn').disabled, false);
});

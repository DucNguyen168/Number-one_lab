const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createResultPoller } = require('../app/static/result-refresh.js');

function harness(time = '2026-10-12T11:30:00Z') {
  const state = { time, calls: [], timers: [], results: [], latest: null, refreshed: null, fail: false };
  const poller = createResultPoller({
    now: () => new Date(state.time),
    api: async (path, options) => {
      state.calls.push({ path, options });
      if (state.fail) throw new Error('offline');
      return path.endsWith('/latest') ? state.latest : { result: state.refreshed };
    },
    onResult: async (result, today) => state.results.push({ result, today }),
    onError: () => {},
    setTimer: (callback, delay) => { state.timers.push({ callback, delay }); return state.timers.length; },
    clearTimer: () => {},
  });
  return { poller, state };
}

test('starts at 18:30 Vietnam time, with no source calls before it', async () => {
  const { poller, state } = harness('2026-10-12T11:29:59Z');
  await poller.start();
  assert.equal(state.calls.length, 0);
  assert.equal(state.timers.at(-1).delay, 1000);
  state.time = '2026-10-12T11:30:00Z';
  await state.timers.at(-1).callback();
  assert.deepEqual(state.calls.map(call => call.path), ['/api/results/latest', '/api/results/refresh']);
  assert.equal(state.calls[1].options.method, 'POST');
  assert.equal(state.calls[0].options.cache, 'no-store');
  assert.equal(state.timers.at(-1).delay, 10000);
});

test('keeps retrying absent results and recovers from network failure', async () => {
  const { poller, state } = harness();
  state.fail = true;
  await poller.start();
  assert.equal(state.timers.at(-1).delay, 10000);
  state.fail = false;
  await state.timers.at(-1).callback();
  assert.equal(state.timers.at(-1).delay, 10000);
  state.refreshed = { draw_date: '2026-10-12', status: 'observed', special_prize: '00123' };
  await state.timers.at(-1).callback();
  assert.equal(state.results.at(-1).result.special_prize, '00123');
  assert.equal(state.timers.at(-1).delay, 60000);
});

test('uses the Vietnam calendar date after UTC midnight offset', async () => {
  const { poller, state } = harness('2026-10-12T17:01:00Z'); // 00:01 next day VN
  await poller.start();
  assert.equal(state.calls.length, 0);
  assert.equal(state.timers.at(-1).delay, 60000);
  state.time = '2026-10-13T11:30:00Z';
  state.refreshed = { draw_date: '2026-10-13', status: 'observed' };
  await poller.wake();
  assert.equal(state.results.at(-1).today, '2026-10-13');
});

test('keeps checking late results and conflicted results', async () => {
  const { poller, state } = harness('2026-10-12T16:59:00Z'); // 23:59 VN
  state.latest = { draw_date: '2026-10-12', status: 'conflict' };
  state.refreshed = state.latest;
  await poller.start();
  assert.equal(state.calls.length, 2);
  assert.equal(state.timers.at(-1).delay, 10000);
});

test('does not fetch sources again when today is already available', async () => {
  const { poller, state } = harness();
  state.latest = { draw_date: '2026-10-12', status: 'observed' };
  await poller.start();
  assert.equal(state.calls.length, 1);
  assert.equal(state.results.length, 1);
  assert.equal(state.timers.at(-1).delay, 60000);
});

test('visibility wakes cannot overlap an active request; stop prevents rescheduling', async () => {
  let release;
  let calls = 0;
  const timers = [];
  const poller = createResultPoller({
    now: () => new Date('2026-10-12T11:30:00Z'),
    api: async () => {
      calls++;
      return new Promise(resolve => { release = resolve; });
    },
    onResult: async () => {},
    setTimer: (callback, delay) => timers.push(delay),
    clearTimer: () => {},
  });
  const first = poller.start();
  await poller.wake();
  assert.equal(calls, 1);
  poller.stop();
  release({ draw_date: '2026-10-12', status: 'observed' });
  await first;
  assert.deepEqual(timers, []);
});

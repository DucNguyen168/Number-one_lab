/* A single, shared polling loop. No source calls before the configured draw time. */
function createResultPoller({
  api, onResult, onError = console.warn,
  now = () => new Date(),
  setTimer = setTimeout, clearTimer = clearTimeout,
  timezone = 'Asia/Ho_Chi_Minh', startTime = '18:30', intervalSeconds = 10,
}) {
  let timer = null;
  let running = false;
  let stopped = true;
  const interval = Math.max(10, intervalSeconds) * 1000;

  function clock() {
    const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
      timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
    }).formatToParts(now()).map(part => [part.type, part.value]));
    const [hour, minute] = startTime.split(':').map(Number);
    return {
      today: `${parts.year}-${parts.month}-${parts.day}`,
      untilStart: ((hour * 60 + minute) * 60
        - (Number(parts.hour) * 3600 + Number(parts.minute) * 60 + Number(parts.second))) * 1000,
    };
  }

  async function poll() {
    if (running || stopped) return;
    clearTimer(timer);
    running = true;
    let delay = interval;
    try {
      const local = clock();
      if (local.untilStart > 0) {
        // Recheck the clock each minute; wake exactly at 18:30 across UTC dates.
        delay = Math.min(local.untilStart, 60000);
        return;
      }
      let result = await api('/api/results/latest', { cache: 'no-store' });
      if (!result || result.draw_date !== local.today || result.status === 'conflict') {
        const refreshed = await api('/api/results/refresh', { method: 'POST', cache: 'no-store' });
        result = refreshed.result;
      }
      if (result) await onResult(result, local.today);
      if (result?.draw_date === local.today && result.status !== 'conflict') {
        delay = 60000; // Keep displaying later reconciliation and conflict changes.
      }
    } catch (error) {
      onError(error);
    } finally {
      running = false;
      if (!stopped) timer = setTimer(poll, delay);
    }
  }

  return {
    start() { stopped = false; return poll(); },
    wake() { return poll(); },
    stop() { stopped = true; clearTimer(timer); },
  };
}

if (typeof module !== 'undefined') module.exports = { createResultPoller };

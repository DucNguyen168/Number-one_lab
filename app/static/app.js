/* ============================================================
   XSMB Research Lab — app.js
   ============================================================ */

// ── State ──────────────────────────────────────────────────
const state = {
  currentPage: 'overview',
  latestPrediction: null,
  latestLogisticPrediction: null,
  latestDigitPrediction: null,
  latestCatBoostPrediction: null,
  toastTimer: null,
  currentTab: 'all',       // 'all' | 'selected' | 'excluded'
  currentSort: 'rank',     // 'rank' | 'number' | 'days'
  countdownTimer: null,
  autoRefreshTimer: null,
  resultPoller: null,
  smartRefreshSeenDate: null, // Ngày kết quả đã phát hiện
  smartRefreshSignature: null,
  smartRefreshAt: 0,
  detailCache: new Map(),
  // Exclude recent numbers feature
  excludeRecentEnabled: false,
  excludeRecentDays: 3,
  recentNumbers: [],       // Array of { draw_date, last_two }
  fortuneFilter: 'all',
  fortuneExcludeRecentEnabled: false,
  fortuneExcludeRecentDays: 3,
  fortuneRecentNumbers: [],  // Array of { draw_date, last_two }
  catboostFilter: 'all',
  catboostExcludeRecent: false,
  catboostRecentNumbers: [],
  automation: null,
  refreshVersion: 0,
  pendingReads: new Map(),
  pageUpdatedAt: new Map(),
  detailRequest: 0,
  detailId: null,
  resultsRows: [],
  resultsHasMore: false,
  resultsTask: null,
};

// ── Helpers ────────────────────────────────────────────────
const el = (id) => document.getElementById(id);

const formatPercent = (value, digits = 2) =>
  value === null || value === undefined ? '—' : `${(value * 100).toFixed(digits)}%`;

const formatMoney = (value) =>
  value === null || value === undefined ? '—' : `${(value / 1_000_000).toFixed(2)}M ₫`;

const formatDateTime = (value) =>
  value ? new Date(value).toLocaleString('vi-VN', { hour12: false }) : '—';

const PAGE_CONFIG = {
  overview: {
    path: '/',
    eyebrow: 'OVERVIEW',
    title: 'Tổng quan hệ thống',
    description: 'Theo dõi trạng thái dữ liệu, dự đoán và kết quả mới nhất.',
  },
  results: {
    path: '/ket-qua',
    eyebrow: 'BỘ SƯU TẬP DỮ LIỆU',
    title: 'Phòng lưu trữ kết quả',
    description: 'Tra cứu kết quả XSMB, kiểm chứng nguồn và cập nhật lịch sử kỳ quay.',
  },
  'two-digit': {
    path: '/du-doan-n-1',
    eyebrow: 'N-1 TERMINAL · MÔ HÌNH A',
    title: 'Dự đoán N-1',
    description: 'Phân tích tần suất, theo dõi thứ hạng và đối chiếu kết quả trên cùng một bảng điện.',
  },
  'fortune-two-digit': {
    path: '/du-doan-than-tai',
    eyebrow: 'FORTUNE MODEL · 00–99',
    title: 'Dự đoán Thần Tài',
    description: 'Mô hình Logistic độc lập để kiểm chứng chéo với mô hình tần suất bằng kết quả thực.',
  },
  'one-digit': {
    path: '/du-doan-catboost-2-so',
    eyebrow: 'MODEL C · CATBOOST 00–99',
    title: 'Dự đoán CatBoost hai số cuối',
    description: 'Mô hình cây tăng cường đa lớp để kiểm chứng chéo Tần suất A và Logistic B.',
  },
  backtest: {
    path: '/backtest',
    eyebrow: 'WALK-FORWARD',
    title: 'Kiểm chứng mô hình',
    description: 'Đánh giá hai mô hình bằng dữ liệu quá khứ và so sánh với baseline ngẫu nhiên.',
  },
};

function pageFromPath(pathname) {
  const normalized = pathname !== '/' ? pathname.replace(/\/+$/, '') : '/';
  if (normalized === '/du-doan-2-so') return 'two-digit';
  return Object.entries(PAGE_CONFIG).find(([, config]) => config.path === normalized)?.[0] || 'overview';
}

function showPage(pageName, { updateHistory = false } = {}) {
  const page = PAGE_CONFIG[pageName] ? pageName : 'overview';
  const config = PAGE_CONFIG[page];
  state.currentPage = page;
  document.body.dataset.currentPage = page;
  if (updateHistory && window.location.pathname !== config.path) {
    window.history.replaceState({ ...window.history.state, scrollY: window.scrollY }, '', window.location.href);
    window.history.pushState({ page }, '', config.path);
  }

  document.querySelectorAll('[data-page-view]').forEach(section => {
    section.classList.toggle('is-active', section.dataset.pageView === page);
  });
  document.querySelectorAll('[data-page-link]').forEach(link => {
    const active = link.dataset.pageLink === page;
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });

  el('page-eyebrow').textContent = config.eyebrow;
  el('page-title').textContent = config.title;
  el('page-description').textContent = config.description;
  document.title = `${config.title} · XSMB Research Lab`;
  el('page-feedback').hidden = true;
  el('page-announcement').textContent = config.title;
  updatePageStatus(page);
}

function initPageNavigation() {
  showPage(pageFromPath(window.location.pathname));
  window.history.scrollRestoration = 'manual';
  let scrollFrame;
  window.addEventListener('scroll', () => {
    if (scrollFrame) return;
    scrollFrame = requestAnimationFrame(() => {
      window.history.replaceState({ ...window.history.state, scrollY: window.scrollY }, '', window.location.href);
      scrollFrame = null;
    });
  }, { passive: true });
  document.querySelectorAll('[data-page-link], [data-route]').forEach(link => {
    link.addEventListener('click', event => {
      if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      const page = link.dataset.pageLink || link.dataset.route;
      if (page === state.currentPage) return;
      showPage(page, { updateHistory: true });
      window.scrollTo({ top: 0, behavior: 'instant' });
      window.DashboardUI.transitionPage();
      el('page-title').focus({ preventScroll: true });
      refreshDashboard();
    });
  });
  window.addEventListener('popstate', event => {
    showPage(pageFromPath(window.location.pathname));
    window.DashboardUI.transitionPage();
    window.scrollTo({ top: event.state?.scrollY || 0, behavior: 'instant' });
    el('page-title').focus({ preventScroll: true });
    refreshDashboard();
  });
}

async function api(path, options = {}) {
  const isRead = !options.method || options.method.toUpperCase() === 'GET';
  const key = `${path}:${JSON.stringify(options)}`;
  if (isRead && state.pendingReads.has(key)) return state.pendingReads.get(key);
  const request = (async () => {
    const controller = isRead ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), 25000) : null;
    try {
      const response = await fetch(path, {
        ...options,
        ...(controller ? { signal: controller.signal } : {}),
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      });
      const data = await response.json().catch(error => {
        if (error.name === 'AbortError') throw error;
        if (response.ok) throw new Error('Phản hồi dữ liệu không hợp lệ. Vui lòng thử lại.');
        return {};
      });
      if (!response.ok) {
        throw new Error(data.detail || data.sync_error || data.catboost_prediction_error
          || data.logistic_prediction_error || data.prediction_error || `HTTP ${response.status}`);
      }
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('Kết nối quá thời gian. Vui lòng thử lại.');
      throw error;
    } finally {
      if (timer) clearTimeout(timer);
    }
  })();
  if (isRead) state.pendingReads.set(key, request);
  try { return await request; }
  finally { if (isRead) state.pendingReads.delete(key); }
}

function openAutomationDialog() {
  el('automation-message').textContent = '';
  window.DashboardUI.openDialog(el('automation-dialog'));
  loadHealth().catch(error => { el('automation-message').textContent = error.message; });
}

function renderAutomationStatus(health) {
  const automation = health.automation;
  state.automation = automation;
  const pill = el('scheduler-pill');
  if (!automation) {
    pill.textContent = health.automation_mode === 'vercel_cron' ? 'Vercel Cron' : health.scheduler_enabled ? 'Scheduler bật' : 'Scheduler tắt';
    pill.className = 'pill neutral';
    return;
  }
  const vercel = automation.mode === 'vercel_cron';
  const failed = ['failed', 'partial_failure', 'source_failed', 'interrupted'].includes(automation.last_run?.status);
  pill.textContent = !automation.configured ? 'Scheduler tắt'
    : !automation.auto_prediction ? 'Tự tạo đang tắt' : failed ? 'Tự động: có lỗi'
      : vercel ? 'Vercel Cron' : 'Scheduler bật';
  pill.className = `pill ${!automation.configured || failed ? 'error' : 'neutral'}`;
  let note = vercel
    ? 'Vercel Cron chạy theo lịch của bản Production. Kiểm tra Settings → Cron Jobs nếu chưa có lượt chạy.'
    : automation.configured ? 'Scheduler đang chạy trên máy chủ.' : 'Scheduler chưa bật trên máy chủ.';
  if (!automation.auto_prediction) note += ' AUTO_PREDICTION đang tắt.';
  if (automation.last_run) {
    const labels = { completed: 'hoàn tất', running: 'đang chạy', interrupted: 'bị gián đoạn hoặc quá thời gian',
      failed: 'thất bại', partial_failure: 'có mô hình lỗi', source_failed: 'lỗi nguồn kết quả',
      waiting_result: 'đang chờ kết quả', disabled: 'tự tạo đang tắt' };
    const run = automation.last_run;
    note += ` Lượt gần nhất (${['manual', 'admin'].includes(run.trigger) ? 'chạy bù thủ công' : 'Cron'}): ${labels[run.status] || run.status}, ${formatDateTime(run.started_at)}.`;
  } else if (vercel) note += ' Chưa ghi nhận lượt Cron hoặc chạy bù trong phiên bản này.';
  el('automation-status').textContent = note;
  pill.title = note;
}

// ── Toast ─────────────────────────────────────────────────
function toast(message, type = 'default') {
  const node = el('toast');
  node.textContent = message;
  node.className = `toast visible${type !== 'default' ? ' ' + type : ''}`;
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => { node.className = 'toast'; }, 4500);
}

// ── Button busy state ──────────────────────────────────────
function setBusy(button, busy, label) {
  if (!button.dataset.label) button.dataset.label = button.innerHTML;
  button.disabled = busy;
  if (busy) button.textContent = label;
  else button.innerHTML = button.dataset.label;
}

// ── Badge & Cell helpers ───────────────────────────────────
function badge(label, kind) {
  const span = document.createElement('span');
  span.className = `badge ${kind}`;
  span.textContent = label;
  return span;
}

function cell(text) {
  const td = document.createElement('td');
  td.textContent = text ?? '—';
  return td;
}

function predictionDateCell(prediction) {
  const node = cell(prediction.prediction_date);
  if (prediction.prediction_kind === 'retrospective') {
    node.append(badge('HỒI KIỂM', 'pending'));
    node.title = 'Tạo sau kết quả, chỉ huấn luyện dữ liệu trước ngày này; không tính vào tỷ lệ dự đoán trực tiếp.';
  }
  return node;
}

// Theme preference is applied before paint. Storage failures never stop boot.
function initThemeToggle() {
  const toggle = el('sky-toggle');
  applyTheme(document.documentElement.dataset.theme || 'light', false);
  toggle.addEventListener('click', () => {
    applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
  });
}

function applyTheme(theme, persist = true) {
  document.documentElement.dataset.theme = theme;
  document.body.dataset.theme = theme;
  if (persist) {
    try { localStorage.setItem('xsmb-theme', theme); } catch { /* Storage is optional. */ }
  }
  const dark = theme === 'dark';
  el('sky-toggle').setAttribute('aria-pressed', String(dark));
  el('sky-toggle').setAttribute('aria-label', dark ? 'Chuyển sang chế độ sáng' : 'Chuyển sang chế độ tối');
  document.querySelector('meta[name="theme-color"]').content = dark ? '#101722' : '#f5f7fb';
}

function startCountdown() {
  function tick() {
    const now = new Date();
    // Giờ quay XSMB MB: 18:10 (thực tế hay đổi, để 18:15 cho an toàn)
    const target = new Date(now);
    target.setHours(18, 15, 0, 0);
    if (now >= target) target.setDate(target.getDate() + 1);

    const diff = target - now;
    const h = Math.floor(diff / 3_600_000);
    const m = Math.floor((diff % 3_600_000) / 60_000);
    const s = Math.floor((diff % 60_000) / 1_000);

    el('countdown-time').textContent =
      `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;

    const isToday = now.getDate() === target.getDate() - (now >= target ? 0 : 0);
    if (h === 0 && m < 30) {
      el('countdown-status').textContent = '⚡ Còn ít hơn 30 phút — Hãy tạo dự đoán ngay!';
      el('countdown-bar').style.background = 'linear-gradient(135deg, #dc2626, #f59e0b)';
    } else if (now.getHours() >= 18 && now.getHours() < 19) {
      el('countdown-status').textContent = '🔴 Đang trong giờ quay — KHÔNG tạo dự đoán cho hôm nay';
      el('countdown-bar').style.background = 'linear-gradient(135deg, #b91c1c, #991b1b)';
    } else {
      el('countdown-status').textContent = 'Dự đoán an toàn trước 18:00 (giờ Việt Nam)';
      el('countdown-bar').style.background = '';
    }
  }
  tick();
  state.countdownTimer = setInterval(tick, 1000);
}

// ═══════════════════════════════════════════════════════════
// HEALTH
// ═══════════════════════════════════════════════════════════
async function loadHealth() {
  try {
    const health = await api('/api/health', { cache: 'no-store' });
    el('health-pill').textContent = `MongoDB · ${health.status}`;
    el('health-pill').className = 'pill ok';
    renderAutomationStatus(health);
  } catch (error) {
    el('health-pill').textContent = 'Mất kết nối';
    el('health-pill').className = 'pill error';
    // Không throw — cho phép trang load tiếp
    console.error('Health check failed:', error);
  }
}

// ═══════════════════════════════════════════════════════════
// METRICS
// ═══════════════════════════════════════════════════════════
async function loadMetrics() {
  const metrics = await api('/api/metrics/summary');
  el('metric-draws').textContent = metrics.draws.toLocaleString('vi-VN');
  el('metric-predictions').textContent = metrics.predictions.toLocaleString('vi-VN');
  el('metric-conflicts').textContent = metrics.conflicts.toLocaleString('vi-VN');

  // Hit rate display
  if (metrics.evaluated) {
    el('metric-hit-rate').textContent = formatPercent(metrics.hit_rate);
    el('metric-evaluated').textContent =
      `${metrics.hits} HIT / ${metrics.misses} MISS (${metrics.evaluated} kỳ)`;
  } else {
    el('metric-hit-rate').textContent = '—';
    el('metric-evaluated').textContent = 'Chưa đủ dữ liệu live';
  }

  el('metric-latest-draw').textContent = metrics.latest_draw_date
    ? `Mới nhất: ${metrics.latest_draw_date}` : 'Chưa có dữ liệu';
  el('metric-latest-prediction').textContent = metrics.latest_prediction_date
    ? `Gần nhất: ${metrics.latest_prediction_date}` : 'Chưa có dự đoán';
}

// ═══════════════════════════════════════════════════════════
// LATEST RESULT
// ═══════════════════════════════════════════════════════════
async function loadLatestResult() {
  const result = await api('/api/results/latest', { cache: 'no-store' });
  renderLatestResult(result);
}

function renderLatestResult(result) {
  const root = el('latest-result');
  root.replaceChildren();
  if (!result) {
    root.className = 'empty-state';
    root.textContent = 'Chưa có kết quả. Hãy chạy backfill.';
    return;
  }
  root.className = 'latest-result-card';

  const left = document.createElement('div');
  const dateNode = document.createElement('div');
  dateNode.className = 'result-date';
  dateNode.textContent = result.draw_date;
  const statusBadge = badge(result.status, result.status === 'conflict' ? 'conflict' : 'observed');
  left.append(dateNode, statusBadge);
  const updated = document.createElement('div');
  updated.className = 'result-date';
  updated.textContent = `Cập nhật: ${formatDateTime(result.updated_at || result.created_at)}`;
  left.append(updated);

  const number = document.createElement('div');
  number.className = 'result-number';
  number.append(document.createTextNode(result.special_prize.slice(0, 3)));
  const tail = document.createElement('b');
  tail.textContent = result.last_two;
  number.append(tail);

  root.append(left, number);
}

// ═══════════════════════════════════════════════════════════
// NUMBER GRID — Render theo tab & sort
// ═══════════════════════════════════════════════════════════
function getExcludeReason(score, cutoffProbability, recentWindowDays) {
  const reasons = [];
  const prob = score.probability;

  if (score.recent_hit) {
    reasons.push(`⚠️ Vừa ra trong ${recentWindowDays || 3} ngày qua`);
  }
  if (score.days_since_last_hit === null) {
    reasons.push('📉 Chưa bao giờ xuất hiện trong lịch sử');
  } else if (score.days_since_last_hit > 180) {
    reasons.push(`📅 Lần xuất hiện gần nhất cách ngày dự đoán ${score.days_since_last_hit} ngày`);
  }
  if (cutoffProbability && prob < cutoffProbability) {
    const pct = (prob * 100).toFixed(4);
    const cutPct = (cutoffProbability * 100).toFixed(4);
    reasons.push(`📊 Điểm ${pct}% < ngưỡng cut-off ${cutPct}%`);
  }
  if (reasons.length === 0) {
    reasons.push(`Rank #${score.rank}/100 — dưới ngưỡng chọn`);
  }
  return reasons;
}

// ── Exclude Recent Numbers Helpers ─────────────────────────
async function loadRecentNumbers(days) {
  try {
    const data = await api(`/api/results/recent-last-two?days=${days}`);
    state.recentNumbers = data.results || [];
    return state.recentNumbers;
  } catch (err) {
    console.warn('Không tải được recent numbers:', err);
    state.recentNumbers = [];
    return [];
  }
}

function getExcludedRecentSet() {
  return new Set(state.recentNumbers.map(r => r.last_two));
}

function updateExcludeRecentChips() {
  const chipsEl = el('excluded-recent-chips');
  const legendEl = el('legend-excluded-recent');
  chipsEl.replaceChildren();

  if (!state.excludeRecentEnabled || state.recentNumbers.length === 0) {
    chipsEl.style.display = 'none';
    if (legendEl) legendEl.style.display = 'none';
    return;
  }

  chipsEl.style.display = 'flex';
  if (legendEl) legendEl.style.display = '';

  // Label
  const label = document.createElement('span');
  label.style.cssText = 'font-size:0.68rem;font-weight:700;color:var(--muted);white-space:nowrap;';
  label.textContent = 'Loại:';
  chipsEl.append(label);

  state.recentNumbers.forEach(({ draw_date, last_two }) => {
    const chip = document.createElement('div');
    chip.className = 'excluded-recent-chip';
    const num = document.createElement('span');
    num.textContent = last_two;
    const date = document.createElement('span');
    date.className = 'excluded-recent-chip-date';
    date.textContent = draw_date;
    chip.append(num, date);
    chip.title = `Số ${last_two} đã trúng ngày ${draw_date}`;
    chipsEl.append(chip);
  });
}

function renderNumberGrid(prediction) {
  const root = el('number-grid');
  const excludedPanel = el('excluded-panel');

  root.replaceChildren();
  excludedPanel.replaceChildren();

  if (!prediction) {
    root.innerHTML = '<div class="empty-state" style="grid-column:1/-1">Chưa có dự đoán N-1. Chọn số lượng ở phía trên để bắt đầu.</div>';
    return;
  }

  const selected = new Set(prediction.numbers || []);
  const actual = prediction.evaluation?.actual_last_two;
  const scores = prediction.scores || [];
  const cutoff = prediction.cutoff_probability;
  const recentWindow = prediction.recent_hit_window_days || 3;

  // Update cutoff info
  el('cutoff-info').innerHTML = cutoff
    ? `Ngưỡng cut-off: <strong>${(cutoff * 100).toFixed(4)}%</strong>`
    : '';

  // Update tab counts
  el('tab-selected-count').textContent = selected.size;
  el('tab-excluded-count').textContent = 100 - selected.size;

  // Sort scores
  let sortedScores = [...scores];
  if (state.currentSort === 'rank') {
    sortedScores.sort((a, b) => a.rank - b.rank);
  } else if (state.currentSort === 'number') {
    sortedScores.sort((a, b) => a.number.localeCompare(b.number));
  } else if (state.currentSort === 'days') {
    // Gan cao nhất (nhiều ngày) lên đầu, null xuống cuối
    sortedScores.sort((a, b) => {
      if (a.days_since_last_hit === null && b.days_since_last_hit === null) return 0;
      if (a.days_since_last_hit === null) return 1;
      if (b.days_since_last_hit === null) return -1;
      return b.days_since_last_hit - a.days_since_last_hit;
    });
  }

  const tab = state.currentTab;
  const excludedRecentSet = state.excludeRecentEnabled ? getExcludedRecentSet() : new Set();

  // ── Build Grid (tab: all / selected) ──
  if (tab !== 'excluded') {
    root.style.display = 'grid';
    excludedPanel.style.display = 'none';

    // Nếu tab = selected, chỉ vẽ số trong selected set
    const displayScores = tab === 'selected'
      ? sortedScores.filter(s => selected.has(s.number))
      : sortedScores;

    for (const score of displayScores) {
      const number = score.number;
      const isSelected = selected.has(number);
      const isActual = actual === number;
      const isHit = isSelected && isActual;
      const isExcludedByRecent = excludedRecentSet.has(number);

      const node = document.createElement('div');
      node.setAttribute('role', 'gridcell');
      node.setAttribute('tabindex', '0');

      const classes = ['number-cell'];
      if (isSelected) classes.push('selected');
      if (isActual) classes.push('actual');
      if (score.recent_hit) classes.push('recent-hit');
      if (isExcludedByRecent && state.excludeRecentEnabled) classes.push('excluded-by-recent');
      node.className = classes.join(' ');

      // Số hiển thị
      const numSpan = document.createElement('span');
      numSpan.className = 'cell-num';
      numSpan.textContent = number;
      node.append(numSpan);

      // Rank hiển thị trực tiếp
      const rankSpan = document.createElement('span');
      rankSpan.className = 'cell-rank';
      rankSpan.textContent = `#${score.rank}`;
      node.append(rankSpan);

      // Indicator vừa ra
      if (score.recent_hit) {
        const dot = document.createElement('span');
        dot.className = 'recent-dot';
        dot.title = `Số này đã ra trong ${recentWindow} ngày qua`;
        node.append(dot);
      }

      // Tooltip chi tiết
      const daysText = score.days_since_last_hit !== null
        ? `${score.days_since_last_hit} ngày trước` : 'Chưa bao giờ ra';
      const recentText = score.recent_hit ? `\n⚠️ Vừa ra trong ${recentWindow} ngày` : '';
      const excludedText = isExcludedByRecent && state.excludeRecentEnabled
        ? `\n🚫 Bị loại: đã trúng trong ${state.excludeRecentDays} ngày gần nhất` : '';
      node.title = [
        `Số ${number} — Rank #${score.rank}`,
        `Xác suất: ${(score.probability * 100).toFixed(4)}%`,
        `Lần cuối ra: ${daysText}`,
        recentText,
        excludedText,
        isHit ? '✅ HIT!' : isActual ? '🎯 Kết quả thực tế (MISS)' : '',
      ].filter(Boolean).join('\n');

      root.appendChild(node);
    }

    // Grid template responsive theo số items
    if (tab === 'selected' && displayScores.length <= 65) {
      root.style.gridTemplateColumns = 'repeat(10, 1fr)';
    } else {
      root.style.gridTemplateColumns = '';
    }

  } else {
    // ── Build Excluded panel ──
    root.style.display = 'none';
    excludedPanel.style.display = 'grid';

    const excludedScores = sortedScores.filter(s => !selected.has(s.number));

    for (const score of excludedScores) {
      const reasons = getExcludeReason(score, cutoff, recentWindow);

      const row = document.createElement('div');
      row.className = 'excluded-row';

      const numEl = document.createElement('div');
      numEl.className = 'excluded-num';
      numEl.textContent = score.number;

      const info = document.createElement('div');
      info.className = 'excluded-info';

      const reasonEl = document.createElement('div');
      reasonEl.className = 'excluded-reason';
      reasonEl.textContent = reasons[0];

      const detailEl = document.createElement('div');
      detailEl.className = 'excluded-detail';
      const daysText = score.days_since_last_hit !== null
        ? `Lần cuối: ${score.days_since_last_hit} ngày trước` : 'Chưa xuất hiện trong lịch sử';
      detailEl.textContent = `${(score.probability * 100).toFixed(4)}% · ${daysText}`;

      const rankEl = document.createElement('span');
      rankEl.className = 'excluded-rank';
      rankEl.textContent = `#${score.rank}`;

      if (reasons.length > 1) {
        reasons.slice(1).forEach(r => {
          const extra = document.createElement('div');
          extra.className = 'excluded-detail';
          extra.textContent = r;
          info.append(extra);
        });
      }

      info.prepend(reasonEl, detailEl);
      row.append(numEl, info, rankEl);
      excludedPanel.append(row);
    }
  }
}

// ═══════════════════════════════════════════════════════════
// EXPORT / COPY — Xuất dãy số đã chọn
// ═══════════════════════════════════════════════════════════
function updateSelectedExport(prediction) {
  const exportBar = el('export-bar');
  const exportStr = el('export-number-string');
  if (!prediction || !prediction.numbers || prediction.numbers.length === 0) {
    if (exportBar) exportBar.style.display = 'none';
    return;
  }

  // Lấy scores đã sắp xếp theo rank để lọc top N chính xác
  const scores = prediction.scores || [];
  const selected = new Set(prediction.numbers);

  // Lấy tập số đang bị loại bởi exclude-recent toggle
  const excludedByRecent = state.excludeRecentEnabled ? getExcludedRecentSet() : new Set();

  // Số đã chọn, chưa bị loại, sắp theo rank
  const selectedByRank = scores
    .filter(s => selected.has(s.number) && !excludedByRecent.has(s.number))
    .sort((a, b) => a.rank - b.rank);

  // Đọc top N từ select
  const topSelect = el('export-top-select');
  const topVal = topSelect ? topSelect.value : 'all';
  const limit = topVal === 'all' ? selectedByRank.length : parseInt(topVal, 10);
  const toExport = selectedByRank.slice(0, limit);

  const count = toExport.length;
  const excluded = excludedByRecent.size;
  exportStr.textContent = count > 0 ? toExport.map(s => s.number).join(',') : '—';

  // Cập nhật label số lượng
  const countLabel = el('export-count-label');
  if (countLabel) {
    countLabel.textContent = excluded > 0
      ? `${count} số (đã bỏ ${excluded} bị loại)`
      : `${count} số`;
  }

  if (exportBar) exportBar.style.display = '';
}

function initExportBar() {
  const topSelect = el('export-top-select');
  const copyBtn = el('copy-selected-btn');
  const exportStr = el('export-number-string');

  if (topSelect) {
    topSelect.addEventListener('change', () => {
      updateSelectedExport(state.latestPrediction);
    });
  }

  if (copyBtn) {
    copyBtn.addEventListener('click', async () => {
      const text = exportStr ? exportStr.textContent : '';
      if (!text || text === '—') return;
      try {
        await navigator.clipboard.writeText(text);
        const origHTML = copyBtn.innerHTML;
        copyBtn.innerHTML = '<span class="copy-btn-icon">✓</span> Đã copy!';
        copyBtn.classList.add('copy-success');
        setTimeout(() => {
          copyBtn.innerHTML = origHTML;
          copyBtn.classList.remove('copy-success');
        }, 1800);
        toast(`✅ Đã copy ${text.split(',').length} số vào clipboard!`, 'success');
      } catch {
        // Fallback cho trình duyệt không hỗ trợ clipboard API
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.cssText = 'position:fixed;opacity:0;';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        toast(`✅ Đã copy ${text.split(',').length} số vào clipboard!`, 'success');
      }
    });
  }
}

// ═══════════════════════════════════════════════════════════
// LATEST PREDICTION
// ═══════════════════════════════════════════════════════════
async function loadLatestPrediction() {
  const prediction = await api('/api/predictions/latest');
  state.latestPrediction = prediction;
  renderNumberGrid(prediction);
  updateSelectedExport(prediction);

  const meta = el('prediction-meta');
  meta.replaceChildren();

  if (!prediction) {
    const note = document.createElement('span');
    note.textContent = 'Chưa có prediction';
    note.className = 'meta-chip';
    meta.append(note);
    return;
  }

  const evalStatus = prediction.evaluation?.status;
  const hit = prediction.evaluation?.hit;

  const chips = [
    { text: `📅 ${prediction.prediction_date}`, cls: '' },
    { text: `Top ${prediction.selected_count}`, cls: '' },
    { text: `Train đến ${prediction.trained_through}`, cls: '' },
    { text: `Coverage ${formatPercent(prediction.coverage_probability)}`, cls: '' },
  ];

  if (evalStatus === 'evaluated') {
    chips.push({ text: hit ? '✅ HIT' : '❌ MISS', cls: hit ? 'hit-chip' : 'miss-chip' });
    if (prediction.evaluation?.actual_last_two) {
      chips.push({ text: `Kết quả: ${prediction.evaluation.actual_last_two}`, cls: '' });
    }
  } else {
    chips.push({ text: evalStatus === 'invalidated' ? '⚠️ Kết quả cần xác minh' : '⏳ PENDING', cls: 'pending-chip' });
  }

  chips.forEach(({ text, cls }) => {
    const node = document.createElement('span');
    node.className = `meta-chip ${cls}`.trim();
    node.textContent = text;
    meta.append(node);
  });
}

// ═══════════════════════════════════════════════════════════
// FACTORIZED LOGISTIC — TRANG THẦN TÀI
// ═══════════════════════════════════════════════════════════
function renderFortunePrediction(prediction) {
  const grid = el('fortune-number-grid');
  const meta = el('fortune-prediction-meta');
  const exportBox = el('fortune-export');
  grid.replaceChildren();
  meta.replaceChildren();

  if (!prediction) {
    exportBox.hidden = true;
    const empty = document.createElement('div');
    empty.className = 'fortune-empty';
    empty.textContent = 'Chưa có dự đoán Logistic cho lựa chọn này.';
    grid.append(empty);
    return;
  }

  const evaluation = prediction.evaluation || { status: 'pending' };
  const selected = new Set(prediction.numbers || []);
  const actual = evaluation.actual_last_two;
  const chips = [
    `📅 ${prediction.prediction_date}`,
    `Top ${prediction.selected_count}`,
    `Train đến ${prediction.trained_through}`,
    `Coverage ${formatPercent(prediction.coverage_probability)}`,
    evaluation.status === 'evaluated'
      ? (evaluation.hit ? '✅ HIT' : '❌ MISS')
      : evaluation.status === 'invalidated' ? '⚠️ Kết quả cần xác minh' : '⏳ PENDING',
  ];
  if (actual) chips.push(`Kết quả ${actual}`);
  chips.forEach((text) => {
    const chip = document.createElement('span');
    chip.className = 'fortune-meta-chip';
    chip.textContent = text;
    meta.append(chip);
  });

  const fortuneExcludedSet = getFortuneExcludedRecentSet();

  const scores = [...(prediction.scores || [])]
    .sort((a, b) => a.rank - b.rank)
    .filter((score) => {
      const isExcludedByRecent = fortuneExcludedSet.has(score.number);
      if (state.fortuneFilter === 'selected') {
        return selected.has(score.number) && !isExcludedByRecent;
      }
      if (state.fortuneFilter === 'excluded') {
        return !selected.has(score.number) || isExcludedByRecent;
      }
      return true;
    });

  scores.forEach((score) => {
    const isSelected = selected.has(score.number);
    const isActual = actual === score.number;
    const node = document.createElement('div');
    const isExcluded = fortuneExcludedSet.has(score.number);
    node.className = `fortune-number${isSelected ? ' selected' : ''}${isActual ? ' actual' : ''}${isSelected && evaluation.hit && isActual ? ' hit' : ''}${isExcluded ? ' excluded-recent' : ''}`;
    node.setAttribute('role', 'gridcell');
    const number = document.createElement('strong');
    number.textContent = score.number;
    const probability = document.createElement('span');
    probability.textContent = formatPercent(score.probability, 3);
    const rank = document.createElement('small');
    rank.textContent = `#${score.rank}`;
    node.append(number, probability, rank);
    node.title = isExcluded
      ? `Số ${score.number} · rank #${score.rank} · đã bị loại vì xuất hiện trong ${state.fortuneExcludeRecentDays} kỳ gần nhất`
      : `Số ${score.number} · rank #${score.rank} · điểm ${formatPercent(score.probability, 4)}`;
    grid.append(node);
  });

  updateFortuneRippleDelays();

  const selectedScores = [...(prediction.scores || [])]
    .filter(score => selected.has(score.number) && !fortuneExcludedSet.has(score.number))
    .sort((a, b) => a.rank - b.rank);
  const removedSelectedCount = [...selected].filter(number => fortuneExcludedSet.has(number)).length;
  el('fortune-export-string').textContent = selectedScores.map(score => score.number).join(',');
  el('fortune-export-count').textContent = removedSelectedCount > 0
    ? `${selectedScores.length} số · đã loại ${removedSelectedCount} số vừa ra`
    : `${selectedScores.length} số`;
  exportBox.hidden = false;
}

function updateFortuneRippleDelays() {
  const grid = el('fortune-number-grid');
  if (!grid || !grid.children.length) return;

  const renderedColumns = getComputedStyle(grid).gridTemplateColumns
    .split(' ')
    .filter(Boolean).length || 1;
  const cells = [...grid.querySelectorAll('.fortune-number')];
  const rows = Math.ceil(cells.length / renderedColumns);
  const centerColumn = (renderedColumns - 1) / 2;
  const centerRow = (rows - 1) / 2;

  cells.forEach((cell, index) => {
    const column = index % renderedColumns;
    const row = Math.floor(index / renderedColumns);
    const distance = Math.hypot(column - centerColumn, row - centerRow);
    cell.style.setProperty('--fortune-ripple-delay', `${(distance * 0.105).toFixed(3)}s`);
  });
}

function initFortuneGlitter() {
  // Model skins may opt in; the workspace keeps data unobstructed.
}

async function loadLatestLogisticPrediction() {
  const selectedCount = Number(el('fortune-selected-count').value);
  const prediction = await api(`/api/logistic-predictions/latest?selected_count=${selectedCount}`);
  state.latestLogisticPrediction = prediction;
  renderFortunePrediction(prediction);
}

async function loadLogisticPredictionHistory() {
  const predictions = await api('/api/logistic-predictions?limit=50');
  const body = el('fortune-prediction-history');
  body.replaceChildren();
  if (!predictions.length) {
    const row = document.createElement('tr');
    const td = cell('Chưa có dự đoán Logistic');
    td.colSpan = 6;
    td.style.textAlign = 'center';
    row.append(td);
    body.append(row);
    return;
  }
  predictions.forEach((prediction) => {
    const evaluation = prediction.evaluation || { status: 'pending' };
    const row = document.createElement('tr');
    row.append(
      predictionDateCell(prediction),
      cell(prediction.selected_count),
      cell(prediction.trained_through),
      cell(evaluation.actual_last_two || '—'),
    );
    const status = document.createElement('td');
    status.append(evaluation.status === 'evaluated'
      ? badge(evaluation.hit ? 'HIT' : 'MISS', evaluation.hit ? 'hit' : 'miss')
      : badge(evaluation.status === 'invalidated' ? 'CẦN ĐỐI CHIẾU LẠI' : 'PENDING', 'pending'));
    row.append(status);
    const action = document.createElement('td');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'fortune-detail-button';
    button.textContent = 'Xem chi tiết';
    button.addEventListener('click', () => openPredictionDetail(prediction._id));
    action.append(button);
    row.append(action);
    body.append(row);
  });
}

function comparisonCard(label, value, detail = '') {
  const card = document.createElement('article');
  card.className = 'fortune-comparison-card';
  const caption = document.createElement('span');
  caption.textContent = label;
  const strong = document.createElement('strong');
  strong.textContent = value;
  const small = document.createElement('small');
  small.textContent = detail;
  card.append(caption, strong, small);
  return card;
}

function comparisonModelDetail(model, total) {
  const ci = model?.confidence_interval_95;
  const interval = Array.isArray(ci)
    ? `CI 95% ${formatPercent(ci[0])} – ${formatPercent(ci[1])}`
    : 'Chưa có khoảng tin cậy';
  return `${model?.hits || 0}/${total} HIT · ${interval}`;
}

async function loadModelComparison() {
  const selectedCount = Number(el('fortune-selected-count').value);
  const comparison = await api(`/api/model-comparison?selected_count=${selectedCount}`);
  const root = el('fortune-comparison-summary');
  root.replaceChildren(
    comparisonCard('Kỳ ghép cặp', comparison.paired_predictions, `Top ${selectedCount}`),
    comparisonCard('Mô hình tần suất', formatPercent(comparison.frequency_model.hit_rate), comparisonModelDetail(comparison.frequency_model, comparison.paired_predictions)),
    comparisonCard('Mô hình Logistic', formatPercent(comparison.logistic_model.hit_rate), comparisonModelDetail(comparison.logistic_model, comparison.paired_predictions)),
    comparisonCard('Chênh lệch B − A', formatPercent(comparison.lift_logistic_vs_frequency), `Baseline ${formatPercent(comparison.baseline, 0)} · McNemar p=${comparison.mcnemar_exact_p ?? '—'}`),
  );
  const note = el('fortune-comparison-note');
  if (note) note.textContent = comparison.note;

  const body = el('fortune-comparison-history');
  body.replaceChildren();
  if (!comparison.recent_pairs.length) {
    const row = document.createElement('tr');
    const td = cell('Chưa có đủ cặp dự đoán đã đối chiếu');
    td.colSpan = 4;
    td.style.textAlign = 'center';
    row.append(td);
    body.append(row);
    return;
  }
  comparison.recent_pairs.forEach((pair) => {
    const row = document.createElement('tr');
    row.append(cell(pair.prediction_date), cell(pair.actual_last_two));
    const frequency = document.createElement('td');
    frequency.append(badge(pair.frequency_hit ? 'HIT' : 'MISS', pair.frequency_hit ? 'hit' : 'miss'));
    const logistic = document.createElement('td');
    logistic.append(badge(pair.logistic_hit ? 'HIT' : 'MISS', pair.logistic_hit ? 'hit' : 'miss'));
    row.append(frequency, logistic);
    body.append(row);
  });
}

// ═══════════════════════════════════════════════════════════
// BÁO CÁO ROLLING 365 KỲ — hai mô hình cùng cutoff mỗi ngày
// ═══════════════════════════════════════════════════════════
async function loadRollingModelComparison() {
  const selectedCount = Number(el('fortune-selected-count').value);
  try {
    const report = await api(`/api/model-comparison/rolling?selected_count=${selectedCount}`);
    if (report.status === 'not_ready') {
      el('fortune-historical-title').textContent = 'Chưa có báo cáo rolling cập nhật';
      el('fortune-historical-note').textContent = report.message;
      el('fortune-historical-summary').replaceChildren();
      el('fortune-historical-daily-body').replaceChildren();
      el('fortune-historical-daily-stats').replaceChildren();
      el('fortune-rolling-window-badge').textContent = 'Chờ báo cáo';
      return;
    }
    const metrics = report.metrics;
    el('fortune-historical-title').textContent =
      `${report.paired_predictions} kỳ gần nhất · ${report.start_date} đến ${report.end_date}`;
    el('fortune-historical-note').textContent =
      `Đối chiếu walk-forward song song theo dữ liệu đến ${report.dataset.last_date}. `
      + 'Báo cáo đã lưu; việc mở trang không chạy lại huấn luyện.';
    el('fortune-historical-summary').replaceChildren(
      comparisonCard('Tần suất A', formatPercent(metrics.frequency.hit_rate), comparisonModelDetail(metrics.frequency, report.paired_predictions)),
      comparisonCard('Logistic B', formatPercent(metrics.logistic.hit_rate), comparisonModelDetail(metrics.logistic, report.paired_predictions)),
      comparisonCard('Baseline', formatPercent(metrics.baseline, 0), `Top ${selectedCount}`),
      comparisonCard('B − A', formatPercent(metrics.delta_logistic_vs_frequency), `McNemar p=${metrics.mcnemar_exact_p}`),
    );
    el('fortune-rolling-window-badge').textContent = `${report.paired_predictions} kỳ · hồi kiểm`;
    renderHistoricalDailyTable(report.daily);
    renderHistoricalDailyStats(report.daily);
  } catch (err) {
    console.warn('Rolling model comparison load failed:', err);
    el('fortune-historical-title').textContent = 'Chưa tải được đối chiếu rolling';
    el('fortune-historical-summary').replaceChildren();
    el('fortune-historical-daily-stats').replaceChildren();
    el('fortune-rolling-window-badge').textContent = 'Chưa tải được';
    el('fortune-historical-note').textContent = 'Hệ thống sẽ thử lại khi dữ liệu hợp lệ sẵn sàng.';
    const body = el('fortune-historical-daily-body');
    if (body) {
      body.replaceChildren();
      const row = document.createElement('tr');
      const td = cell('Không tải được dữ liệu lịch sử chi tiết');
      td.colSpan = 7;
      td.style.textAlign = 'center';
      row.append(td);
      body.append(row);
    }
  }
}

function renderHistoricalDailyStats(rows) {
  const root = el('fortune-historical-daily-stats');
  if (!root) return;
  root.replaceChildren();

  const total = rows.length;
  const freqHits = rows.filter(r => r.frequency_hit).length;
  const logHits = rows.filter(r => r.logistic_hit).length;
  const bothHit = rows.filter(r => r.frequency_hit && r.logistic_hit).length;
  const bothMiss = rows.filter(r => !r.frequency_hit && !r.logistic_hit).length;
  const logOnly = rows.filter(r => !r.frequency_hit && r.logistic_hit).length;
  const freqOnly = rows.filter(r => r.frequency_hit && !r.logistic_hit).length;

  // Streak tính toán
  let currentStreak = 0;
  let maxStreak = 0;
  let currentMissStreak = 0;
  let maxMissStreak = 0;
  // Tính cho logistic
  for (const r of [...rows].reverse()) {
    if (r.logistic_hit) {
      currentStreak++;
      maxStreak = Math.max(maxStreak, currentStreak);
      currentMissStreak = 0;
    } else {
      currentStreak = 0;
      currentMissStreak++;
      maxMissStreak = Math.max(maxMissStreak, currentMissStreak);
    }
  }

  const stats = [
    comparisonCard('Tổng kỳ', total, 'Dữ liệu thật'),
    comparisonCard('Tần suất A', `${freqHits}/${total}`, formatPercent(freqHits / total)),
    comparisonCard('Logistic B', `${logHits}/${total}`, formatPercent(logHits / total)),
    comparisonCard('B − A', `+${logHits - freqHits} kỳ`, formatPercent((logHits - freqHits) / total)),
    comparisonCard('Cả hai HIT', `${bothHit}`, `${(bothHit / total * 100).toFixed(1)}% kỳ`),
    comparisonCard('Cả hai MISS', `${bothMiss}`, `${(bothMiss / total * 100).toFixed(1)}% kỳ`),
    comparisonCard('Chỉ B đúng', `${logOnly}`, `${(logOnly / total * 100).toFixed(1)}% kỳ`),
    comparisonCard('Chỉ A đúng', `${freqOnly}`, `${(freqOnly / total * 100).toFixed(1)}% kỳ`),
  ];
  root.replaceChildren(...stats);
}

function renderHistoricalDailyTable(rows) {
  const body = el('fortune-historical-daily-body');
  if (!body) return;
  body.replaceChildren();

  const pageSize = 30;
  const pageState = { current: 0 };
  const totalPages = Math.ceil(rows.length / pageSize);

  function renderPage() {
    body.replaceChildren();
    const start = pageState.current * pageSize;
    const pageRows = rows.slice(start, start + pageSize);

    pageRows.forEach((row, idx) => {
      const tr = document.createElement('tr');
      tr.append(
        cell(start + idx + 1),
        cell(row.prediction_date),
        cell(row.actual_last_two),
      );
      // Tần suất A
      const freqTd = document.createElement('td');
      freqTd.append(badge(row.frequency_hit ? 'HIT' : 'MISS', row.frequency_hit ? 'hit' : 'miss'));
      tr.append(freqTd);
      // Logistic B
      const logTd = document.createElement('td');
      logTd.append(badge(row.logistic_hit ? 'HIT' : 'MISS', row.logistic_hit ? 'hit' : 'miss'));
      tr.append(logTd);
      // Comparison
      const cmpTd = document.createElement('td');
      if (row.logistic_hit && !row.frequency_hit) {
        cmpTd.append(badge('B thắng', 'hit'));
      } else if (!row.logistic_hit && row.frequency_hit) {
        cmpTd.append(badge('A thắng', 'miss'));
      } else if (row.logistic_hit && row.frequency_hit) {
        cmpTd.append(badge('Cả hai', 'verified'));
      } else {
        cmpTd.append(badge('Trượt', 'pending'));
      }
      tr.append(cmpTd);
      // Log loss
      const llTd = document.createElement('td');
      const llDiff = row.logistic_log_loss - row.frequency_log_loss;
      llTd.textContent = llDiff > 0 ? `+${llDiff.toFixed(2)}` : llDiff.toFixed(2);
      llTd.style.color = llDiff <= 0 ? 'var(--fortune-red, #9d0c14)' : 'var(--muted)';
      llTd.style.fontWeight = llDiff <= 0 ? '700' : '400';
      tr.append(llTd);
      body.append(tr);
    });

    // Pagination row
    const pageTr = document.createElement('tr');
    const pageTd = document.createElement('td');
    pageTd.colSpan = 7;
    pageTd.className = 'historical-daily-pagination';

    const info = document.createElement('span');
    info.className = 'historical-daily-page-info';
    info.textContent = `Trang ${pageState.current + 1}/${totalPages} · ${rows.length} kỳ`;

    const prevBtn = document.createElement('button');
    prevBtn.type = 'button';
    prevBtn.className = 'fortune-detail-button';
    prevBtn.textContent = '← Trước';
    prevBtn.disabled = pageState.current === 0;
    prevBtn.addEventListener('click', () => { pageState.current--; renderPage(); });

    const nextBtn = document.createElement('button');
    nextBtn.type = 'button';
    nextBtn.className = 'fortune-detail-button';
    nextBtn.textContent = 'Sau →';
    nextBtn.disabled = pageState.current >= totalPages - 1;
    nextBtn.addEventListener('click', () => { pageState.current++; renderPage(); });

    pageTd.append(prevBtn, info, nextBtn);
    pageTr.append(pageTd);
    body.append(pageTr);
  }

  renderPage();
}

function initFortunePage() {
  initFortuneGlitter();
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(updateFortuneRippleDelays, 120);
  });
  document.querySelectorAll('[data-fortune-filter]').forEach((button) => {
    button.addEventListener('click', () => {
      document.querySelectorAll('[data-fortune-filter]').forEach(item => item.classList.remove('active'));
      button.classList.add('active');
      state.fortuneFilter = button.dataset.fortuneFilter;
      renderFortunePrediction(state.latestLogisticPrediction);
    });
  });
  el('fortune-selected-count').addEventListener('change', async () => {
    await Promise.allSettled([
      loadLatestLogisticPrediction(),
      loadModelComparison(),
      loadRollingModelComparison(),
    ]);
  });
  initFortuneExcludeRecentToggle();
  el('fortune-copy-button').addEventListener('click', async () => {
    const text = el('fortune-export-string').textContent;
    if (!text || text === '—') return;
    try {
      await navigator.clipboard.writeText(text);
      toast(`Đã sao chép ${text.split(',').length} số Logistic.`, 'success');
    } catch {
      const area = document.createElement('textarea');
      area.value = text;
      area.style.cssText = 'position:fixed;opacity:0';
      document.body.append(area);
      area.select();
      document.execCommand('copy');
      area.remove();
      toast(`Đã sao chép ${text.split(',').length} số Logistic.`, 'success');
    }
  });
}

// ═══════════════════════════════════════════════════════════
// CATBOOST DIRECT MULTICLASS 00-99
// ═══════════════════════════════════════════════════════════
function catboostRecentSet() {
  return new Set(state.catboostExcludeRecent
    ? state.catboostRecentNumbers.map(item => item.last_two)
    : []);
}

function catboostRecentDisplaySet() {
  return new Set(state.catboostRecentNumbers.map(item => item.last_two));
}

function latestCatBoostRecentNumber() {
  return state.catboostRecentNumbers[0]?.last_two || null;
}

function renderCatBoostPrediction(prediction) {
  const grid = el('catboost-number-grid');
  const meta = el('catboost-prediction-meta');
  const exportBox = el('catboost-export');
  if (!grid || !meta || !exportBox) return;
  grid.replaceChildren();
  meta.replaceChildren();
  if (!prediction) {
    exportBox.hidden = true;
    const empty = document.createElement('div');
    empty.className = 'catboost-empty';
    empty.innerHTML = '<span>🐭</span><strong>Chưa có snapshot CatBoost</strong><small>Chọn Top N rồi bấm “Huấn luyện và khóa” để tạo bảng đầu tiên.</small>';
    grid.append(empty);
    return;
  }

  const evaluation = prediction.evaluation || { status: 'pending' };
  const recent = catboostRecentSet();
  const recentDisplay = catboostRecentDisplaySet();
  const latestRecent = latestCatBoostRecentNumber();
  const selected = new Set((prediction.numbers || []).filter(number => !recent.has(number)));
  const actual = evaluation.actual_last_two;
  [
    { text: `📅 ${prediction.prediction_date}`, cls: 'date' },
    { text: `Top ${prediction.selected_count}`, cls: 'count' },
    { text: `Train đến ${prediction.trained_through}`, cls: 'train' },
    { text: `Coverage ${formatPercent(prediction.coverage_probability)}`, cls: 'coverage' },
    {
      text: evaluation.status === 'evaluated' ? (evaluation.hit ? '✅ HIT' : '❌ MISS') : evaluation.status === 'invalidated' ? '⚠️ Kết quả cần xác minh' : '⏳ PENDING',
      cls: evaluation.status === 'evaluated' ? (evaluation.hit ? 'hit' : 'miss') : 'pending',
    },
  ].forEach(({ text, cls }) => {
    const chip = document.createElement('span');
    chip.className = `meta-chip catboost-meta-chip ${cls}`;
    chip.textContent = text;
    meta.append(chip);
  });

  document.querySelectorAll('[data-catboost-tab]').forEach(button => {
    const type = button.dataset.catboostTab;
    if (type === 'all') button.textContent = 'Đủ 100 số';
    if (type === 'selected') button.textContent = `Được chọn (${selected.size})`;
    if (type === 'excluded') button.textContent = `Bị loại (${100 - selected.size})`;
    button.setAttribute('aria-selected', String(type === state.catboostFilter));
  });

  let scores = [...(prediction.scores || [])].sort((a, b) => a.rank - b.rank);
  if (state.catboostFilter === 'selected') scores = scores.filter(score => selected.has(score.number));
  if (state.catboostFilter === 'excluded') scores = scores.filter(score => !selected.has(score.number));
  scores.forEach(score => {
    const node = document.createElement('div');
    const isSelected = selected.has(score.number);
    const isActual = actual === score.number;
    const isRecent = recentDisplay.has(score.number);
    const isLatestRecent = latestRecent === score.number;
    node.className = `catboost-number${isSelected ? ' selected' : ' excluded'}${score.rank <= 10 ? ' top-ten' : ''}${isActual ? ' actual' : ''}${isActual && isSelected ? ' hit' : ''}${isRecent ? ' recent' : ''}${isLatestRecent ? ' latest-recent' : ''}`;
    node.innerHTML = `<strong>${score.number}</strong><span>${formatPercent(score.probability, 3)}</span><small>#${score.rank}</small>`;
    node.title = `Số ${score.number} · rank #${score.rank} · ${formatPercent(score.probability, 4)}${isLatestRecent ? ' · kết quả kỳ gần nhất' : isRecent ? ' · vừa ra gần đây' : ''}`;
    node.setAttribute('role', 'gridcell');
    node.setAttribute('aria-label', `Số ${score.number}, hạng ${score.rank}, ${isSelected ? 'được chọn' : 'bị loại'}${isLatestRecent ? ', kết quả kỳ gần nhất' : isRecent ? ', vừa ra gần đây' : ''}`);
    grid.append(node);
  });

  const exportScores = (prediction.scores || [])
    .filter(score => selected.has(score.number))
    .sort((a, b) => a.rank - b.rank);
  el('catboost-number-string').textContent = exportScores.map(score => score.number).join(',');
  el('catboost-export-label').textContent = `${exportScores.length} số theo thứ hạng mô hình${recent.size ? ` · bỏ ${recent.size} số vừa ra` : ''}`;
  exportBox.hidden = false;
}

async function loadLatestCatBoostPrediction() {
  const count = Number(el('catboost-selected-count')?.value || 65);
  const prediction = await api(`/api/catboost-predictions/latest?selected_count=${count}`);
  state.latestCatBoostPrediction = prediction;
  renderCatBoostPrediction(prediction);
}

async function loadCatBoostHistory() {
  const predictions = await api('/api/catboost-predictions?limit=50');
  const body = el('catboost-prediction-history');
  if (!body) return;
  body.replaceChildren();
  if (!predictions.length) {
    const row = document.createElement('tr');
    const td = cell('Chưa có snapshot CatBoost'); td.colSpan = 7; td.style.textAlign = 'center';
    row.append(td); body.append(row); return;
  }
  predictions.forEach(prediction => {
    const evaluation = prediction.evaluation || { status: 'pending' };
    const row = document.createElement('tr');
    row.append(
      predictionDateCell(prediction), cell(prediction.selected_count),
      cell(prediction.trained_through), cell(formatPercent(prediction.coverage_probability)),
      cell(evaluation.actual_last_two || '—'),
    );
    const status = document.createElement('td');
    status.append(evaluation.status === 'evaluated'
      ? badge(evaluation.hit ? 'HIT' : 'MISS', evaluation.hit ? 'hit' : 'miss')
      : badge(evaluation.status === 'invalidated' ? 'CẦN ĐỐI CHIẾU LẠI' : 'PENDING', 'pending'));
    const model = cell(prediction.model_version);
    const detail = document.createElement('button');
    detail.type = 'button';
    detail.className = 'detail-button';
    detail.textContent = 'Xem chi tiết';
    detail.addEventListener('click', () => openPredictionDetail(prediction._id));
    model.append(detail);
    row.append(status, model);
    body.append(row);
  });
}

async function loadCatBoostComparison() {
  const count = Number(el('catboost-selected-count')?.value || 65);
  const report = await api(`/api/model-comparison/three-way?selected_count=${count}`);
  const cards = el('catboost-comparison-cards');
  const body = el('catboost-comparison-history');
  const note = el('catboost-comparison-note');
  if (!cards || !body || !note) return;
  cards.replaceChildren(); body.replaceChildren();
  const definitions = [
    ['Tần suất A', report.frequency_model],
    ['Logistic B', report.logistic_model],
    ['CatBoost C', report.catboost_model],
    ['Baseline', { hit_rate: report.baseline, hits: null }],
  ];
  definitions.forEach(([label, model], index) => {
    const card = document.createElement('div');
    card.className = `catboost-metric model-${['a', 'b', 'c', 'baseline'][index]}${label === 'CatBoost C' ? ' featured' : ''}`;
    const caption = document.createElement('span'); caption.textContent = label;
    const value = document.createElement('strong'); value.textContent = formatPercent(model?.hit_rate);
    const detail = document.createElement('small');
    detail.textContent = model?.hits == null ? `Top ${report.selected_count}` : comparisonModelDetail(model, report.paired_predictions);
    card.append(caption, value, detail);
    cards.append(card);
  });
  (report.recent_pairs || []).forEach(item => {
    const row = document.createElement('tr');
    row.append(cell(item.prediction_date), cell(item.actual_last_two),
      cell(item.frequency_hit ? '✅ HIT' : '❌ MISS'),
      cell(item.logistic_hit ? '✅ HIT' : '❌ MISS'),
      cell(item.catboost_hit ? '✅ HIT' : '❌ MISS'));
    body.append(row);
  });
  if (!report.recent_pairs?.length) {
    const row = document.createElement('tr'); const td = cell('Chưa có ngày đủ cả ba snapshot đã đánh giá');
    td.colSpan = 5; td.style.textAlign = 'center'; row.append(td); body.append(row);
  }
  const paired = report.comparisons?.find(pair =>
    pair.model_a === report.frequency_model.model_version && pair.model_b === report.catboost_model.model_version);
  note.textContent = report.note + (paired?.mcnemar_holm_p == null ? ''
    : ` Tần suất/CatBoost: McNemar p=${paired.mcnemar_exact_p}, sau Holm=${paired.mcnemar_holm_p}.`);
}

async function loadCatBoostRecentNumbers() {
  const days = Number(el('catboost-exclude-days')?.value || 3);
  const data = await api(`/api/results/recent-last-two?days=${days}`);
  state.catboostRecentNumbers = [...(data.results || [])]
    .sort((left, right) => right.draw_date.localeCompare(left.draw_date));
  const chips = el('catboost-recent-chips');
  if (!chips) return;
  chips.replaceChildren();
  state.catboostRecentNumbers.forEach((item, index) => {
    const chip = document.createElement('span');
    chip.className = index === 0 ? 'latest' : 'recent';
    chip.textContent = `${index === 0 ? '★ ' : ''}${item.last_two} · ${item.draw_date}`;
    chips.append(chip);
  });
  chips.hidden = !state.catboostExcludeRecent || !state.catboostRecentNumbers.length;
}

function initCatBoostPage() {
  document.querySelectorAll('[data-catboost-tab]').forEach(button => {
    button.addEventListener('click', () => {
      document.querySelectorAll('[data-catboost-tab]').forEach(item => item.classList.remove('active'));
      button.classList.add('active'); state.catboostFilter = button.dataset.catboostTab;
      renderCatBoostPrediction(state.latestCatBoostPrediction);
    });
  });
  el('catboost-selected-count')?.addEventListener('change', async () => {
    await Promise.allSettled([loadLatestCatBoostPrediction(), loadCatBoostComparison()]);
  });
  el('catboost-exclude-recent')?.addEventListener('change', async event => {
    state.catboostExcludeRecent = event.target.checked;
    if (state.catboostExcludeRecent) await loadCatBoostRecentNumbers();
    else el('catboost-recent-chips').hidden = true;
    renderCatBoostPrediction(state.latestCatBoostPrediction);
  });
  el('catboost-exclude-days')?.addEventListener('change', async () => {
    await loadCatBoostRecentNumbers(); renderCatBoostPrediction(state.latestCatBoostPrediction);
  });
  el('catboost-copy')?.addEventListener('click', async () => {
    const text = el('catboost-number-string')?.textContent || '';
    if (!text || text === '—') return;
    const button = el('catboost-copy');
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const area = document.createElement('textarea');
      area.value = text;
      area.style.cssText = 'position:fixed;opacity:0;pointer-events:none';
      document.body.append(area);
      area.select();
      document.execCommand('copy');
      area.remove();
    }
    const original = button.textContent;
    button.textContent = '✓ Đã sao chép';
    button.classList.add('copied');
    setTimeout(() => { button.textContent = original; button.classList.remove('copied'); }, 1600);
    toast(`Đã sao chép ${text.split(',').length} số CatBoost.`, 'success');
  });
}

function renderDigitBacktestSummary(run) {
  const root = el('digit-backtest-summary');
  if (!run) {
    root.className = 'empty-state';
    root.textContent = 'Chưa có backtest cho dự đoán một số cuối.';
    return;
  }
  root.className = 'backtest-grid';
  root.replaceChildren();
  const stats = [
    { label: 'Số kỳ', value: run.total_predictions },
    { label: 'Hit rate Top‑1', value: formatPercent(run.hit_rate), cls: run.lift_vs_random > 0 ? 'positive' : 'negative' },
    { label: 'Random baseline', value: formatPercent(run.random_baseline) },
    { label: 'Lift', value: formatPercent(run.lift_vs_random), cls: run.lift_vs_random > 0 ? 'positive' : 'negative' },
    { label: 'CI 95%', value: `${formatPercent(run.confidence_interval_95?.lower)} – ${formatPercent(run.confidence_interval_95?.upper)}` },
  ];
  stats.forEach(({ label, value, cls }) => {
    const card = document.createElement('div');
    card.className = `backtest-stat ${cls || ''}`.trim();
    const caption = document.createElement('span');
    caption.textContent = label;
    const strong = document.createElement('strong');
    strong.textContent = value;
    card.append(caption, strong);
    root.append(card);
  });
}

async function loadDigitBacktests() {
  const runs = await api('/api/digit-backtests?limit=10');
  renderDigitBacktestSummary(runs[0] || null);
  const body = el('digit-backtest-history');
  body.replaceChildren();
  if (!runs.length) {
    const row = document.createElement('tr');
    const td = cell('Chưa có lần backtest');
    td.colSpan = 7;
    td.style.textAlign = 'center';
    row.append(td);
    body.append(row);
    return;
  }
  runs.forEach(run => {
    const row = document.createElement('tr');
    row.append(
      cell(formatDateTime(run.created_at)),
      cell(run.total_predictions),
      cell(formatPercent(run.hit_rate)),
      cell(formatPercent(run.random_baseline)),
      cell(formatPercent(run.lift_vs_random)),
      cell(`${formatPercent(run.confidence_interval_95?.lower)} – ${formatPercent(run.confidence_interval_95?.upper)}`),
      cell(run.mean_brier_score?.toFixed(5)),
    );
    body.append(row);
  });
}

// ═══════════════════════════════════════════════════════════
// PREDICTION HISTORY TABLE
// ═══════════════════════════════════════════════════════════
function closePredictionDetail() {
  state.detailRequest += 1;
  window.DashboardUI.closeDialog(el('prediction-detail-modal'));
}

function detailSummaryItem(label, value) {
  const item = document.createElement('div');
  item.className = 'detail-summary-item';
  const caption = document.createElement('span');
  caption.textContent = label;
  const strong = document.createElement('strong');
  strong.textContent = value ?? '—';
  item.append(caption, strong);
  return item;
}

function renderPredictionDetail(prediction) {
  const evaluation = prediction.evaluation || { status: 'pending' };
  const selected = new Set(prediction.numbers || []);
  const actual = evaluation.actual_last_two;
  const summary = el('prediction-detail-summary');
  summary.replaceChildren(
    detailSummaryItem('Ngày dự đoán', prediction.prediction_date),
    detailSummaryItem('Đánh giá', evaluation.status === 'evaluated' ? (evaluation.hit ? 'HIT' : 'MISS') : evaluation.status === 'invalidated' ? 'CẦN XÁC MINH' : 'PENDING'),
    detailSummaryItem('Mô hình', prediction.model_version),
    detailSummaryItem('Số lượng chọn', `Top ${prediction.selected_count}`),
    detailSummaryItem('Điểm coverage thô', formatPercent(prediction.coverage_probability, 4)),
    detailSummaryItem('Ngưỡng cut-off', formatPercent(prediction.cutoff_probability, 4)),
    detailSummaryItem('Số kỳ huấn luyện', Number(prediction.training_draw_count || 0).toLocaleString('vi-VN')),
    detailSummaryItem('Train đến', prediction.trained_through),
    detailSummaryItem(prediction.prediction_kind === 'retrospective' ? 'Hồi kiểm tạo lúc' : 'Khóa lúc',
      formatDateTime(prediction.prediction_kind === 'retrospective' ? prediction.created_at : prediction.locked_at)),
    detailSummaryItem('Kết quả đặc biệt', evaluation.actual_special_prize || 'Chưa có'),
    detailSummaryItem('Hai số cuối', actual || 'Chưa có'),
    detailSummaryItem('Dataset hash', prediction.dataset_hash || '—'),
  );
  if (prediction.prediction_kind === 'retrospective') {
    summary.prepend(detailSummaryItem('HỒI KIỂM · Không tính vào tỷ lệ trực tiếp', prediction.note));
  }

  const grid = el('prediction-detail-grid');
  grid.replaceChildren();
  const orderedScores = [...(prediction.scores || [])].sort((a, b) => a.number.localeCompare(b.number));
  for (const score of orderedScores) {
    const node = document.createElement('div');
    const isSelected = selected.has(score.number);
    const isActual = actual === score.number;
    node.className = `number-cell${isSelected ? ' selected' : ''}${isActual ? ' actual' : ''}${score.recent_hit ? ' recent-hit' : ''}`;
    node.setAttribute('role', 'gridcell');
    const number = document.createElement('span');
    number.className = 'cell-num';
    number.textContent = score.number;
    const probability = document.createElement('span');
    probability.className = 'cell-probability';
    probability.textContent = formatPercent(score.probability, 3);
    node.append(number, probability);
    node.title = `Rank #${score.rank} · ${formatPercent(score.probability, 4)} · ${score.days_since_last_hit ?? '—'} ngày từ lần cuối`;
    grid.append(node);
  }

  const selectedList = el('prediction-detail-selected');
  selectedList.replaceChildren();
  [...(prediction.scores || [])]
    .filter(score => selected.has(score.number))
    .sort((a, b) => a.rank - b.rank)
    .forEach(score => {
      const chip = document.createElement('span');
      chip.className = `selected-number-chip${actual === score.number ? ' actual' : ''}`;
      chip.textContent = `${score.number} · #${score.rank}`;
      chip.title = formatPercent(score.probability, 4);
      selectedList.append(chip);
    });

  const windows = el('prediction-detail-windows');
  windows.replaceChildren();
  (prediction.window_details || []).forEach(window => {
    const row = document.createElement('div');
    row.className = 'window-row';
    const name = document.createElement('strong');
    name.textContent = window.window === 'all' ? 'Toàn bộ' : `${window.window} kỳ`;
    const detail = document.createElement('span');
    detail.textContent = `${formatPercent(window.weight, 0)} · ${window.observations} quan sát`;
    row.append(name, detail);
    windows.append(row);
  });

  const scoreBody = el('prediction-detail-scores');
  scoreBody.replaceChildren();
  [...(prediction.scores || [])].sort((a, b) => a.rank - b.rank).forEach(score => {
    const row = document.createElement('tr');
    if (selected.has(score.number)) row.classList.add('is-selected');
    if (actual === score.number) row.classList.add('is-actual');
    row.append(
      cell(`#${score.rank}`),
      cell(score.number),
      cell(formatPercent(score.probability, 4)),
      cell(score.days_since_last_hit === null || score.days_since_last_hit === undefined ? 'Chưa từng ra' : `${score.days_since_last_hit} ngày`),
    );
    const status = document.createElement('td');
    const statusWrap = document.createElement('div');
    statusWrap.className = 'status-inline';
    statusWrap.append(badge(selected.has(score.number) ? 'ĐÃ CHỌN' : 'LOẠI', selected.has(score.number) ? 'verified' : 'observed'));
    if (score.recent_hit) statusWrap.append(badge('VỪA RA', 'pending'));
    if (actual === score.number) statusWrap.append(badge('KẾT QUẢ', evaluation.hit ? 'hit' : 'miss'));
    status.append(statusWrap);
    row.append(status);
    scoreBody.append(row);
  });
}

async function openPredictionDetail(predictionId) {
  const requestId = ++state.detailRequest;
  state.detailId = predictionId;
  const modal = el('prediction-detail-modal');
  const loading = el('prediction-detail-loading');
  const content = el('prediction-detail-content');
  loading.hidden = false;
  loading.textContent = 'Đang tải chi tiết dự đoán…';
  content.hidden = true;
  el('detail-retry-btn').hidden = true;
  window.DashboardUI.openDialog(modal);
  try {
    let prediction = state.detailCache.get(predictionId);
    if (!prediction) {
      prediction = await api(`/api/predictions/${encodeURIComponent(predictionId)}`);
      state.detailCache.set(predictionId, prediction);
    }
    if (requestId !== state.detailRequest || !modal.open) return;
    renderPredictionDetail(prediction);
    loading.hidden = true;
    content.hidden = false;
  } catch (error) {
    if (requestId !== state.detailRequest || !modal.open) return;
    loading.textContent = `Không tải được chi tiết: ${error.message}`;
    el('detail-retry-btn').hidden = false;
  }
}

async function loadPredictionHistory() {
  const predictions = await api('/api/predictions?limit=50');
  const body = el('prediction-history');
  body.replaceChildren();

  if (!predictions.length) {
    const row = document.createElement('tr');
    const td = cell('Chưa có dự đoán');
    td.colSpan = 7;
    td.style.textAlign = 'center';
    row.append(td);
    body.append(row);
    return;
  }

  predictions.forEach((pred) => {
    const row = document.createElement('tr');
    row.append(
      predictionDateCell(pred),
      cell(pred.model_version),
      cell(pred.selected_count),
      cell(pred.trained_through),
      cell(pred.evaluation?.actual_last_two || '—'),
    );
    const statusCell = document.createElement('td');
    const ev = pred.evaluation || { status: 'pending' };
    if (ev.status === 'evaluated') {
      statusCell.append(badge(ev.hit ? 'HIT' : 'MISS', ev.hit ? 'hit' : 'miss'));
    } else {
      statusCell.append(badge(ev.status === 'invalidated' ? 'CẦN ĐỐI CHIẾU LẠI' : 'PENDING', 'pending'));
    }
    row.append(statusCell);
    const actionCell = document.createElement('td');
    const detailButton = document.createElement('button');
    detailButton.type = 'button';
    detailButton.className = 'detail-button';
    detailButton.textContent = 'Xem chi tiết';
    detailButton.addEventListener('click', () => openPredictionDetail(pred._id));
    actionCell.append(detailButton);
    row.append(actionCell);
    body.append(row);
  });
}

// ═══════════════════════════════════════════════════════════
// DRAW RESULTS TABLE
// ═══════════════════════════════════════════════════════════
const RESULTS_PAGE_SIZE = 6;
const resultDate = value => /^\d{4}-\d{2}-\d{2}$/.test(value || '') ? value.split('-').reverse().join('/') : (value || '—');

function resultModelCell(result) {
  const cell = document.createElement('td');
  cell.className = 'results-models-cell';
  const group = document.createElement('div');
  group.className = 'results-models';
  const names = { A: 'Dự đoán N-1', B: 'Thần Tài', C: 'CatBoost' };
  const labels = { hit: 'Đúng', miss: 'Sai', pending: 'Chưa đánh giá', missing: 'Chưa có dự đoán', invalidated: 'Cần đối chiếu lại' };
  for (const [letter, name] of Object.entries(names)) {
    const outcome = result.model_outcomes?.[letter];
    const status = Object.hasOwn(labels, outcome?.status) ? outcome.status : 'missing';
    const marker = document.createElement('span');
    marker.className = `result-model result-model-${status === 'hit' || status === 'miss' ? status : 'neutral'}`;
    const replay = outcome?.prediction_kind === 'retrospective';
    const count = outcome?.selected_count || result.model_selected_count;
    const label = `${letter} · ${name}: ${labels[status]}${count ? ` · Top ${count}` : ''}${replay ? ' · Hồi kiểm sau kết quả' : ''}`;
    marker.title = label;
    marker.setAttribute('role', 'img');
    marker.setAttribute('aria-label', label);
    const text = document.createElement('strong');
    text.textContent = letter;
    text.setAttribute('aria-hidden', 'true');
    const symbol = document.createElement('small');
    symbol.textContent = status === 'hit' ? '✓' : status === 'miss' ? '×' : '—';
    symbol.setAttribute('aria-hidden', 'true');
    marker.append(text, symbol);
    if (replay) {
      const note = document.createElement('sup');
      note.className = 'result-model-replay';
      note.textContent = 'HK';
      note.setAttribute('aria-hidden', 'true');
      marker.append(note);
    }
    group.append(marker);
  }
  cell.append(group);
  return cell;
}

function renderResults() {
  const body = el('result-history');
  body.replaceChildren();
  if (!state.resultsRows.length) {
    const row = document.createElement('tr');
    const message = cell('Chưa có kết quả. Bạn có thể bổ sung dữ liệu ở khu vực bên dưới.');
    message.colSpan = 5;
    message.className = 'results-empty';
    row.append(message);
    body.append(row);
  }
  state.resultsRows.forEach(result => {
    const row = document.createElement('tr');
    const dateCell = cell(resultDate(result.draw_date));
    dateCell.className = 'results-date-cell';
    const prizeCell = cell(result.special_prize);
    prizeCell.className = 'results-prize-cell';
    const numberCell = document.createElement('td');
    const number = document.createElement('span');
    number.className = 'results-number';
    number.textContent = result.last_two ?? '—';
    numberCell.append(number);
    const statusCell = document.createElement('td');
    const labels = { observed: 'Đã ghi nhận', verified: 'Đã xác minh', conflict: 'Chờ đối chiếu' };
    const kind = ['verified', 'conflict'].includes(result.status) ? result.status : 'observed';
    statusCell.append(badge(labels[result.status] || result.status || 'Chưa xác định', kind));
    row.append(dateCell, prizeCell, numberCell, statusCell, resultModelCell(result));
    body.append(row);
  });
  const count = state.resultsRows.length;
  el('results-range').textContent = count
    ? `Đang hiển thị ${count} ngày · ${resultDate(state.resultsRows[count - 1].draw_date)} – ${resultDate(state.resultsRows[0].draw_date)}${state.resultsHasMore ? '' : ' · Đã hết dữ liệu'}`
    : 'Chưa có ngày nào được lưu';
  el('results-more-btn').hidden = !state.resultsHasMore;
  const selectedCount = state.resultsRows[0]?.model_selected_count;
  el('results-model-count').textContent = selectedCount ? `Đối chiếu Top ${selectedCount}` : 'Bộ dự đoán tự động';
}

// One extra row tells us whether another page exists, without a count query.
async function fetchResultWindow(count, before = null) {
  const rows = [];
  let hasMore = false;
  while (rows.length < count) {
    const limit = Math.min(count - rows.length + 1, 1000);
    const batch = await api(`/api/results?limit=${limit}&include_models=true${before ? `&before=${encodeURIComponent(before)}` : ''}`);
    if (!Array.isArray(batch)) throw new Error('Dữ liệu kết quả không hợp lệ.');
    const take = Math.min(count - rows.length, limit - 1, batch.length);
    rows.push(...batch.slice(0, take));
    hasMore = batch.length > take;
    if (!hasMore || rows.length >= count) break;
    before = rows[rows.length - 1].draw_date;
  }
  return { rows, hasMore };
}

async function loadResults({ append = false } = {}) {
  // Polling, refresh and repeated clicks share the current request.
  if (state.resultsTask) return state.resultsTask;
  if (append && !state.resultsHasMore) return;
  const button = el('results-more-btn');
  state.resultsTask = (async () => {
    setBusy(button, true, 'Đang tải…');
    el('result-history').setAttribute('aria-busy', 'true');
    try {
      const count = append ? RESULTS_PAGE_SIZE : Math.max(RESULTS_PAGE_SIZE, state.resultsRows.length);
      const before = append ? state.resultsRows[state.resultsRows.length - 1]?.draw_date : null;
      const page = await fetchResultWindow(count, before);
      state.resultsRows = append ? [...state.resultsRows, ...page.rows] : page.rows;
      state.resultsHasMore = page.hasMore;
      renderResults();
    } catch (error) {
      el('results-range').textContent = append
        ? 'Chưa tải được các ngày trước. Bấm Xem thêm để thử lại.'
        : 'Chưa cập nhật được kết quả. Bấm Làm mới để thử lại.';
      if (!state.resultsRows.length) {
        const row = document.createElement('tr');
        const message = cell('Không tải được kết quả. Vui lòng kiểm tra kết nối và thử lại.');
        message.colSpan = 5;
        message.className = 'results-empty';
        row.append(message);
        el('result-history').replaceChildren(row);
      }
      throw error;
    } finally {
      state.resultsTask = null;
      setBusy(button, false);
      el('result-history').setAttribute('aria-busy', 'false');
    }
  })();
  return state.resultsTask;
}

// ═══════════════════════════════════════════════════════════
// BACKTEST
// ═══════════════════════════════════════════════════════════
function renderBacktestSummary(run) {
  const root = el('backtest-summary');
  root.className = 'backtest-grid';
  root.replaceChildren();

  const liftPositive = run.lift_vs_random > 0;
  const aboveBreakeven = run.hit_rate > 0.6316;

  const stats = [
    { label: 'Số kỳ', value: run.total_predictions },
    { label: 'Hit rate', value: formatPercent(run.hit_rate), cls: aboveBreakeven ? 'positive' : 'negative' },
    { label: 'Random baseline', value: formatPercent(run.random_baseline) },
    { label: 'Lift vs random', value: formatPercent(run.lift_vs_random), cls: liftPositive ? 'positive' : 'negative' },
    {
      label: 'CI 95%',
      value: `${formatPercent(run.confidence_interval_95.lower)} – ${formatPercent(run.confidence_interval_95.upper)}`
    },
    { label: 'Longest miss', value: `${run.longest_miss_streak ?? '—'} kỳ`, cls: (run.longest_miss_streak > 10) ? 'negative' : '' },
    { label: 'Max drawdown', value: formatMoney(run.max_drawdown_vnd), cls: 'negative' },
    { label: 'Brier score', value: run.mean_brier_score?.toFixed(5) },
    { label: 'Log loss', value: run.mean_log_loss?.toFixed(4) },
    {
      label: 'Hòa vốn?',
      value: run.confidence_interval_95.lower > 0.6316 ? '✅ CI > 63.16%' : '⚠️ Chưa đủ bằng chứng',
      cls: run.confidence_interval_95.lower > 0.6316 ? 'positive' : 'negative',
    },
  ];

  stats.forEach(({ label, value, cls }) => {
    const card = document.createElement('div');
    card.className = `backtest-stat ${cls || ''}`.trim();
    const caption = document.createElement('span');
    caption.textContent = label;
    const strong = document.createElement('strong');
    strong.textContent = value;
    card.append(caption, strong);
    root.append(card);
  });
}

async function loadBacktests() {
  const runs = await api('/api/backtests?limit=10');
  const body = el('backtest-history');
  body.replaceChildren();

  runs.forEach((run) => {
    const row = document.createElement('tr');
    row.append(
      cell(formatDateTime(run.created_at)),
      cell(run.selected_count),
      cell(run.total_predictions),
      cell(formatPercent(run.hit_rate)),
      cell(formatPercent(run.random_baseline)),
      cell(formatPercent(run.lift_vs_random)),
      cell(`${formatPercent(run.confidence_interval_95?.lower)} – ${formatPercent(run.confidence_interval_95?.upper)}`),
      cell(run.longest_miss_streak != null ? `${run.longest_miss_streak} kỳ` : '—'),
      cell(formatMoney(run.max_drawdown_vnd)),
    );
    body.append(row);
  });
}

// ═══════════════════════════════════════════════════════════
// DASHBOARD REFRESH
// ═══════════════════════════════════════════════════════════
async function handlePolledResult(result, today) {
  renderLatestResult(result);
  if (result.draw_date !== today) return;
  if (result.status !== 'conflict' && state.smartRefreshSeenDate !== today) {
    state.smartRefreshSeenDate = today;
    toast(`✅ Kết quả ngày ${today} vừa cập nhật! Giải đặc biệt: ${result.special_prize}`, 'success');
  }
  const signature = JSON.stringify([result.draw_date, result.special_prize,
    result.last_two, result.status, result.updated_at]);
  const now = Date.now();
  // Check results each minute, but refresh other data only on a revision or every 5 minutes.
  if (signature === state.smartRefreshSignature && now - state.smartRefreshAt < 300000) return;
  state.smartRefreshSignature = signature;
  state.smartRefreshAt = now;
  await refreshDashboard();
}

function updatePageStatus(page = state.currentPage) {
  const updated = state.pageUpdatedAt.get(page);
  el('page-update-status').textContent = updated
    ? `Cập nhật lúc ${updated.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })}`
    : 'Chưa tải dữ liệu';
}

async function refreshDashboard() {
  const page = state.currentPage;
  const version = ++state.refreshVersion;
  el('page-progress').hidden = false;
  el('page-update-status').textContent = 'Đang cập nhật dữ liệu…';
  el('page-feedback').hidden = true;
  el('main-content').setAttribute('aria-busy', 'true');
  setBusy(el('refresh-page-btn'), true, 'Đang tải…');
  setBusy(el('retry-page-btn'), true, 'Đang tải…');
  const loaders = {
    overview: [loadMetrics, loadLatestResult],
    results: [loadResults],
    'two-digit': [loadLatestPrediction, loadPredictionHistory],
    'fortune-two-digit': [loadLatestLogisticPrediction, loadLogisticPredictionHistory,
      loadModelComparison, loadRollingModelComparison],
    'one-digit': [loadLatestCatBoostPrediction, loadCatBoostHistory,
      loadCatBoostComparison, loadCatBoostRecentNumbers],
    backtest: [loadBacktests, loadDigitBacktests],
  };
  try {
    const results = await Promise.allSettled((loaders[page] || loaders.overview).map(load => load()));
    if (version !== state.refreshVersion || page !== state.currentPage) return;
    const failed = results.filter(result => result.status === 'rejected');
    if (failed.length) {
      el('page-feedback-message').textContent = failed.length === results.length
        ? 'Chưa tải được dữ liệu. Kiểm tra kết nối rồi thử lại; dữ liệu đã hiển thị được giữ nguyên.'
        : 'Một phần dữ liệu chưa cập nhật được. Bạn có thể tiếp tục xem hoặc thử tải lại.';
      el('page-feedback').hidden = false;
      el('page-update-status').textContent = 'Cập nhật chưa hoàn tất';
    } else {
      state.pageUpdatedAt.set(page, new Date());
      updatePageStatus(page);
    }

    // Luôn tô màu các số vừa ra; công tắc chỉ quyết định có loại chúng khỏi dãy
    // được chọn hay không. Số ở kỳ mới nhất nhận ngôi sao duy nhất trên bảng.
    if (page === 'one-digit') renderCatBoostPrediction(state.latestCatBoostPrediction);

    // Khi dữ liệu kết quả vừa được đồng bộ, cập nhật lại ngay tập loại trừ
    // đang bật để bảng hiển thị và chuỗi sao chép không dùng danh sách cũ.
    if (page === 'two-digit' && state.excludeRecentEnabled) {
      await loadRecentNumbers(state.excludeRecentDays);
      updateExcludeRecentChips();
      renderNumberGrid(state.latestPrediction);
      updateSelectedExport(state.latestPrediction);
    }
    if (page === 'fortune-two-digit' && state.fortuneExcludeRecentEnabled) {
      await loadFortuneRecentNumbers(state.fortuneExcludeRecentDays);
      updateFortuneExcludeRecentChips();
      renderFortunePrediction(state.latestLogisticPrediction);
    }
  } catch (error) {
    if (version !== state.refreshVersion || page !== state.currentPage) return;
    el('page-feedback-message').textContent = `Chưa cập nhật được bộ lọc: ${error.message}`;
    el('page-feedback').hidden = false;
    el('page-update-status').textContent = 'Cập nhật chưa hoàn tất';
  } finally {
    if (version === state.refreshVersion && page === state.currentPage) {
      el('page-progress').hidden = true;
      el('main-content').setAttribute('aria-busy', 'false');
      setBusy(el('refresh-page-btn'), false);
      setBusy(el('retry-page-btn'), false);
    }
  }
}

async function runAction(button, busyLabel, action, successMessage) {
  setBusy(button, true, busyLabel);
  el('action-status').textContent = busyLabel;
  try {
    const result = await action();
    const message = successMessage(result);
    if (el('automation-dialog').open) el('automation-message').textContent = message;
    toast(message, 'success');
    await refreshDashboard();
  } catch (error) {
    if (el('automation-dialog').open) el('automation-message').textContent = error.message;
    toast(error.message, 'error');
  } finally {
    setBusy(button, false);
    el('action-status').textContent = 'Sẵn sàng';
  }
}

// ═══════════════════════════════════════════════════════════
// EXCLUDE RECENT TOGGLE
// ═══════════════════════════════════════════════════════════
function initExcludeRecentToggle() {
  const toggle = el('exclude-recent-toggle');
  const daysWrap = el('exclude-recent-days-wrap');
  const daysSelect = el('exclude-recent-days');

  async function applyToggle() {
    state.excludeRecentEnabled = toggle.checked;
    state.excludeRecentDays = Number(daysSelect.value);

    daysWrap.style.display = toggle.checked ? '' : 'none';

    if (toggle.checked) {
      await loadRecentNumbers(state.excludeRecentDays);
    } else {
      state.recentNumbers = [];
    }
    updateExcludeRecentChips();
    renderNumberGrid(state.latestPrediction);
    updateSelectedExport(state.latestPrediction);
  }

  toggle.addEventListener('change', applyToggle);

  daysSelect.addEventListener('change', async () => {
    if (!state.excludeRecentEnabled) return;
    state.excludeRecentDays = Number(daysSelect.value);
    await loadRecentNumbers(state.excludeRecentDays);
    updateExcludeRecentChips();
    renderNumberGrid(state.latestPrediction);
    updateSelectedExport(state.latestPrediction);
  });
}

// ═══════════════════════════════════════════════════════════
// FORTUNE EXCLUDE RECENT TOGGLE
// ─────────────────────────────────────────────────────────────────────────────
function updateFortuneExcludeRecentChips() {
  const chips = el('fortune-excluded-recent-chips');
  if (!chips) return;
  if (!state.fortuneExcludeRecentEnabled || state.fortuneRecentNumbers.length === 0) {
    chips.style.display = 'none';
    chips.replaceChildren();
    return;
  }
  chips.replaceChildren();
  const label = document.createElement('span');
  label.className = 'fortune-excluded-label';
  label.textContent = 'Đang loại:';
  chips.append(label);
  state.fortuneRecentNumbers.forEach(({ draw_date, last_two }) => {
    const chip = document.createElement('span');
    chip.className = 'excluded-recent-chip';
    chip.title = `Số ${last_two} đã trúng ngày ${draw_date}`;
    const number = document.createElement('span');
    number.textContent = last_two;
    const date = document.createElement('span');
    date.className = 'excluded-recent-chip-date';
    date.textContent = draw_date;
    chip.append(number, date);
    chips.append(chip);
  });
  chips.style.display = 'flex';
}

function getFortuneExcludedRecentSet() {
  return new Set(
    state.fortuneExcludeRecentEnabled
      ? state.fortuneRecentNumbers.map(result => result.last_two)
      : []
  );
}

function initFortuneExcludeRecentToggle() {
  const toggle = el('fortune-exclude-recent-toggle');
  const daysWrap = el('fortune-exclude-recent-days-wrap');
  const daysSelect = el('fortune-exclude-recent-days');

  if (!toggle) return;

  async function applyFortuneToggle() {
    state.fortuneExcludeRecentEnabled = toggle.checked;
    state.fortuneExcludeRecentDays = Number(daysSelect.value);

    daysWrap.style.display = toggle.checked ? '' : 'none';

    if (toggle.checked) {
      await loadFortuneRecentNumbers(state.fortuneExcludeRecentDays);
    } else {
      state.fortuneRecentNumbers = [];
    }
    updateFortuneExcludeRecentChips();
    renderFortunePrediction(state.latestLogisticPrediction);
  }

  toggle.addEventListener('change', applyFortuneToggle);

  daysSelect.addEventListener('change', async () => {
    if (!state.fortuneExcludeRecentEnabled) return;
    state.fortuneExcludeRecentDays = Number(daysSelect.value);
    await loadFortuneRecentNumbers(state.fortuneExcludeRecentDays);
    updateFortuneExcludeRecentChips();
    renderFortunePrediction(state.latestLogisticPrediction);
  });
}

async function loadFortuneRecentNumbers(days) {
  try {
    const data = await api(`/api/results/recent-last-two?days=${days}`);
    state.fortuneRecentNumbers = data.results || [];
    return state.fortuneRecentNumbers;
  } catch (error) {
    console.warn('Không tải được số vừa ra cho trang Thần Tài:', error);
    state.fortuneRecentNumbers = [];
    return [];
  }
}
// TAB SYSTEM
// ═══════════════════════════════════════════════════════════
function initTabs() {
  const tabs = [...document.querySelectorAll('.tab-btn')];
  tabs.forEach((btn, index) => {
    btn.setAttribute('aria-selected', String(btn.classList.contains('active')));
    btn.tabIndex = btn.classList.contains('active') ? 0 : -1;
    btn.setAttribute('aria-controls', btn.dataset.tab === 'excluded' ? 'excluded-panel' : 'number-grid');
    btn.addEventListener('keydown', event => {
      const next = { ArrowRight: (index + 1) % tabs.length, ArrowLeft: (index + tabs.length - 1) % tabs.length,
        Home: 0, End: tabs.length - 1 }[event.key];
      if (next === undefined) return;
      event.preventDefault();
      tabs[next].focus();
      tabs[next].click();
    });
    btn.addEventListener('click', () => {
      tabs.forEach(tab => {
        const active = tab === btn;
        tab.classList.toggle('active', active);
        tab.setAttribute('aria-selected', String(active));
        tab.tabIndex = active ? 0 : -1;
      });
      state.currentTab = btn.dataset.tab;
      // Toolbar only useful for all/selected
      el('grid-toolbar').style.display = state.currentTab === 'excluded' ? 'none' : '';
      renderNumberGrid(state.latestPrediction);
      updateSelectedExport(state.latestPrediction);
    });
  });
}

// ═══════════════════════════════════════════════════════════
// SORT BUTTONS
// ═══════════════════════════════════════════════════════════
function initSortButtons() {
  document.querySelectorAll('.sort-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.sort-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.currentSort = btn.dataset.sort;
      renderNumberGrid(state.latestPrediction);
      updateSelectedExport(state.latestPrediction);
    });
  });
}

// ═══════════════════════════════════════════════════════════
// EVENT LISTENERS
// ═══════════════════════════════════════════════════════════
el('automation-open-btn').addEventListener('click', openAutomationDialog);
el('scheduler-pill').addEventListener('click', openAutomationDialog);
el('automation-close-btn').addEventListener('click', () => window.DashboardUI.closeDialog(el('automation-dialog')));
el('refresh-page-btn').addEventListener('click', () => refreshDashboard());
el('retry-page-btn').addEventListener('click', () => refreshDashboard());
el('results-more-btn').addEventListener('click', () => {
  // The inline status contains the error and the same button can retry.
  loadResults({ append: true }).catch(() => {});
});
el('replay-form').addEventListener('submit', event => {
  event.preventDefault();
  const payload = { prediction_date: el('replay-date').value, selected_count: Number(el('replay-count').value) };
  runAction(el('replay-run-btn'), 'Đang hồi kiểm cả 3 mô hình…',
    () => api('/api/prediction-replays/generate', { method: 'POST', body: JSON.stringify(payload) }),
    result => `Đã bổ sung ${result.models.filter(model => model.created).length} bản hồi kiểm ngày ${result.prediction_date}. Xem trong lịch sử từng mô hình.`);
});
el('automation-run-btn').addEventListener('click', () => runAction(
  el('automation-run-btn'), 'Đang đồng bộ và tạo dự đoán…',
  async () => {
    try { return await api('/api/auto-daily', { method: 'POST' }); }
    finally { await loadHealth(); }
  },
  result => result.status === 'already_running' ? 'Một lượt tự động đang chạy; đợi hoàn tất rồi kiểm tra lại.'
    : result.status === 'throttled' ? 'Vừa chạy tự động xong. Đợi 30 giây rồi thử lại nếu cần.'
    : result.status === 'waiting_result' ? 'Đã đồng bộ. Đang chờ kết quả hợp lệ để tạo dự đoán ngày tiếp theo.'
      : result.status === 'disabled' ? 'Đã đồng bộ; AUTO_PREDICTION đang tắt trên máy chủ.'
        : `Đã kiểm tra và bổ sung các dự đoán ngày ${result.target_date}.`,
));

el('backfill-btn').addEventListener('click', () => runAction(
  el('backfill-btn'), '⬇ Đang kiểm tra và bổ sung dữ liệu…',
  () => api('/api/sync/backfill?start_year=2019', { method: 'POST' }),
  (result) => {
    const fallback = result.source_failures
      ? ` · ${result.source_failures} lượt nguồn lỗi, đã dùng nguồn dự phòng`
      : ` · ${result.source_successes} lượt nguồn thành công`;
    const skipped = result.skipped_years
      ? ` · bỏ qua ${result.skipped_years} năm đã đầy đủ`
      : '';
    const failed = result.failed_years
      ? ` · ${result.failed_years} năm chưa đồng bộ được`
      : '';
    return `Đã nhận ${result.records_received} kết quả, thêm ${result.inserted}, ghi ${result.write_operations} thay đổi${skipped}${failed}${fallback}.`;
  },
));

el('sync-btn').addEventListener('click', () => runAction(
  el('sync-btn'), '🔄 Đang đồng bộ…',
  () => api('/api/sync/current', { method: 'POST' }),
  (result) => {
    const sourceState = result.sync.source_failures
      ? `${result.sync.source_successes} nguồn thành công, ${result.sync.source_failures} nguồn lỗi (fallback đã hoạt động)`
      : `${result.sync.source_successes} nguồn thành công`;
    const duration = result.sync.duration_ms != null
      ? ` · ${(result.sync.duration_ms / 1000).toFixed(1)} giây`
      : '';
    return `Đồng bộ ${result.sync.records_received} kết quả · ghi ${result.sync.write_operations ?? '—'} thay đổi · ${sourceState}${duration} · đối chiếu ${result.evaluation.evaluated} bộ 2 số và ${result.digit_evaluation?.evaluated || 0} bộ 1 số.`;
  },
));

el('evaluate-btn').addEventListener('click', () => runAction(
  el('evaluate-btn'), '✓ Đang đối chiếu…',
  () => api('/api/evaluations/run', { method: 'POST' }),
  (result) => `Đã đối chiếu: bộ 2 số ${result.evaluated} kỳ; bộ 1 số ${result.digit_evaluation?.evaluated || 0} kỳ.`,
));

el('prediction-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button');
  const payload = { selected_count: Number(el('selected-count').value) };
  runAction(
    button, '🔒 Đang tạo snapshot…',
    () => api('/api/predictions/generate', { method: 'POST', body: JSON.stringify(payload) }),
    (result) => result.created
      ? `✅ Đã khóa prediction ngày ${result.prediction.prediction_date}.`
      : `Prediction ngày ${result.prediction.prediction_date} đã tồn tại — không ghi đè.`,
  );
});

el('fortune-prediction-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button');
  const payload = { selected_count: Number(el('fortune-selected-count').value) };
  runAction(
    button, '🧧 Đang huấn luyện và khóa snapshot…',
    () => api('/api/logistic-predictions/generate', { method: 'POST', body: JSON.stringify(payload) }),
    (result) => result.created
      ? `Đã khóa dự đoán Logistic ngày ${result.prediction.prediction_date}.`
      : `Dự đoán Logistic ngày ${result.prediction.prediction_date} đã tồn tại.`,
  );
});

el('catboost-prediction-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button');
  const payload = { selected_count: Number(el('catboost-selected-count').value) };
  runAction(
    button, '🐾 CatBoost đang huấn luyện…',
    () => api('/api/catboost-predictions/generate', { method: 'POST', body: JSON.stringify(payload) }),
    (result) => result.created
      ? `✅ Đã khóa CatBoost Top ${result.prediction.selected_count} ngày ${result.prediction.prediction_date}.`
      : `Snapshot CatBoost ngày ${result.prediction.prediction_date} đã tồn tại — không ghi đè.`,
  );
});

el('backtest-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button');
  const minTrain = Number(el('backtest-min-train').value) || 365;
  runAction(
    button, '▶ Đang walk-forward…',
    () => api('/api/backtests/run', {
      method: 'POST',
      body: JSON.stringify({
        selected_count: Number(el('backtest-count').value),
        minimum_training_draws: minTrain,
      }),
    }),
    (result) => {
      renderBacktestSummary(result);
      return `Backtest hoàn tất ${result.total_predictions} kỳ · hit ${formatPercent(result.hit_rate)}.`;
    },
  );
});

el('digit-backtest-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button');
  const minimumTrainingDraws = Number(el('digit-backtest-min-train').value) || 365;
  runAction(
    button, '▶ Đang backtest Top‑1…',
    () => api('/api/digit-backtests/run', {
      method: 'POST',
      body: JSON.stringify({ minimum_training_draws: minimumTrainingDraws }),
    }),
    (result) => {
      renderDigitBacktestSummary(result);
      return `Backtest 1 số: ${result.hits}/${result.total_predictions} HIT · ${formatPercent(result.hit_rate)}.`;
    },
  );
});

el('detail-modal-close').addEventListener('click', closePredictionDetail);
el('prediction-detail-modal').addEventListener('close', () => { state.detailRequest += 1; });
el('detail-retry-btn').addEventListener('click', () => openPredictionDetail(state.detailId));

// ═══════════════════════════════════════════════════════════
// SMART AUTO-REFRESH — Tự động cập nhật sau khi có kết quả XSMB
// ═══════════════════════════════════════════════════════════

async function startSmartAutoRefresh() {
  let settings = {};
  try {
    settings = await api('/api/settings/public', { cache: 'no-store' });
  } catch (error) {
    console.warn('Using default result refresh schedule:', error);
  }
  state.resultPoller?.stop();
  state.resultPoller = createResultPoller({
    api,
    timezone: settings.timezone,
    startTime: settings.result_poll_start_time,
    intervalSeconds: settings.result_poll_interval_seconds,
    onResult: handlePolledResult,
  });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) state.resultPoller.wake();
  });
  window.addEventListener('online', () => state.resultPoller.wake());
  await state.resultPoller.start();
}

(async () => {
  initThemeToggle();
  initPageNavigation();
  initTabs();
  initSortButtons();
  initExcludeRecentToggle();
  initExportBar();
  initFortunePage();
  initCatBoostPage();
  startCountdown();
  startSmartAutoRefresh(); // Kiểm tra kết quả mỗi 10 giây từ 18:30

  await Promise.allSettled([loadHealth(), refreshDashboard()]);
})();

/* ============================================================
   XSMB Research Lab — app.js
   ============================================================ */

// ── State ──────────────────────────────────────────────────
const state = {
  currentPage: 'overview',
  latestPrediction: null,
  latestDigitPrediction: null,
  toastTimer: null,
  currentTab: 'all',       // 'all' | 'selected' | 'excluded'
  currentSort: 'rank',     // 'rank' | 'number' | 'days'
  countdownTimer: null,
  autoRefreshTimer: null,
  smartRefreshTimer: null, // Smart auto-refresh timer
  smartRefreshSeenDate: null, // Ngày kết quả đã phát hiện
  detailCache: new Map(),
  // Exclude recent numbers feature
  excludeRecentEnabled: false,
  excludeRecentDays: 3,
  recentNumbers: [],       // Array of { draw_date, last_two }
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
    eyebrow: 'DATA PIPELINE',
    title: 'Kết quả và đồng bộ dữ liệu',
    description: 'Thu thập kết quả, đối chiếu dự đoán pending và xem dữ liệu đã lưu trong MongoDB.',
  },
  'two-digit': {
    path: '/du-doan-2-so',
    eyebrow: 'TWO DIGITS · 00–99',
    title: 'Dự đoán hai số cuối',
    description: 'Tạo snapshot Top 60–80, xem bảng điểm và lịch sử đánh giá từng ngày.',
  },
  'one-digit': {
    path: '/du-doan-1-so',
    eyebrow: 'LAST DIGIT · 0–9',
    title: 'Dự đoán một số cuối',
    description: 'Xếp hạng 10 chữ số, chọn Top‑1 và theo dõi kết quả HIT/MISS riêng.',
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
  return Object.entries(PAGE_CONFIG).find(([, config]) => config.path === normalized)?.[0] || 'overview';
}

function showPage(pageName, { updateHistory = false } = {}) {
  const page = PAGE_CONFIG[pageName] ? pageName : 'overview';
  const config = PAGE_CONFIG[page];
  state.currentPage = page;
  document.body.dataset.currentPage = page;
  if (updateHistory && window.location.pathname !== config.path) {
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
}

function initPageNavigation() {
  showPage(pageFromPath(window.location.pathname));
  document.querySelectorAll('[data-page-link]').forEach(link => {
    link.addEventListener('click', event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      showPage(link.dataset.pageLink, { updateHistory: true });
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  });
  window.addEventListener('popstate', () => {
    showPage(pageFromPath(window.location.pathname));
  });
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
  return data;
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
  if (!button.dataset.label) button.dataset.label = button.textContent;
  button.disabled = busy;
  button.textContent = busy ? label : button.dataset.label;
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

// ═══════════════════════════════════════════════════════════
// DARK MODE TOGGLE
// ═══════════════════════════════════════════════════════════
function initThemeToggle() {
  const savedTheme = localStorage.getItem('xsmb-theme') || 'light';
  applyTheme(savedTheme);

  el('theme-toggle').addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme');
    applyTheme(current === 'dark' ? 'light' : 'dark');
  });
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('xsmb-theme', theme);
  el('theme-icon').textContent = theme === 'dark' ? '☀️' : '🌙';
  el('theme-label').textContent = theme === 'dark' ? 'Light mode' : 'Dark mode';
}

// ═══════════════════════════════════════════════════════════
// COUNTDOWN TIMER đến 18:15 hàng ngày
// ═══════════════════════════════════════════════════════════
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
    const health = await api('/api/health');
    el('health-pill').textContent = `MongoDB · ${health.status}`;
    el('health-pill').className = 'pill ok';
    el('scheduler-pill').textContent = health.scheduler_enabled ? '⏱ Scheduler bật' : 'Scheduler tắt';
    el('scheduler-pill').className = health.scheduler_enabled ? 'pill ok' : 'pill neutral';
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
  const result = await api('/api/results/latest');
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
    reasons.push(`📅 Gan ${score.days_since_last_hit} ngày (lâu bất thường)`);
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
    root.innerHTML = '<div class="empty-state" style="grid-column:1/-1">Chưa có prediction. Hãy tạo dự đoán.</div>';
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
        ? `Gan ${score.days_since_last_hit} ngày` : 'Chưa từng ra';
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
// LATEST PREDICTION
// ═══════════════════════════════════════════════════════════
async function loadLatestPrediction() {
  const prediction = await api('/api/predictions/latest');
  state.latestPrediction = prediction;
  renderNumberGrid(prediction);

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
    chips.push({ text: '⏳ PENDING', cls: 'pending-chip' });
  }

  chips.forEach(({ text, cls }) => {
    const node = document.createElement('span');
    node.className = `meta-chip ${cls}`.trim();
    node.textContent = text;
    meta.append(node);
  });
}

// ═══════════════════════════════════════════════════════════
// LAST DIGIT 0-9 — TOP 1
// ═══════════════════════════════════════════════════════════
function renderDigitPrediction(prediction) {
  const grid = el('digit-grid');
  const highlight = el('digit-highlight');
  const meta = el('digit-prediction-meta');
  grid.replaceChildren();
  highlight.replaceChildren();
  meta.replaceChildren();

  if (!prediction) {
    highlight.className = 'digit-highlight empty-state';
    highlight.textContent = 'Chưa có dự đoán một số cuối.';
    for (let digit = 0; digit < 10; digit += 1) {
      const node = document.createElement('div');
      node.className = 'digit-cell';
      const number = document.createElement('span');
      number.className = 'digit-cell-number';
      number.textContent = String(digit);
      const score = document.createElement('span');
      score.className = 'digit-cell-probability';
      score.textContent = '—';
      node.append(number, score);
      grid.append(node);
    }
    return;
  }

  const evaluation = prediction.evaluation || { status: 'pending' };
  const actual = evaluation.actual_digit;
  highlight.className = 'digit-highlight';
  const label = document.createElement('span');
  label.className = 'digit-highlight-label';
  label.textContent = 'Chữ số có điểm cao nhất';
  const number = document.createElement('strong');
  number.className = 'digit-highlight-number';
  number.textContent = prediction.predicted_digit;
  const score = document.createElement('span');
  score.className = 'digit-highlight-score';
  score.textContent = `Điểm thô ${formatPercent(prediction.prediction_probability, 3)} · baseline 10%`;
  highlight.append(label, number, score);

  const chips = [
    { text: `📅 ${prediction.prediction_date}`, cls: '' },
    { text: `Train đến ${prediction.trained_through}`, cls: '' },
    { text: `${Number(prediction.training_draw_count || 0).toLocaleString('vi-VN')} kỳ train`, cls: '' },
  ];
  if (evaluation.status === 'evaluated') {
    chips.push({ text: evaluation.hit ? '✅ HIT' : '❌ MISS', cls: evaluation.hit ? 'hit-chip' : 'miss-chip' });
    chips.push({ text: `Kết quả: ${actual}`, cls: '' });
  } else {
    chips.push({ text: '⏳ PENDING', cls: 'pending-chip' });
  }
  chips.forEach(({ text, cls }) => {
    const node = document.createElement('span');
    node.className = `meta-chip ${cls}`.trim();
    node.textContent = text;
    meta.append(node);
  });

  [...(prediction.scores || [])]
    .sort((a, b) => Number(a.digit) - Number(b.digit))
    .forEach(item => {
      const isTop = item.digit === prediction.predicted_digit;
      const isActual = item.digit === actual;
      const node = document.createElement('div');
      node.className = `digit-cell${isTop ? ' top' : ''}${isActual ? ' actual' : ''}${isTop && evaluation.hit ? ' hit' : ''}`;
      node.setAttribute('role', 'gridcell');
      const digit = document.createElement('span');
      digit.className = 'digit-cell-number';
      digit.textContent = item.digit;
      const probability = document.createElement('span');
      probability.className = 'digit-cell-probability';
      probability.textContent = formatPercent(item.probability, 3);
      const rank = document.createElement('span');
      rank.className = 'digit-cell-rank';
      rank.textContent = `Rank #${item.rank}`;
      node.append(digit, probability, rank);
      node.title = `Chữ số ${item.digit} · rank #${item.rank} · điểm thô ${formatPercent(item.probability, 4)}`;
      grid.append(node);
    });
}

async function loadLatestDigitPrediction() {
  const prediction = await api('/api/digit-predictions/latest');
  state.latestDigitPrediction = prediction;
  renderDigitPrediction(prediction);
}

async function loadDigitPredictionHistory() {
  const predictions = await api('/api/digit-predictions?limit=50');
  const body = el('digit-prediction-history');
  body.replaceChildren();
  if (!predictions.length) {
    const row = document.createElement('tr');
    const td = cell('Chưa có dự đoán một số cuối');
    td.colSpan = 7;
    td.style.textAlign = 'center';
    row.append(td);
    body.append(row);
    return;
  }

  predictions.forEach(prediction => {
    const evaluation = prediction.evaluation || { status: 'pending' };
    const row = document.createElement('tr');
    row.append(
      cell(prediction.prediction_date),
      cell(prediction.predicted_digit),
      cell(formatPercent(prediction.prediction_probability, 3)),
      cell(formatPercent(prediction.random_baseline, 0)),
      cell(prediction.trained_through),
      cell(evaluation.actual_digit || '—'),
    );
    const status = document.createElement('td');
    status.append(evaluation.status === 'evaluated'
      ? badge(evaluation.hit ? 'HIT' : 'MISS', evaluation.hit ? 'hit' : 'miss')
      : badge('PENDING', 'pending'));
    row.append(status);
    body.append(row);
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
  el('prediction-detail-modal').hidden = true;
  document.body.classList.remove('modal-open');
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
    detailSummaryItem('Đánh giá', evaluation.status === 'evaluated' ? (evaluation.hit ? 'HIT' : 'MISS') : 'PENDING'),
    detailSummaryItem('Mô hình', prediction.model_version),
    detailSummaryItem('Số lượng chọn', `Top ${prediction.selected_count}`),
    detailSummaryItem('Điểm coverage thô', formatPercent(prediction.coverage_probability, 4)),
    detailSummaryItem('Ngưỡng cut-off', formatPercent(prediction.cutoff_probability, 4)),
    detailSummaryItem('Số kỳ huấn luyện', Number(prediction.training_draw_count || 0).toLocaleString('vi-VN')),
    detailSummaryItem('Train đến', prediction.trained_through),
    detailSummaryItem('Khóa lúc', formatDateTime(prediction.locked_at)),
    detailSummaryItem('Kết quả đặc biệt', evaluation.actual_special_prize || 'Chưa có'),
    detailSummaryItem('Hai số cuối', actual || 'Chưa có'),
    detailSummaryItem('Dataset hash', prediction.dataset_hash || '—'),
  );

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
  const modal = el('prediction-detail-modal');
  const loading = el('prediction-detail-loading');
  const content = el('prediction-detail-content');
  modal.hidden = false;
  loading.hidden = false;
  loading.textContent = 'Đang tải prediction…';
  content.hidden = true;
  document.body.classList.add('modal-open');
  el('detail-modal-close').focus();
  try {
    let prediction = state.detailCache.get(predictionId);
    if (!prediction) {
      prediction = await api(`/api/predictions/${encodeURIComponent(predictionId)}`);
      state.detailCache.set(predictionId, prediction);
    }
    renderPredictionDetail(prediction);
    loading.hidden = true;
    content.hidden = false;
  } catch (error) {
    loading.textContent = `Không tải được chi tiết: ${error.message}`;
    toast(error.message, 'error');
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
      cell(pred.prediction_date),
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
      statusCell.append(badge('PENDING', 'pending'));
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
async function loadResults() {
  const results = await api('/api/results?limit=50');
  const body = el('result-history');
  body.replaceChildren();

  results.forEach((result) => {
    const row = document.createElement('tr');
    row.append(cell(result.draw_date), cell(result.special_prize), cell(result.last_two));
    const statusCell = document.createElement('td');
    statusCell.append(badge(result.status, result.status === 'conflict' ? 'conflict' : 'observed'));
    row.append(statusCell);
    row.append(cell(Object.values(result.sources || {}).map(s => s.name).join(', ') || '—'));
    body.append(row);
  });
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
async function refreshDashboard() {
  await Promise.allSettled([
    loadMetrics(),
    loadLatestResult(),
    loadLatestPrediction(),
    loadLatestDigitPrediction(),
    loadPredictionHistory(),
    loadDigitPredictionHistory(),
    loadResults(),
    loadBacktests(),
    loadDigitBacktests(),
  ]);
}

async function runAction(button, busyLabel, action, successMessage) {
  setBusy(button, true, busyLabel);
  el('action-status').textContent = busyLabel;
  try {
    const result = await action();
    toast(successMessage(result), 'success');
    await refreshDashboard();
  } catch (error) {
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
  }

  toggle.addEventListener('change', applyToggle);

  daysSelect.addEventListener('change', async () => {
    if (!state.excludeRecentEnabled) return;
    state.excludeRecentDays = Number(daysSelect.value);
    await loadRecentNumbers(state.excludeRecentDays);
    updateExcludeRecentChips();
    renderNumberGrid(state.latestPrediction);
  });
}

// ═══════════════════════════════════════════════════════════
// TAB SYSTEM
// ═══════════════════════════════════════════════════════════
function initTabs() {
  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.currentTab = btn.dataset.tab;
      // Toolbar only useful for all/selected
      el('grid-toolbar').style.display = state.currentTab === 'excluded' ? 'none' : '';
      renderNumberGrid(state.latestPrediction);
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
    });
  });
}

// ═══════════════════════════════════════════════════════════
// EVENT LISTENERS
// ═══════════════════════════════════════════════════════════
el('backfill-btn').addEventListener('click', () => runAction(
  el('backfill-btn'), '⬇ Đang tải lịch sử…',
  () => api('/api/sync/backfill?start_year=2019', { method: 'POST' }),
  (result) => {
    const fallback = result.source_failures
      ? ` · ${result.source_failures} lượt nguồn lỗi, đã dùng nguồn dự phòng`
      : ` · ${result.source_successes} lượt nguồn thành công`;
    return `Đã xử lý ${result.records_received} kết quả, thêm mới ${result.inserted}${fallback}.`;
  },
));

el('sync-btn').addEventListener('click', () => runAction(
  el('sync-btn'), '🔄 Đang đồng bộ…',
  () => api('/api/sync/current', { method: 'POST' }),
  (result) => {
    const sourceState = result.sync.source_failures
      ? `${result.sync.source_successes} nguồn thành công, ${result.sync.source_failures} nguồn lỗi (fallback đã hoạt động)`
      : `${result.sync.source_successes} nguồn thành công`;
    return `Đồng bộ ${result.sync.records_received} kết quả · ${sourceState} · đối chiếu ${result.evaluation.evaluated} bộ 2 số và ${result.digit_evaluation?.evaluated || 0} bộ 1 số.`;
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

el('digit-prediction-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button');
  const payload = {};
  runAction(
    button, '🔒 Đang xếp hạng 0–9…',
    () => api('/api/digit-predictions/generate', { method: 'POST', body: JSON.stringify(payload) }),
    (result) => result.created
      ? `✅ Đã khóa số ${result.prediction.predicted_digit} cho ngày ${result.prediction.prediction_date}.`
      : `Dự đoán một số ngày ${result.prediction.prediction_date} đã tồn tại — không ghi đè.`,
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
el('prediction-detail-modal').addEventListener('click', (event) => {
  if (event.target === event.currentTarget) closePredictionDetail();
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && !el('prediction-detail-modal').hidden) {
    closePredictionDetail();
  }
});

// ═══════════════════════════════════════════════════════════
// SMART AUTO-REFRESH — Tự động cập nhật sau khi có kết quả XSMB
// ═══════════════════════════════════════════════════════════

/**
 * Khởng giờ polling: 18:15 – 21:00 giờ Việt Nam.
 * Cứ 2 phút gọi /api/results/latest một lần.
 * Nếu kết quả hôm nay xuất hiện lần đầu → refresh dashboard + toast.
 * Dừng polling khi ra khỏi khung giờ hoặc đã nhận kết quả.
 */
function startSmartAutoRefresh() {
  function isInRefreshWindow() {
    const now = new Date();
    // Convert to UTC+7 (Việt Nam)
    const vnOffset = 7 * 60;
    const utcMin = now.getUTCHours() * 60 + now.getUTCMinutes();
    const vnMin = (utcMin + vnOffset) % (24 * 60);
    // 18:15 = 1095 phút, 21:00 = 1260 phút
    return vnMin >= 1095 && vnMin < 1260;
  }

  function todayVN() {
    const now = new Date();
    const vnTime = new Date(now.getTime() + 7 * 60 * 60 * 1000);
    return vnTime.toISOString().slice(0, 10);
  }

  async function poll() {
    // Dừng nếu ngoài khung giờ
    if (!isInRefreshWindow()) {
      state.smartRefreshTimer = setTimeout(poll, 5 * 60 * 1000); // thử lại sau 5 phút
      return;
    }

    const today = todayVN();

    try {
      const result = await api('/api/results/latest');
      if (result && result.draw_date === today) {
        // Kết quả hôm nay đã xuất hiện!
        if (state.smartRefreshSeenDate !== today) {
          state.smartRefreshSeenDate = today;
          // Refresh toàn bộ dashboard
          await refreshDashboard();
          // Reload exclude-recent nếu đang bật
          if (state.excludeRecentEnabled) {
            await loadRecentNumbers(state.excludeRecentDays);
            updateExcludeRecentChips();
            renderNumberGrid(state.latestPrediction);
          }
          toast(`✅ Kết quả ngày ${today} vừa cập nhật! Giải đặc biệt: ${result.special_prize}`, 'success');
        }
      }
    } catch (err) {
      // Không throw — để polling tiếp tục
      console.warn('Smart refresh poll failed:', err);
    }

    // Tiếp tục poll mỗi 2 phút
    state.smartRefreshTimer = setTimeout(poll, 2 * 60 * 1000);
  }

  // Khởi động: nếu đang trong khung giờ thì poll ngay, ngược lại đợi đến đó
  if (isInRefreshWindow()) {
    poll();
  } else {
    // Tính số ms đến 18:15 VN tiếp theo
    const now = new Date();
    const vnNow = new Date(now.getTime() + 7 * 60 * 60 * 1000);
    const vnToday1815 = new Date(vnNow);
    vnToday1815.setUTCHours(11, 15, 0, 0); // 18:15 VN = 11:15 UTC
    let msUntilWindow = vnToday1815.getTime() - now.getTime();
    if (msUntilWindow < 0) msUntilWindow += 24 * 60 * 60 * 1000; // ngày mai
    state.smartRefreshTimer = setTimeout(poll, msUntilWindow);
  }
}

(async () => {
  initThemeToggle();
  initPageNavigation();
  initTabs();
  initSortButtons();
  initExcludeRecentToggle();
  startCountdown();
  startSmartAutoRefresh(); // Tự động cập nhật kết quả sau 18:15

  try {
    await loadHealth();
    await refreshDashboard();
  } catch (error) {
    toast(error.message, 'error');
  }
})();

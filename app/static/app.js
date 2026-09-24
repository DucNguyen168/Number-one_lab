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
  smartRefreshTimer: null, // Smart auto-refresh timer
  smartRefreshSeenDate: null, // Ngày kết quả đã phát hiện
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
// SKY DRAG TOGGLE — Sun/Moon/Cloud interactive drag widget
// Kéo mây che Sun = Dark mode | che Moon = Light mode
// Thả giữa = Limbo 5s → auto-snap về gần nhất
// ═══════════════════════════════════════════════════════════
const SKY = {
  toggle: null,        // #sky-toggle
  cloud: null,         // #sky-cloud
  arrow: null,         // #sky-arrow
  countdown: null,     // .sky-countdown-bar
  dragging: false,
  didDrag: false,
  startX: 0,
  startCloudLeft: 0,
  cloudLeft: 0,        // current px from left edge of toggle
  limboTimer: null,
  limboRatio: 0.5,     // store ratio when entering limbo
};

// Ngưỡng snap: phần trăm width của toggle
const SKY_SNAP = 0.40;   // < 40% → snap moon (light), > 60% → snap sun (dark)

function initThemeToggle() {
  SKY.toggle  = el('sky-toggle');
  SKY.cloud   = el('sky-cloud');
  SKY.arrow   = el('sky-arrow');
  if (!SKY.toggle || !SKY.cloud) return;

  // Tạo countdown bar bên trong toggle
  SKY.countdown = document.createElement('div');
  SKY.countdown.className = 'sky-countdown-bar';
  SKY.toggle.appendChild(SKY.countdown);

  // Áp theme đã lưu (không animate)
  const saved = localStorage.getItem('xsmb-theme') || 'light';
  _skyApply(saved, false);

  // Keyboard toggle
  SKY.toggle.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      if (!SKY.dragging) {
        const cur = document.documentElement.getAttribute('data-theme');
        applyTheme(cur === 'dark' ? 'light' : 'dark');
      }
    }
  });

  // Click toggle (không phải drag)
  SKY.toggle.addEventListener('click', (e) => {
    if (!SKY.didDrag) {
      const cur = document.documentElement.getAttribute('data-theme');
      applyTheme(cur === 'dark' ? 'light' : 'dark');
    }
    SKY.didDrag = false;
  });

  // Mouse drag
  SKY.cloud.addEventListener('mousedown', _skyDragStart);
  window.addEventListener('mousemove', _skyDragMove);
  window.addEventListener('mouseup', _skyDragEnd);

  // Touch drag
  SKY.cloud.addEventListener('touchstart', _skyDragStart, { passive: false });
  window.addEventListener('touchmove', _skyDragMove, { passive: false });
  window.addEventListener('touchend', _skyDragEnd);
}

function _skyX(e) {
  return e.touches ? e.touches[0].clientX : e.clientX;
}

function _skyDragStart(e) {
  e.preventDefault();
  e.stopPropagation();
  SKY.dragging = true;
  SKY.didDrag  = false;

  // Lấy vị trí hiện tại của cloud
  const tRect = SKY.toggle.getBoundingClientRect();
  const cRect = SKY.cloud.getBoundingClientRect();
  SKY.cloudLeft      = cRect.left - tRect.left;
  SKY.startX         = _skyX(e);
  SKY.startCloudLeft = SKY.cloudLeft;

  SKY.cloud.classList.add('sky-no-transition');
  SKY.cloud.style.left  = SKY.cloudLeft + 'px';
  SKY.cloud.style.right = 'auto';
  SKY.toggle.classList.add('sky-dragging');

  // Hủy limbo nếu đang drag lại trong 5s
  _skyClrLimbo(false);  // false = giữ backdrop cho đến khi snap
}

function _skyDragMove(e) {
  if (!SKY.dragging) return;
  e.preventDefault();

  const dx = _skyX(e) - SKY.startX;
  if (Math.abs(dx) > 3) SKY.didDrag = true;

  const toggleW = SKY.toggle.offsetWidth;
  const cloudW  = SKY.cloud.offsetWidth;
  const minL    = 2;
  const maxL    = toggleW - cloudW - 2;
  SKY.cloudLeft = Math.max(minL, Math.min(SKY.startCloudLeft + dx, maxL));
  SKY.cloud.style.left = SKY.cloudLeft + 'px';
}

function _skyDragEnd(e) {
  if (!SKY.dragging) return;
  SKY.dragging = false;
  SKY.toggle.classList.remove('sky-dragging');
  SKY.cloud.classList.remove('sky-no-transition');

  if (!SKY.didDrag) return;

  const toggleW   = SKY.toggle.offsetWidth;
  const cloudW    = SKY.cloud.offsetWidth;
  const cloudCtr  = SKY.cloudLeft + cloudW / 2;
  const ratio     = cloudCtr / toggleW;

  if (ratio <= SKY_SNAP) {
    // Snap về moon (trái) = Light mode
    applyTheme('light');
  } else if (ratio >= (1 - SKY_SNAP)) {
    // Snap về sun (phải) = Dark mode
    applyTheme('dark');
  } else {
    // Limbo — không che cái nào
    _skyEnterLimbo(ratio);
  }
}

function _skyEnterLimbo(ratio) {
  SKY.limboRatio = ratio;
  SKY.toggle.classList.add('sky-limbo-active');
  document.body.classList.add('sky-limbo');

  // Hiển thị mũi tên chỉ hướng gần nhất
  if (SKY.arrow) {
    const nearLeft = ratio < 0.5;
    SKY.arrow.innerHTML = nearLeft
      ? '<span style="animation:none;display:inline-block;transform:scaleX(-1)">➜</span>&nbsp;Kéo về'
      : 'Kéo về&nbsp;<span style="display:inline-block">➜</span>';
    SKY.arrow.classList.add('active');
  }

  // Countdown bar
  if (SKY.countdown) {
    // Khởi động lại animation bằng cách clone node
    const newBar = SKY.countdown.cloneNode(false);
    SKY.countdown.replaceWith(newBar);
    SKY.countdown = newBar;
    SKY.countdown.classList.add('active');
  }

  // Auto-snap sau 5s
  SKY.limboTimer = setTimeout(() => {
    _skyClrLimbo(true);
    _skyApply(SKY.limboRatio < 0.5 ? 'light' : 'dark', true);
  }, 5000);
}

function _skyClrLimbo(clearBodyClass = true) {
  if (SKY.limboTimer) { clearTimeout(SKY.limboTimer); SKY.limboTimer = null; }
  if (clearBodyClass) document.body.classList.remove('sky-limbo');
  if (SKY.toggle)    SKY.toggle.classList.remove('sky-limbo-active');
  if (SKY.arrow)     { SKY.arrow.classList.remove('active'); SKY.arrow.innerHTML = ''; }
  if (SKY.countdown) { SKY.countdown.classList.remove('active'); }
}

// Hàm apply chính — đặt theme và di cloud đến đúng vị trí
function _skyApply(theme, animate = true) {
  document.documentElement.setAttribute('data-theme', theme);
  document.body.setAttribute('data-theme', theme);
  localStorage.setItem('xsmb-theme', theme);

  if (!SKY.cloud || !SKY.toggle) return;

  if (!animate) SKY.cloud.classList.add('sky-no-transition');

  const toggleW = SKY.toggle.offsetWidth || 112;
  const cloudW  = SKY.cloud.offsetWidth  || 46;

  if (theme === 'light') {
    // Cloud bên TRÁI che Moon → Light (ban ngày)
    SKY.cloud.style.right = 'auto';
    SKY.cloud.style.left  = '4px';
  } else {
    // Cloud bên PHẢI che Sun → Dark (ban đêm)
    SKY.cloud.style.right = 'auto';
    SKY.cloud.style.left  = (toggleW - cloudW - 4) + 'px';
  }

  if (!animate) {
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (SKY.cloud) SKY.cloud.classList.remove('sky-no-transition');
    }));
  }

  if (SKY.toggle) {
    SKY.toggle.setAttribute('aria-label',
      theme === 'dark' ? 'Chuyển sang chế độ Sáng' : 'Chuyển sang chế độ Tối');
  }
}

// API công khai — dùng trong toàn app
function applyTheme(theme) {
  _skyClrLimbo(true);
  _skyApply(theme, true);
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
      : '⏳ PENDING',
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
  const rain = el('fortune-glitter-rain');
  if (!rain || rain.children.length) return;

  const particleCount = 34;
  for (let index = 0; index < particleCount; index += 1) {
    const particle = document.createElement('i');
    const lane = ((index * 37) % 101) + ((index % 3) * 0.17);
    const duration = 5.8 + ((index * 13) % 37) / 10;
    const delay = -((index * 29) % 91) / 10;
    const drift = ((index * 17) % 90) - 45;
    const size = 3 + ((index * 7) % 6);
    particle.style.setProperty('--glitter-x', `${lane}%`);
    particle.style.setProperty('--glitter-duration', `${duration.toFixed(1)}s`);
    particle.style.setProperty('--glitter-delay', `${delay.toFixed(1)}s`);
    particle.style.setProperty('--glitter-drift', `${drift}px`);
    particle.style.setProperty('--glitter-size', `${size}px`);
    rain.append(particle);
  }
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
      cell(prediction.prediction_date),
      cell(prediction.selected_count),
      cell(prediction.trained_through),
      cell(evaluation.actual_last_two || '—'),
    );
    const status = document.createElement('td');
    status.append(evaluation.status === 'evaluated'
      ? badge(evaluation.hit ? 'HIT' : 'MISS', evaluation.hit ? 'hit' : 'miss')
      : badge('PENDING', 'pending'));
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

async function loadModelComparison() {
  const selectedCount = Number(el('fortune-selected-count').value);
  const comparison = await api(`/api/model-comparison?selected_count=${selectedCount}`);
  const root = el('fortune-comparison-summary');
  root.replaceChildren(
    comparisonCard('Kỳ ghép cặp', comparison.paired_predictions, `Top ${selectedCount}`),
    comparisonCard('Mô hình tần suất', formatPercent(comparison.frequency_model.hit_rate), `${comparison.frequency_model.hits} HIT`),
    comparisonCard('Mô hình Logistic', formatPercent(comparison.logistic_model.hit_rate), `${comparison.logistic_model.hits} HIT`),
    comparisonCard('Chênh lệch B − A', formatPercent(comparison.lift_logistic_vs_frequency), `Baseline ${formatPercent(comparison.baseline, 0)}`),
  );

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
    const metrics = report.metrics;
    el('fortune-historical-title').textContent =
      `${report.paired_predictions} kỳ gần nhất · ${report.start_date} đến ${report.end_date}`;
    el('fortune-historical-note').textContent =
      `Đối chiếu walk-forward song song theo dữ liệu đến ${report.dataset.last_date}. `
      + 'Báo cáo tự làm mới khi kết quả mới được đồng bộ.';
    el('fortune-historical-summary').replaceChildren(
      comparisonCard('Tần suất A', formatPercent(metrics.frequency.hit_rate), `${metrics.frequency.hits} HIT`),
      comparisonCard('Logistic B', formatPercent(metrics.logistic.hit_rate), `${metrics.logistic.hits} HIT`),
      comparisonCard('Baseline', formatPercent(metrics.baseline, 0), `Top ${selectedCount}`),
      comparisonCard('B − A', formatPercent(metrics.delta_logistic_vs_frequency), `McNemar p=${metrics.mcnemar_exact_p}`),
    );
    el('fortune-rolling-window-badge').textContent = `${report.paired_predictions} kỳ · live`;
    renderHistoricalDailyTable(report.daily);
    renderHistoricalDailyStats(report.daily);
  } catch (err) {
    console.warn('Rolling model comparison load failed:', err);
    el('fortune-historical-title').textContent = 'Chưa thể tạo đối chiếu rolling';
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
      text: evaluation.status === 'evaluated' ? (evaluation.hit ? '✅ HIT' : '❌ MISS') : '⏳ PENDING',
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
      cell(prediction.prediction_date), cell(prediction.selected_count),
      cell(prediction.trained_through), cell(formatPercent(prediction.coverage_probability)),
      cell(evaluation.actual_last_two || '—'),
    );
    const status = document.createElement('td');
    status.append(evaluation.status === 'evaluated'
      ? badge(evaluation.hit ? 'HIT' : 'MISS', evaluation.hit ? 'hit' : 'miss')
      : badge('PENDING', 'pending'));
    row.append(status, cell(prediction.model_version));
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
    card.innerHTML = `<span>${label}</span><strong>${formatPercent(model?.hit_rate)}</strong><small>${model?.hits == null ? `Top ${report.selected_count}` : `${model.hits}/${report.paired_predictions} HIT`}</small>`;
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
  note.textContent = report.note;
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
    loadLatestLogisticPrediction(),
    loadLatestCatBoostPrediction(),
    loadPredictionHistory(),
    loadLogisticPredictionHistory(),
    loadModelComparison(),
    loadRollingModelComparison(),
    loadCatBoostHistory(),
    loadCatBoostComparison(),
    loadCatBoostRecentNumbers(),
    loadResults(),
    loadBacktests(),
    loadDigitBacktests(),
  ]);

  // Luôn tô màu các số vừa ra; công tắc chỉ quyết định có loại chúng khỏi dãy
  // được chọn hay không. Số ở kỳ mới nhất nhận ngôi sao duy nhất trên bảng.
  renderCatBoostPrediction(state.latestCatBoostPrediction);

  // Khi dữ liệu kết quả vừa được đồng bộ, cập nhật lại ngay tập loại trừ
  // đang bật để bảng hiển thị và chuỗi sao chép không dùng danh sách cũ.
  if (state.excludeRecentEnabled) {
    await loadRecentNumbers(state.excludeRecentDays);
    updateExcludeRecentChips();
    renderNumberGrid(state.latestPrediction);
    updateSelectedExport(state.latestPrediction);
  }
  if (state.fortuneExcludeRecentEnabled) {
    await loadFortuneRecentNumbers(state.fortuneExcludeRecentDays);
    updateFortuneExcludeRecentChips();
    renderFortunePrediction(state.latestLogisticPrediction);
  }
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
  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
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
  initExportBar();
  initFortunePage();
  initCatBoostPage();
  startCountdown();
  startSmartAutoRefresh(); // Tự động cập nhật kết quả sau 18:15

  try {
    await loadHealth();
    await refreshDashboard();
  } catch (error) {
    toast(error.message, 'error');
  }
})();

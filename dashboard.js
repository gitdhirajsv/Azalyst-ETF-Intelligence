// ─── Azalyst Dashboard — dashboard.js ───────────────────────────────────────
// Reads status.json every 5 seconds and updates all UI components.
// No page reload. Charts update in-place using Chart.js .update().
// ────────────────────────────────────────────────────────────────────────────

const REFRESH_INTERVAL = 5000; // ms
const STATUS_FILE = 'status.json';

// ── Chart instances (created once, updated on each poll) ──────────────────
let pieChart = null;
let barChart = null;

// ── Helpers ──────────────────────────────────────────────────────────────────
function rupee(val) {
  return '₹' + Number(val).toLocaleString('en-IN');
}

function logClass(line) {
  const l = line.toLowerCase();
  if (l.includes('complete') || l.includes('started') || l.includes('dispatched')) return 'ok';
  if (l.includes('cycle') || l.includes('signal') || l.includes('intel')) return 'info';
  if (l.includes('warn') || l.includes('skip') || l.includes('error')) return 'warn';
  return '';
}

// ── DOM updaters ─────────────────────────────────────────────────────────────

function updateStats(data) {
  document.getElementById('portfolioValue').textContent  = rupee(data.portfolio_value);
  document.getElementById('totalDeposited').textContent  = rupee(data.total_deposited);
  document.getElementById('cashAvailable').textContent   = rupee(data.cash);
  document.getElementById('marketValue').textContent     = rupee(data.market_value);

  const change = data.change || '0';
  const el = document.getElementById('portfolioChange');
  el.textContent = (parseFloat(change) >= 0 ? '+' : '') + change + '% overall';
  el.className = 'stat-sub ' + (parseFloat(change) >= 0 ? 'green' : 'red');

  const pos = data.positions || [];
  document.getElementById('positionsSummary').textContent =
    pos.length + ' open · ' + (data.closed_trades || 0) + ' closed';
}

function updatePieChart(data) {
  const { labels, values } = data.allocation;
  const COLORS = ['#3b82f6', '#f59e0b', '#22c55e', '#8b5cf6', '#ef4444', '#06b6d4'];

  if (!pieChart) {
    pieChart = new Chart(document.getElementById('pieChart'), {
      type: 'pie',
      data: {
        labels,
        datasets: [{
          data: values,
          backgroundColor: COLORS.slice(0, labels.length),
          borderWidth: 2,
          borderColor: '#ffffff'
        }]
      },
      options: {
        plugins: {
          legend: {
            position: 'right',
            labels: { color: '#475569', font: { size: 12 }, padding: 12, boxWidth: 12 }
          }
        },
        responsive: true,
        animation: { duration: 400 }
      }
    });
  } else {
    pieChart.data.labels = labels;
    pieChart.data.datasets[0].data = values;
    pieChart.data.datasets[0].backgroundColor = COLORS.slice(0, labels.length);
    pieChart.update();
  }
}

function updateBarChart(data) {
  const { labels, values } = data.pnl;

  if (!barChart) {
    barChart = new Chart(document.getElementById('barChart'), {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: 'P&L (INR)',
          data: values,
          backgroundColor: values.map(v => v >= 0 ? '#3b82f6' : '#ef4444'),
          borderRadius: 5
        }]
      },
      options: {
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: '#64748b', font: { size: 12 } }, grid: { display: false } },
          y: { ticks: { color: '#64748b', font: { size: 12 } }, grid: { color: '#f1f5f9' } }
        },
        responsive: true,
        animation: { duration: 400 }
      }
    });
  } else {
    barChart.data.labels = labels;
    barChart.data.datasets[0].data = values;
    barChart.data.datasets[0].backgroundColor = values.map(v => v >= 0 ? '#3b82f6' : '#ef4444');
    barChart.update();
  }
}

function updateConfidence(data) {
  const container = document.getElementById('confidenceBars');
  const threshold = data.confidence_threshold || 62;
  document.getElementById('thresholdNote').textContent = 'Threshold: ' + threshold + '.0';

  container.innerHTML = (data.confidence || []).map(item => `
    <div class="conf-row">
      <div class="conf-label">
        <span>${item.symbol}</span>
        <span>${item.score.toFixed(1)}</span>
      </div>
      <div class="bar-bg">
        <div class="bar-fill" style="width:${Math.min(item.score, 100)}%"></div>
      </div>
    </div>
  `).join('');
}

function updateArticles(data) {
  const box = document.getElementById('articleUpdates');
  box.innerHTML = (data.articles || []).map(a => `
    <div class="msg-item">
      <span class="msg-tag ${a.tag}">${a.label}</span>${a.text}
    </div>
  `).join('');
}

function updateLogs(data) {
  const box = document.getElementById('logTail');
  const lines = (data.logs || []).slice().reverse(); // newest first
  box.innerHTML = lines.map(line => `
    <div class="log-line ${logClass(line)}">${line}</div>
  `).join('');
}

function updateTimestamp() {
  const now = new Date();
  document.getElementById('lastUpdated').textContent =
    'Last updated: ' + now.toLocaleTimeString('en-IN');
}

// ── Main fetch + update cycle ─────────────────────────────────────────────────
function fetchAndUpdate() {
  fetch(STATUS_FILE + '?t=' + Date.now())   // cache-busting query param
    .then(res => {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    })
    .then(data => {
      updateStats(data);
      updatePieChart(data);
      updateBarChart(data);
      updateConfidence(data);
      updateArticles(data);
      updateLogs(data);
      updateTimestamp();
    })
    .catch(err => {
      console.warn('Dashboard fetch error:', err.message);
      document.getElementById('lastUpdated').textContent = 'Update failed — retrying...';
    });
}

// ── Boot ──────────────────────────────────────────────────────────────────────
fetchAndUpdate();                            // immediate first load
setInterval(fetchAndUpdate, REFRESH_INTERVAL); // then every 5 seconds

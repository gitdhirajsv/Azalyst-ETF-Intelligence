// ─── Azalyst Dashboard — dashboard.js ───────────────────────────────────────
const REFRESH_INTERVAL = 30000;
const STATUS_FILE = 'status.json';

let pieChart = null;
let barChart = null;

function rupee(v) { return '₹' + Number(v).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2}); }
function logClass(l) {
  l = l.toLowerCase();
  if (l.includes('complete') || l.includes('started') || l.includes('dispatched') || l.includes('generated')) return 'ok';
  if (l.includes('cycle') || l.includes('signal') || l.includes('intel') || l.includes('info')) return 'info';
  if (l.includes('warn') || l.includes('skip') || l.includes('error')) return 'warn';
  return '';
}
function pnlClass(v) { return parseFloat(v) >= 0 ? 'green' : 'red'; }
function sevBadge(s) {
  const m = {'CRITICAL':'badge-crit','HIGH':'badge-high','MEDIUM':'badge-med','LOW':'badge-low'};
  return `<span class="badge ${m[s]||'badge-low'}">${s||'—'}</span>`;
}

// ── Stats ────────────────────────────────────────────────────────────────────
function updateStats(d) {
  document.getElementById('portfolioValue').textContent  = rupee(d.portfolio_value);
  document.getElementById('totalDeposited').textContent  = rupee(d.total_deposited);
  document.getElementById('cashAvailable').textContent   = rupee(d.cash);

  const unreal = d.unrealised_str || d.unrealised_pnl;
  const real   = d.realised_str   || d.realised_pnl;
  const unEl   = document.getElementById('unrealisedPnl');
  const reEl   = document.getElementById('realisedPnl');
  unEl.textContent = (typeof unreal === 'string' ? '₹' : '₹') + (d.unrealised_str || unreal);
  reEl.textContent = '₹' + (d.realised_str || real);
  unEl.className = 'stat-val ' + pnlClass(d.unrealised_pnl);
  reEl.className = 'stat-val ' + pnlClass(d.realised_pnl);

  const chEl = document.getElementById('portfolioChange');
  chEl.textContent = d.change || '–';
  chEl.className = 'stat-sub ' + pnlClass(d.change_raw || 0);

  const pos = d.positions || [];
  document.getElementById('positionsSummary').textContent =
    pos.length + ' open · ' + (d.closed_trades || 0) + ' closed';
}

// ── Charts ───────────────────────────────────────────────────────────────────
function updatePieChart(d) {
  const { labels, values } = d.allocation;
  const COLORS = ['#3b82f6','#f59e0b','#22c55e','#8b5cf6','#ef4444','#06b6d4','#f97316'];
  if (!pieChart) {
    pieChart = new Chart(document.getElementById('pieChart'), {
      type: 'pie',
      data: { labels, datasets: [{ data: values, backgroundColor: COLORS.slice(0,labels.length), borderWidth:2, borderColor:'#fff' }] },
      options: {
        plugins: { legend: { position:'right', labels:{ color:'#475569', font:{size:12}, padding:12, boxWidth:12 } } },
        responsive:true, animation:{duration:400}
      }
    });
  } else {
    pieChart.data.labels = labels;
    pieChart.data.datasets[0].data = values;
    pieChart.data.datasets[0].backgroundColor = COLORS.slice(0,labels.length);
    pieChart.update();
  }
}

function updateBarChart(d) {
  const { labels, values } = d.pnl;
  if (!barChart) {
    barChart = new Chart(document.getElementById('barChart'), {
      type: 'bar',
      data: {
        labels,
        datasets: [{ label:'P&L (INR)', data:values,
          backgroundColor: values.map(v => v>=0 ? '#22c55e' : '#ef4444'),
          borderRadius:5 }]
      },
      options: {
        plugins:{ legend:{display:false} },
        scales: {
          x:{ ticks:{color:'#64748b',font:{size:12}}, grid:{display:false} },
          y:{ ticks:{color:'#64748b',font:{size:12}}, grid:{color:'#f1f5f9'} }
        },
        responsive:true, animation:{duration:400}
      }
    });
  } else {
    barChart.data.labels = labels;
    barChart.data.datasets[0].data = values;
    barChart.data.datasets[0].backgroundColor = values.map(v => v>=0?'#22c55e':'#ef4444');
    barChart.update();
  }
}

// ── Open Positions Table ─────────────────────────────────────────────────────
function updatePositions(d) {
  const tbody = document.getElementById('positionsTbody');
  const pos   = d.positions || [];
  if (!pos.length) {
    tbody.innerHTML = '<tr><td colspan="12" class="no-data">No open positions yet</td></tr>';
    return;
  }
  tbody.innerHTML = pos.map(p => `
    <tr>
      <td>${p.trade_id}</td>
      <td><strong>${p.ticker}</strong></td>
      <td style="max-width:160px;overflow:hidden;text-overflow:ellipsis">${p.etf_name}</td>
      <td>${p.sector}</td>
      <td>${rupee(p.entry)}</td>
      <td>${rupee(p.current)}</td>
      <td>${p.units}</td>
      <td>${rupee(p.invested)}</td>
      <td class="${pnlClass(p.pnl)}"><strong>${p.pnl_str ? '₹'+p.pnl_str : rupee(p.pnl)}</strong></td>
      <td class="${pnlClass(p.pnl_pct)}">${p.pnl_pct_str || p.pnl_pct+'%'}</td>
      <td>${p.confidence}/100</td>
      <td>${sevBadge(p.severity)}</td>
    </tr>`).join('');
}

// ── Track Record ─────────────────────────────────────────────────────────────
function updateTrackRecord(d) {
  const tr = d.track_record || {};
  document.getElementById('trTotalTrades').textContent = tr.total_trades || 0;
  document.getElementById('trWinners').textContent     = tr.winners || 0;
  document.getElementById('trLosers').textContent      = tr.losers  || 0;
  document.getElementById('trWinRate').textContent     = (tr.win_rate || 0) + '%';

  const wrEl = document.getElementById('trWinRate');
  wrEl.className = 'track-val ' + ((tr.win_rate||0) >= 50 ? 'green' : 'red');

  if (tr.best) {
    document.getElementById('trBest').textContent      = tr.best.pnl_pct_str;
    document.getElementById('trBestTicker').textContent = tr.best.ticker;
  } else {
    document.getElementById('trBest').textContent      = '–';
    document.getElementById('trBestTicker').textContent = 'No closed trades yet';
  }
  if (tr.worst) {
    document.getElementById('trWorst').textContent      = tr.worst.pnl_pct_str;
    document.getElementById('trWorstTicker').textContent = tr.worst.ticker;
  } else {
    document.getElementById('trWorst').textContent      = '–';
    document.getElementById('trWorstTicker').textContent = 'No closed trades yet';
  }
}

// ── Closed Trades Table ───────────────────────────────────────────────────────
function updateClosedTrades(d) {
  const tbody  = document.getElementById('closedTbody');
  const closed = d.closed_trades_list || [];
  if (!closed.length) {
    tbody.innerHTML = '<tr><td colspan="10" class="no-data">No closed trades yet — positions close on stop-loss (-10%) or after 180 days</td></tr>';
    return;
  }
  tbody.innerHTML = closed.map(ct => `
    <tr>
      <td>${ct.trade_id}</td>
      <td><strong>${ct.ticker}</strong></td>
      <td style="max-width:140px;overflow:hidden;text-overflow:ellipsis">${ct.etf_name}</td>
      <td>${rupee(ct.entry)}</td>
      <td>${rupee(ct.exit)}</td>
      <td class="${pnlClass(ct.pnl)}"><strong>${ct.pnl_str ? '₹'+ct.pnl_str : rupee(ct.pnl)}</strong></td>
      <td class="${pnlClass(ct.pnl_pct)}">${ct.pnl_pct_str || ct.pnl_pct+'%'}</td>
      <td>${ct.days_held}d</td>
      <td>${ct.exit_reason}</td>
      <td><span class="badge ${ct.winner ? 'badge-win' : 'badge-loss'}">${ct.winner ? 'WIN' : 'LOSS'}</span></td>
    </tr>`).join('');
}

// ── Confidence Bars ───────────────────────────────────────────────────────────
function updateConfidence(d) {
  const container = document.getElementById('confidenceBars');
  const threshold = d.confidence_threshold || 62;
  document.getElementById('thresholdNote').textContent = 'Threshold: ' + threshold + '.0';
  container.innerHTML = (d.confidence || []).map(item => `
    <div class="conf-row">
      <div class="conf-label"><span>${item.symbol}</span><span>${item.score.toFixed(1)}</span></div>
      <div class="bar-bg"><div class="bar-fill" style="width:${Math.min(item.score,100)}%"></div></div>
    </div>`).join('');
}

// ── Articles ──────────────────────────────────────────────────────────────────
function updateArticles(d) {
  document.getElementById('articleUpdates').innerHTML = (d.articles || []).map(a => `
    <div class="msg-item">
      <span class="msg-tag ${a.tag}">${a.label}</span>${a.text}
    </div>`).join('');
}

// ── Logs ──────────────────────────────────────────────────────────────────────
function updateLogs(d) {
  document.getElementById('logTail').innerHTML = (d.logs || []).slice().reverse().map(line =>
    `<div class="log-line ${logClass(line)}">${line}</div>`).join('');
}

// ── Timestamp ─────────────────────────────────────────────────────────────────
function updateTimestamp(d) {
  const gen = d.generated_at ? ` · data: ${d.generated_at}` : '';
  document.getElementById('lastUpdated').textContent =
    'Page updated: ' + new Date().toLocaleTimeString('en-IN') + gen;
}

// ── Main fetch loop ───────────────────────────────────────────────────────────
function fetchAndUpdate() {
  fetch(STATUS_FILE + '?t=' + Date.now())
    .then(res => { if (!res.ok) throw new Error('HTTP ' + res.status); return res.json(); })
    .then(d => {
      updateStats(d);
      updatePieChart(d);
      updateBarChart(d);
      updatePositions(d);
      updateTrackRecord(d);
      updateClosedTrades(d);
      updateConfidence(d);
      updateArticles(d);
      updateLogs(d);
      updateTimestamp(d);
    })
    .catch(err => {
      console.warn('Fetch error:', err.message);
      document.getElementById('lastUpdated').textContent = 'Update failed — retrying...';
    });
}

fetchAndUpdate();
setInterval(fetchAndUpdate, REFRESH_INTERVAL);

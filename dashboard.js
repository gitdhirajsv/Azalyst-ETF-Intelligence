const REFRESH_INTERVAL = 30000;
const STATUS_FILE = "status.json";
const CHART_COLORS = ["#3b82f6", "#f59e0b", "#22c55e", "#8b5cf6", "#ef4444", "#06b6d4", "#f97316", "#14b8a6"];

let pieChart = null;
let barChart = null;

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function rupee(value) {
  return "\u20B9" + Number(value || 0).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

function pnlClass(value) {
  return Number(value || 0) >= 0 ? "green" : "red";
}

function logClass(line) {
  const text = String(line || "").toLowerCase();
  if (text.includes("warn") || text.includes("error")) return "log-warn";
  if (text.includes("written") || text.includes("complete") || text.includes("dispatched")) return "log-ok";
  return "log-info";
}

function severityBadge(severity) {
  const mapping = {
    CRITICAL: "badge-crit",
    HIGH: "badge-high",
    MEDIUM: "badge-med",
    LOW: "badge-low"
  };
  return `<span class="badge ${mapping[severity] || "badge-low"}">${escapeHtml(severity || "-")}</span>`;
}

function regimePill(regime) {
  const mapping = {
    NORMAL: "pill pill-normal",
    ELEVATED: "pill pill-elevated",
    HIGH: "pill pill-high",
    EXTREME: "pill pill-extreme",
    Unknown: "pill pill-unknown"
  };
  return `<span class="${mapping[regime] || "pill pill-unknown"}">${escapeHtml(regime || "Unknown")}</span>`;
}

function renderTags(items, cls) {
  if (!items || !items.length) {
    return `<span class="tag ${cls}">-</span>`;
  }
  return items.map(item => `<span class="tag ${cls}">${escapeHtml(item)}</span>`).join("");
}

function updateMarketSnapshot(data) {
  const container = document.getElementById("marketSnapshot");
  const items = (data.market_snapshot || []).filter(item => item.ticker !== "^VIX");
  if (!items.length) {
    container.innerHTML = `<div class="card"><div class="no-data">Market data unavailable</div></div>`;
    return;
  }

  container.innerHTML = items.map(item => `
    <div class="market-tile">
      <div class="market-label">${escapeHtml(item.label)}</div>
      <div class="market-price">${Number(item.price || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}</div>
      <div class="market-chg ${item.direction === "up" ? "green" : "red"}">${escapeHtml(item.change_str || "-")}</div>
      <div class="market-meta">${escapeHtml(item.region || "")}</div>
    </div>
  `).join("");
}

function updateRiskPanel(data) {
  const controls = data.risk_controls || {};
  document.getElementById("vixPill").innerHTML = regimePill(controls.vix_regime || "Unknown");
  document.getElementById("vixValue").textContent = controls.vix ? `VIX ${Number(controls.vix).toFixed(2)}` : "VIX unavailable";
  document.getElementById("cbPill").innerHTML = controls.circuit_breaker_active
    ? `<span class="pill pill-bad">Active</span>`
    : `<span class="pill pill-ok">Clear</span>`;

  const ddNow = Number(controls.drawdown_from_peak_pct || 0);
  const maxDd = Number(controls.max_drawdown_pct || 0);
  const ddEl = document.getElementById("ddNow");
  const maxEl = document.getElementById("maxDd");
  ddEl.textContent = `${ddNow.toFixed(2)}%`;
  maxEl.textContent = `${maxDd.toFixed(2)}%`;
  ddEl.className = `risk-value ${ddNow >= 8 ? "red" : ddNow >= 4 ? "amber" : "green"}`;
  maxEl.className = `risk-value ${maxDd >= 12 ? "red" : maxDd >= 6 ? "amber" : "green"}`;

  const rows = controls.sector_concentration || [];
  const sectorConc = document.getElementById("sectorConc");
  if (!rows.length) {
    sectorConc.innerHTML = `<div class="no-data">No open positions yet</div>`;
    return;
  }

  sectorConc.innerHTML = rows.map(row => `
    <div class="sector-row">
      <div class="sector-head">
        <span>${escapeHtml(row.sector)}</span>
        <span class="${row.at_cap ? "red" : "muted"}">${Number(row.weight || 0).toFixed(1)}%</span>
      </div>
      <div class="bar-bg"><div class="bar-fill ${row.at_cap ? "at-cap" : ""}" style="width:${Math.min(Number(row.weight || 0), 100)}%"></div></div>
    </div>
  `).join("");
}

function updateSignalCards(data) {
  const container = document.getElementById("signalCards");
  const signals = data.signals || [];
  if (!signals.length) {
    container.innerHTML = `<div class="no-data">No active signal details yet</div>`;
    return;
  }

  container.innerHTML = signals.slice(0, 8).map(signal => {
    const breakdown = signal.breakdown || {};
    const confidence = Number(signal.confidence || 0);
    const confidenceClass = confidence >= 80 ? "tag-bull" : confidence >= 65 ? "tag-neu" : "tag-bear";
    return `
      <div class="signal-card">
        <div class="signal-head">
          <div>
            <div class="signal-title">${escapeHtml(signal.sector_label)}</div>
            <div class="signal-meta">${escapeHtml(signal.latest_at || "-")} - ${escapeHtml(String(signal.article_count || 0))} articles</div>
          </div>
          <div style="text-align:right;">
            <div class="msg-tag ${confidenceClass}">${escapeHtml(String(confidence))}/100</div>
            <div style="margin-top:6px;">${severityBadge(signal.severity)}</div>
          </div>
        </div>
        <div class="signal-headline">${escapeHtml(signal.headline || "-")}</div>
        <div class="signal-tags">
          ${renderTags(signal.regions, "tag-blue")}
          ${renderTags(signal.sources, "tag-purple")}
        </div>
        <div class="signal-grid">
          <div class="signal-box">
            <div class="signal-box-title">ETF Routing</div>
            <div class="signal-box-body">
              <strong>India:</strong> ${escapeHtml((signal.india_etfs || []).join(", ") || "-")}<br>
              <strong>Global:</strong> ${escapeHtml((signal.global_etfs || []).join(", ") || "-")}
            </div>
          </div>
          <div class="signal-box">
            <div class="signal-box-title">Score Breakdown</div>
            <div class="signal-box-body">
              <div class="breakdown-row"><span>Signal</span><span>${Number(breakdown.signal_strength || 0).toFixed(1)}</span></div>
              <div class="breakdown-row"><span>Volume</span><span>${Number(breakdown.volume_confirmation || 0).toFixed(1)}</span></div>
              <div class="breakdown-row"><span>Sources</span><span>${Number(breakdown.source_diversity || 0).toFixed(1)}</span></div>
              <div class="breakdown-row"><span>Recency</span><span>${Number(breakdown.recency || 0).toFixed(1)}</span></div>
              <div class="breakdown-row"><span>Severity</span><span>${Number(breakdown.geopolitical_severity || 0).toFixed(1)}</span></div>
            </div>
          </div>
        </div>
      </div>
    `;
  }).join("");
}

function updateArticles(data) {
  const container = document.getElementById("articleUpdates");
  const items = data.articles || [];
  if (!items.length) {
    container.innerHTML = `<div class="no-data">No recent signal updates</div>`;
    return;
  }
  container.innerHTML = items.map(item => `
    <div class="msg-item">
      <span class="msg-tag ${escapeHtml(item.tag)}">${escapeHtml(item.label)}</span>
      ${escapeHtml(item.text)}
    </div>
  `).join("");
}

function updateConfidence(data) {
  const container = document.getElementById("confidenceBars");
  const rows = data.confidence || [];
  document.getElementById("thresholdNote").textContent = `Signal threshold: ${Number(data.confidence_threshold || 62).toFixed(0)}`;
  if (!rows.length) {
    container.innerHTML = `<div class="no-data">No confidence data yet</div>`;
    return;
  }

  container.innerHTML = rows.map(row => `
    <div class="conf-row">
      <div class="conf-label"><span>${escapeHtml(row.symbol)}</span><span>${Number(row.score || 0).toFixed(1)}</span></div>
      <div class="conf-bar"><div class="conf-fill" style="width:${Math.min(Number(row.score || 0), 100)}%"></div></div>
    </div>
  `).join("");
}

function updateStats(data) {
  document.getElementById("portfolioValue").textContent = rupee(data.portfolio_value);
  document.getElementById("totalDeposited").textContent = rupee(data.total_deposited);
  document.getElementById("cashAvailable").textContent = rupee(data.cash);

  const unrealised = document.getElementById("unrealisedPnl");
  const realised = document.getElementById("realisedPnl");
  unrealised.textContent = `\u20B9${data.unrealised_str || "0.00"}`;
  realised.textContent = `\u20B9${data.realised_str || "0.00"}`;
  unrealised.className = `stat-val ${pnlClass(data.unrealised_pnl)}`;
  realised.className = `stat-val ${pnlClass(data.realised_pnl)}`;

  document.getElementById("portfolioChange").textContent = `${data.change || "-"} total return`;
  document.getElementById("portfolioChange").className = `stat-sub ${pnlClass(data.change_raw)}`;
  document.getElementById("positionsSummary").textContent = `${(data.positions || []).length} open - ${Number(data.closed_trades || 0)} closed`;

  const partial = Number(data.partial_realised_pnl || 0);
  document.getElementById("realisedSub").textContent = partial !== 0
    ? `Closed trades + partial exits (${rupee(partial)} partial)`
    : "Closed trades and partial exits";
}

function ensurePieChart(labels, values) {
  if (!labels.length) return;
  if (!pieChart) {
    pieChart = new Chart(document.getElementById("pieChart"), {
      type: "doughnut",
      data: { labels, datasets: [{ data: values, backgroundColor: CHART_COLORS.slice(0, labels.length), borderWidth: 2, borderColor: "#ffffff" }] },
      options: { plugins: { legend: { position: "right", labels: { color: "#475569", font: { size: 12 }, padding: 12, boxWidth: 12 } } }, cutout: "62%", responsive: true, animation: { duration: 400 } }
    });
    return;
  }
  pieChart.data.labels = labels;
  pieChart.data.datasets[0].data = values;
  pieChart.data.datasets[0].backgroundColor = CHART_COLORS.slice(0, labels.length);
  pieChart.update();
}

function ensureBarChart(labels, values) {
  if (!labels.length) return;
  const colors = values.map(value => Number(value || 0) >= 0 ? "#22c55e" : "#ef4444");
  if (!barChart) {
    barChart = new Chart(document.getElementById("barChart"), {
      type: "bar",
      data: { labels, datasets: [{ label: "P&L (INR)", data: values, backgroundColor: colors, borderRadius: 5 }] },
      options: { plugins: { legend: { display: false } }, scales: { x: { ticks: { color: "#64748b", font: { size: 12 } }, grid: { display: false } }, y: { ticks: { color: "#64748b", font: { size: 12 } }, grid: { color: "#f1f5f9" } } }, responsive: true, animation: { duration: 400 } }
    });
    return;
  }
  barChart.data.labels = labels;
  barChart.data.datasets[0].data = values;
  barChart.data.datasets[0].backgroundColor = colors;
  barChart.update();
}

function updateCharts(data) {
  const allocation = data.allocation || { labels: [], values: [] };
  const pnl = data.pnl || { labels: [], values: [] };
  ensurePieChart(allocation.labels || [], allocation.values || []);
  ensureBarChart(pnl.labels || [], pnl.values || []);
}

function positionStatus(position) {
  if (position.half_exited) return `<span class="badge badge-half">1/2 Exited</span>`;
  if (Number(position.pnl_pct || 0) >= 15) return `<span class="badge badge-win">At Profit Trigger</span>`;
  if (Number(position.dist_to_trail_pct || 0) <= 3) return `<span class="badge badge-loss">Near Stop</span>`;
  return "-";
}

function updatePositions(data) {
  const tbody = document.getElementById("positionsTbody");
  const positions = data.positions || [];
  if (!positions.length) {
    tbody.innerHTML = `<tr><td colspan="15" class="no-data">No open positions yet</td></tr>`;
    return;
  }

  tbody.innerHTML = positions.map(position => `
    <tr>
      <td>${escapeHtml(position.trade_id)}</td>
      <td><strong>${escapeHtml(position.ticker)}</strong></td>
      <td style="max-width:170px;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(position.etf_name)}</td>
      <td>${escapeHtml(position.sector)}</td>
      <td>${rupee(position.entry)}</td>
      <td>${rupee(position.current)}</td>
      <td>${rupee(position.peak_price)}</td>
      <td class="${pnlClass(position.pnl_pct)}">${escapeHtml(position.pnl_pct_str)}</td>
      <td class="${pnlClass(position.pnl)}"><strong>\u20B9${escapeHtml(position.pnl_str)}</strong></td>
      <td>${rupee(position.trail_stop)}</td>
      <td class="${Number(position.dist_to_trail_pct || 0) <= 3 ? "red" : Number(position.dist_to_trail_pct || 0) <= 6 ? "amber" : "green"}">${Number(position.dist_to_trail_pct || 0).toFixed(2)}%</td>
      <td>${escapeHtml(String(position.days_held || 0))}d</td>
      <td>${escapeHtml(String(position.confidence || 0))}/100</td>
      <td>${severityBadge(position.severity)}</td>
      <td>${positionStatus(position)}</td>
    </tr>
  `).join("");
}

function setKpi(id, value, suffix, cls) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = value === null || value === undefined || value === "" ? "-" : `${value}${suffix || ""}`;
  el.className = cls ? `kpi-val ${cls}` : "kpi-val";
}

function applyTradeCard(valueId, tickerId, reasonId, trade) {
  const valueEl = document.getElementById(valueId);
  const tickerEl = document.getElementById(tickerId);
  const reasonEl = document.getElementById(reasonId);
  if (!trade) {
    valueEl.textContent = "-";
    valueEl.className = "stat-val";
    tickerEl.textContent = "No closed trades yet";
    reasonEl.textContent = "";
    return;
  }

  const pct = Number(trade.pnl_pct || 0);
  valueEl.textContent = `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`;
  valueEl.className = `stat-val ${pct >= 0 ? "green" : "red"}`;
  tickerEl.textContent = trade.etf_name ? `${trade.ticker} - ${trade.etf_name}` : trade.ticker;
  reasonEl.textContent = trade.exit_reason || "";
}

function updateTrackRecord(data) {
  const track = data.track_record || {};
  document.getElementById("trTotalTrades").textContent = Number(track.total_trades || 0);
  document.getElementById("trWinners").textContent = Number(track.winners || 0);
  document.getElementById("trLosers").textContent = Number(track.losers || 0);

  const winRate = Number(track.win_rate || 0);
  const winRateEl = document.getElementById("trWinRate");
  winRateEl.textContent = `${winRate.toFixed(1)}%`;
  winRateEl.className = `track-val ${winRate >= 50 ? "green" : "red"}`;

  const avgWin = Number(track.avg_win || 0);
  const avgLoss = Number(track.avg_loss || 0);
  const profitFactor = Number(track.profit_factor || 0);
  const sharpe = Number(track.sharpe_proxy || 0);
  const expectancy = Number(track.expectancy || 0);

  setKpi("trAvgWin", `${avgWin >= 0 ? "+" : ""}${avgWin.toFixed(2)}`, "%", "green");
  setKpi("trAvgLoss", avgLoss.toFixed(2), "%", "red");
  setKpi("trPF", profitFactor ? profitFactor.toFixed(2) : "-", "", profitFactor >= 1.5 ? "green" : profitFactor >= 1 ? "amber" : "red");
  setKpi("trSharpe", sharpe ? sharpe.toFixed(2) : "-", "", sharpe >= 1 ? "green" : sharpe >= 0 ? "amber" : "red");
  setKpi("trExpectancy", expectancy ? `${expectancy >= 0 ? "+" : ""}${expectancy.toFixed(2)}` : "-", "%", expectancy >= 0 ? "green" : "red");

  applyTradeCard("trBest", "trBestTicker", "trBestReason", track.best);
  applyTradeCard("trWorst", "trWorstTicker", "trWorstReason", track.worst);
}

function updateClosedTrades(data) {
  const tbody = document.getElementById("closedTbody");
  const trades = data.closed_trades_list || [];
  if (!trades.length) {
    tbody.innerHTML = `<tr><td colspan="10" class="no-data">No closed trades yet</td></tr>`;
    return;
  }

  tbody.innerHTML = trades.slice().reverse().map(trade => `
    <tr>
      <td>${escapeHtml(trade.trade_id)}</td>
      <td><strong>${escapeHtml(trade.ticker)}</strong></td>
      <td style="max-width:170px;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(trade.etf_name)}</td>
      <td>${rupee(trade.entry)}</td>
      <td>${rupee(trade.exit)}</td>
      <td class="${pnlClass(trade.pnl)}"><strong>\u20B9${escapeHtml(trade.pnl_str)}</strong></td>
      <td class="${pnlClass(trade.pnl_pct)}">${escapeHtml(trade.pnl_pct_str)}</td>
      <td>${escapeHtml(String(trade.days_held || 0))}d</td>
      <td>${escapeHtml(trade.exit_reason)}</td>
      <td><span class="badge ${trade.winner ? "badge-win" : "badge-loss"}">${trade.winner ? "WIN" : "LOSS"}</span></td>
    </tr>
  `).join("");
}

function updateLogs(data) {
  const container = document.getElementById("logTail");
  const lines = data.logs || [];
  if (!lines.length) {
    container.innerHTML = `<div class="no-data">No log lines available</div>`;
    return;
  }
  container.innerHTML = lines.slice().reverse().map(line => `<div class="${logClass(line)}">${escapeHtml(line)}</div>`).join("");
}

function updateTimestamp(data) {
  const localTime = new Date().toLocaleTimeString("en-IN");
  const generated = data.generated_at ? ` - data ${data.generated_at}` : "";
  document.getElementById("lastUpdated").textContent = `Page updated ${localTime}${generated}`;
}

function fetchAndUpdate() {
  fetch(`${STATUS_FILE}?t=${Date.now()}`)
    .then(response => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then(data => {
      updateMarketSnapshot(data);
      updateRiskPanel(data);
      updateSignalCards(data);
      updateArticles(data);
      updateConfidence(data);
      updateStats(data);
      updateCharts(data);
      updatePositions(data);
      updateTrackRecord(data);
      updateClosedTrades(data);
      updateLogs(data);
      updateTimestamp(data);
    })
    .catch(error => {
      console.warn(error.message);
      document.getElementById("lastUpdated").textContent = "Update failed - retrying...";
    });
}

fetchAndUpdate();
setInterval(fetchAndUpdate, REFRESH_INTERVAL);

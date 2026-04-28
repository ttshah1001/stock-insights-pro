(function () {
  'use strict';

  const API = '';
  function url(path) { return (API || '') + path; }

  var currentTicker = '';
  var currentName = '';

  // --- Tabs ---
  document.querySelectorAll('.tab').forEach(function (btn) {
    btn.addEventListener('click', function () {
      const tab = this.dataset.tab;
      document.querySelectorAll('.tab').forEach(function (b) { b.classList.remove('active'); });
      document.querySelectorAll('.panel').forEach(function (p) { p.classList.remove('active'); });
      this.classList.add('active');
      const panel = document.getElementById('panel-' + tab);
      if (panel) panel.classList.add('active');
    });
  });

  // --- Format helpers ---
  function formatPrice(n) {
    if (n == null || n === '') return '—';
    return '$' + Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  function formatVolume(n) {
    if (n == null) return '—';
    if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B';
    if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(2) + 'K';
    return String(n);
  }
  function formatPct(n) {
    if (n == null || n === '') return '—';
    return Number(n).toFixed(2) + '%';
  }

  function hidePrompts() {
    ['market-prompt', 'analysis-prompt', 'quant-prompt'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.classList.add('hidden');
    });
  }

  function showPrompts() {
    ['market-prompt', 'analysis-prompt', 'quant-prompt'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.classList.remove('hidden');
    });
  }

  // --- Quote ---
  function showQuote(data) {
    const card = document.getElementById('quote-card');
    const err = document.getElementById('quote-error');
    if (data.error) {
      if (card) card.classList.add('hidden');
      if (err) { err.textContent = data.error || 'No data'; err.classList.remove('hidden'); }
      return;
    }
    if (err) err.classList.add('hidden');
    if (card) card.classList.remove('hidden');
    var t = document.getElementById('quote-ticker');
    if (t) t.textContent = data.ticker || '';
    var u = document.getElementById('quote-updated');
    if (u) u.textContent = data.updated ? 'Updated ' + new Date(data.updated).toLocaleString() : '';
    var c = document.getElementById('quote-close');
    if (c) c.textContent = formatPrice(data.close);
    var o = document.getElementById('quote-open');
    if (o) o.textContent = formatPrice(data.open);
    var h = document.getElementById('quote-high');
    if (h) h.textContent = formatPrice(data.high);
    var l = document.getElementById('quote-low');
    if (l) l.textContent = formatPrice(data.low);
    var v = document.getElementById('quote-volume');
    if (v) v.textContent = data.volume != null ? formatVolume(data.volume) : '—';
  }

  // --- Charts ---
  const chartCanvas = document.getElementById('price-chart');
  const chartCtx = chartCanvas ? chartCanvas.getContext('2d') : null;
  const volumeCanvas = document.getElementById('volume-chart');
  const volumeCtx = volumeCanvas ? volumeCanvas.getContext('2d') : null;
  var chartData = [];

  function drawPriceChart() {
    if (!chartCanvas || !chartCtx) return;
    const w = chartCanvas.width = chartCanvas.offsetWidth;
    const h = chartCanvas.height = chartCanvas.offsetHeight;
    chartCtx.clearRect(0, 0, w, h);
    if (!chartData.length) return;
    const closes = chartData.map(function (d) { return d.close; }).filter(function (c) { return c != null; });
    if (!closes.length) return;
    const min = Math.min.apply(null, closes);
    const max = Math.max.apply(null, closes);
    const pad = (max - min) * 0.05 || 1;
    const yMin = min - pad;
    const yMax = max + pad;
    const n = chartData.length;
    const padding = { left: 50, right: 20, top: 20, bottom: 30 };
    const plotW = w - padding.left - padding.right;
    const plotH = h - padding.top - padding.bottom;
    chartCtx.strokeStyle = '#2563eb';
    chartCtx.lineWidth = 2;
    chartCtx.lineJoin = 'round';
    chartCtx.beginPath();
    chartData.forEach(function (d, i) {
      const x = padding.left + (i / (n - 1 || 1)) * plotW;
      const v = d.close != null ? d.close : (chartData[i - 1] && chartData[i - 1].close);
      if (v == null) return;
      const y = padding.top + plotH - ((v - yMin) / (yMax - yMin)) * plotH;
      if (i === 0) chartCtx.moveTo(x, y);
      else chartCtx.lineTo(x, y);
    });
    chartCtx.stroke();
    chartCtx.fillStyle = 'rgba(37, 99, 235, 0.08)';
    chartCtx.lineTo(padding.left + plotW, padding.top + plotH);
    chartCtx.lineTo(padding.left, padding.top + plotH);
    chartCtx.closePath();
    chartCtx.fill();
  }

  function drawVolumeChart() {
    if (!volumeCanvas || !volumeCtx || !chartData.length) return;
    const w = volumeCanvas.width = volumeCanvas.offsetWidth;
    const h = volumeCanvas.height = volumeCanvas.offsetHeight;
    volumeCtx.clearRect(0, 0, w, h);
    const vols = chartData.map(function (d) { return d.volume || 0; });
    const maxVol = Math.max.apply(null, vols) || 1;
    const n = chartData.length;
    const barW = Math.max(1, (w - 60) / n - 1);
    const left = 40;
    chartData.forEach(function (d, i) {
      const x = left + (i / (n - 1 || 1)) * (w - left - 20);
      const bh = (d.volume || 0) / maxVol * (h - 20);
      volumeCtx.fillStyle = (d.close >= (d.open || d.close)) ? 'rgba(22, 163, 74, 0.5)' : 'rgba(220, 38, 38, 0.5)';
      volumeCtx.fillRect(x - barW / 2, h - bh, barW, bh);
    });
  }

  // --- Analysis ---
  const analysisKeys = [
    'Close', 'Open', 'High', 'Low', 'Volume',
    'rsi', 'macd', 'macd_signal', 'macd_hist',
    'sma_short', 'sma_long', 'ema_short', 'ema_long',
    'bb_upper', 'bb_lower', 'bb_mid', 'bb_width', 'bb_position',
    'atr', 'adx', 'di_plus', 'di_minus',
    'stoch_k', 'stoch_d', 'obv'
  ];

  function showAnalysis(data) {
    if (!data || typeof data !== 'object') return;
    const card = document.getElementById('analysis-card');
    const err = document.getElementById('analysis-error');
    if (!card || !err) return;
    if (data.error) {
      card.classList.add('hidden');
      err.textContent = data.error;
      err.classList.remove('hidden');
      return;
    }
    err.classList.add('hidden');
    card.classList.remove('hidden');
    var titleEl = document.getElementById('analysis-ticker');
    if (titleEl) titleEl.textContent = (data.ticker || '') + ' — ' + (data.date || '');
    var barsCount = document.getElementById('analysis-bars-count');
    if (barsCount) barsCount.textContent = data.bars_count != null ? (data.bars_count + ' trading days of data') : '';
    const grid = document.getElementById('analysis-grid');
    if (!grid) return;
    grid.innerHTML = '';
    analysisKeys.forEach(function (k) {
      if (data[k] === undefined) return;
      const div = document.createElement('div');
      div.className = 'item';
      var val = data[k];
      if (val != null && typeof val === 'number' && !Number.isNaN(val)) val = val.toFixed(4);
      div.innerHTML = '<span class="label">' + k + '</span><span class="value">' + (val != null && val !== '' ? String(val) : '—') + '</span>';
      grid.appendChild(div);
    });
  }

  function drawSeriesChart(canvasId, dates, values, color, yMin, yMax) {
    var canvas = document.getElementById(canvasId);
    if (!canvas || !values || !values.length) return;
    var ctx = canvas.getContext('2d');
    var w = canvas.width = canvas.offsetWidth;
    var h = canvas.height = canvas.offsetHeight;
    ctx.clearRect(0, 0, w, h);
    var min = yMin != null ? yMin : (Math.min.apply(null, values.filter(function (v) { return v != null; })) || 0);
    var max = yMax != null ? yMax : (Math.max.apply(null, values.filter(function (v) { return v != null; })) || 100);
    if (max === min) max = min + 1;
    var n = values.length;
    var padding = { left: 40, right: 15, top: 15, bottom: 25 };
    var plotW = w - padding.left - padding.right;
    var plotH = h - padding.top - padding.bottom;
    ctx.strokeStyle = color || '#2563eb';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    var started = false;
    for (var i = 0; i < n; i++) {
      var v = values[i];
      if (v == null) { started = false; continue; }
      var x = padding.left + (i / (n - 1 || 1)) * plotW;
      var y = padding.top + plotH - ((v - min) / (max - min)) * plotH;
      if (!started) { ctx.moveTo(x, y); started = true; }
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }

  // --- Risk ---
  function showRisk(data) {
    const card = document.getElementById('risk-card');
    if (!card) return;
    if (data.error) {
      card.classList.add('hidden');
      return;
    }
    card.classList.remove('hidden');
    const grid = document.getElementById('risk-grid');
    grid.innerHTML = '';
    Object.keys(data).forEach(function (k) {
      const div = document.createElement('div');
      div.className = 'item';
      const v = data[k];
      div.innerHTML = '<span class="label">' + k + '</span><span class="value">' + (v != null ? (typeof v === 'number' ? v.toFixed(4) : v) : '—') + '</span>';
      grid.appendChild(div);
    });
  }

  // --- Quant ---
  function showQuant(list) {
    const wrap = document.getElementById('quant-table-wrap');
    const err = document.getElementById('quant-error');
    const loading = document.getElementById('quant-loading');
    const summaryEl = document.getElementById('quant-summary');
    const summaryGrid = document.getElementById('quant-summary-grid');
    if (loading) loading.classList.add('hidden');
    if (!Array.isArray(list)) list = [];
    if (!list.length) {
      if (wrap) wrap.classList.add('hidden');
      if (summaryEl) summaryEl.classList.add('hidden');
      if (err) { err.textContent = 'No recommendations returned.'; err.classList.remove('hidden'); }
      return;
    }
    if (err) err.classList.add('hidden');
    if (wrap) wrap.classList.remove('hidden');
    if (summaryEl) summaryEl.classList.remove('hidden');
    var buyCount = list.filter(function (r) { return r && r.action === 'BUY'; }).length;
    var sellCount = list.filter(function (r) { return r && r.action === 'SELL'; }).length;
    var holdCount = list.filter(function (r) { return r && r.action === 'HOLD'; }).length;
    if (summaryGrid) {
      summaryGrid.innerHTML =
        '<div class="item"><span class="label">BUY</span><span class="value action-buy">' + buyCount + '</span></div>' +
        '<div class="item"><span class="label">SELL</span><span class="value action-sell">' + sellCount + '</span></div>' +
        '<div class="item"><span class="label">HOLD</span><span class="value action-hold">' + holdCount + '</span></div>' +
        '<div class="item"><span class="label">Tickers</span><span class="value">' + list.length + '</span></div>';
    }
    const tbody = document.getElementById('quant-tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    list.forEach(function (r) {
      if (!r || typeof r !== 'object') return;
      const tr = document.createElement('tr');
      const actionClass = 'action-' + (r.action ? r.action.toLowerCase() : 'hold');
      const rsiVal = r.rsi != null ? (typeof r.rsi === 'number' ? r.rsi.toFixed(0) : r.rsi) : '—';
      tr.innerHTML =
        '<td><strong>' + (r.ticker || '') + '</strong></td>' +
        '<td class="' + actionClass + '">' + (r.action || '—') + '</td>' +
        '<td>' + (r.conviction != null ? r.conviction : '—') + '</td>' +
        '<td>' + formatPrice(r.current_price) + '</td>' +
        '<td>' + formatPrice(r.stop_loss) + '</td>' +
        '<td>' + formatPrice(r.take_profit) + '</td>' +
        '<td>' + (r.risk_level || '—') + '</td>' +
        '<td>' + rsiVal + '</td>' +
        '<td>' + (r.return_5d_pct != null ? formatPct(r.return_5d_pct) : '—') + '</td>' +
        '<td>' + (r.volatility_annual_pct != null ? formatPct(r.volatility_annual_pct) : '—') + '</td>' +
        '<td class="advice-cell">' + (r.advice_summary || '—') + '</td>' +
        '<td class="reasoning">' + (Array.isArray(r.reasoning) ? r.reasoning.join(' · ') : (r.reasoning || '—')) + '</td>';
      tbody.appendChild(tr);
    });
  }

  // --- Load all sections for one ticker ---
  function loadAllForTicker(ticker) {
    if (!ticker) return;
    currentTicker = ticker;
    hidePrompts();

    // Quote
    fetch(url('/api/quote/' + encodeURIComponent(ticker)))
      .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); })
      .then(function (result) {
        if (result.ok && result.data && !result.data.error) showQuote(result.data);
        else showQuote(result.data || { error: 'No quote' });
      })
      .catch(function () { showQuote({ error: 'Failed to load quote' }); });

    // Bars + chart
    var days = document.getElementById('chart-days') ? document.getElementById('chart-days').value : 252;
    fetch(url('/api/bars/' + encodeURIComponent(ticker) + '?days=' + days))
      .then(function (r) { return r.json(); })
      .then(function (bars) {
        chartData = Array.isArray(bars) ? bars : [];
        var container = document.getElementById('chart-container');
        var volContainer = document.getElementById('volume-container');
        if (container) container.classList.add('has-data');
        if (chartData.length && volContainer) volContainer.classList.remove('hidden');
        drawPriceChart();
        drawVolumeChart();
      })
      .catch(function () { chartData = []; drawPriceChart(); });

    // Analysis
    fetch(url('/api/analysis/' + encodeURIComponent(ticker)))
      .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); })
      .then(function (result) {
        if (result.ok && result.data && !result.data.error) showAnalysis(result.data);
        else showAnalysis(result.data || { error: 'Analysis failed' });
      })
      .catch(function () { showAnalysis({ error: 'Failed to load analysis' }); });

    // Analysis series (indicator charts)
    fetch(url('/api/analysis_series/' + encodeURIComponent(ticker) + '?days=180'))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error || !data.series) return;
        var wrap = document.getElementById('analysis-charts');
        if (wrap) wrap.classList.remove('hidden');
        drawSeriesChart('rsi-chart', data.dates, data.series.rsi, '#f59e0b', 0, 100);
        drawSeriesChart('macd-chart', data.dates, data.series.macd_hist, '#8b5cf6');
        drawSeriesChart('adx-chart', data.dates, data.series.adx, '#06b6d4', 0, 60);
      })
      .catch(function () {});

    // Risk
    fetch(url('/api/risk/' + encodeURIComponent(ticker)))
      .then(function (r) { return r.json(); })
      .then(showRisk)
      .catch(function () { showRisk({ error: 'Failed' }); });

    // Quant (single ticker)
    var loading = document.getElementById('quant-loading');
    var err = document.getElementById('quant-error');
    if (loading) loading.classList.remove('hidden');
    if (err) err.classList.add('hidden');
    fetch(url('/api/quant?symbols=' + encodeURIComponent(ticker)))
      .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); })
      .then(function (result) {
        if (loading) loading.classList.add('hidden');
        var list = Array.isArray(result.data) ? result.data : [];
        if (!result.ok && result.data && result.data.error && err) {
          err.textContent = result.data.error || 'Request failed.';
          err.classList.remove('hidden');
        }
        showQuant(list);
      })
      .catch(function () {
        if (loading) loading.classList.add('hidden');
        showQuant([]);
        if (err) { err.textContent = 'Failed to load recommendations.'; err.classList.remove('hidden'); }
      });
  }

  // --- Go button: resolve then load all ---
  document.getElementById('btn-go').addEventListener('click', function () {
    var input = document.getElementById('global-stock-input');
    var label = document.getElementById('global-stock-label');
    var errEl = document.getElementById('global-stock-error');
    var q = (input && input.value) ? input.value.trim() : '';
    if (!q) {
      if (errEl) { errEl.textContent = 'Enter a ticker or company name.'; errEl.classList.remove('hidden'); }
      return;
    }
    if (errEl) errEl.classList.add('hidden');
    if (label) { label.classList.add('hidden'); label.textContent = ''; }

    fetch(url('/api/resolve?q=' + encodeURIComponent(q)))
      .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); })
      .then(function (result) {
        if (!result.ok || !result.data || result.data.error) {
          if (errEl) {
            errEl.textContent = result.data && result.data.error ? result.data.error : 'Could not find that symbol or company.';
            errEl.classList.remove('hidden');
          }
          return;
        }
        var ticker = result.data.ticker;
        var name = result.data.name || ticker;
        currentTicker = ticker;
        currentName = name;
        if (label) {
          label.textContent = 'Showing: ' + ticker + (name !== ticker ? ' (' + name + ')' : '');
          label.classList.remove('hidden');
        }
        loadAllForTicker(ticker);
      })
      .catch(function () {
        if (errEl) { errEl.textContent = 'Network error. Try again.'; errEl.classList.remove('hidden'); }
      });
  });

  // Allow Enter in global input to trigger Go
  var globalInput = document.getElementById('global-stock-input');
  if (globalInput) {
    globalInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') document.getElementById('btn-go').click();
    });
  }

  window.addEventListener('resize', function () { drawPriceChart(); drawVolumeChart(); });
})();

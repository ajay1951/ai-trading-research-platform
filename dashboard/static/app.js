// ─── STATE ────────────────────────────────────────────
let lastTradeTime = null;
let chartDataLoaded = false;
let activeAsset = 'BTC/USDT';
let activeTimeframe = '15m';
let filterFeed = false;
let tickerData = {};
let lastUpdateTs = Date.now();
let activeChartType = 'candles'; // 'candles' or 'equity'

// ─── UI HANDLERS ──────────────────────────────────────
function showToast(message) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerText = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

document.getElementById('theme-toggle').addEventListener('click', () => {
    document.body.classList.toggle('light-mode');
    const isLight = document.body.classList.contains('light-mode');
    chart.applyOptions({
        layout: {
            background: { color: isLight ? '#f8fafc' : '#0B0E14' },
            textColor: isLight ? '#475569' : '#94a3b8'
        },
        grid: {
            vertLines: { color: isLight ? 'rgba(0,0,0,0.05)' : 'rgba(43, 43, 67, 0.4)' },
            horzLines: { color: isLight ? 'rgba(0,0,0,0.05)' : 'rgba(43, 43, 67, 0.4)' }
        }
    });
});

document.getElementById('asset-select').addEventListener('change', e => { activeAsset = e.target.value; forceChartReload(); });
document.getElementById('timeframe-select').addEventListener('change', e => { activeTimeframe = e.target.value; forceChartReload(); });
document.getElementById('filter-feed').addEventListener('change', e => { filterFeed = e.target.checked; lastTradeTime = null; fetchTrades(); });

document.getElementById('tab-candles').addEventListener('click', e => {
    activeChartType = 'candles';
    e.target.classList.add('active');
    document.getElementById('tab-equity').classList.remove('active');
    document.getElementById('asset-select').style.display = 'inline-block';
    document.getElementById('timeframe-select').style.display = 'inline-block';
    candleSeries.applyOptions({ visible: true });
    volumeSeries.applyOptions({ visible: true });
    equitySeries.applyOptions({ visible: false });
    forceChartReload();
});

document.getElementById('tab-equity').addEventListener('click', e => {
    activeChartType = 'equity';
    e.target.classList.add('active');
    document.getElementById('tab-candles').classList.remove('active');
    document.getElementById('asset-select').style.display = 'none';
    document.getElementById('timeframe-select').style.display = 'none';
    candleSeries.applyOptions({ visible: false });
    volumeSeries.applyOptions({ visible: false });
    equitySeries.applyOptions({ visible: true });
    fetchEquityData();
});

// ─── CHART INITIALIZATION ─────────────────────────────
const chartContainer = document.getElementById('tvchart');
const chart = LightweightCharts.createChart(chartContainer, {
    layout: { background: { color: '#0B0E14' }, textColor: '#94a3b8' },
    grid: { vertLines: { color: 'rgba(43, 43, 67, 0.4)' }, horzLines: { color: 'rgba(43, 43, 67, 0.4)' } },
    timeScale: { timeVisible: true, secondsVisible: false, borderColor: 'rgba(43,43,67,0.6)' },
    rightPriceScale: { borderColor: 'rgba(43,43,67,0.6)' },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
});

const candleSeries = chart.addCandlestickSeries({
    upColor: '#10b981', downColor: '#ef4444',
    borderDownColor: '#ef4444', borderUpColor: '#10b981',
    wickDownColor: '#ef4444', wickUpColor: '#10b981',
});

const volumeSeries = chart.addHistogramSeries({
    priceFormat: { type: 'volume' },
    priceScaleId: '',
    scaleMargins: { top: 0.85, bottom: 0 },
});

const equitySeries = chart.addLineSeries({
    color: '#8b5cf6',
    lineWidth: 3,
    visible: false,
    priceFormat: { type: 'price', precision: 2, minMove: 0.01 }
});

new ResizeObserver(entries => {
    if (entries.length === 0 || entries[0].target !== chartContainer) return;
    const r = entries[0].contentRect;
    chart.applyOptions({ height: r.height, width: r.width });
}).observe(chartContainer);

// ─── DATA FETCHING ────────────────────────────────────

async function forceChartReload() {
    if (activeChartType !== 'candles') return;
    chartDataLoaded = false;
    candleSeries.setData([]);
    volumeSeries.setData([]);
    document.getElementById('chart-status').innerText = 'SYNCING';
    document.getElementById('chart-status').style.color = 'var(--accent-blue)';
    lastTradeTime = null;
    await fetchChartData();
    await fetchTrades();
}

async function fetchChartData() {
    if (activeChartType !== 'candles') return;
    try {
        const res = await fetch(`/api/chart?asset=${encodeURIComponent(activeAsset)}&timeframe=${encodeURIComponent(activeTimeframe)}`);
        const data = await res.json();
        if (Array.isArray(data) && data.length > 0) {
            candleSeries.setData(data.map(d => ({ time: d.time, open: d.open, high: d.high, low: d.low, close: d.close })));
            volumeSeries.setData(data.map(d => ({
                time: d.time, value: d.volume,
                color: d.close >= d.open ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)'
            })));
            document.getElementById('chart-status').innerText = 'LIVE';
            document.getElementById('chart-status').style.color = 'var(--long-color)';
            chartDataLoaded = true;
            lastUpdateTs = Date.now();
        } else if (data.error) {
            showToast("Chart sync error: " + data.error);
            document.getElementById('chart-status').innerText = 'ERROR';
            document.getElementById('chart-status').style.color = 'var(--short-color)';
        }
    } catch (e) {
        console.error("Chart sync failed", e);
        showToast("Network error syncing chart.");
        document.getElementById('chart-status').innerText = 'OFFLINE';
        document.getElementById('chart-status').style.color = 'var(--short-color)';
    }
}

async function fetchEquityData() {
    if (activeChartType !== 'equity') return;
    try {
        const res = await fetch('/api/equity');
        const data = await res.json();
        if (Array.isArray(data) && data.length > 0) {
            equitySeries.setData(data.map(d => ({ time: d.time, value: d.value })));
            chart.timeScale().fitContent();
            document.getElementById('chart-status').innerText = 'LIVE';
            document.getElementById('chart-status').style.color = 'var(--long-color)';
            lastUpdateTs = Date.now();
        } else if (data.error) {
            showToast("Equity sync error: " + data.error);
        }
    } catch (e) {
        console.error("Equity fetch failed", e);
        showToast("Network error syncing equity.");
    }
}

async function fetchTrades() {
    try {
        const res = await fetch('/api/trades');
        const data = await res.json();
        if (!Array.isArray(data) || data.length === 0) return;

        const feed = document.getElementById('order-feed');
        const latestTrade = data[data.length - 1];

        if (latestTrade && latestTrade.timestamp !== lastTradeTime) {
            lastTradeTime = latestTrade.timestamp;
            feed.innerHTML = '';
            let markers = [];

            for (let i = data.length - 1; i >= 0; i--) {
                const t = data[i];
                if (!t || !t.timestamp) continue;
                if (filterFeed && t.asset !== activeAsset && activeChartType === 'candles') continue;

                const d = new Date(t.timestamp);
                const timeStr = d.toLocaleString('en-US', { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit', hour12: false });
                const confStr = (parseFloat(t.confidence) * 100).toFixed(0) + '%';
                const priceFmt = parseFloat(t.price).toLocaleString('en-US', { minimumFractionDigits: 2 });

                const card = document.createElement('div');
                card.className = `trade-card ${t.action}`;
                card.innerHTML = `
                    <div class="trade-left">
                        <span class="trade-action">${t.action} ${t.asset || ''}</span>
                        <span class="trade-time">${timeStr}</span>
                    </div>
                    <div class="trade-right">
                        <span class="trade-price">$${priceFmt}</span>
                        <span class="trade-alloc">${t.allocation} · ${confStr}</span>
                    </div>
                `;
                feed.appendChild(card);

                if (chartDataLoaded && activeChartType === 'candles' && t.asset === activeAsset && (t.action === 'LONG' || t.action === 'SHORT')) {
                    const unixTime = Math.floor(d.getTime() / 1000);
                    if (!isNaN(unixTime)) {
                        markers.push({
                            time: unixTime,
                            position: t.action === 'LONG' ? 'belowBar' : 'aboveBar',
                            color: t.action === 'LONG' ? '#10b981' : '#ef4444',
                            shape: t.action === 'LONG' ? 'arrowUp' : 'arrowDown',
                            text: t.action, size: 2
                        });
                    }
                }
            }

            if (chartDataLoaded && activeChartType === 'candles') {
                markers.sort((a, b) => a.time - b.time);
                candleSeries.setMarkers(markers);
            }
        }
    } catch (e) { console.error("Trade fetch failed", e); }
}

async function fetchPortfolio() {
    try {
        const [portRes, tickRes] = await Promise.all([
            fetch('/api/portfolio'),
            fetch('/api/ticker')
        ]);
        const data = await portRes.json();
        tickerData = await tickRes.json();

        if (data && data.total_value !== undefined) {
            document.getElementById('top-balance').innerText = `$${parseFloat(data.total_value).toLocaleString('en-US', {minimumFractionDigits: 2})}`;
            const pnl = parseFloat(data.realized_pnl);
            const pnlEl = document.getElementById('top-pnl');
            pnlEl.innerText = `${pnl >= 0 ? '+' : ''}$${pnl.toLocaleString('en-US', {minimumFractionDigits: 2})}`;
            pnlEl.style.color = pnl >= 0 ? 'var(--long-color)' : 'var(--short-color)';

            const assetTicker = tickerData[activeAsset];
            if (assetTicker) {
                document.getElementById('top-price').innerText = `$${parseFloat(assetTicker.last).toLocaleString('en-US', {minimumFractionDigits: 2})}`;
                const chg = parseFloat(assetTicker.change);
                const chgEl = document.getElementById('top-change');
                chgEl.innerText = `${chg >= 0 ? '▲' : '▼'} ${Math.abs(chg).toFixed(2)}% (24h)`;
                chgEl.style.color = chg >= 0 ? 'var(--long-color)' : 'var(--short-color)';

                document.getElementById('stat-high').innerText = `$${parseFloat(assetTicker.high).toLocaleString('en-US', {minimumFractionDigits: 0})}`;
                document.getElementById('stat-low').innerText = `$${parseFloat(assetTicker.low).toLocaleString('en-US', {minimumFractionDigits: 0})}`;
            }

            const positions = data.positions || {};
            let lockedCash = 0;
            const tbody = document.getElementById('positions-body');
            tbody.innerHTML = '';

            if (Object.keys(positions).length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" style="padding:1rem; text-align:center; color:var(--text-muted);">No Active Positions — AI is in Cash</td></tr>`;
            } else {
                for (const [asset, pos] of Object.entries(positions)) {
                    lockedCash += pos.locked_cash || 0;
                    const t = tickerData[asset];
                    const currentPrice = t ? t.last : pos.entry_price;

                    let floatPnl = pos.type === 'LONG'
                        ? (currentPrice - pos.entry_price) * pos.amount
                        : (pos.entry_price - currentPrice) * pos.amount;

                    const pnlColor = floatPnl >= 0 ? 'var(--long-color)' : 'var(--short-color)';
                    const pnlSign = floatPnl >= 0 ? '+' : '';
                    const typeColor = pos.type === 'LONG' ? 'var(--long-color)' : 'var(--short-color)';

                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td style="font-weight:600; font-family:'Inter',sans-serif;">${asset}</td>
                        <td style="color:${typeColor}; font-weight:700;">${pos.type}</td>
                        <td>$${pos.entry_price.toLocaleString('en-US', {minimumFractionDigits: 2})}</td>
                        <td style="color:var(--text-secondary);">$${parseFloat(currentPrice).toLocaleString('en-US', {minimumFractionDigits: 2})}</td>
                        <td>$${(pos.locked_cash || 0).toLocaleString('en-US', {minimumFractionDigits: 0})}</td>
                        <td style="text-align:right; font-weight:700; color:${pnlColor};">${pnlSign}$${floatPnl.toLocaleString('en-US', {minimumFractionDigits: 2})}</td>
                    `;
                    tbody.appendChild(row);
                }
            }

            const freeCash = parseFloat(data.cash);
            document.getElementById('cash-allocation').innerHTML =
                `<span style="color:var(--long-color);">Cash: $${freeCash.toLocaleString('en-US',{minimumFractionDigits:0})}</span>` +
                ` · <span style="color:var(--accent-purple);">Locked: $${lockedCash.toLocaleString('en-US',{minimumFractionDigits:0})}</span>`;
        }
    } catch (e) { 
        console.error("Portfolio fetch failed", e); 
        showToast("Error fetching portfolio data");
    }
}

async function fetchStats() {
    try {
        const res = await fetch('/api/stats');
        const s = await res.json();
        document.getElementById('stat-total').innerText = s.total_trades || 0;
        document.getElementById('stat-wins').innerText = s.wins || 0;
        document.getElementById('stat-losses').innerText = s.losses || 0;
        const wr = s.win_rate || 0;
        const wrEl = document.getElementById('stat-winrate');
        wrEl.innerText = `${wr}%`;
        wrEl.style.color = wr >= 50 ? 'var(--long-color)' : wr > 0 ? 'var(--neutral-color)' : 'var(--text-muted)';
    } catch (e) { console.error("Stats fetch failed", e); }
}

function updateConnectionBadge() {
    const age = (Date.now() - lastUpdateTs) / 1000;
    const badge = document.getElementById('conn-badge');
    const text = document.getElementById('conn-text');
    const updatedEl = document.getElementById('last-updated');

    if (age < 60) {
        badge.className = 'conn-badge online';
        text.innerText = 'LIVE';
    } else {
        badge.className = 'conn-badge offline';
        text.innerText = 'STALE';
    }

    if (age < 10) updatedEl.innerText = 'just now';
    else if (age < 60) updatedEl.innerText = `${Math.floor(age)}s ago`;
    else updatedEl.innerText = `${Math.floor(age / 60)}m ago`;
}

// ─── BOOT ─────────────────────────────────────────────
async function bootSequence() {
    if (activeChartType === 'candles') {
        await fetchChartData();
    } else {
        await fetchEquityData();
    }
    await Promise.all([fetchTrades(), fetchPortfolio(), fetchStats()]);
    setInterval(fetchTrades, 2000);
    setInterval(fetchPortfolio, 5000);
    setInterval(() => {
        if (activeChartType === 'candles') fetchChartData();
        else fetchEquityData();
    }, 30000);
    setInterval(fetchStats, 15000);
    setInterval(updateConnectionBadge, 3000);
}

bootSequence();

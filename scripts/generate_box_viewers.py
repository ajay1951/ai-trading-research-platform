import os
import pandas as pd
import json

csv_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'backtest_trades_log.csv')
if not os.path.exists(csv_path):
    print(f"Error: {csv_path} not found.")
    exit(1)

df = pd.read_csv(csv_path)
print(f"Loaded {len(df):,} trades from {csv_path}")

# 1. Generate Formatted Excel Spreadsheet with Grid Boxes
xlsx_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'backtest_trades_log.xlsx')
try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Backtest Trades"
    ws.views.sheetView[0].showGridLines = True

    # Styles
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    win_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid") # Soft green
    loss_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid") # Soft red
    
    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    headers = list(df.columns)
    ws.append(headers)

    for col_idx, cell in enumerate(ws[1], 1):
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border
    ws.row_dimensions[1].height = 26

    # Data Rows
    for r_idx, row in df.iterrows():
        row_vals = list(row)
        ws.append(row_vals)
        cur_row = ws[r_idx + 2]
        is_win = row['pnl_usd'] > 0
        fill_color = win_fill if is_win else loss_fill
        
        for cell in cur_row:
            cell.border = thin_border
            cell.alignment = Alignment(vertical="center")
        
        # PnL columns highlighted
        cur_row[headers.index('pnl_usd')].fill = fill_color
        cur_row[headers.index('pnl_pct')].fill = fill_color
        cur_row[headers.index('pnl_usd')].font = Font(bold=True, color="166534" if is_win else "991B1B")
        cur_row[headers.index('pnl_pct')].font = Font(bold=True, color="166534" if is_win else "991B1B")
        ws.row_dimensions[r_idx + 2].height = 20

    # Auto-fit column widths
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    wb.save(xlsx_path)
    print(f"[+] Successfully generated Excel Box Spreadsheet: {xlsx_path}")
except Exception as e:
    print(f"[!] Excel export error: {e}")

# 2. Generate Interactive HTML Boxed Data-Grid Dashboard
html_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'backtest_trades_viewer.html')

trades_json = df.to_json(orient='records')
total_trades = len(df)
wins = len(df[df['pnl_usd'] > 0])
losses = len(df[df['pnl_usd'] <= 0])
win_rate = (wins / total_trades * 100) if total_trades else 0
total_pnl = df['pnl_usd'].sum()
final_wallet = df['cumulative_wallet_usd'].iloc[-1] if total_trades else 50.0

html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Interactive Box-Grid Backtest Trade Log</title>
<style>
  :root {{
    --bg: #0b0f19;
    --card-bg: #111827;
    --border: #1f293d;
    --text: #f3f4f6;
    --text-dim: #9ca3af;
    --accent: #3b82f6;
    --win: #10b981;
    --loss: #ef4444;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    padding: 24px;
  }}
  .header {{
    margin-bottom: 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 16px;
  }}
  h1 {{ font-size: 24px; font-weight: 700; color: #fff; }}
  .kpi-row {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
  }}
  .kpi-box {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3);
  }}
  .kpi-box .label {{ font-size: 12px; color: var(--text-dim); text-transform: uppercase; font-weight: 600; }}
  .kpi-box .val {{ font-size: 24px; font-weight: 700; margin-top: 6px; }}
  .text-win {{ color: var(--win); }}
  .text-loss {{ color: var(--loss); }}
  .text-accent {{ color: var(--accent); }}

  /* Filter Controls */
  .controls {{
    display: flex;
    gap: 12px;
    margin-bottom: 16px;
    flex-wrap: wrap;
    align-items: center;
  }}
  .search-input {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    color: #fff;
    padding: 10px 16px;
    border-radius: 8px;
    font-size: 14px;
    min-width: 260px;
  }}
  .btn-filter {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    color: var(--text-dim);
    padding: 8px 16px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 600;
    transition: 0.15s;
  }}
  .btn-filter.active, .btn-filter:hover {{
    background: var(--accent);
    color: #fff;
    border-color: var(--accent);
  }}

  /* Box Grid Table */
  .table-container {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow-x: auto;
    max-height: 75vh;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    text-align: left;
  }}
  th {{
    background: #1e293b;
    color: #94a3b8;
    padding: 12px 14px;
    font-weight: 600;
    border: 1px solid var(--border);
    position: sticky;
    top: 0;
    z-index: 10;
    white-space: nowrap;
    user-select: none;
    cursor: pointer;
  }}
  th:hover {{ color: #fff; }}
  td {{
    padding: 10px 14px;
    border: 1px solid var(--border);
    white-space: nowrap;
  }}
  tr:hover {{
    background: #1a2234;
  }}
  .badge {{
    display: inline-block;
    padding: 3px 8px;
    border-radius: 4px;
    font-weight: 600;
    font-size: 11px;
  }}
  .badge-long {{ background: rgba(16,185,129,0.15); color: #34d399; border: 1px solid rgba(16,185,129,0.3); }}
  .badge-short {{ background: rgba(239,68,68,0.15); color: #f87171; border: 1px solid rgba(239,68,68,0.3); }}
  .badge-win {{ background: rgba(16,185,129,0.2); color: #10b981; }}
  .badge-loss {{ background: rgba(239,68,68,0.2); color: #ef4444; }}
  .pagination {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 16px;
    color: var(--text-dim);
    font-size: 13px;
  }}
  .page-btns {{ display: flex; gap: 8px; }}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>Trade Execution Box-Grid Log</h1>
    <p style="color: var(--text-dim); font-size: 13px; margin-top: 4px;">Audited trade-by-trade ledger from 2020 to 2026 backtest simulation</p>
  </div>
</div>

<div class="kpi-row">
  <div class="kpi-box">
    <div class="label">Total Trades</div>
    <div class="val">{total_trades:,}</div>
  </div>
  <div class="kpi-box">
    <div class="label">Win Rate</div>
    <div class="val text-accent">{win_rate:.1f}%</div>
  </div>
  <div class="kpi-box">
    <div class="label">Winning Trades</div>
    <div class="val text-win">{wins:,}</div>
  </div>
  <div class="kpi-box">
    <div class="label">Losing Trades</div>
    <div class="val text-loss">{losses:,}</div>
  </div>
  <div class="kpi-box">
    <div class="label">Final Wallet Balance</div>
    <div class="val text-win">${final_wallet:,.2f}</div>
  </div>
</div>

<div class="controls">
  <input type="text" id="searchInput" class="search-input" placeholder="Search by Coin (SOL, DOGE, ADA) or Reason...">
  <button class="btn-filter active" onclick="setFilter('ALL')">All Trades ({total_trades})</button>
  <button class="btn-filter" onclick="setFilter('LONG')">Longs Only</button>
  <button class="btn-filter" onclick="setFilter('SHORT')">Shorts Only</button>
  <button class="btn-filter" onclick="setFilter('WIN')">Wins ({wins})</button>
  <button class="btn-filter" onclick="setFilter('LOSS')">Losses ({losses})</button>
</div>

<div class="table-container">
  <table id="tradesTable">
    <thead>
      <tr>
        <th>#</th>
        <th>Symbol</th>
        <th>Side</th>
        <th>Entry Time</th>
        <th>Exit Time</th>
        <th>Entry Price</th>
        <th>Exit Price</th>
        <th>PnL ($)</th>
        <th>Return (%)</th>
        <th>Wallet ($)</th>
        <th>BTC Drift</th>
        <th>Why Entered (Entry Rationale)</th>
        <th>Why Won / Lost (Exit Diagnostic)</th>
        <th>Macro News / Market Catalyst</th>
        <th>Regime</th>
      </tr>
    </thead>
    <tbody id="tableBody"></tbody>
  </table>
</div>

<div class="pagination">
  <span id="pageInfo">Showing 1 to 50 of {total_trades}</span>
  <div class="page-btns">
    <button class="btn-filter" onclick="changePage(-1)">Previous</button>
    <button class="btn-filter" onclick="changePage(1)">Next</button>
  </div>
</div>

<script>
  const tradesData = {trades_json};
  let currentFilter = 'ALL';
  let searchTerm = '';
  let currentPage = 1;
  const pageSize = 100;

  function renderTable() {{
    const tbody = document.getElementById('tableBody');
    tbody.innerHTML = '';

    const filtered = tradesData.filter(t => {{
      const matchFilter = 
        currentFilter === 'ALL' ? true :
        currentFilter === 'LONG' ? t.side === 'LONG' :
        currentFilter === 'SHORT' ? t.side === 'SHORT' :
        currentFilter === 'WIN' ? t.pnl_usd > 0 :
        currentFilter === 'LOSS' ? t.pnl_usd <= 0 : true;

      const q = searchTerm.toLowerCase();
      const matchSearch = !searchTerm || 
        t.symbol.toLowerCase().includes(q) ||
        (t.exit_trigger && t.exit_trigger.toLowerCase().includes(q)) ||
        (t.entry_remarks && t.entry_remarks.toLowerCase().includes(q)) ||
        (t.exit_remarks && t.exit_remarks.toLowerCase().includes(q)) ||
        (t.macro_news_event && t.macro_news_event.toLowerCase().includes(q)) ||
        (t.side && t.side.toLowerCase().includes(q));

      return matchFilter && matchSearch;
    }});

    const startIdx = (currentPage - 1) * pageSize;
    const pageItems = filtered.slice(startIdx, startIdx + pageSize);

    for (const t of pageItems) {{
      const tr = document.createElement('tr');
      const isWin = t.pnl_usd > 0;
      const pnlClass = isWin ? 'text-win' : 'text-loss';
      const sideBadge = t.side === 'LONG' ? '<span class="badge badge-long">LONG</span>' : '<span class="badge badge-short">SHORT</span>';
      const btcVal = Number(t.btc_drift_pct || 0);
      const btcColor = btcVal >= 0 ? '#34d399' : '#f87171';
      
      tr.innerHTML = `
        <td style="color: var(--text-dim); font-weight:600;">${{t.trade_id}}</td>
        <td style="font-weight:700;">${{t.symbol}}</td>
        <td>${{sideBadge}}</td>
        <td style="color: var(--text-dim); font-size:12px;">${{t.entry_time ? t.entry_time.replace('+00:00','') : ''}}</td>
        <td style="color: var(--text-dim); font-size:12px;">${{t.exit_time ? t.exit_time.replace('+00:00','') : ''}}</td>
        <td>$${{Number(t.entry_price).toFixed(4)}}</td>
        <td>$${{Number(t.exit_price).toFixed(4)}}</td>
        <td class="${{pnlClass}}" style="font-weight:700;">${{isWin ? '+' : ''}}$${{Number(t.pnl_usd).toFixed(2)}}</td>
        <td class="${{pnlClass}}" style="font-weight:700;">${{isWin ? '+' : ''}}$${{Number(t.pnl_pct).toFixed(2)}}%</td>
        <td style="font-weight:600;">$${{Number(t.cumulative_wallet_usd).toLocaleString(undefined, {{minimumFractionDigits:2, maximumFractionDigits:2}})}}</td>
        <td style="color:${{btcColor}}; font-weight:600;">${{btcVal >= 0 ? '+' : ''}}${{btcVal.toFixed(1)}}%</td>
        <td style="font-size:12px; max-width:260px; white-space:normal; color:#cbd5e1;">${{t.entry_remarks || 'Momentum breakout'}}</td>
        <td style="font-size:12px; max-width:280px; white-space:normal; color:#cbd5e1;">${{t.exit_remarks || t.exit_trigger || ''}}</td>
        <td style="font-size:11px; max-width:220px; white-space:normal; color:#38bdf8; font-weight:500;">${{t.macro_news_event || ''}}</td>
        <td><span style="font-size:11px; font-weight:600; color:${{t.regime==='BULL'?'#34d399':'#f87171'}}">${{t.regime}}</span></td>
      `;
      tbody.appendChild(tr);
    }}

    const totalPages = Math.ceil(filtered.length / pageSize) || 1;
    document.getElementById('pageInfo').innerText = 
      `Showing ${{filtered.length ? startIdx + 1 : 0}} to ${{Math.min(startIdx + pageSize, filtered.length)}} of ${{filtered.length}} filtered trades (Page ${{currentPage}} of ${{totalPages}})`;
  }}

  function setFilter(f) {{
    currentFilter = f;
    currentPage = 1;
    document.querySelectorAll('.btn-filter').forEach(b => {{
      b.classList.toggle('active', b.innerText.toLowerCase().includes(f.toLowerCase()) || (f==='ALL' && b.innerText.includes('All')));
    }});
    renderTable();
  }}

  function changePage(delta) {{
    currentPage += delta;
    if (currentPage < 1) currentPage = 1;
    renderTable();
  }}

  document.getElementById('searchInput').addEventListener('input', (e) => {{
    searchTerm = e.target.value;
    currentPage = 1;
    renderTable();
  }});

  renderTable();
</script>

</body>
</html>
"""

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"[+] Successfully generated Interactive Box-Grid HTML Viewer: {html_path}")

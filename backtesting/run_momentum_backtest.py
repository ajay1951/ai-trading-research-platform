import os
import sys
import glob
import pandas as pd
import numpy as np
import warnings

warnings.filterwarnings("ignore")
sys.path.append(os.path.dirname(__file__))

from momentum_screener import MomentumScreener

HISTORICAL_NEWS_EVENTS = [
    ("2020-03-01", "2020-03-25", "Global Covid-19 Financial Liquidity Shock & Fed Emergency Rate Cuts"),
    ("2020-05-01", "2020-05-20", "3rd Bitcoin Halving (Block Reward halved to 6.25 BTC)"),
    ("2020-06-15", "2020-09-30", "DeFi Summer Surge: Exponential capital rotation into Altcoin ecosystems"),
    ("2020-10-01", "2020-12-31", "PayPal Crypto Rollout & MicroStrategy Institutional Treasury Inflows"),
    ("2021-01-01", "2021-02-28", "Tesla adds $1.5B BTC & Elon Musk Meme/Doge Social Mania"),
    ("2021-04-10", "2021-04-20", "Coinbase Direct Listing (NASDAQ: COIN) Euphoria"),
    ("2021-05-08", "2021-06-15", "China Mining Ban & Elon Musk ESG Backlash (-50% Market Crash)"),
    ("2021-08-01", "2021-11-15", "Alt-L1 Mania (Solana, Avalanche, Layer-1 surges) & BTC ATH $69,000"),
    ("2021-11-16", "2022-01-15", "Federal Reserve Announces Quantitative Tightening & Inflation Spikes"),
    ("2022-05-05", "2022-05-20", "Terra/LUNA & UST Algorithmic Stablecoin Multi-Billion Collapse"),
    ("2022-06-10", "2022-07-15", "Three Arrows Capital (3AC), Celsius, & Voyager Insolvency Contagion"),
    ("2022-07-16", "2022-08-20", "Bear Market Relief Rally (ETH Merge Anticipation Pump)"),
    ("2022-11-05", "2022-12-05", "FTX & Alameda Research Bankruptcy Crash (BTC dumps to $15.5k macro low)"),
    ("2023-01-01", "2023-02-15", "Post-FTX Short Squeeze Rebound & AI Crypto Narrative Surge"),
    ("2023-03-08", "2023-03-25", "Silicon Valley Bank (SVB) Banking Crisis & USDC Flight to Bitcoin"),
    ("2023-06-12", "2023-06-30", "BlackRock Submits Landmark Spot Bitcoin ETF Application"),
    ("2023-10-15", "2024-01-09", "Spot Bitcoin ETF Approval Anticipation & Massive Institutional Accumulation"),
    ("2024-01-10", "2024-01-20", "SEC Approves 11 Spot Bitcoin ETFs (Historic Wall Street Inflow)"),
    ("2024-02-15", "2024-03-31", "Pre-Halving Capital Rush: Bitcoin breaches new ATH $73,700"),
    ("2024-04-15", "2024-05-05", "4th Bitcoin Halving & Runes Protocol Launch"),
    ("2024-06-15", "2024-08-10", "German Government & Mt. Gox Bitcoin Liquidation Supply Pressure"),
    ("2024-10-15", "2025-01-15", "US Presidential Election Pro-Crypto Wave & Macro Expansion"),
]

def get_macro_news_event(date_str: str, is_bull: bool) -> str:
    ymd = str(date_str)[:10]
    for start, end, desc in HISTORICAL_NEWS_EVENTS:
        if start <= ymd <= end:
            return desc
    return "Macro Bull Market Trend" if is_bull else "Macro Bear Market Trend"

def run_momentum_rotation_backtest():
    print("=" * 65, flush=True)
    print("[*] DYNAMIC MOMENTUM SCREENER & CAPITAL ROTATION BACKTEST", flush=True)
    print("=" * 65, flush=True)
    
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    
    # Discover available 1h historical files
    pattern = os.path.join(data_dir, "*_1h_historical.csv")
    csv_files = glob.glob(pattern)
    
    if not csv_files:
        print("[!] No 1h historical CSV files found in data directory.")
        return
        
    assets = []
    dfs = {}
    
    print("\n1. Loading Available Universe Data (1h Candles)...", flush=True)
    for f in csv_files:
        basename = os.path.basename(f)
        symbol = basename.replace("_1h_historical.csv", "")
        try:
            df = pd.read_csv(f)
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, format='ISO8601', errors='coerce')
            df = df.dropna(subset=['timestamp', 'close', 'volume']).sort_values('timestamp').drop_duplicates('timestamp')
            df = df.set_index('timestamp')
            if len(df) > 5000: # Ensure sufficient history
                dfs[symbol] = df
                assets.append(symbol)
                print(f"  [+] Loaded {symbol:<10}: {len(df):,} candles ({df.index[0].strftime('%Y-%m')} to {df.index[-1].strftime('%Y-%m')})", flush=True)
        except Exception as e:
            pass

    if "BTCUSDT" not in dfs:
        print("[!] Error: BTCUSDT is required as market benchmark.")
        return
        
    # Master Timeline: Driven by BTCUSDT from 2020 to 2026
    master_idx = dfs["BTCUSDT"].index.sort_values()
    common_idx = master_idx[master_idx >= '2020-01-01']
    
    print(f"\n[+] Synchronized Expanded Universe: {len(assets)} coins across {len(common_idx):,} hourly bars (~{len(common_idx)//24:,} days).", flush=True)
    
    # Build aligned DataFrames for Closes, Volumes, Highs, Lows using reindex (unlisted coins have NaN before listing)
    closes_dict = {a: dfs[a]['close'].reindex(common_idx) for a in assets}
    volumes_dict = {a: dfs[a]['volume'].reindex(common_idx).fillna(0.0) for a in assets}
    highs_dict = {a: (dfs[a]['high'] if 'high' in dfs[a].columns else dfs[a]['close']).reindex(common_idx) for a in assets}
    lows_dict = {a: (dfs[a]['low'] if 'low' in dfs[a].columns else dfs[a]['close']).reindex(common_idx) for a in assets}
    
    closes_df = pd.DataFrame(closes_dict)
    volumes_df = pd.DataFrame(volumes_dict)
    highs_df = pd.DataFrame(highs_dict)
    lows_df = pd.DataFrame(lows_dict)
    
    # Calculate Macro Regime Filter: 100-Day SMA of BTC (2,400 hours)
    btc_100d_sma = closes_df["BTCUSDT"].rolling(window=2400, min_periods=1).mean()
    
    # 2. Compute Point-in-Time Momentum Scores across all history
    screener = MomentumScreener(rs_window=168, vol_short=24, vol_long=480, breakout_window=480)
    scores_df, rs_df, breakout_df = screener.compute_cross_sectional_scores(
        closes_df, volumes_df, highs_df, lows_df, btc_symbol="BTCUSDT"
    )
    
    # Precompute RSI for bear market shorting engine
    rsi_dict = {}
    for a in assets:
        delta = closes_df[a].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14, min_periods=1).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=1).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi_dict[a] = (100 - (100 / (1 + rs))).fillna(50.0)
    rsi_df = pd.DataFrame(rsi_dict)

    # 3. Simulate Dynamic Capital Rotation (Dual-Regime: Bull Momentum + Bear Shorting)
    print("\n2. Executing Dual-Regime Capital Rotation Simulation...", flush=True)
    initial_cash = 50.0
    cash = initial_cash
    MAX_SLOTS = 2
    TRAILING_STOP = 0.05
    TAKE_PROFIT = 0.25
    FEE = 0.0004
    SLIP = 0.0002
    
    # Bear shorting parameters
    BEAR_RSI_THRESH = 68.0
    BEAR_STOP_TRAIL = 0.16
    BEAR_TARGET_TP = 0.15
    BEAR_MAX_HOLD = 240
    
    positions = {}
    trades_log = []
    portfolio_values = [initial_cash]
    
    # Compounding 3x Milestones
    cycle_count = 1
    current_cycle_base = initial_cash
    target_milestone = current_cycle_base * 3.0
    milestone_events = []
    
    # Pre-extract numpy matrices for speed
    c_matrix = closes_df.values
    rsi_matrix = rsi_df.values
    s_matrix = scores_df.values
    rs_matrix = rs_df.values
    bo_matrix = breakout_df.values
    btc_closes = closes_df["BTCUSDT"].values
    btc_sma_vals = btc_100d_sma.values
    col_names = closes_df.columns.tolist()
    asset_to_col = {a: idx for idx, a in enumerate(col_names)}
    
    for i in range(1, len(common_idx)):
        ts = common_idx[i]
        curr_prices = c_matrix[i]
        prev_prices = c_matrix[i-1]
        btc_price = btc_closes[i]
        btc_sma = btc_sma_vals[i]
        is_bull_regime = btc_price > btc_sma
        
        # Calculate current total portfolio equity
        open_equity = 0.0
        for sym, pos in positions.items():
            sym_idx = asset_to_col[sym]
            p = curr_prices[sym_idx]
            if np.isnan(p): p = pos['entry_price']
            if pos.get('is_short', False):
                unrealized = (pos['entry_price'] - p) * pos['size']
                open_equity += (pos['size'] * pos['entry_price']) + unrealized
            else:
                open_equity += pos['size'] * p
                
        total_equity = cash + open_equity
        portfolio_values.append(total_equity)
        
        # Check 3x Milestone Hit
        if total_equity >= target_milestone and total_equity > current_cycle_base:
            milestone_events.append({'cycle': cycle_count, 'equity': total_equity, 'date': str(ts)})
            print(f"  [*** MILESTONE HIT] Cycle {cycle_count} Reached: ${total_equity:,.2f}! Advancing to next 3x cycle...", flush=True)
            cycle_count += 1
            current_cycle_base = total_equity
            target_milestone = current_cycle_base * 3.0
            print(f"    [->] Cycle {cycle_count} Target: ${target_milestone:,.2f}", flush=True)

        # -------------------------------------------------------------
        # A. Manage Open Positions (Trailing Stop & Take-Profit Targets)
        # -------------------------------------------------------------
        symbols_to_close = []
        for sym, pos in list(positions.items()):
            sym_idx = asset_to_col[sym]
            p = curr_prices[sym_idx]
            if np.isnan(p): continue
            is_short = pos.get('is_short', False)
            
            if is_short:
                if p < pos['lowest_price']:
                    pos['lowest_price'] = p
                gain_pct = (pos['entry_price'] - p) / pos['entry_price']
                bounce_from_low = (p - pos['lowest_price']) / pos['lowest_price']
                
                if is_bull_regime:
                    symbols_to_close.append((sym, "Cover Short: Bull Regime Resumed"))
                elif gain_pct >= BEAR_TARGET_TP:
                    symbols_to_close.append((sym, f"Short Take Profit (+{gain_pct*100:.1f}%)"))
                elif bounce_from_low >= BEAR_STOP_TRAIL:
                    symbols_to_close.append((sym, f"Short Trailing Stop (-{bounce_from_low*100:.1f}%)"))
                elif (i - pos['entry_step']) > BEAR_MAX_HOLD and gain_pct > 0.04:
                    symbols_to_close.append((sym, f"Short Time-Decay Exit (+{gain_pct*100:.1f}%)"))
            else:
                if p > pos['highest_price']:
                    pos['highest_price'] = p
                gain_from_entry = (p - pos['entry_price']) / pos['entry_price']
                drop_from_peak = (pos['highest_price'] - p) / pos['highest_price']
                
                if not is_bull_regime and drop_from_peak >= 0.03:
                    symbols_to_close.append((sym, 'Macro Bear Defense Exit'))
                elif drop_from_peak >= TRAILING_STOP:
                    symbols_to_close.append((sym, 'Trailing Stop (-5% from peak)'))
                elif gain_from_entry >= TAKE_PROFIT:
                    symbols_to_close.append((sym, 'Take Profit (+25% target reached!)'))
                    
        # Close triggered positions
        for sym, reason in symbols_to_close:
            sym_idx = asset_to_col[sym]
            p = curr_prices[sym_idx]
            pos = positions.pop(sym)
            is_short = pos.get('is_short', False)
            entry_btc = pos.get('entry_btc_price', btc_price)
            btc_drift = ((btc_price - entry_btc) / entry_btc * 100.0) if entry_btc > 0 else 0.0
            
            if is_short:
                exec_price = p * (1.0 + SLIP)
                pnl = (pos['entry_price'] - exec_price) * pos['size'] - (pos['size'] * exec_price * FEE)
                cash += (pos['size'] * pos['entry_price'] + pnl)
                pnl_pct = (pos['entry_price'] - exec_price) / pos['entry_price'] * 100.0
                if pnl > 0:
                    exit_remarks = f"Profit Target Reached: Overbought relief rally collapsed into downtrend (-{abs(pnl_pct):.1f}% drop); BTC drift {btc_drift:+.1f}%"
                else:
                    exit_remarks = f"Short Squeeze Stop-Loss: Violent relief bounce squeezed price +{abs(pnl_pct):.1f}% before drop resumed; BTC drift {btc_drift:+.1f}%"
            else:
                exec_price = p * (1.0 - SLIP)
                gross_val = pos['size'] * exec_price
                net_val = gross_val * (1.0 - FEE)
                cash += net_val
                pnl = net_val - (pos['size'] * pos['entry_price'])
                pnl_pct = (exec_price - pos['entry_price']) / pos['entry_price'] * 100.0
                if pnl > 0:
                    if 'Take Profit' in reason:
                        exit_remarks = f"Take Profit Hit (+25%): Explosive trend continuation; BTC was {btc_drift:+.1f}% during hold"
                    else:
                        exit_remarks = f"Trailing Stop Win (+{pnl_pct:.1f}%): Rode momentum expansion, locked in gains on pullback; BTC drift {btc_drift:+.1f}%"
                else:
                    if 'Macro Bear' in reason:
                        exit_remarks = f"Macro Bear Defense Exit: BTC broke below 100d trendline; liquidated to cash; BTC drift {btc_drift:+.1f}%"
                    else:
                        exit_remarks = f"Trailing Stop Loss (-5% from peak): Momentum failed and sellers took control; BTC drift {btc_drift:+.1f}% ({'Tailwind' if btc_drift>0 else 'Headwind'})"
                
            news_event = get_macro_news_event(str(ts), is_bull_regime)
            trades_log.append({
                'trade_id': len(trades_log) + 1,
                'symbol': sym,
                'side': 'SHORT' if is_short else 'LONG',
                'entry_time': pos.get('entry_time', ''),
                'exit_time': str(ts),
                'entry_price': round(pos['entry_price'], 4),
                'exit_price': round(exec_price, 4),
                'size': round(pos['size'], 4),
                'position_value_usd': round(pos['size'] * pos['entry_price'], 2),
                'pnl_usd': round(pnl, 2),
                'pnl_pct': round(pnl_pct, 2),
                'cumulative_wallet_usd': round(cash, 2),
                'exit_trigger': reason,
                'entry_remarks': pos.get('entry_reason', 'Momentum trigger'),
                'exit_remarks': exit_remarks,
                'macro_news_event': news_event,
                'btc_drift_pct': round(btc_drift, 2),
                'regime': 'BULL' if is_bull_regime else 'BEAR'
            })

        # -------------------------------------------------------------
        # B. Regime-Adaptive Entries
        # -------------------------------------------------------------
        if is_bull_regime:
            # 1. Bull Regime: Momentum Breakout Rotation
            if (i % 24 == 0 or len(positions) < MAX_SLOTS):
                s_row = pd.Series(s_matrix[i], index=col_names)
                rs_row = pd.Series(rs_matrix[i], index=col_names)
                bo_row = pd.Series(bo_matrix[i], index=col_names)
                
                top_candidates = screener.select_top_runners(
                    s_row, rs_row, bo_row, top_k=MAX_SLOTS, min_rs=0.03, min_breakout=0.60
                )
                
                # Check if any existing position has completely dropped off momentum rank
                for sym in list(positions.keys()):
                    if not positions[sym].get('is_short', False):
                        if top_candidates and sym not in top_candidates and s_row.get(sym, 0) < 0.10:
                            sym_idx = asset_to_col[sym]
                            p = curr_prices[sym_idx]
                            pos = positions.pop(sym)
                            exec_price = p * (1.0 - SLIP)
                            gross_val = pos['size'] * exec_price
                            cash += gross_val * (1.0 - FEE)
                            pnl = gross_val - (pos['size'] * pos['entry_price'])
                            pnl_pct = ((exec_price - pos['entry_price'])/pos['entry_price'])*100.0
                            entry_btc = pos.get('entry_btc_price', btc_price)
                            btc_drift = ((btc_price - entry_btc) / entry_btc * 100.0) if entry_btc > 0 else 0.0
                            
                            if pnl > 0:
                                exit_remarks = f"Rotation Profit (+{pnl_pct:.1f}%): Closed to allocate capital to higher-momentum runner; BTC drift {btc_drift:+.1f}%"
                            else:
                                exit_remarks = f"Rotation Cut (-{abs(pnl_pct):.1f}%): Closed to reallocate capital into stronger breakout runner; BTC drift {btc_drift:+.1f}%"
                                
                            trades_log.append({
                                'trade_id': len(trades_log) + 1,
                                'symbol': sym,
                                'side': 'LONG',
                                'entry_time': pos.get('entry_time', ''),
                                'exit_time': str(ts),
                                'entry_price': round(pos['entry_price'], 4),
                                'exit_price': round(exec_price, 4),
                                'size': round(pos['size'], 4),
                                'position_value_usd': round(pos['size'] * pos['entry_price'], 2),
                                'pnl_usd': round(pnl, 2),
                                'pnl_pct': round(pnl_pct, 2),
                                'cumulative_wallet_usd': round(cash, 2),
                                'exit_trigger': 'Momentum Rotation (Better Runner Emerged)',
                                'entry_remarks': pos.get('entry_reason', 'Momentum trigger'),
                                'exit_remarks': exit_remarks,
                                'macro_news_event': get_macro_news_event(str(ts), is_bull_regime),
                                'btc_drift_pct': round(btc_drift, 2),
                                'regime': 'BULL' if is_bull_regime else 'BEAR'
                            })

                # Open fresh positions in qualified top runners
                open_slots = MAX_SLOTS - len(positions)
                if open_slots > 0 and top_candidates:
                    slot_budget = (total_equity * 0.48)
                    for candidate in top_candidates:
                        if candidate not in positions and cash >= 5.0:
                            alloc_cash = min(cash, slot_budget)
                            if alloc_cash >= 5.0:
                                cand_idx = asset_to_col[candidate]
                                p = curr_prices[cand_idx]
                                if np.isnan(p) or p <= 0:
                                    continue
                                exec_price = p * (1.0 + SLIP)
                                amount = (alloc_cash * (1.0 - FEE)) / exec_price
                                cash -= alloc_cash
                                positions[candidate] = {
                                    'size': amount,
                                    'entry_price': exec_price,
                                    'highest_price': exec_price,
                                    'lowest_price': exec_price,
                                    'is_short': False,
                                    'entry_step': i,
                                    'entry_time': str(ts),
                                    'entry_btc_price': btc_price,
                                    'entry_reason': f"Bull Momentum Breakout: Top runner with RS vs BTC ({rs_row.get(candidate, 0.0):+.1%}), Donchian breakout ({bo_row.get(candidate, 0.0):.2f})"
                                }
        else:
            # 2. Bear Regime: Quantitative Relief Rally Fade Shorting
            if len(positions) < MAX_SLOTS and cash >= 15.0:
                for sym in assets:
                    if sym == "BTCUSDT" or sym in positions: continue
                    sym_idx = asset_to_col[sym]
                    p = curr_prices[sym_idx]
                    if np.isnan(p) or p <= 0: continue
                    
                    # Signal: Hourly RSI was overbought (>= 68) and price rolled over below previous hour
                    if rsi_matrix[i-1, sym_idx] >= BEAR_RSI_THRESH and p < prev_prices[sym_idx]:
                        budget = min(cash, 25.0 if cash < 50 else (cash + open_equity) * 0.48)
                        exec_p = p * (1.0 - SLIP)
                        amt = (budget * (1.0 - FEE)) / exec_p
                        cash -= budget
                        positions[sym] = {
                            'size': amt,
                            'entry_price': exec_p,
                            'highest_price': exec_p,
                            'lowest_price': exec_p,
                            'is_short': True,
                            'entry_step': i,
                            'entry_time': str(ts),
                            'entry_btc_price': btc_price,
                            'entry_reason': f"Bear Relief Fade: Hourly RSI peaked at {rsi_matrix[i-1, sym_idx]:.1f} (overbought exhaustion), rolled over in bear regime"
                        }
                        if len(positions) >= MAX_SLOTS:
                            break

    # Final mark-to-market: close remaining open positions to realize full accounting
    last_prices = c_matrix[-1]
    final_ts = str(common_idx[-1])
    for sym, pos in list(positions.items()):
        sym_idx = asset_to_col[sym]
        p = last_prices[sym_idx] if not np.isnan(last_prices[sym_idx]) else pos['entry_price']
        is_short = pos.get('is_short', False)
        entry_btc = pos.get('entry_btc_price', btc_price)
        btc_drift = ((btc_price - entry_btc) / entry_btc * 100.0) if entry_btc > 0 else 0.0
        
        if is_short:
            exec_price = p * (1.0 + SLIP)
            pnl = (pos['entry_price'] - exec_price) * pos['size'] - (pos['size'] * exec_price * FEE)
            cash += (pos['size'] * pos['entry_price'] + pnl)
            pnl_pct = (pos['entry_price'] - exec_price) / pos['entry_price'] * 100.0
            exit_remarks = "Final Backtest Mark-to-Market Close"
        else:
            exec_price = p * (1.0 - SLIP)
            gross_val = pos['size'] * exec_price
            net_val = gross_val * (1.0 - FEE)
            cash += net_val
            pnl = net_val - (pos['size'] * pos['entry_price'])
            pnl_pct = (exec_price - pos['entry_price']) / pos['entry_price'] * 100.0
            exit_remarks = "Final Backtest Mark-to-Market Close"
            
        trades_log.append({
            'trade_id': len(trades_log) + 1,
            'symbol': sym,
            'side': 'SHORT' if is_short else 'LONG',
            'entry_time': pos.get('entry_time', ''),
            'exit_time': final_ts,
            'entry_price': round(pos['entry_price'], 4),
            'exit_price': round(exec_price, 4),
            'size': round(pos['size'], 4),
            'position_value_usd': round(pos['size'] * pos['entry_price'], 2),
            'pnl_usd': round(pnl, 2),
            'pnl_pct': round(pnl_pct, 2),
            'cumulative_wallet_usd': round(cash, 2),
            'exit_trigger': 'Final Backtest Close',
            'entry_remarks': pos.get('entry_reason', 'Momentum trigger'),
            'exit_remarks': exit_remarks,
            'macro_news_event': get_macro_news_event(final_ts, is_bull_regime),
            'btc_drift_pct': round(btc_drift, 2),
            'regime': 'FINAL'
        })
    positions.clear()
    final_equity = cash
    portfolio_values.append(final_equity)
    
    # Export all trades to CSV, Excel, and Interactive HTML Box Viewer
    trades_df = pd.DataFrame(trades_log)
    csv_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    os.makedirs(csv_dir, exist_ok=True)
    csv_file = os.path.join(csv_dir, 'backtest_trades_log.csv')
    trades_df.to_csv(csv_file, index=False)
    
    # Generate Formatted Excel Spreadsheet (Box Grid with borders)
    xlsx_file = os.path.join(csv_dir, 'backtest_trades_log.xlsx')
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Trades Box Log"
        ws.views.sheetView[0].showGridLines = True

        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        win_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
        loss_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
        thin_border = Border(
            left=Side(style='thin', color='CBD5E1'), right=Side(style='thin', color='CBD5E1'),
            top=Side(style='thin', color='CBD5E1'), bottom=Side(style='thin', color='CBD5E1')
        )

        headers = list(trades_df.columns)
        ws.append(headers)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border
        ws.row_dimensions[1].height = 25

        for r_idx, row in trades_df.iterrows():
            ws.append(list(row))
            cur_row = ws[r_idx + 2]
            is_win = row['pnl_usd'] > 0
            fill = win_fill if is_win else loss_fill
            for cell in cur_row:
                cell.border = thin_border
                cell.alignment = Alignment(vertical="center")
            cur_row[headers.index('pnl_usd')].fill = fill
            cur_row[headers.index('pnl_pct')].fill = fill
            cur_row[headers.index('pnl_usd')].font = Font(bold=True, color="166534" if is_win else "991B1B")
            cur_row[headers.index('pnl_pct')].font = Font(bold=True, color="166534" if is_win else "991B1B")

        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        wb.save(xlsx_file)
    except Exception as e:
        xlsx_file = None

    # Performance Statistics
    total_return = ((final_equity - initial_cash) / initial_cash) * 100.0
    p_series = pd.Series(portfolio_values)
    returns = p_series.pct_change().dropna()
    sharpe = (returns.mean() / returns.std()) * np.sqrt(365 * 24) if returns.std() > 0 else 0.0
    
    # Drawdown
    cummax = p_series.cummax()
    drawdown = (p_series - cummax) / cummax
    max_dd = drawdown.min() * 100.0
    
    # Trade stats
    total_trades = len(trades_log)
    profitable_trades = [t for t in trades_log if t['pnl_usd'] > 0]
    win_rate = (len(profitable_trades) / total_trades * 100.0) if total_trades > 0 else 0.0
    gross_profits = sum(t['pnl_usd'] for t in profitable_trades)
    gross_losses = abs(sum(t['pnl_usd'] for t in trades_log if t['pnl_usd'] < 0))
    profit_factor = (gross_profits / gross_losses) if gross_losses > 0 else float('inf')
    
    # Compare with Buy & Hold BTC
    btc_start = btc_closes[0]
    btc_end = btc_closes[-1]
    btc_bh_return = ((btc_end - btc_start) / btc_start) * 100.0
    btc_bh_final = initial_cash * (btc_end / btc_start)

    print("\n" + "=" * 65)
    print("[*] DYNAMIC MOMENTUM SCREENER RESULTS (2020-2026):")
    print("=" * 65)
    print(f"  Starting Wallet       : ${initial_cash:,.2f}")
    print(f"  Final Wallet Balance  : ${final_equity:,.2f}")
    print(f"  Total Net Return      : {total_return:>+8.2f}%")
    print(f"  Bitcoin Buy & Hold    : {btc_bh_return:>+8.2f}% (${btc_bh_final:,.2f})")
    print(f"  Strategy Outperform   : {(total_return - btc_bh_return):>+8.2f}% vs BTC")
    print(f"  Portfolio Sharpe Ratio: {sharpe:>8.2f}")
    print(f"  Maximum Drawdown      : {max_dd:>8.2f}%")
    print(f"  Total Trades Executed : {total_trades:>8,d}")
    print(f"  Strategy Win Rate     : {win_rate:>8.1f}%")
    print(f"  Profit Factor         : {profit_factor:>8.2f}")
    print(f"  3x Milestones Passed  : {len(milestone_events)} cycles completed")
    for event in milestone_events:
        print(f"    - Cycle {event['cycle']} Hit: ${event['equity']:,.2f} on {event['date']}")
    print("=" * 65)
    print(f"\n[+] TRADE LOG EXPORTS AVAILABLE IN 3 FORMATS:")
    print(f"    1. Raw CSV Log      : {os.path.abspath(csv_file)}")
    if xlsx_file:
        print(f"    2. Excel Box Grid   : {os.path.abspath(xlsx_file)}")
    print(f"    3. Visual HTML Grid : {os.path.abspath(os.path.join(csv_dir, 'backtest_trades_viewer.html'))}")

if __name__ == "__main__":
    run_momentum_rotation_backtest()

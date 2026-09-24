import os
import sys
import glob
import pandas as pd
import numpy as np
import warnings

warnings.filterwarnings("ignore")
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backtesting'))

from momentum_screener import MomentumScreener

data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
pattern = os.path.join(data_dir, "*_1h_historical.csv")
csv_files = glob.glob(pattern)

dfs = {}
assets = []

for f in csv_files:
    basename = os.path.basename(f)
    symbol = basename.replace("_1h_historical.csv", "")
    try:
        df = pd.read_csv(f)
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, format='ISO8601', errors='coerce')
        df = df.dropna(subset=['timestamp', 'close']).sort_values('timestamp').drop_duplicates('timestamp')
        df = df.set_index('timestamp')
        if len(df) > 5000:
            dfs[symbol] = df
            assets.append(symbol)
    except Exception:
        pass

btc_df = dfs["BTCUSDT"]
master_idx = btc_df.index[btc_df.index >= '2020-01-01'].sort_values()

closes_dict = {a: dfs[a]['close'].reindex(master_idx) for a in assets}
volumes_dict = {a: dfs[a]['volume'].reindex(master_idx).fillna(0.0) for a in assets}
highs_dict = {a: (dfs[a]['high'] if 'high' in dfs[a].columns else dfs[a]['close']).reindex(master_idx) for a in assets}
lows_dict = {a: (dfs[a]['low'] if 'low' in dfs[a].columns else dfs[a]['close']).reindex(master_idx) for a in assets}

closes_df = pd.DataFrame(closes_dict)
volumes_df = pd.DataFrame(volumes_dict)
highs_df = pd.DataFrame(highs_dict)
lows_df = pd.DataFrame(lows_dict)

full_btc = dfs["BTCUSDT"]['close']
btc_100d_sma = full_btc.rolling(2400, min_periods=1).mean().reindex(master_idx)

# Precompute RSI for bear market shorting
rsi_df = pd.DataFrame()
for a in assets:
    delta = closes_df[a].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=1).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi_df[a] = (100 - (100 / (1 + rs))).fillna(50.0)

screener = MomentumScreener(rs_window=168, vol_short=24, vol_long=480, breakout_window=480)
scores_df, rs_df, breakout_df = screener.compute_cross_sectional_scores(
    closes_df, volumes_df, highs_df, lows_df, btc_symbol="BTCUSDT"
)

print(f"Loaded {len(assets)} coins across {len(master_idx)} hours.")

initial_cash = 50.0
cash = initial_cash
positions = {} # {sym: {'size', 'entry_price', 'highest_price', 'lowest_price', 'is_short', 'entry_step'}}
trades_log = []
portfolio_values = [initial_cash]

MAX_SLOTS = 2
FEE = 0.0004
SLIP = 0.0002

c_matrix = closes_df.values
rsi_matrix = rsi_df.values
s_matrix = scores_df.values
rs_matrix = rs_df.values
bo_matrix = breakout_df.values
btc_closes = closes_df["BTCUSDT"].values
btc_sma_vals = btc_100d_sma.values
col_names = closes_df.columns.tolist()
asset_to_col = {a: idx for idx, a in enumerate(col_names)}

milestones = []
cycle = 1
base = 50.0
target = 150.0

for i in range(1, len(master_idx)):
    ts = master_idx[i]
    curr_prices = c_matrix[i]
    prev_prices = c_matrix[i-1]
    btc_price = btc_closes[i]
    btc_sma = btc_sma_vals[i]
    is_bull_regime = btc_price > btc_sma
    
    # Calculate equity
    open_equity = 0.0
    for sym, pos in positions.items():
        p = curr_prices[asset_to_col[sym]]
        if np.isnan(p): p = pos['entry_price']
        if pos['is_short']:
            unrealized = (pos['entry_price'] - p) * pos['size']
            open_equity += (pos['size'] * pos['entry_price']) + unrealized
        else:
            open_equity += pos['size'] * p
            
    tot_equity = cash + open_equity
    portfolio_values.append(tot_equity)
    
    if tot_equity >= target and tot_equity > base:
        milestones.append((cycle, tot_equity, str(ts)))
        print(f"  [*** MILESTONE HIT] Cycle {cycle} Reached: ${tot_equity:,.2f}! Advancing to next cycle...", flush=True)
        cycle += 1
        base = tot_equity
        target = base * 3.0
        print(f"    [->] Cycle {cycle} Target: ${target:,.2f}", flush=True)
        
    # Manage existing positions
    to_close = []
    for sym, pos in list(positions.items()):
        p = curr_prices[asset_to_col[sym]]
        if np.isnan(p): continue
        
        if pos['is_short']:
            if p < pos['lowest_price']: pos['lowest_price'] = p
            gain = (pos['entry_price'] - p) / pos['entry_price']
            bounce = (p - pos['lowest_price']) / pos['lowest_price']
            
            if is_bull_regime: # Regime flipped to bull
                to_close.append((sym, "Cover Short: Bull Regime Resumed"))
            elif gain >= 0.15:
                to_close.append((sym, f"Short TP (+{gain*100:.1f}%)"))
            elif bounce >= 0.16:
                to_close.append((sym, f"Short Trail Stop (-{bounce*100:.1f}%)"))
            elif (i - pos['entry_step']) > 240 and gain > 0.04:
                to_close.append((sym, f"Short Time Exit (+{gain*100:.1f}%)"))
        else:
            if p > pos['highest_price']: pos['highest_price'] = p
            gain = (p - pos['entry_price']) / pos['entry_price']
            drop = (pos['highest_price'] - p) / pos['highest_price']
            
            if not is_bull_regime and drop >= 0.03:
                to_close.append((sym, "Macro Bear Defense Exit"))
            elif drop >= 0.05:
                to_close.append((sym, f"Long Trail Stop (-{drop*100:.1f}%)"))
            elif gain >= 0.25:
                to_close.append((sym, f"Long TP (+{gain*100:.1f}%)"))
                
    for sym, reason in to_close:
        p = curr_prices[asset_to_col[sym]]
        pos = positions.pop(sym)
        if pos['is_short']:
            exec_p = p * (1 + SLIP)
            pnl = (pos['entry_price'] - exec_p) * pos['size'] - (pos['size'] * exec_p * FEE)
            cash += (pos['size'] * pos['entry_price'] + pnl)
            pnl_pct = (pos['entry_price'] - exec_p) / pos['entry_price'] * 100.0
        else:
            exec_p = p * (1 - SLIP)
            gross = pos['size'] * exec_p
            cash += gross * (1 - FEE)
            pnl = gross - (pos['size'] * pos['entry_price'])
            pnl_pct = (exec_p - pos['entry_price']) / pos['entry_price'] * 100.0
            
        trades_log.append({'symbol': sym, 'pnl': pnl, 'pnl_pct': pnl_pct, 'reason': reason, 'date': str(ts)})

    # Regime-Based Entries
    if is_bull_regime:
        # BULL REGIME: Momentum Breakout Rotation
        if (i % 24 == 0 or len(positions) < MAX_SLOTS):
            s_row = pd.Series(s_matrix[i], index=col_names)
            rs_row = pd.Series(rs_matrix[i], index=col_names)
            bo_row = pd.Series(bo_matrix[i], index=col_names)
            
            top_candidates = screener.select_top_runners(
                s_row, rs_row, bo_row, top_k=MAX_SLOTS, min_rs=0.03, min_breakout=0.60
            )
            
            open_slots = MAX_SLOTS - len(positions)
            if open_slots > 0 and top_candidates:
                slot_budget = (tot_equity * 0.48)
                for cand in top_candidates:
                    if cand not in positions and cash >= 5.0:
                        p = curr_prices[asset_to_col[cand]]
                        if not np.isnan(p) and p > 0:
                            alloc = min(cash, slot_budget)
                            exec_p = p * (1 + SLIP)
                            amt = (alloc * (1 - FEE)) / exec_p
                            cash -= alloc
                            positions[cand] = {
                                'size': amt, 'entry_price': exec_p, 'highest_price': exec_p,
                                'lowest_price': exec_p, 'is_short': False, 'entry_step': i
                            }
    else:
        # BEAR REGIME: Active Relief Rally Fade Shorting
        if len(positions) < MAX_SLOTS and cash >= 15.0:
            for sym in assets:
                if sym == "BTCUSDT" or sym in positions: continue
                s_idx = asset_to_col[sym]
                p = curr_prices[s_idx]
                if np.isnan(p) or p <= 0: continue
                
                # If coin experienced an overbought bounce and is now rolling over
                if rsi_matrix[i-1, s_idx] >= 68.0 and p < prev_prices[s_idx]:
                    budget = min(cash, 25.0 if cash < 50 else (cash + open_equity) * 0.48)
                    exec_p = p * (1 - SLIP)
                    amt = (budget * (1 - FEE)) / exec_p
                    cash -= budget
                    positions[sym] = {
                        'size': amt, 'entry_price': exec_p, 'lowest_price': exec_p,
                        'highest_price': exec_p, 'is_short': True, 'entry_step': i
                    }
                    if len(positions) >= MAX_SLOTS:
                        break

final_eq = cash
last_prices = c_matrix[-1]
for sym, pos in positions.items():
    p = last_prices[asset_to_col[sym]]
    if pos['is_short']:
        unrealized = (pos['entry_price'] - p) * pos['size']
        final_eq += (pos['size'] * pos['entry_price']) + unrealized
    else:
        final_eq += pos['size'] * p
        
btc_start = closes_df["BTCUSDT"].dropna().iloc[0]
btc_end = closes_df["BTCUSDT"].dropna().iloc[-1]
btc_ret = ((btc_end - btc_start) / btc_start) * 100.0
total_ret = ((final_eq - initial_cash) / initial_cash) * 100.0

print("\n" + "=" * 65)
print(f"[*] DUAL-REGIME (BULL BREAKOUT + BEAR SHORTING) 7-YEAR RESULTS:")
print("=" * 65)
print(f"  Starting Wallet       : ${initial_cash:,.2f}")
print(f"  Final Wallet Balance  : ${final_eq:,.2f}")
print(f"  Net Total Return      : {total_ret:>+8.2f}%")
print(f"  Bitcoin Return        : {btc_ret:>+8.2f}%")
print(f"  Alpha vs Bitcoin      : {(total_ret - btc_ret):>+8.2f}%")
print(f"  Total Trades Executed : {len(trades_log):>8d}")
wins = [t for t in trades_log if t['pnl'] > 0]
win_rate = len(wins) / len(trades_log) * 100 if trades_log else 0
print(f"  Win Rate              : {win_rate:>8.1f}%")
print("=" * 65)

import os
import sys
import glob
import pandas as pd
import numpy as np
import warnings

warnings.filterwarnings("ignore")

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
        if df.index[0] <= pd.Timestamp('2021-11-01', tz='UTC') and df.index[-1] >= pd.Timestamp('2023-01-01', tz='UTC'):
            dfs[symbol] = df
            assets.append(symbol)
    except Exception:
        pass

btc_df = dfs["BTCUSDT"]
bear_mask = (btc_df.index >= '2021-11-01') & (btc_df.index <= '2023-01-01')
bear_idx = btc_df.index[bear_mask].sort_values()

closes_df = pd.DataFrame({a: dfs[a]['close'].reindex(bear_idx) for a in assets})
highs_df = pd.DataFrame({a: (dfs[a]['high'] if 'high' in dfs[a].columns else dfs[a]['close']).reindex(bear_idx) for a in assets})
lows_df = pd.DataFrame({a: (dfs[a]['low'] if 'low' in dfs[a].columns else dfs[a]['close']).reindex(bear_idx) for a in assets})
volumes_df = pd.DataFrame({a: dfs[a]['volume'].reindex(bear_idx).fillna(0.0) for a in assets})

full_btc = dfs["BTCUSDT"]['close']
btc_50d_sma = full_btc.rolling(1200, min_periods=1).mean().reindex(bear_idx)

# Let's test a strategy that does:
# 1. Short Overbought Relief Rallies: When an altcoin rallies (RSI > 70 or price near 20-day high)
#    and then prints a reversal (close < prev close and close < 24h EMA), short it!
# 2. Or: Long Extreme Capitulation Wicks (RSI < 20 on 1h with volume > 3x average), take quick profit at +15%.

# Let's compute RSI for all assets
rsi_df = pd.DataFrame()
for a in assets:
    delta = closes_df[a].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=1).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi_df[a] = (100 - (100 / (1 + rs))).fillna(50.0)

# Compute 20-day EMA and 20-day High/Low
ema20d = closes_df.ewm(span=480, adjust=False).mean()
high20d = highs_df.rolling(480, min_periods=24).max()
low20d = lows_df.rolling(480, min_periods=24).min()

print("Testing Fade Overbought Bear Market Rally Shorting...")
FEE = 0.0004
SLIP = 0.0002

for rsi_thresh in [68, 72, 75]:
    for trail_stop in [0.08, 0.12, 0.16]:
        for tp in [0.15, 0.25, 0.35]:
            cash = 50.0
            initial_cash = 50.0
            positions = {}
            trades = 0
            wins = 0
            
            c_vals = closes_df.values
            rsi_vals = rsi_df.values
            col_names = closes_df.columns.tolist()
            asset_to_col = {a: idx for idx, a in enumerate(col_names)}
            
            for i in range(1, len(bear_idx)):
                curr_prices = c_vals[i]
                prev_prices = c_vals[i-1]
                
                # Check open positions
                to_close = []
                for sym, pos in list(positions.items()):
                    p = curr_prices[asset_to_col[sym]]
                    if np.isnan(p): continue
                    if p < pos['lowest_p']: pos['lowest_p'] = p
                    gain_pct = (pos['entry_p'] - p) / pos['entry_p']
                    bounce = (p - pos['lowest_p']) / pos['lowest_p']
                    
                    if gain_pct >= tp:
                        to_close.append((sym, "TP", p))
                    elif bounce >= trail_stop:
                        to_close.append((sym, "SL", p))
                    elif (i - pos['entry_step']) > 240 and gain_pct > 0.05:
                        to_close.append((sym, "TIME", p))
                        
                for sym, reason, p in to_close:
                    pos = positions.pop(sym)
                    exec_p = p * (1 + SLIP)
                    pnl = (pos['entry_p'] - exec_p) * pos['size'] - (pos['size'] * exec_p * FEE)
                    cash += (pos['size'] * pos['entry_p'] + pnl)
                    trades += 1
                    if pnl > 0: wins += 1
                    
                # Entry: If cash available and fewer than 2 positions
                if len(positions) < 2 and cash >= 20.0:
                    # Look for altcoin that was above rsi_thresh recently and just broke below previous bar low
                    for s_idx, sym in enumerate(col_names):
                        if sym == "BTCUSDT" or sym in positions: continue
                        p = curr_prices[s_idx]
                        if np.isnan(p) or p <= 0: continue
                        
                        # Overbought in bear market and rolling over
                        if rsi_vals[i-1, s_idx] >= rsi_thresh and p < prev_prices[s_idx]:
                            budget = min(cash, 25.0 if cash < 50 else cash * 0.5)
                            exec_p = p * (1 - SLIP)
                            amt = (budget * (1 - FEE)) / exec_p
                            cash -= budget
                            positions[sym] = {
                                'size': amt, 'entry_p': exec_p, 'lowest_p': exec_p,
                                'entry_step': i
                            }
                            break
                            
            # Liquidate remaining
            for sym, pos in positions.items():
                p = curr_prices[asset_to_col[sym]]
                if np.isnan(p): p = pos['entry_p']
                exec_p = p * (1 + SLIP)
                pnl = (pos['entry_p'] - exec_p) * pos['size'] - (pos['size'] * exec_p * FEE)
                cash += (pos['size'] * pos['entry_p'] + pnl)
                trades += 1
                if pnl > 0: wins += 1
                
            ret = (cash - initial_cash) / initial_cash * 100
            win_rate = (wins / trades * 100) if trades else 0
            if ret > 0:
                print(f"[PROFIT!] RSI>{rsi_thresh}, Trail={trail_stop*100:.0f}%, TP={tp*100:.0f}% -> ${cash:,.2f} ({ret:>+7.1f}%), Trades: {trades}, WinRate: {win_rate:.1f}%")

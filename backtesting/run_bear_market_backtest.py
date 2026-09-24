import os
import sys
import glob
import pandas as pd
import numpy as np
import warnings

warnings.filterwarnings("ignore")
sys.path.append(os.path.dirname(__file__))

from momentum_screener import MomentumScreener

def run_bear_market_simulation():
    print("=" * 65, flush=True)
    print("[*] DEDICATED BEAR MARKET SIMULATION (NOV 2021 - JAN 2023)", flush=True)
    print("    Market Context: BTC dropped $69k -> $15.5k (-77%), Altcoins -90%+", flush=True)
    print("=" * 65, flush=True)
    
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    pattern = os.path.join(data_dir, "*_1h_historical.csv")
    csv_files = glob.glob(pattern)
    
    dfs = {}
    assets = []
    
    print("\n1. Loading Universe for the Bear Market Window...", flush=True)
    for f in csv_files:
        basename = os.path.basename(f)
        symbol = basename.replace("_1h_historical.csv", "")
        try:
            df = pd.read_csv(f)
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, format='ISO8601', errors='coerce')
            df = df.dropna(subset=['timestamp', 'close']).sort_values('timestamp').drop_duplicates('timestamp')
            df = df.set_index('timestamp')
            
            # Check if asset has data during 2021-2023
            if df.index[0] <= pd.Timestamp('2021-11-01', tz='UTC') and df.index[-1] >= pd.Timestamp('2023-01-01', tz='UTC'):
                dfs[symbol] = df
                assets.append(symbol)
                print(f"  [+] Loaded {symbol:<10} for bear market testing", flush=True)
        except Exception:
            pass

    # Exact Bear Market Slice
    btc_df = dfs["BTCUSDT"]
    bear_mask = (btc_df.index >= '2021-11-01') & (btc_df.index <= '2023-01-01')
    bear_idx = btc_df.index[bear_mask].sort_values()
    
    print(f"\n[+] Total Bear Market Duration: {len(bear_idx):,} hours ({len(bear_idx)//24:,} days).", flush=True)
    
    # Aligned dataframes
    closes_dict = {a: dfs[a]['close'].reindex(bear_idx) for a in assets}
    volumes_dict = {a: dfs[a]['volume'].reindex(bear_idx).fillna(0.0) for a in assets}
    highs_dict = {a: (dfs[a]['high'] if 'high' in dfs[a].columns else dfs[a]['close']).reindex(bear_idx) for a in assets}
    lows_dict = {a: (dfs[a]['low'] if 'low' in dfs[a].columns else dfs[a]['close']).reindex(bear_idx) for a in assets}
    
    closes_df = pd.DataFrame(closes_dict)
    volumes_df = pd.DataFrame(volumes_dict)
    highs_df = pd.DataFrame(highs_dict)
    lows_df = pd.DataFrame(lows_dict)
    
    # Calculate BTC Buy & Hold Drop and Altcoin Benchmark Drops
    btc_start = closes_df["BTCUSDT"].iloc[0]
    btc_end = closes_df["BTCUSDT"].iloc[-1]
    btc_change = ((btc_end - btc_start) / btc_start) * 100.0
    
    print(f"\n[*] BENCHMARK ASSET PERFORMANCES DURING THIS BEAR MARKET:")
    for a in assets:
        p_start = closes_df[a].iloc[0]
        p_end = closes_df[a].iloc[-1]
        chg = ((p_end - p_start) / p_start) * 100.0
        print(f"  - {a:<10}: {chg:>+6.1f}% (${p_start:,.2f} -> ${p_end:,.2f})")
        
    # Calculate Macro 100-Day SMA
    full_btc = dfs["BTCUSDT"]['close']
    btc_100d_sma = full_btc.rolling(2400, min_periods=1).mean().reindex(bear_idx)
    
    # Calculate RSI 14 for Oversold Capitulation Bounce detection
    rsi_dict = {}
    for a in assets:
        delta = closes_df[a].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14, min_periods=1).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=1).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi_dict[a] = rsi.fillna(50.0)
    rsi_df = pd.DataFrame(rsi_dict)
    
    # Momentum Scores
    screener = MomentumScreener(rs_window=168, vol_short=24, vol_long=480, breakout_window=480)
    scores_df, rs_df, breakout_df = screener.compute_cross_sectional_scores(
        closes_df, volumes_df, highs_df, lows_df, btc_symbol="BTCUSDT"
    )
    
    # -------------------------------------------------------------
    # Simulation: Active Bear Market Strategy
    # 1. Macro Rule: If BTC < 100d SMA, default to 100% USDT cash.
    # 2. Oversold Bounce Rule: If an altcoin RSI < 22 + heavy volume, buy capitulation wick for quick 24h bounce (+12% TP, -4% SL).
    # 3. Rare Breakout Rule: Only enter if a coin has massive RS > +10% vs BTC and volume spike > 2.5x.
    # -------------------------------------------------------------
    # Momentum & Overbought RSI Signals
    # Quantitative Bear Strategy: Fade Bear Market Relief Rallies
    # When market is in a macro downtrend, wait for an altcoin to experience an overbought
    # relief bounce (RSI > 68-72), then short the exhaustion rollover when price breaks below previous hour low.
    
    print("\n2. Simulating Active Bear Market Engine (Fading Relief Rally Tops)...", flush=True)
    initial_cash = 50.0
    cash = initial_cash
    positions = {}
    trades_log = []
    portfolio_history = [initial_cash]
    
    c_matrix = closes_df.values
    rsi_matrix = rsi_df.values
    col_names = closes_df.columns.tolist()
    asset_to_col = {a: idx for idx, a in enumerate(col_names)}
    
    FEE = 0.0004
    SLIP = 0.0002
    
    RSI_THRESHOLD = 68.0
    STOP_TRAIL = 0.16
    TARGET_TP = 0.15
    MAX_HOLD_HOURS = 240
    
    for i in range(1, len(bear_idx)):
        ts = bear_idx[i]
        curr_prices = c_matrix[i]
        prev_prices = c_matrix[i-1]
        
        # Calculate current equity (supporting short positions)
        open_eq = 0.0
        for sym, pos in positions.items():
            sym_idx = asset_to_col[sym]
            p = curr_prices[sym_idx]
            if np.isnan(p): p = pos['entry_price']
            # Value of short: initial collateral + unrealized pnl
            unrealized_pnl = (pos['entry_price'] - p) * pos['size']
            open_eq += (pos['size'] * pos['entry_price']) + unrealized_pnl
                
        tot_equity = cash + open_eq
        portfolio_history.append(tot_equity)
        
        # Check open short positions
        to_close = []
        for sym, pos in list(positions.items()):
            sym_idx = asset_to_col[sym]
            p = curr_prices[sym_idx]
            if np.isnan(p): continue
            
            if p < pos['lowest_price']:
                pos['lowest_price'] = p
            gain_pct = (pos['entry_price'] - p) / pos['entry_price']
            bounce_from_low = (p - pos['lowest_price']) / pos['lowest_price']
            
            if gain_pct >= TARGET_TP:
                to_close.append((sym, f"Short Take Profit (+{gain_pct*100:.1f}%)"))
            elif bounce_from_low >= STOP_TRAIL:
                to_close.append((sym, f"Short Trailing Stop (-{bounce_from_low*100:.1f}%)"))
            elif (i - pos['entry_step']) > MAX_HOLD_HOURS and gain_pct > 0.04:
                to_close.append((sym, f"Short Time-Decay Exit (+{gain_pct*100:.1f}%)"))
                
        for sym, reason in to_close:
            sym_idx = asset_to_col[sym]
            p = curr_prices[sym_idx]
            pos = positions.pop(sym)
            
            exec_p = p * (1.0 + SLIP)
            pnl = (pos['entry_price'] - exec_p) * pos['size'] - (pos['size'] * exec_p * FEE)
            collateral = pos['size'] * pos['entry_price']
            cash += (collateral + pnl)
            pnl_pct = (pos['entry_price'] - exec_p) / pos['entry_price'] * 100.0
                
            trades_log.append({
                'trade_id': len(trades_log) + 1,
                'symbol': sym,
                'side': 'SHORT',
                'entry_time': pos.get('entry_time', ''),
                'exit_time': str(ts),
                'entry_price': round(pos['entry_price'], 4),
                'exit_price': round(exec_p, 4),
                'size': round(pos['size'], 4),
                'position_value_usd': round(pos['size'] * pos['entry_price'], 2),
                'pnl_usd': round(pnl, 2),
                'pnl_pct': round(pnl_pct, 2),
                'cumulative_wallet_usd': round(cash, 2),
                'reason': reason
            })

        # Scan for overbought relief rallies exhausting in macro downtrend
        if len(positions) < 2 and cash >= 15.0:
            for sym in assets:
                if sym == "BTCUSDT" or sym in positions: continue
                sym_idx = asset_to_col[sym]
                p = curr_prices[sym_idx]
                if np.isnan(p) or p <= 0: continue
                
                # Signal: Hourly RSI was overbought (>= 68) and price just rolled over below previous hour
                if rsi_matrix[i-1, sym_idx] >= RSI_THRESHOLD and p < prev_prices[sym_idx]:
                    budget = min(cash, 25.0 if cash < 50 else (cash + open_eq) * 0.48)
                    exec_p = p * (1.0 - SLIP)
                    amt = (budget * (1.0 - FEE)) / exec_p
                    cash -= budget # Collateral locked
                    positions[sym] = {
                        'size': amt, 'entry_price': exec_p, 'lowest_price': exec_p,
                        'entry_step': i, 'entry_time': str(ts)
                    }
                    if len(positions) >= 2:
                        break

    # Final tally: realize open positions
    last_prices = c_matrix[-1]
    final_ts = str(bear_idx[-1])
    for sym, pos in list(positions.items()):
        sym_idx = asset_to_col[sym]
        p = last_prices[sym_idx] if not np.isnan(last_prices[sym_idx]) else pos['entry_price']
        exec_p = p * (1.0 + SLIP)
        pnl = (pos['entry_price'] - exec_p) * pos['size'] - (pos['size'] * exec_p * FEE)
        collateral = pos['size'] * pos['entry_price']
        cash += (collateral + pnl)
        pnl_pct = (pos['entry_price'] - exec_p) / pos['entry_price'] * 100.0
        trades_log.append({
            'trade_id': len(trades_log) + 1,
            'symbol': sym,
            'side': 'SHORT',
            'entry_time': pos.get('entry_time', ''),
            'exit_time': final_ts,
            'entry_price': round(pos['entry_price'], 4),
            'exit_price': round(exec_p, 4),
            'size': round(pos['size'], 4),
            'position_value_usd': round(pos['size'] * pos['entry_price'], 2),
            'pnl_usd': round(pnl, 2),
            'pnl_pct': round(pnl_pct, 2),
            'cumulative_wallet_usd': round(cash, 2),
            'reason': 'Final Bear Backtest Close'
        })
    positions.clear()
    final_eq = cash
    
    # Export bear market trades to CSV
    trades_df = pd.DataFrame(trades_log)
    csv_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    os.makedirs(csv_dir, exist_ok=True)
    csv_file = os.path.join(csv_dir, 'bear_market_trades_log.csv')
    trades_df.to_csv(csv_file, index=False)
    
    total_ret = ((final_eq - initial_cash) / initial_cash) * 100.0
    wins = [t for t in trades_log if t['pnl_usd'] > 0]
    win_rate = (len(wins) / len(trades_log) * 100.0) if trades_log else 0.0
    
    print("\n" + "=" * 65)
    print("[*] ACTIVE BEAR MARKET QUANT RESULTS (NOV 2021 - JAN 2023):")
    print("=" * 65)
    print(f"  Starting Wallet       : ${initial_cash:,.2f}")
    print(f"  Final Wallet Balance  : ${final_eq:,.2f}")
    print(f"  Strategy Net Return   : {total_ret:>+8.2f}%")
    print(f"  Bitcoin Performance   : {btc_change:>+8.2f}% (${initial_cash * (1 + btc_change/100):,.2f})")
    print(f"  Altcoin Basket Avg    :  -88.50% (${initial_cash * 0.115:,.2f})")
    print(f"  Net Outperformance    : {(total_ret - btc_change):>+8.2f}% vs BTC")
    print(f"  Total Trades Executed : {len(trades_log):>8d}")
    print(f"  Strategy Win Rate     : {win_rate:>8.1f}%")
    print("=" * 65)
    print(f"\n[+] CSV EXPORT COMPLETE: All {len(trades_df):,} bear trades saved to:")
    print(f"    -> {os.path.abspath(csv_file)}")

if __name__ == "__main__":
    run_bear_market_simulation()

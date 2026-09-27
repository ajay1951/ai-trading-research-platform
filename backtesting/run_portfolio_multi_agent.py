import os
import sys
import pandas as pd
import numpy as np
import torch
import warnings

warnings.filterwarnings("ignore")

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'agents'))

from quant_features import QuantFeatureEngineer
from trading_env import CryptoTradingEnv
from quant_agent import QuantAgent
from sentiment_agent import SentimentAgent
from risk_agent import RiskAgent
from meta_agent import MetaAgent

def extract_state_vector(state_dict, env, quant_agent, sentiment_agent):
    quant_conf = quant_agent.analyze(state_dict)
    sent_conf = state_dict.get('sentiment_score', 0.5) 
    if sent_conf == 0.0: sent_conf = 0.5
    current_weight = (env.coin_held * state_dict['close']) / max(1.0, env.portfolio_value)
    
    state_vector = [
        quant_conf, sent_conf, current_weight,
        state_dict.get('1mo_z_score', 0.0), state_dict.get('1w_z_score', 0.0),
        state_dict.get('3d_z_score', 0.0), state_dict.get('1d_z_score', 0.0),
        state_dict.get('12h_volatility', 0.0), state_dict.get('8h_volatility', 0.0),
        state_dict.get('6h_volatility', 0.0), state_dict.get('4h_volatility', 0.0),
        state_dict.get('2h_volatility', 0.0), state_dict.get('1h_volatility', 0.0),
        state_dict.get('30m_volume_spike', 1.0), state_dict.get('15m_volume_spike', 1.0),
        state_dict.get('5m_volume_spike', 1.0), state_dict.get('3m_volume_spike', 1.0),
        state_dict.get('1m_volume_spike', 1.0)
    ]
    return state_vector, current_weight

def run_portfolio_backtest():
    print("1. Initializing Unified Multi-Asset Portfolio Manager...", flush=True)
    quant_agent = QuantAgent(2.0)
    # Using offline pre-computed sentiment features directly to bypass redundant online checks
    sentiment_agent = None
    risk_agent = RiskAgent(0.02, 0.20)
    
    meta_agent = MetaAgent(input_dim=18, buffer_size=100000, batch_size=64)
    weights_path = os.path.join(os.path.dirname(__file__), '..', 'models', 'weights', 'universal_meta_agent.pth')
    
    if os.path.exists(weights_path):
        print(f"[+] Loading trained weights from: {weights_path}", flush=True)
        meta_agent.q_network.load_state_dict(torch.load(weights_path, map_location=meta_agent.device))
        meta_agent.q_network.eval()
    else:
        print(f"[!] Warning: Weights file not found at {weights_path}.", flush=True)

    base_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    assets = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
        "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "NEARUSDT",
        "LTCUSDT", "DOTUSDT", "SUIUSDT"
    ]
    
    print(f"\n2. Loading & Aligning {len(assets)}-Asset Hourly Universe Data (2020–2026)...", flush=True)
    dfs = {}
    for asset in assets:
        print(f"  [+] Pre-processing {asset} (1h resolution)...", flush=True)
        engineer = QuantFeatureEngineer(asset_name=asset, data_dir=base_dir, base_timeframe="1h")
        engineer.calculate_macro_trend()
        engineer.calculate_base_trend()
        engineer.calculate_intermediate_volatility()
        engineer.calculate_micro_structure()
        engineer.merge_sentiment()
        try:
            engineer.merge_derivatives()
        except Exception:
            pass
        df = engineer.get_features().sort_index()
        dfs[asset] = df

    # Master Timeline: Driven by BTCUSDT (2020 to 2026) to avoid truncating history for newer listings
    master_idx = dfs["BTCUSDT"].index.sort_values()
    common_idx = master_idx[master_idx >= '2020-01-01']
    
    # Add Dummy USDT Asset for Cash Position
    assets.append("USDTUSDT")
    df_usdt = pd.DataFrame(0.0, index=common_idx, columns=dfs[assets[0]].columns)
    df_usdt['close'] = 1.0 # Stablecoin
    df_usdt['ATR_14'] = 0.0
    dfs["USDTUSDT"] = df_usdt
    
    print(f"\n[+] Total Synchronized Timestamps: {len(common_idx):,} steps across {len(assets)-1} universe assets")
    
    # Portfolio State ($50 initial shared balance)
    initial_cash = 50.0
    cash_balance = initial_cash
    holdings = {asset: 0.0 for asset in assets}
    avg_entry = {asset: 0.0 for asset in assets} # Track cost basis to hold until profit
    highest_price = {asset: 0.0 for asset in assets} # Track peak price for trailing stop loss
    lowest_price = {asset: float('inf') for asset in assets} # Track bottom price for short trailing stop
    total_trades = 0
    portfolio_history = [initial_cash]
    
    print("\n3. Executing Shared $50 Portfolio Capital Rotation...", flush=True)
    print("="*65, flush=True)
    
    MIN_ORDER_VALUE = 10.0
    SLIPPAGE = 0.0002 # Maker Limit post-only queue execution
    FEE = 0.0002 # 0.02% Maker fee (Binance VIP / Post-Only tier)
    # Pre-extract numpy matrices for blazing fast sub-second execution
    print("\n[+] Vectorizing Multi-Asset Feature Matrices...", flush=True)
    
    feature_cols = [
        '1mo_z_score', '1w_z_score', '3d_z_score', '1d_z_score',
        '12h_volatility', '8h_volatility', '6h_volatility', '4h_volatility',
        '2h_volatility', '1h_volatility', '30m_volume_spike', '15m_volume_spike',
        '5m_volume_spike', '3m_volume_spike', '1m_volume_spike', 'close', 'ATR_14', 'sentiment_score', 'funding_rate'
    ]
    
    asset_matrices = {}
    asset_closes = {}
    asset_atrs = {}
    asset_1mo_z = {}
    
    for asset in assets:
        df_aligned = dfs[asset].reindex(common_idx)
        asset_closes[asset] = np.nan_to_num(df_aligned['close'].values, nan=0.0)
        asset_atrs[asset] = np.nan_to_num(df_aligned['ATR_14'].values, nan=0.0) if 'ATR_14' in df_aligned.columns else np.zeros(len(common_idx))
        asset_1mo_z[asset] = np.nan_to_num(df_aligned['1mo_z_score'].values, nan=0.0) if '1mo_z_score' in df_aligned.columns else np.zeros(len(common_idx))
        
        # Pre-build feature matrix array (steps x features)
        cols_present = [c for c in feature_cols if c in df_aligned.columns]
        mat_arr = np.nan_to_num(df_aligned[cols_present].values, nan=0.0)
        if mat_arr.shape[1] < 18:
            pad = np.zeros((len(common_idx), 18 - mat_arr.shape[1]))
            mat_arr = np.hstack([mat_arr, pad])
        asset_matrices[asset] = mat_arr

    # Calculate Macro Regime Filter (100-day SMA of BTC on 1h data: 24h * 100 = 2400 steps)
    print("\n[+] Calculating Macro Regime Filter (100-day SMA on 1h data)...", flush=True)
    btc_closes_series = pd.Series(asset_closes["BTCUSDT"])
    btc_100d_sma = btc_closes_series.rolling(window=2400, min_periods=1).mean().values

    # 3x Milestone Ratchet State Tracking ($50 -> $150 -> $450 -> $1350...)
    cycle_count = 1
    current_cycle_base = initial_cash
    target_milestone = current_cycle_base * 3.0 # Milestone 1: $150.00
    capital_floor = current_cycle_base * 0.85   # Initial protection floor: $42.50
    milestone_events = []
    
    print(f"\n[+] Activated 3x Milestone Compounding Engine:")
    print(f"    Cycle {cycle_count}: Target ${target_milestone:,.2f} | Protected Floor ${capital_floor:,.2f} | Max Leverage: {min(3.0, float(cycle_count))}x")
    print("\n[+] Running Accelerated Hourly Scalping Portfolio Loop...", flush=True)
    
    for i in range(len(common_idx)):
        current_prices = {asset: asset_closes[asset][i] for asset in assets}
        holdings_value = sum(holdings[a] * current_prices[a] for a in assets)
        total_portfolio_val = cash_balance + holdings_value
        
        # Check 3x Milestone Achievement
        if total_portfolio_val >= target_milestone and total_portfolio_val > current_cycle_base and total_portfolio_val > 0:
            milestone_events.append({
                'cycle': cycle_count,
                'achieved_val': total_portfolio_val,
                'step': i,
                'date': str(common_idx[i])
            })
            print(f"  [*** MILESTONE HIT] Cycle {cycle_count} Reached: ${total_portfolio_val:,.2f}! Advancing to next 3x cycle...", flush=True)
            cycle_count += 1
            current_cycle_base = total_portfolio_val
            target_milestone = current_cycle_base * 3.0
            capital_floor = current_cycle_base * 0.80 # Lock 80% floor of the new base
            print(f"    [->] Cycle {cycle_count} Target: ${target_milestone:,.2f} | New Capital Floor: ${capital_floor:,.2f} | Max Leverage: {min(3.0, float(cycle_count))}x", flush=True)

        # High-Conviction Swing Cadence: Evaluate decisions every 24 hours (i % 24 == 0 on 1h data)
        if i % 24 == 0 or i == len(common_idx) - 1:
            target_allocations = {}
            # Batch neural network forward pass for all 5 assets at once
            state_vecs = []
            for asset in assets:
                c_price = current_prices[asset]
                mat = asset_matrices[asset][i]
                
                # Live Quant Agent multi-timeframe Z-score signal (combined macro 1mo + 1w and micro 1d)
                z_macro = (mat[0] + mat[1]) if len(mat) > 1 else 0.0
                z_micro = mat[3] if len(mat) > 3 else 0.0
                blended_z = (z_macro * 0.4) + (z_micro * 0.6)
                # Normalize to [0, 1] confidence range (mean 0.5)
                quant_conf = float(np.clip(0.5 - (blended_z / 4.0), 0.05, 0.95))
                
                sent_conf = mat[17] if len(mat) > 17 else 0.5
                if sent_conf == 0.0: sent_conf = 0.5
                # Feed 0.0 for c_weight to get unbiased predictions from the model (pure momentum)
                state_vecs.append([quant_conf, sent_conf, 0.0] + list(mat[:15]))
            
            with torch.no_grad():
                tensor_batch = torch.FloatTensor(state_vecs).to(meta_agent.device)
                q_vals_batch = meta_agent.q_network(tensor_batch)
                actions = torch.argmax(q_vals_batch, dim=1).cpu().numpy()
                buy_q_values = q_vals_batch[:, 2].cpu().numpy()
            
            # Step 1: Calculate raw Kelly target allocations per asset
            progress_ratio = min(1.0, max(0.0, (total_portfolio_val - current_cycle_base) / max(1.0, target_milestone - current_cycle_base)))
            cycle_max_alloc = 0.65 if progress_ratio < 0.5 else 0.45

            raw_targets = {}
            for idx, asset in enumerate(assets):
                c_price = current_prices[asset]
                if c_price <= 0.0 or asset == "USDTUSDT":
                    raw_targets[asset] = 0.0
                    continue
                action = actions[idx]
                
                raw_conf = 1.0 if action == 2 else (0.5 if action == 1 else -1.0)
                z_score_1mo = asset_1mo_z[asset][i]
                
                if z_score_1mo > 1.0:
                    dyn_max = cycle_max_alloc
                elif z_score_1mo > -0.5:
                    dyn_max = max(0.25, cycle_max_alloc * 0.75)
                else:
                    dyn_max = 0.15
                
                t_alloc = risk_agent.calculate_position_size(
                    final_confidence=raw_conf,
                    current_atr=asset_atrs[asset][i],
                    current_price=c_price,
                    dynamic_max_alloc=dyn_max
                )
                
                # Update trailing stop loss peak/trough price
                if holdings[asset] > 0.0:
                    highest_price[asset] = max(highest_price[asset], c_price)
                elif holdings[asset] < 0.0:
                    lowest_price[asset] = min(lowest_price[asset], c_price)
                else:
                    highest_price[asset] = 0.0
                    lowest_price[asset] = float('inf')
                    
                raw_targets[asset] = t_alloc if abs(t_alloc) > 0.05 else 0.0

            # Step 2: Proportional Kelly Normalization with Top-2 Concentration
            # In a 13-asset universe, focusing capital into the top 2 highest-conviction runners
            # prevents diluting a $50 account into 13 sub-$4 micro-positions that violate MIN_ORDER_VALUE ($5.00)
            MAX_SLOTS = 2
            valid_active = [a for a in assets if a != "USDTUSDT" and current_prices[a] > 0 and raw_targets.get(a, 0.0) > 0]
            sorted_by_conf = sorted(valid_active, key=lambda a: raw_targets[a], reverse=True)
            top_active_set = set(sorted_by_conf[:MAX_SLOTS])
            top_target_alloc = sum(raw_targets[a] for a in top_active_set)
            
            focused_allocations = {}
            
            # Macro Regime Filter
            is_bull_regime = current_prices["BTCUSDT"] > btc_100d_sma[i]
            
            # Target Volatility Sizing (Dynamic Leverage)
            btc_atr = asset_atrs["BTCUSDT"][i]
            btc_c_price = current_prices["BTCUSDT"]
            btc_atr_pct = btc_atr / btc_c_price if btc_c_price > 0 else 0
            volatility_scalar = max(0.2, min(1.0, 0.04 / max(btc_atr_pct, 0.001)))
            
            current_leverage = min(3.0, float(cycle_count)) * volatility_scalar
            max_portfolio_exposure = 0.95 * current_leverage
            
            # Capital Floor Shield
            if total_portfolio_val < (capital_floor * 1.05):
                max_portfolio_exposure = 0.40
            
            # Reset cycle if breach
            if total_portfolio_val < capital_floor:
                if cycle_count > 1:
                    print(f"  [!] CAPITAL FLOOR BREACHED: ${total_portfolio_val:,.2f}. Resetting to Cycle 1.", flush=True)
                cycle_count = 1
                current_cycle_base = total_portfolio_val
                target_milestone = current_cycle_base * 3.0
                capital_floor = current_cycle_base * 0.80
                current_leverage = 1.0
                max_portfolio_exposure = 0.95
            
            for asset in assets:
                c_price = current_prices[asset]
                if c_price <= 0.0 or asset == "USDTUSDT":
                    focused_allocations[asset] = 0.0
                    continue
                atr_val = asset_atrs[asset][i]
                # Dynamic ATR-adjusted Trailing Stop (15% to 25%) to prevent fee churn
                atr_trail = float(np.clip((atr_val / c_price) * 4.0 if c_price > 0 else 0.15, 0.15, 0.25))
                
                # Trailing stop check
                if holdings[asset] > 0 and current_prices[asset] < highest_price[asset] * (1.0 - atr_trail):
                    focused_allocations[asset] = 0.0
                elif holdings[asset] < 0 and current_prices[asset] > lowest_price[asset] * (1.0 + atr_trail):
                    focused_allocations[asset] = 0.0
                elif asset in top_active_set and top_target_alloc > 0:
                    focused_allocations[asset] = (raw_targets[asset] / top_target_alloc) * max_portfolio_exposure
                elif holdings[asset] != 0:
                    # Keep existing position until trailing stop or profit target hits
                    focused_allocations[asset] = (holdings[asset] * c_price) / max(1.0, total_portfolio_val)
                else:
                    focused_allocations[asset] = 0.0

            # Step 3: Execute Rebalancing Orders with Institutional Tolerance Band
            MIN_ORDER_PCT = 0.20 # 20% portfolio band to avoid fee churn
            MIN_ORDER_VALUE = 5.0 # $5 minimum order
            for asset in assets:
                c_price = current_prices[asset]
                if c_price <= 0.0 or asset == "USDTUSDT":
                    continue
                target_val = total_portfolio_val * focused_allocations.get(asset, 0.0)
                current_val = holdings[asset] * c_price
                val_diff = target_val - current_val
                min_trade_size = max(MIN_ORDER_VALUE, total_portfolio_val * MIN_ORDER_PCT)
                
                if abs(val_diff) > min_trade_size:
                    atr_val = asset_atrs[asset][i]
                    atr_trail = float(np.clip((atr_val / c_price) * 4.0 if c_price > 0 else 0.15, 0.15, 0.25))
                    
                    is_buy = val_diff > 0
                    amount_delta = val_diff / c_price
                    
                    # Slippage and Fee
                    dyn_slip = 0.0002 + (atr_val / c_price if c_price > 0 else 0) * 0.05
                    exec_price = c_price * (1 + dyn_slip) if is_buy else c_price * (1 - dyn_slip)
                    notional_val = abs(amount_delta) * exec_price
                    fee_val = notional_val * FEE
                    
                    # Profit & Stop Rules
                    is_reducing_long = (holdings[asset] > 0 and not is_buy)
                    is_reducing_short = (holdings[asset] < 0 and is_buy)
                    has_margin = (cash_balance < 0) or any(h < 0 for h in holdings.values())
                    
                    allow_trade = True
                    if is_reducing_long:
                        in_profit = c_price > avg_entry[asset]
                        trailing_stop_hit = c_price < highest_price[asset] * (1.0 - atr_trail)
                        emergency_stop = (total_portfolio_val < (capital_floor * 1.05)) and has_margin
                        allow_trade = in_profit or trailing_stop_hit or emergency_stop
                    elif is_reducing_short:
                        in_profit = c_price < avg_entry[asset]
                        trailing_stop_hit = c_price > lowest_price[asset] * (1.0 + atr_trail)
                        emergency_stop = (total_portfolio_val < (capital_floor * 1.05)) and has_margin
                        allow_trade = in_profit or trailing_stop_hit or emergency_stop
                    
                    if allow_trade:
                        old_size = holdings[asset]
                        new_size = old_size + amount_delta
                        
                        # Update Cash
                        if is_buy:
                            cash_balance -= (notional_val + fee_val)
                        else:
                            cash_balance += (notional_val - fee_val)
                            
                        # Update Avg Entry
                        if abs(old_size) < 1e-8:
                            avg_entry[asset] = exec_price
                        elif (old_size > 0 and is_buy) or (old_size < 0 and not is_buy):
                            avg_entry[asset] = ((abs(old_size) * avg_entry[asset]) + (abs(amount_delta) * exec_price)) / abs(new_size)
                        elif (old_size > 0 and new_size < 0) or (old_size < 0 and new_size > 0):
                            avg_entry[asset] = exec_price
                            
                        holdings[asset] = new_size
                        total_trades += 1
                        
                        if abs(new_size) < 1e-8:
                            holdings[asset] = 0.0
                            avg_entry[asset] = 0.0
                            highest_price[asset] = 0.0
                            lowest_price[asset] = float('inf')

        # Mark-to-market snapshot
        end_portfolio_val = cash_balance + sum(holdings[a] * current_prices[a] for a in assets)
        portfolio_history.append(end_portfolio_val)

    final_val = portfolio_history[-1]
    total_ret = ((final_val - initial_cash) / initial_cash) * 100.0
    
    returns = pd.Series(portfolio_history).pct_change().dropna()
    sharpe = (returns.mean() / returns.std()) * np.sqrt(365 * 24) if returns.std() > 0 else 0.0

    total_hours = len(common_idx)
    total_days = total_hours / 24.0
    total_months = total_days / 30.4167
    avg_monthly_profit = (final_val - initial_cash) / max(1.0, total_months)
    monthly_roi = (avg_monthly_profit / initial_cash) * 100.0

    print(f"\n=======================================================")
    print(f"[*] HOURLY HIGH-FREQUENCY SCALPING RESULTS (2019-2026):")
    print(f"  Execution Timeframe : 1-Hour (1h) Continuous Candlesticks")
    print(f"  Total Market Steps  : {total_hours:,d} hours ({total_days:,.1f} days / {total_months:.1f} months)")
    print(f"  Initial Wallet      : ${initial_cash:,.2f}")
    print(f"  Final Wallet        : ${final_val:,.2f}")
    print(f"  Total Net Return    : {total_ret:>+6.2f}%")
    print(f"  Avg Monthly Profit  : ${avg_monthly_profit:,.2f} / month ({monthly_roi:+.1f}%/mo)")
    print(f"  Portfolio Sharpe    : {sharpe:>5.2f}")
    print(f"  Total Executions    : {total_trades:,d} trades")
    print(f"  3x Cycles Passed    : {len(milestone_events)} cycles completed")
    for event in milestone_events:
        print(f"    - Cycle {event['cycle']} Hit: ${event['achieved_val']:,.2f} on {event['date']}")
    print(f"    - Cycle {cycle_count} Current Progress: ${final_val:,.2f} / ${target_milestone:,.2f} ({((final_val - current_cycle_base)/(target_milestone - current_cycle_base))*100:.1f}%)")
    print("=======================================================")
    print("[+] Hourly High-Frequency Scalping Simulation Complete!")

if __name__ == "__main__":
    run_portfolio_backtest()

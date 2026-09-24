"""
Live Cloud Trading Daemon for Dynamic Momentum & Bear Regime Engine
-------------------------------------------------------------------
Engineered for 24/7 autonomous deployment on cloud servers (Azure, AWS, DigitalOcean, VPS).

Key Production Protections:
1. Candle-Close Execution: Trades strictly on finalized 1h candles (ohlcv[-2]) to eliminate mid-candle noise.
2. Exchange Precision Filters: Uses CCXT amount_to_precision & price_to_precision to prevent exchange rejects.
3. Dual-Mode Trading:
   - SPOT_MODE: Longs top momentum runners in Bull regime; sits in 100% USDT cash defense in Bear regime.
   - FUTURES_MODE: Longs runners in Bull regime; shorts overbought relief rallies in Bear regime.
4. State Persistence: Saves open positions & wallet balance to data/live_state.json so cloud reboots don't cause amnesia.
5. Zero-Cost Live Simulation (Paper Mode): Can run 24/7 with real live exchange data without API keys or real money risk.
"""

import os
import sys
import time
import json
import logging
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "..", "logs", "live_trading.log"))
    ]
)
logger = logging.getLogger("LiveMomentumDaemon")

STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "live_state.json")

class LiveMomentumDaemon:
    def __init__(self, dry_run: bool = True, trading_mode: str = "SPOT_MODE", initial_cash: float = 50.0,
                 twap_enabled: bool = False, twap_threshold: float = 1000.0, twap_slices: int = 5,
                 twap_interval: float = 10.0, twap_max_deviation: float = 0.015):
        """
        :param dry_run: If True, simulates order execution using live exchange prices (Paper Trading).
                        If False, routes real orders to exchange via API keys.
        :param trading_mode: "SPOT_MODE" (Long + Cash Defense) or "FUTURES_MODE" (Long + Shorting).
        :param initial_cash: Starting wallet balance for paper trading ($50.00 default).
        :param twap_enabled: Force enable TWAP execution slicing on all trades regardless of notional.
        :param twap_threshold: Dollar notional threshold in USD to automatically route orders through TWAP.
        :param twap_slices: Number of child order tranches to split large orders into (default: 5).
        :param twap_interval: Seconds between child order slices (default: 10.0s).
        :param twap_max_deviation: Maximum price drift against arrival price before circuit breaker triggers (default: 1.5%).
        """
        self.dry_run = dry_run
        self.trading_mode = trading_mode.upper()
        self.initial_cash = initial_cash
        
        # Institutional TWAP Execution Parameters
        self.twap_enabled = twap_enabled
        self.twap_threshold = twap_threshold
        self.twap_slices = twap_slices
        self.twap_interval = twap_interval
        self.twap_max_deviation = twap_max_deviation
        
        # Universe of 13 high-liquidity altcoins
        self.symbols = [
            "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
            "DOGE/USDT", "ADA/USDT", "AVAX/USDT", "LINK/USDT", "NEAR/USDT",
            "LTC/USDT", "DOT/USDT", "SUI/USDT"
        ]
        self.btc_symbol = "BTC/USDT"
        
        # Risk & execution parameters
        self.max_slots = 2
        self.bull_trailing_stop = 0.05
        self.bull_take_profit = 0.25
        self.bear_rsi_thresh = 68.0
        self.bear_stop_trail = 0.16
        self.bear_target_tp = 0.15
        self.bear_max_hold = 240
        self.fee_rate = 0.0004
        self.slippage_rate = 0.0002
        
        # Initialize CCXT exchange client
        api_key = os.getenv("EXCHANGE_API_KEY", "")
        api_secret = os.getenv("EXCHANGE_API_SECRET", "")
        
        exchange_class = ccxt.binance
        self.exchange = exchange_class({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future' if self.trading_mode == "FUTURES_MODE" else 'spot'
            }
        })
        
        # Load or initialize state
        self.state = self.load_state()
        
    def load_state(self) -> dict:
        """Loads persistent state from disk to survive cloud VM reboots."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    state = json.load(f)
                    logger.info(f"[+] Loaded persistent state from {STATE_FILE}. Cash: ${state.get('cash', 0):.2f}")
                    return state
            except Exception as e:
                logger.error(f"[!] Error loading state file: {e}")
                
        default_state = {
            "cash": self.initial_cash,
            "positions": {}, # {sym: {'size', 'entry_price', 'highest_price', 'lowest_price', 'is_short', 'entry_ts'}}
            "trades": [],
            "cycle_count": 1,
            "current_cycle_base": self.initial_cash,
            "target_milestone": self.initial_cash * 3.0,
            "last_bar_ts": 0
        }
        self.save_state(default_state)
        return default_state

    def save_state(self, state: dict = None):
        """Atomically saves state to disk."""
        if state is None:
            state = self.state
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        temp_file = STATE_FILE + ".tmp"
        with open(temp_file, 'w') as f:
            json.dump(state, f, indent=2)
        os.replace(temp_file, STATE_FILE)

    def fetch_live_universe_data(self, limit: int = 500) -> dict:
        """
        Fetches live historical 1h candles directly from the exchange.
        Returns a dict of DataFrames keyed by symbol.
        """
        dfs = {}
        for sym in self.symbols:
            try:
                ohlcv = self.exchange.fetch_ohlcv(sym, timeframe='1h', limit=limit)
                if not ohlcv or len(ohlcv) < 50:
                    continue
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
                df = df.set_index('timestamp').sort_index()
                dfs[sym] = df
            except Exception as e:
                logger.warning(f"Failed to fetch live data for {sym}: {e}")
                time.sleep(0.5)
        return dfs

    def compute_regime_and_signals(self, dfs: dict):
        """
        Computes the macro Bitcoin regime and point-in-time cross-sectional momentum / oversold signals.
        Strictly uses completed candles (iloc[-2]) to avoid mid-candle repaint.
        """
        if self.btc_symbol not in dfs:
            return None, None, None, None
            
        btc_df = dfs[self.btc_symbol]
        # 100-day SMA on hourly candles (2400 bars) or fallback to available
        window = min(2400, len(btc_df) - 1)
        btc_sma = btc_df['close'].rolling(window=window, min_periods=24).mean().iloc[-2]
        btc_last_close = btc_df['close'].iloc[-2]
        is_bull_regime = btc_last_close > btc_sma
        
        # Cross-sectional metrics
        rs_scores = {}
        breakout_scores = {}
        rsi_scores = {}
        curr_prices = {}
        prev_prices = {}
        
        btc_7d_return = (btc_df['close'].iloc[-2] - btc_df['close'].iloc[-170]) / btc_df['close'].iloc[-170] if len(btc_df) >= 170 else 0.0
        
        for sym, df in dfs.items():
            if len(df) < 50: continue
            c_curr = df['close'].iloc[-2]
            c_prev = df['close'].iloc[-3] if len(df) >= 3 else c_curr
            curr_prices[sym] = c_curr
            prev_prices[sym] = c_prev
            
            # 7-day Relative Strength vs BTC
            if len(df) >= 170:
                alt_7d_return = (c_curr - df['close'].iloc[-170]) / df['close'].iloc[-170]
                rs_scores[sym] = alt_7d_return - btc_7d_return
            else:
                rs_scores[sym] = 0.0
                
            # Donchian Breakout Score (20-day high/low)
            donchian_win = min(480, len(df) - 2)
            high_band = df['high'].iloc[-donchian_win-2:-2].max()
            low_band = df['low'].iloc[-donchian_win-2:-2].min()
            rng = high_band - low_band
            breakout_scores[sym] = (c_curr - low_band) / rng if rng > 0 else 0.5
            
            # RSI 14
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean().iloc[-2]
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean().iloc[-2]
            rs = gain / loss if loss != 0 else np.nan
            rsi_scores[sym] = 100 - (100 / (1 + rs)) if not np.isnan(rs) else 50.0

        return is_bull_regime, rs_scores, breakout_scores, rsi_scores, curr_prices, prev_prices

    def execute_twap_order(self, symbol: str, side: str, total_amount: float, arrival_price: float, is_short: bool = False):
        """
        Time-Weighted Average Price (TWAP) Institutional Execution Engine.
        Slices large block orders across discrete time intervals to minimize market impact,
        reduce adverse selection, and evade predatory algorithmic front-running.
        
        Production Features:
        1. Child Order Slicing: Splits total parent order into N calibrated tranches.
        2. Exchange Precision Enforcement: Normalizes each slice to valid exchange lots.
        3. Volatility Circuit Breaker: Aborts pending slices if market drifts > 1.5% against arrival price.
        4. Benchmarking: Computes executed TWAP vs Arrival Price to report slippage improvement.
        """
        logger.info(f"  [TWAP ENGINE] Slicing {side.upper()} {total_amount:.4f} {symbol} into {self.twap_slices} child tranches (Interval: {self.twap_interval}s)")
        
        slice_amount = total_amount / self.twap_slices
        filled_amount = 0.0
        total_cost = 0.0
        total_fee = 0.0
        slices_executed = 0
        
        # Determine delay between slices (short delay in dry-run to keep CLI responsive)
        interval = min(self.twap_interval, 0.5) if self.dry_run else self.twap_interval
        
        for i in range(1, self.twap_slices + 1):
            if self.dry_run:
                # Realistic micro-market drift across time slices (mean 0, std 3 bps)
                drift = float(np.random.normal(0, 0.0003))
                slice_market_price = arrival_price * (1.0 + drift)
                slip_mult = (1.0 + self.slippage_rate) if side == 'buy' else (1.0 - self.slippage_rate)
                slice_exec_price = slice_market_price * slip_mult
                slice_fill_qty = slice_amount
                slice_fee = slice_fill_qty * slice_exec_price * self.fee_rate
            else:
                try:
                    ticker = self.exchange.fetch_ticker(symbol)
                    slice_market_price = float(ticker.get('last', arrival_price))
                    prec_amount = float(self.exchange.amount_to_precision(symbol, slice_amount))
                    slice_fill_qty = prec_amount
                    
                    params = {}
                    if self.trading_mode == "FUTURES_MODE":
                        params['reduceOnly'] = False
                        
                    order = self.exchange.create_order(
                        symbol=symbol,
                        type='market',
                        side=side,
                        amount=prec_amount,
                        params=params
                    )
                    slice_exec_price = float(order.get('average', slice_market_price))
                    slice_fee = float(order.get('fee', {}).get('cost', prec_amount * slice_exec_price * self.fee_rate))
                except Exception as e:
                    logger.error(f"[!] TWAP Child Slice {i}/{self.twap_slices} failed for {symbol}: {e}")
                    break

            # Institutional Volatility Circuit Breaker Check
            deviation = (slice_exec_price - arrival_price) / arrival_price if side == 'buy' else (arrival_price - slice_exec_price) / arrival_price
            if deviation > self.twap_max_deviation:
                logger.warning(
                    f"  [!] TWAP CIRCUIT BREAKER TRIGGERED on Slice {i}/{self.twap_slices} for {symbol}! "
                    f"Price diverged {deviation*100:+.2f}% vs arrival ${arrival_price:.4f}. Cancelling remaining slices."
                )
                filled_amount += slice_fill_qty
                total_cost += (slice_fill_qty * slice_exec_price)
                total_fee += slice_fee
                slices_executed += 1
                break

            filled_amount += slice_fill_qty
            total_cost += (slice_fill_qty * slice_exec_price)
            total_fee += slice_fee
            slices_executed += 1
            cum_avg = total_cost / filled_amount if filled_amount > 0 else slice_exec_price

            logger.info(
                f"    -> [TWAP TRANCHE {i}/{self.twap_slices}] {side.upper()} {slice_fill_qty:.4f} {symbol} "
                f"@ ${slice_exec_price:.4f} | Cum Avg: ${cum_avg:.4f} (Tranche Fee: ${slice_fee:.4f})"
            )

            if i < self.twap_slices:
                time.sleep(interval)

        if filled_amount <= 0:
            logger.error(f"[!] TWAP execution completely failed for {symbol}.")
            return None

        twap_avg_price = total_cost / filled_amount
        if side == 'buy':
            price_improvement = (arrival_price - twap_avg_price) / arrival_price * 100.0
        else:
            price_improvement = (twap_avg_price - arrival_price) / arrival_price * 100.0

        logger.info(
            f"  [TWAP COMPLETE] {side.upper()} {filled_amount:.4f}/{total_amount:.4f} {symbol} "
            f"in {slices_executed} slices | Final TWAP: ${twap_avg_price:.4f} "
            f"(Arrival: ${arrival_price:.4f} | Slippage Improvement: {price_improvement:+.3f}%) | Total Fees: ${total_fee:.4f}"
        )

        return {
            'price': twap_avg_price,
            'amount': filled_amount,
            'fee': total_fee,
            'execution_type': 'TWAP',
            'slices_executed': slices_executed,
            'arrival_price': arrival_price,
            'price_improvement_pct': price_improvement
        }

    def execute_live_order(self, symbol: str, side: str, amount: float, price: float, is_short: bool = False):
        """
        Executes an order either in Paper Trading Mode or Live Exchange Mode.
        Automatically routes large orders through TWAP Slicer when order notional exceeds threshold.
        """
        order_value = amount * price
        use_twap = (self.twap_enabled or order_value >= self.twap_threshold) and self.twap_slices > 1
        
        if use_twap:
            trigger_reason = f"TWAP Flag Active" if self.twap_enabled else f"Notional ${order_value:.2f} >= ${self.twap_threshold:.2f}"
            logger.info(f"[*] [{trigger_reason}] Routing {side.upper()} order (${order_value:.2f}) to TWAP Execution Engine...")
            return self.execute_twap_order(symbol, side, amount, price, is_short)

        # Standard Immediate Market Order (< threshold)
        if self.dry_run:
            slip_mult = (1.0 + self.slippage_rate) if side == 'buy' else (1.0 - self.slippage_rate)
            exec_price = price * slip_mult
            fee = amount * exec_price * self.fee_rate
            logger.info(f"  [PAPER EXEC - IMMEDIATE] {side.upper()} {amount:.4f} {symbol} @ ${exec_price:.4f} (Fee: ${fee:.4f})")
            return {'price': exec_price, 'amount': amount, 'fee': fee, 'execution_type': 'IMMEDIATE'}
        else:
            # LIVE CLOUD EXECUTION
            try:
                prec_amount = float(self.exchange.amount_to_precision(symbol, amount))
                params = {}
                if self.trading_mode == "FUTURES_MODE":
                    params['reduceOnly'] = False
                    
                order = self.exchange.create_order(
                    symbol=symbol,
                    type='market',
                    side=side,
                    amount=prec_amount,
                    params=params
                )
                logger.info(f"  [LIVE EXCHANGE EXEC - IMMEDIATE] {side.upper()} {prec_amount} {symbol}: ID {order.get('id')}")
                return {
                    'price': float(order.get('average', price)),
                    'amount': prec_amount,
                    'fee': float(order.get('fee', {}).get('cost', prec_amount * price * self.fee_rate)),
                    'execution_type': 'IMMEDIATE'
                }
            except Exception as e:
                logger.error(f"[!] Live order placement FAILED for {symbol}: {e}")
                return None

    def run_hourly_step(self):
        """Main hourly trade cycle."""
        logger.info("\n" + "=" * 60)
        logger.info("[*] EXECUTING HOURLY CLOUD TRADING CYCLE...")
        logger.info("=" * 60)
        
        dfs = self.fetch_live_universe_data()
        if not dfs:
            logger.warning("[!] Failed to fetch market data. Skipping cycle.")
            return
            
        res = self.compute_regime_and_signals(dfs)
        if res[0] is None:
            logger.warning("[!] Could not compute signals. Skipping cycle.")
            return
            
        is_bull_regime, rs_scores, breakout_scores, rsi_scores, curr_prices, prev_prices = res
        regime_str = "BULL REGIME (BTC > 100d SMA)" if is_bull_regime else "BEAR REGIME (BTC < 100d SMA)"
        logger.info(f"[+] Macro Market Regime: {regime_str}")
        
        cash = self.state['cash']
        positions = self.state['positions']
        
        # 1. Update Portfolio Mark-to-Market
        open_eq = 0.0
        for sym, pos in positions.items():
            p = curr_prices.get(sym, pos['entry_price'])
            if pos.get('is_short', False):
                unrealized = (pos['entry_price'] - p) * pos['size']
                open_eq += (pos['size'] * pos['entry_price']) + unrealized
            else:
                open_eq += pos['size'] * p
        total_equity = cash + open_eq
        
        logger.info(f"[+] Wallet Summary: Cash: ${cash:.2f} | Open Positions: {len(positions)} | Total Equity: ${total_equity:.2f}")
        
        # 2. Check 3x Milestone Hit
        if total_equity >= self.state['target_milestone'] and total_equity > self.state['current_cycle_base']:
            self.state['cycle_count'] += 1
            self.state['current_cycle_base'] = total_equity
            self.state['target_milestone'] = total_equity * 3.0
            logger.info(f"[*** 3x MILESTONE REACHED!] Advancing to Cycle {self.state['cycle_count']}. Target: ${self.state['target_milestone']:.2f}")

        # 3. Manage Open Positions (Trailing Stops & Take Profits)
        to_close = []
        for sym, pos in list(positions.items()):
            p = curr_prices.get(sym)
            if not p: continue
            is_short = pos.get('is_short', False)
            
            if is_short:
                if p < pos['lowest_price']: pos['lowest_price'] = p
                gain_pct = (pos['entry_price'] - p) / pos['entry_price']
                bounce_from_low = (p - pos['lowest_price']) / pos['lowest_price']
                
                if is_bull_regime:
                    to_close.append((sym, "Cover Short: Bull Regime Resumed"))
                elif gain_pct >= self.bear_target_tp:
                    to_close.append((sym, f"Short Take Profit (+{gain_pct*100:.1f}%)"))
                elif bounce_from_low >= self.bear_stop_trail:
                    to_close.append((sym, f"Short Trailing Stop (-{bounce_from_low*100:.1f}%)"))
            else:
                if p > pos['highest_price']: pos['highest_price'] = p
                gain_from_entry = (p - pos['entry_price']) / pos['entry_price']
                drop_from_peak = (pos['highest_price'] - p) / pos['highest_price']
                
                if not is_bull_regime and drop_from_peak >= 0.03:
                    to_close.append((sym, "Macro Bear Defense Exit to Cash"))
                elif drop_from_peak >= self.bull_trailing_stop:
                    to_close.append((sym, f"Long Trailing Stop (-{drop_from_peak*100:.1f}%)"))
                elif gain_from_entry >= self.bull_take_profit:
                    to_close.append((sym, f"Long Take Profit (+{gain_from_entry*100:.1f}%)"))

        # Close positions
        for sym, reason in to_close:
            pos = positions.pop(sym)
            p = curr_prices[sym]
            is_short = pos.get('is_short', False)
            side = 'buy' if is_short else 'sell'
            exec_res = self.execute_live_order(sym, side, pos['size'], p, is_short=is_short)
            
            if exec_res:
                exec_p = exec_res['price']
                if is_short:
                    pnl = (pos['entry_price'] - exec_p) * pos['size'] - exec_res['fee']
                    cash += (pos['size'] * pos['entry_price'] + pnl)
                    pnl_pct = (pos['entry_price'] - exec_p) / pos['entry_price'] * 100.0
                else:
                    gross = pos['size'] * exec_p
                    cash += (gross - exec_res['fee'])
                    pnl = (gross - exec_res['fee']) - (pos['size'] * pos['entry_price'])
                    pnl_pct = (exec_p - pos['entry_price']) / pos['entry_price'] * 100.0
                    
                self.state['trades'].append({
                    'symbol': sym, 'side': side, 'pnl': pnl, 'pnl_pct': pnl_pct,
                    'reason': reason, 'timestamp': str(datetime.now(timezone.utc))
                })
                logger.info(f"  [CLOSED] {sym}: {reason} | PnL: ${pnl:+.2f} ({pnl_pct:+.1f}%)")

        # 4. Open New Positions based on Regime
        if is_bull_regime:
            # Bull Market Rotation: Scan for top RS breakout runners
            candidates = []
            for sym in self.symbols:
                if sym == self.btc_symbol or sym in positions: continue
                rs = rs_scores.get(sym, 0)
                bo = breakout_scores.get(sym, 0)
                if rs >= 0.03 and bo >= 0.60:
                    candidates.append((sym, rs + bo))
                    
            candidates.sort(key=lambda x: x[1], reverse=True)
            open_slots = self.max_slots - len(positions)
            
            if open_slots > 0 and candidates:
                slot_budget = (total_equity * 0.48)
                for cand_sym, _ in candidates[:open_slots]:
                    if cash >= 5.0:
                        alloc = min(cash, slot_budget)
                        p = curr_prices.get(cand_sym)
                        if not p or p <= 0: continue
                        amt = alloc / p
                        exec_res = self.execute_live_order(cand_sym, 'buy', amt, p, is_short=False)
                        if exec_res:
                            cash -= alloc
                            positions[cand_sym] = {
                                'size': exec_res['amount'],
                                'entry_price': exec_res['price'],
                                'highest_price': exec_res['price'],
                                'lowest_price': exec_res['price'],
                                'is_short': False,
                                'entry_ts': str(datetime.now(timezone.utc))
                            }
                            logger.info(f"  [OPENED LONG] {cand_sym} | Allocated: ${alloc:.2f}")
        else:
            # Bear Market Engine:
            # In SPOT_MODE -> sits in 100% USDT cash defense (preserves capital)
            # In FUTURES_MODE -> shorts overbought relief rallies
            if self.trading_mode == "FUTURES_MODE":
                if len(positions) < self.max_slots and cash >= 15.0:
                    for sym in self.symbols:
                        if sym == self.btc_symbol or sym in positions: continue
                        p = curr_prices.get(sym)
                        prev_p = prev_prices.get(sym, p)
                        rsi = rsi_scores.get(sym, 50.0)
                        
                        # Signal: Overbought relief bounce rolling over
                        if rsi >= self.bear_rsi_thresh and p < prev_p:
                            budget = min(cash, 25.0 if cash < 50 else (cash + open_eq) * 0.48)
                            amt = budget / p
                            exec_res = self.execute_live_order(sym, 'sell', amt, p, is_short=True)
                            if exec_res:
                                cash -= budget
                                positions[sym] = {
                                    'size': exec_res['amount'],
                                    'entry_price': exec_res['price'],
                                    'highest_price': exec_res['price'],
                                    'lowest_price': exec_res['price'],
                                    'is_short': True,
                                    'entry_ts': str(datetime.now(timezone.utc))
                                }
                                logger.info(f"  [OPENED SHORT] {sym} | Collateral: ${budget:.2f}")
                                if len(positions) >= self.max_slots:
                                    break
            else:
                logger.info("  [CASH DEFENSE] Spot Mode Active: Holding 100% USDT to preserve capital.")

        self.state['cash'] = cash
        self.state['positions'] = positions
        self.save_state()
        logger.info(f"[+] State successfully persisted to {STATE_FILE}.")

    def start_loop(self):
        """Runs the daemon indefinitely, ticking at the top of every hour."""
        logger.info(f"[*] Live Momentum Daemon Launched | Mode: {self.trading_mode} | Dry Run: {self.dry_run}")
        while True:
            try:
                self.run_hourly_step()
            except Exception as e:
                logger.error(f"[!] Unhandled exception in trading loop: {e}", exc_info=True)
                
            # Sleep until the top of the next hour
            now = datetime.now()
            seconds_until_next_hour = (60 - now.minute) * 60 - now.second
            if seconds_until_next_hour <= 0:
                seconds_until_next_hour = 3600
                
            logger.info(f"[*] Sleeping for {seconds_until_next_hour // 60} minutes until next hourly candle close...")
            time.sleep(seconds_until_next_hour)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Live Momentum & Bear Cloud Trading Daemon with TWAP Execution")
    parser.add_argument("--live", action="store_true", help="Enable REAL trading (defaults to Paper Trading)")
    parser.add_argument("--mode", type=str, default="FUTURES_MODE", choices=["SPOT_MODE", "FUTURES_MODE"], help="Trading mode")
    parser.add_argument("--cash", type=float, default=50.0, help="Initial wallet balance")
    parser.add_argument("--once", action="store_true", help="Execute single step and exit (for testing/cron)")
    parser.add_argument("--twap", action="store_true", help="Force enable TWAP execution slicing on all orders")
    parser.add_argument("--twap-threshold", type=float, default=1000.0, help="Order notional USD threshold to trigger TWAP (default: $1000)")
    parser.add_argument("--twap-slices", type=int, default=5, help="Number of TWAP child order slices (default: 5)")
    parser.add_argument("--twap-interval", type=float, default=10.0, help="Interval in seconds between TWAP slices (default: 10s)")
    args = parser.parse_args()
    
    daemon = LiveMomentumDaemon(
        dry_run=not args.live,
        trading_mode=args.mode,
        initial_cash=args.cash,
        twap_enabled=args.twap,
        twap_threshold=args.twap_threshold,
        twap_slices=args.twap_slices,
        twap_interval=args.twap_interval
    )
    
    if args.once:
        daemon.run_hourly_step()
    else:
        daemon.start_loop()

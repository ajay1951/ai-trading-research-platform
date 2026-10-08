"""
Backtesting Integrity Test: Comprehensive Edge-Case Regression Suite
====================================================================
Rigorous boundary tests verifying backtest accounting, discrete signal transitions,
immediate reversals, zero-trade runs, price gap handling, and risk constraints.
"""

import pytest
import numpy as np
import pandas as pd
from training.benchmark_suite import simulate_strategy_returns
from risk.position_sizing import PositionSizer
from risk.exposure import ExposureManager
from risk.circuit_breaker import CircuitBreaker


def test_zero_trades_run_equity_preservation():
    """
    Scenario: Strategy produces 100% cash/neutral signals (0.0) across all bars.
    Expected: Exactly 0 trades, total return 0.0%, max drawdown 0.0%, equity stays 1.0.
    """
    n_bars = 50
    prices = np.linspace(100.0, 200.0, n_bars)
    signals = np.zeros(n_bars)

    metrics, equity_df, trades_df = simulate_strategy_returns(
        prices, signals, fee_rate=0.0004, slippage=0.0002, return_series=True
    )

    assert metrics["trades"] == 0
    assert metrics["return_pct"] == 0.0
    assert metrics["max_drawdown"] == 0.0
    assert metrics["win_rate"] == 0.0
    assert len(trades_df) == 0
    assert np.isclose(equity_df["equity"].iloc[-1], 1.0)
    assert (equity_df["equity"] == 1.0).all()


def test_single_trade_lifecycle_and_terminal_close():
    """
    Scenario: Strategy enters Long at bar 10 ($100) and holds until dataset end at bar 20 ($120).
    Expected: Exactly 1 trade recorded, entered at $100, exited at terminal $120 (+20% gross).
              Net return equals gross return minus 2 * (fee + slippage).
    """
    n_bars = 20
    prices = np.full(n_bars, 100.0)
    prices[10:] = np.linspace(100.0, 120.0, 10) # Climbs to $120
    
    signals = np.zeros(n_bars)
    signals[10:] = 1.0 # Enter long at bar 10

    fee_rate = 0.0004
    slippage = 0.0002
    cost_per_trade = fee_rate + slippage # 0.0006 (6 bps per fill, 12 bps RT)

    metrics, equity_df, trades_df = simulate_strategy_returns(
        prices, signals, fee_rate=fee_rate, slippage=slippage, return_series=True
    )

    assert metrics["trades"] == 1
    assert len(trades_df) == 1
    
    trade = trades_df.iloc[0]
    assert trade["direction"] == "LONG"
    assert np.isclose(trade["entry_price"], 100.0)
    assert np.isclose(trade["exit_price"], 120.0)
    
    expected_gross_pct = (120.0 - 100.0) / 100.0 * 100.0 # +20.0%
    assert np.isclose(trade["gross_return_pct"], expected_gross_pct, atol=1e-2)
    
    # Net return should deduct 2 * cost_per_trade (entry + exit)
    expected_net_pct = expected_gross_pct - (cost_per_trade * 2 * 100.0)
    assert np.isclose(trade["net_return_pct"], expected_net_pct, atol=1e-2)
    assert metrics["return_pct"] > 0.0


def test_long_to_short_immediate_reversal():
    """
    Scenario: Strategy is Long (1.0) from bar 5 to 10, then immediately flips to Short (-1.0) from bar 10 to 15.
    Expected: 
    1. Long trade is closed at bar 10 price.
    2. Short trade is opened at bar 10 price and closed at bar 15.
    3. State transition cost at bar 10 is 2 * cost_per_trade (| -1 - 1 | = 2).
    4. Exactly 2 trades recorded in trade log.
    """
    n_bars = 15
    # Prices: flat 100 (bars 0-5), rises to 110 (bar 10), falls to 90 (bar 14)
    prices = np.full(n_bars, 100.0)
    prices[5:10] = np.linspace(100.0, 110.0, 5) # Long gain
    prices[10:] = np.linspace(110.0, 90.0, 5)   # Short gain (price drops)

    signals = np.zeros(n_bars)
    signals[5:10] = 1.0   # Long
    signals[10:] = -1.0  # Immediately Short

    fee_rate = 0.0004
    slippage = 0.0002

    metrics, equity_df, trades_df = simulate_strategy_returns(
        prices, signals, fee_rate=fee_rate, slippage=slippage, return_series=True
    )

    assert metrics["trades"] == 2
    assert len(trades_df) == 2

    # Check Trade 1 (Long)
    t1 = trades_df.iloc[0]
    assert t1["direction"] == "LONG"
    assert np.isclose(t1["entry_price"], 100.0)
    assert np.isclose(t1["exit_price"], 110.0)
    assert t1["gross_return_pct"] > 0.0

    # Check Trade 2 (Short)
    t2 = trades_df.iloc[1]
    assert t2["direction"] == "SHORT"
    assert np.isclose(t2["entry_price"], 110.0)
    assert np.isclose(t2["exit_price"], 90.0)
    # Short profit: (110 - 90) / 110 = +18.18%
    assert t2["gross_return_pct"] > 0.0

    # Both trades should be profitable
    assert metrics["win_rate"] == 100.0
    assert metrics["return_pct"] > 0.0


def test_short_to_long_immediate_reversal():
    """
    Scenario: Strategy is Short (-1.0) during downtrend (100 -> 80), then flips to Long (+1.0) during uptrend (80 -> 100).
    Expected: Exactly 2 trades, both profitable, correct direction tagging and accounting.
    """
    n_bars = 15
    prices = np.full(n_bars, 100.0)
    prices[3:8] = np.linspace(100.0, 80.0, 5)  # Downtrend
    prices[8:] = np.linspace(80.0, 100.0, 7)   # Uptrend

    signals = np.zeros(n_bars)
    signals[3:8] = -1.0  # Short
    signals[8:] = 1.0   # Flip Long

    metrics, equity_df, trades_df = simulate_strategy_returns(
        prices, signals, fee_rate=0.0004, slippage=0.0002, return_series=True
    )

    assert metrics["trades"] == 2
    assert trades_df.iloc[0]["direction"] == "SHORT"
    assert trades_df.iloc[1]["direction"] == "LONG"
    assert trades_df.iloc[0]["gross_return_pct"] > 0.0
    assert trades_df.iloc[1]["gross_return_pct"] > 0.0
    assert metrics["win_rate"] == 100.0


def test_consecutive_duplicate_signals_no_extra_fees():
    """
    Scenario:
    Case 1 (In-Loop Complete Round-Trip): Signal stays Long (1.0) for 50 bars, then drops to Cash (0.0) for 50 bars in flat market.
           Expected: Exactly 1 trade, exactly 1 entry fee and 1 exit fee deducted.
                     Cumulative equity loss is exactly 2 * cost_per_trade (-0.12%).
    Case 2 (Terminal Unclosed Position): Signal stays Long (1.0) for all 100 bars.
           Expected: In-loop mark-to-market equity incurs 1 entry fee (-0.06%), while completed trade log
                     records full 2 * cost_per_trade (-0.12%) net return.
    """
    fee_rate = 0.0004
    slippage = 0.0002
    cost_per_trade = fee_rate + slippage # 0.0006 (6 bps per fill, 12 bps RT)

    # Case 1: Enter at bar 0, exit at bar 50
    n_bars = 100
    prices = np.full(n_bars, 100.0)
    signals_closed = np.zeros(n_bars)
    signals_closed[:50] = 1.0

    metrics_c, equity_df_c, trades_df_c = simulate_strategy_returns(
        prices, signals_closed, fee_rate=fee_rate, slippage=slippage, return_series=True
    )

    assert metrics_c["trades"] == 1
    assert len(trades_df_c) == 1
    expected_rt_loss_pct = -(cost_per_trade * 2 * 100.0) # -0.12%
    assert np.isclose(metrics_c["return_pct"], expected_rt_loss_pct, atol=1e-3)
    assert np.isclose(trades_df_c.iloc[0]["net_return_pct"], expected_rt_loss_pct, atol=1e-3)

    # Case 2: Hold open through terminal bar
    signals_hold = np.ones(n_bars)
    metrics_h, equity_df_h, trades_df_h = simulate_strategy_returns(
        prices, signals_hold, fee_rate=fee_rate, slippage=slippage, return_series=True
    )

    assert metrics_h["trades"] == 1
    assert len(trades_df_h) == 1
    # Terminal equity reflects entry cost during simulation
    assert np.isclose(metrics_h["return_pct"], -(cost_per_trade * 100.0), atol=1e-3)
    # Trade log records complete round-trip net return
    assert np.isclose(trades_df_h.iloc[0]["net_return_pct"], expected_rt_loss_pct, atol=1e-3)


def test_price_gap_slippage_and_large_movement():
    """
    Scenario: Overnight 50% price crash while holding Long position (100 -> 50).
    Expected: Portfolio equity drops by approximately 50%, mark-to-market accounting matches,
              and maximum drawdown correctly captures the ~50% drop.
    """
    prices = np.array([100.0, 100.0, 100.0, 50.0, 50.0])
    signals = np.array([0.0, 1.0, 1.0, 1.0, 0.0])

    metrics, equity_df, trades_df = simulate_strategy_returns(
        prices, signals, fee_rate=0.0004, slippage=0.0002, return_series=True
    )

    assert metrics["trades"] == 1
    assert np.isclose(metrics["max_drawdown"], 50.0, atol=1.0)
    assert np.isclose(trades_df.iloc[0]["exit_price"], 50.0)
    assert metrics["return_pct"] < -49.0


def test_position_sizer_zero_cash_boundary():
    """
    Scenario: PositionSizer invoked with zero/negative cash, zero price, or zero ATR.
    Expected: Returns 0.0 size safely without division by zero or exception.
    """
    sizer = PositionSizer(target_risk_pct_per_trade=0.015, max_leverage=3.0)

    # 1. Zero equity
    assert sizer.calculate_atr_size(equity=0.0, price=100.0, atr=2.0) == 0.0
    # 2. Negative equity
    assert sizer.calculate_atr_size(equity=-100.0, price=100.0, atr=2.0) == 0.0
    # 3. Zero price
    assert sizer.calculate_atr_size(equity=1000.0, price=0.0, atr=2.0) == 0.0
    # 4. Zero ATR
    assert sizer.calculate_atr_size(equity=1000.0, price=100.0, atr=0.0) == 0.0


def test_exposure_limits_enforced_at_boundary():
    """
    Scenario: ExposureManager tests adding position beyond 100% gross exposure or 35% single-asset concentration.
    Expected: check_exposure returns False when limits are breached, True when compliant.
    """
    mgr = ExposureManager(max_gross_exposure=1.0, max_single_asset_pct=0.35)
    equity = 1000.0

    current_positions = {
        "BTCUSDT": {"size": 0.003, "entry_price": 100000.0} # $300 notional (30% of equity)
    }

    # 1. Adding $100 to ETH -> Gross becomes $400 (40%), ETH is 10% -> Compliant (True)
    assert mgr.check_exposure(equity, current_positions, new_symbol="ETHUSDT", new_notional=100.0) is True

    # 2. Adding $100 to BTC -> BTC becomes $400 (40% > 35% concentration cap) -> Rejection (False)
    assert mgr.check_exposure(equity, current_positions, new_symbol="BTCUSDT", new_notional=100.0) is False

    # 3. Adding $800 to SOL -> Gross becomes $1100 (110% > 100% gross cap) -> Rejection (False)
    assert mgr.check_exposure(equity, current_positions, new_symbol="SOLUSDT", new_notional=800.0) is False


def test_empty_or_single_bar_input_graceful_handling():
    """
    Scenario: Input arrays have length 0 or 1.
    Expected: Safe return of empty metrics dictionary without IndexError or unhandled crash.
    """
    empty_p = np.array([])
    empty_s = np.array([])
    res_empty = simulate_strategy_returns(empty_p, empty_s)
    assert res_empty["trades"] == 0
    assert res_empty["return_pct"] == 0.0

    single_p = np.array([100.0])
    single_s = np.array([1.0])
    res_single = simulate_strategy_returns(single_p, single_s)
    assert res_single["trades"] == 0
    assert res_single["return_pct"] == 0.0

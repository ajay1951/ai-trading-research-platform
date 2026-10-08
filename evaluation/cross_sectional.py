"""
Quantitative Research: Cross-Sectional Ranking & Portfolio Construction Engine
=============================================================================
Implements relative-strength asset ranking across a multi-asset universe:
- Ranks model prediction scores P(Up) at timestamp t
- Generates Top-N Long / Bottom-N Short (or Long-Only) portfolio target weights
- Simulates multi-asset portfolio equity curves with next-bar execution (t+1)
- Deducts transaction fees (0.04%) and slippage (0.02%) proportional to portfolio turnover (12 bps round-trip)
"""

from typing import Dict, Any, List, Optional, Tuple, Union
import numpy as np
import pandas as pd


class CrossSectionalRanker:
    """
    Ranks cross-sectional model predictions and assigns portfolio weights.
    """

    @staticmethod
    def rank_assets(
        predictions: Dict[str, float],
        top_n: int = 2,
        bottom_n: int = 2,
        allow_short: bool = True,
        max_single_weight: float = 0.50
    ) -> Dict[str, float]:
        """
        Ranks assets by prediction score descending and produces target portfolio weights.

        :param predictions: Dict of {symbol: score} at timestamp t.
        :param top_n: Number of assets to allocate Long exposure.
        :param bottom_n: Number of assets to allocate Short exposure (if allow_short=True).
        :param allow_short: If True, allocates negative weights to bottom_n assets.
        :param max_single_weight: Maximum absolute weight allowed for any single asset.
        :return: Dict of {symbol: weight} where sum(abs(weights)) <= 1.0 (or <= 2.0 if L/S 100/100).
        """
        # Filter out NaN, null, or invalid scores
        valid_preds = {
            sym: float(score)
            for sym, score in predictions.items()
            if score is not None and not np.isnan(score) and not np.isinf(score)
        }

        weights: Dict[str, float] = {sym: 0.0 for sym in predictions.keys()}
        n_assets = len(valid_preds)

        if n_assets == 0:
            return weights

        # Sort symbols by score descending. For ties, sort by symbol name for deterministic stability.
        sorted_items = sorted(valid_preds.items(), key=lambda x: (x[1], x[0]), reverse=True)
        sorted_symbols = [item[0] for item in sorted_items]

        # Determine effective allocation count based on available assets
        effective_top = min(top_n, n_assets)
        top_weight_per_asset = min(1.0 / effective_top, max_single_weight) if effective_top > 0 else 0.0

        for i in range(effective_top):
            weights[sorted_symbols[i]] = float(top_weight_per_asset)

        if allow_short and n_assets >= (top_n + bottom_n):
            effective_bottom = min(bottom_n, n_assets - effective_top)
            bottom_weight_per_asset = min(1.0 / effective_bottom, max_single_weight) if effective_bottom > 0 else 0.0
            for i in range(effective_bottom):
                short_sym = sorted_symbols[-(i + 1)]
                # Ensure an asset cannot be both long and short
                if weights[short_sym] == 0.0:
                    weights[short_sym] = -float(bottom_weight_per_asset)

        return weights


    @staticmethod
    def apply_rebalance_frequency(weights_df: pd.DataFrame, interval_bars: int = 1) -> pd.DataFrame:
        """
        Samples target weights at scheduled intervals (every interval_bars) and forward-fills
        intermediate bars, ensuring no unnecessary turnover is generated between rebalance timestamps.
        """
        if interval_bars <= 1 or len(weights_df) == 0:
            return weights_df.copy()

        scheduled_weights = weights_df.copy()
        for i in range(len(scheduled_weights)):
            if i % interval_bars != 0:
                scheduled_weights.iloc[i] = scheduled_weights.iloc[i - 1]

        return scheduled_weights

    @staticmethod
    def compute_rank_persistence(predictions_df: pd.DataFrame, top_n: int = 2, bottom_n: int = 2) -> Dict[str, Any]:
        """
        Analyzes stability of cross-sectional rankings over time:
        - Rank autocorrelations at 1h, 4h, 12h, 24h lags
        - Top-N and Bottom-N set overlap fractions (Jaccard similarity)
        - Average holding persistence of Top-N and Bottom-N membership
        - Number of rank membership transitions
        """
        if len(predictions_df) < 25:
            return {
                "rank_corr_1h": 0.0, "rank_corr_4h": 0.0,
                "rank_corr_12h": 0.0, "rank_corr_24h": 0.0,
                "top_n_persistence_1h": 0.0, "top_n_persistence_4h": 0.0,
                "top_n_persistence_24h": 0.0, "avg_top_n_duration_bars": 0.0,
                "top_n_transitions_count": 0
            }

        # Compute rank matrix at each timestamp (1 = highest score)
        ranks_df = predictions_df.rank(axis=1, ascending=False, method='min')

        def calc_lag_corr(lag: int) -> float:
            corrs = []
            for t in range(len(ranks_df) - lag):
                r1 = ranks_df.iloc[t].dropna()
                r2 = ranks_df.iloc[t + lag].dropna()
                common = r1.index.intersection(r2.index)
                if len(common) >= 4:
                    c = r1[common].corr(r2[common], method='spearman')
                    if not np.isnan(c):
                        corrs.append(c)
            return round(float(np.mean(corrs)), 4) if corrs else 0.0

        def calc_overlap(lag: int, pick_top: bool = True) -> float:
            overlaps = []
            for t in range(len(predictions_df) - lag):
                s1 = predictions_df.iloc[t].dropna().sort_values(ascending=False)
                s2 = predictions_df.iloc[t + lag].dropna().sort_values(ascending=False)
                if len(s1) >= (top_n + bottom_n) and len(s2) >= (top_n + bottom_n):
                    set1 = set(s1.index[:top_n] if pick_top else s1.index[-bottom_n:])
                    set2 = set(s2.index[:top_n] if pick_top else s2.index[-bottom_n:])
                    jaccard = len(set1.intersection(set2)) / len(set1.union(set2))
                    overlaps.append(jaccard)
            return round(float(np.mean(overlaps)), 4) if overlaps else 0.0

        # Membership duration tracking
        top_durations = []
        bottom_durations = []
        active_top_runs: Dict[str, int] = {}
        active_bottom_runs: Dict[str, int] = {}
        top_transitions = 0
        prev_top_set = set()

        for t in range(len(predictions_df)):
            s = predictions_df.iloc[t].dropna().sort_values(ascending=False)
            if len(s) >= (top_n + bottom_n):
                current_top = set(s.index[:top_n])
                current_bottom = set(s.index[-bottom_n:])

                if prev_top_set and current_top != prev_top_set:
                    top_transitions += 1
                prev_top_set = current_top

                for sym in current_top:
                    active_top_runs[sym] = active_top_runs.get(sym, 0) + 1
                for sym in list(active_top_runs.keys()):
                    if sym not in current_top:
                        top_durations.append(active_top_runs.pop(sym))

                for sym in current_bottom:
                    active_bottom_runs[sym] = active_bottom_runs.get(sym, 0) + 1
                for sym in list(active_bottom_runs.keys()):
                    if sym not in current_bottom:
                        bottom_durations.append(active_bottom_runs.pop(sym))

        top_durations += list(active_top_runs.values())
        bottom_durations += list(active_bottom_runs.values())

        return {
            "rank_corr_1h": calc_lag_corr(1),
            "rank_corr_4h": calc_lag_corr(4),
            "rank_corr_12h": calc_lag_corr(12),
            "rank_corr_24h": calc_lag_corr(24),
            "top_n_persistence_1h": calc_overlap(1, pick_top=True),
            "top_n_persistence_4h": calc_overlap(4, pick_top=True),
            "top_n_persistence_12h": calc_overlap(12, pick_top=True),
            "top_n_persistence_24h": calc_overlap(24, pick_top=True),
            "bottom_n_persistence_1h": calc_overlap(1, pick_top=False),
            "bottom_n_persistence_4h": calc_overlap(4, pick_top=False),
            "bottom_n_persistence_24h": calc_overlap(24, pick_top=False),
            "avg_top_n_duration_hours": round(float(np.mean(top_durations)), 2) if top_durations else 0.0,
            "median_top_n_duration_hours": round(float(np.median(top_durations)), 2) if top_durations else 0.0,
            "max_top_n_duration_hours": int(np.max(top_durations)) if top_durations else 0,
            "avg_bottom_n_duration_hours": round(float(np.mean(bottom_durations)), 2) if bottom_durations else 0.0,
            "top_n_transitions_count": top_transitions
        }


def simulate_cross_sectional_portfolio(
    prices_df: pd.DataFrame,
    weights_df: pd.DataFrame,
    fee_rate: float = 0.0004,
    slippage: float = 0.0002,
    initial_capital: float = 1000.0,
    return_series: bool = False
) -> Union[Dict[str, Any], Tuple[Dict[str, Any], pd.DataFrame, pd.DataFrame]]:
    """
    Simulates cross-sectional multi-asset portfolio with next-bar open execution (t+1).

    :param prices_df: DataFrame of asset close prices indexed by timestamp, columns = symbols.
    :param weights_df: DataFrame of target weights decided at bar t, indexed by timestamp, columns = symbols.
    :param fee_rate: One-way exchange fee rate (default: 0.04% = 4 bps).
    :param slippage: One-way slippage rate (default: 0.02% = 2 bps).
    :param initial_capital: Starting portfolio value in USD.
    :param return_series: If True, returns detailed equity curve and turnover DataFrames.
    """
    # Align prices and weights
    common_idx = prices_df.index.intersection(weights_df.index)
    if len(common_idx) < 2:
        empty = {
            "return_pct": 0.0, "gross_return_pct": 0.0, "total_fees_pct": 0.0,
            "total_slippage_pct": 0.0, "total_costs_pct": 0.0,
            "sharpe": 0.0, "sortino": 0.0, "max_drawdown": 0.0, "calmar": 0.0,
            "trades": 0, "rebalances": 0, "win_rate": 0.0, "profit_factor": 0.0,
            "turnover": 0.0, "total_turnover": 0.0,
            "avg_holding_period_hours": 0.0, "median_holding_period_hours": 0.0, "max_holding_period_hours": 0
        }
        if return_series:
            return empty, pd.DataFrame(), pd.DataFrame()
        return empty

    aligned_prices = prices_df.loc[common_idx].sort_index()
    aligned_weights = weights_df.loc[common_idx].sort_index()

    symbols = [s for s in aligned_prices.columns if s in aligned_weights.columns]
    price_mat = aligned_prices[symbols].values # shape: (T, M)
    weight_mat = aligned_weights[symbols].values # shape: (T, M)

    n_bars, n_symbols = price_mat.shape
    cost_per_turnover = fee_rate + slippage # 0.0006 per 100% turnover

    equity = initial_capital
    equity_curve = [equity]
    step_returns = []
    step_turnovers = []
    total_rebalances = 0
    trade_returns = []

    # Holding period run tracking
    holding_durations = []
    active_runs: Dict[int, int] = {}

    current_weights = np.zeros(n_symbols)

    for t in range(n_bars - 1):
        target_w = weight_mat[t]
        p_now = price_mat[t]
        p_next = price_mat[t + 1]

        # Track holding durations per asset index
        for sym_idx in range(n_symbols):
            if abs(target_w[sym_idx]) > 1e-6:
                active_runs[sym_idx] = active_runs.get(sym_idx, 0) + 1
            elif sym_idx in active_runs:
                holding_durations.append(active_runs.pop(sym_idx))

        # Calculate asset price step returns
        with np.errstate(divide='ignore', invalid='ignore'):
            asset_step_rets = np.where(p_now > 0, (p_next - p_now) / p_now, 0.0)
            asset_step_rets = np.nan_to_num(asset_step_rets, nan=0.0, posinf=0.0, neginf=0.0)

        # Turnover incurred to shift from current_weights to target_w
        turnover = np.sum(np.abs(target_w - current_weights))
        step_turnovers.append(turnover)
        if turnover > 1e-4:
            total_rebalances += 1

        turnover_cost = turnover * cost_per_turnover
        equity -= (equity * turnover_cost)

        # Gross portfolio step return = sum(w_i * r_i)
        gross_pnl_pct = np.sum(target_w * asset_step_rets)
        equity *= (1.0 + gross_pnl_pct)

        step_ret = (equity / equity_curve[-1]) - 1.0 if len(equity_curve) > 0 else 0.0
        step_returns.append(step_ret)
        trade_returns.append(gross_pnl_pct - turnover_cost)
        equity_curve.append(equity)

        # End-of-bar position drift due to relative price changes
        with np.errstate(divide='ignore', invalid='ignore'):
            drifted_unnorm = target_w * (1.0 + asset_step_rets)
            total_drifted_val = 1.0 + gross_pnl_pct
            current_weights = np.where(total_drifted_val > 1e-9, drifted_unnorm / total_drifted_val, target_w)
            current_weights = np.nan_to_num(current_weights, nan=0.0)

    # Terminal close friction if open positions remain
    terminal_turnover = np.sum(np.abs(current_weights))
    if terminal_turnover > 1e-4:
        equity -= (equity * terminal_turnover * cost_per_turnover)
        equity_curve[-1] = equity
        step_turnovers.append(terminal_turnover)

    holding_durations += list(active_runs.values())

    equity_series = pd.Series(equity_curve)
    ret_series = pd.Series(step_returns)

    total_return_pct = float(((equity - initial_capital) / initial_capital) * 100.0)
    total_turnover = float(np.sum(step_turnovers))
    total_fee_cost_pct = float(total_turnover * fee_rate * 100.0)
    total_slippage_cost_pct = float(total_turnover * slippage * 100.0)
    total_costs_pct = total_fee_cost_pct + total_slippage_cost_pct
    gross_return_pct = total_return_pct + total_costs_pct

    mean_r = ret_series.mean() if len(ret_series) > 0 else 0.0
    std_r = ret_series.std() if len(ret_series) > 0 else 0.0
    sharpe = float((mean_r / (std_r + 1e-9)) * np.sqrt(8760)) if std_r > 0 else 0.0

    downside_r = ret_series[ret_series < 0]
    downside_std = downside_r.std() if len(downside_r) > 0 else 0.0
    sortino = float((mean_r / (downside_std + 1e-9)) * np.sqrt(8760)) if downside_std > 0 else 0.0

    cum_max = equity_series.cummax()
    drawdown = (equity_series - cum_max) / (cum_max + 1e-9)
    max_dd_pct = float(abs(drawdown.min()) * 100.0)
    calmar = float(total_return_pct / max_dd_pct) if max_dd_pct > 0 else 0.0

    wins = [r for r in trade_returns if r > 0]
    losses = [r for r in trade_returns if r < 0]
    win_rate = float(len(wins) / len(trade_returns) * 100.0) if len(trade_returns) > 0 else 0.0
    profit_factor = float(sum(wins) / (abs(sum(losses)) + 1e-9)) if losses else (99.0 if wins else 0.0)
    daily_turnover = float(total_turnover / (max(1, len(common_idx) / 24.0)))

    metrics = {
        "return_pct": round(total_return_pct, 2),
        "gross_return_pct": round(gross_return_pct, 2),
        "total_fees_pct": round(total_fee_cost_pct, 2),
        "total_slippage_pct": round(total_slippage_cost_pct, 2),
        "total_costs_pct": round(total_costs_pct, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "max_drawdown": round(max_dd_pct, 2),
        "calmar": round(calmar, 2),
        "trades": total_rebalances,
        "rebalances": total_rebalances,
        "win_rate": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2),
        "turnover": round(daily_turnover, 4),
        "total_turnover": round(total_turnover, 2),
        "avg_holding_period_hours": round(float(np.mean(holding_durations)), 2) if holding_durations else 0.0,
        "median_holding_period_hours": round(float(np.median(holding_durations)), 2) if holding_durations else 0.0,
        "max_holding_period_hours": int(np.max(holding_durations)) if holding_durations else 0
    }

    if return_series:
        ts_strings = [str(t) for t in common_idx] + [str(common_idx[-1])]
        if len(ts_strings) > len(equity_curve):
            ts_strings = ts_strings[:len(equity_curve)]
        elif len(ts_strings) < len(equity_curve):
            ts_strings += [f"bar_{i}" for i in range(len(equity_curve) - len(ts_strings))]

        equity_df = pd.DataFrame({
            "timestamp": ts_strings,
            "equity": [round(float(e), 4) for e in equity_curve],
            "drawdown_pct": [round(float(abs(d) * 100.0), 4) for d in drawdown]
        })
        weights_out = aligned_weights.copy()
        return metrics, equity_df, weights_out

    return metrics

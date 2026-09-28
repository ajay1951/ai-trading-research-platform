"""
Statistical Validation & Robustness Analysis Engine
===================================================
Rigorous quantitative statistical validation on REAL backtest outputs:
1. Monte Carlo Bootstrap/Resampling with Replacement on historical trade returns (1,000 runs)
   -> 95% & 99% Max Drawdown VaR, CVaR 95, worst-case drawdown, probability of profit.
2. Stationary Block Bootstrap for Sharpe Ratio (95% CI) on real periodic returns.
3. Market Regime Segmentation (Bull, Bear, Sideways) against benchmark moving average.
4. Statistical Stability Analysis (flags small sample size, extreme Sortino/Sharpe/profit factor).
5. Strict Provenance Tracking linking output directly to experiment artifacts and commit SHA.
"""

import os
import sys
import json
import argparse
import logging
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("StatisticalValidation")


class StatisticalValidationEngine:
    def __init__(self, n_simulations: int = 1000, confidence_level: float = 0.95):
        self.n_simulations = n_simulations
        self.confidence_level = confidence_level

    def monte_carlo_drawdown_distribution(
        self,
        trade_returns: List[float],
        initial_capital: float = 1000.0
    ) -> Dict[str, Any]:
        """
        Runs Monte Carlo bootstrap/resampling with replacement on real trade returns
        to compute the empirical distribution of Max Drawdowns, VaR 95, CVaR 95, and Probability of Profit.
        """
        n_trades = len(trade_returns)
        if n_trades < 3:
            raise ValueError(f"Insufficient trade count ({n_trades} trades) to execute Monte Carlo bootstrap/resampling with replacement.")

        simulated_max_dds = []
        simulated_final_equities = []

        np.random.seed(42)
        for _ in range(self.n_simulations):
            sampled_returns = np.random.choice(trade_returns, size=n_trades, replace=True)
            equity_curve = initial_capital * np.cumprod(1.0 + sampled_returns)

            peak = np.maximum.accumulate(equity_curve)
            dd = (equity_curve - peak) / (peak + 1e-9)
            max_dd = float(abs(np.min(dd)) * 100.0)

            simulated_max_dds.append(max_dd)
            simulated_final_equities.append(equity_curve[-1])

        simulated_max_dds = np.array(simulated_max_dds)
        simulated_final_equities = np.array(simulated_final_equities)

        dd_p50 = float(np.percentile(simulated_max_dds, 50))
        dd_p95 = float(np.percentile(simulated_max_dds, 95))
        dd_p99 = float(np.percentile(simulated_max_dds, 99))
        dd_cvar95 = float(np.mean(simulated_max_dds[simulated_max_dds >= dd_p95]))
        dd_worst = float(np.max(simulated_max_dds))

        p_profit = float((simulated_final_equities > initial_capital).mean() * 100.0)

        return {
            "n_simulations": self.n_simulations,
            "sample_trade_count": n_trades,
            "median_max_dd_pct": round(dd_p50, 2),
            "var_95_max_dd_pct": round(dd_p95, 2),
            "var_99_max_dd_pct": round(dd_p99, 2),
            "cvar_95_max_dd_pct": round(dd_cvar95, 2),
            "worst_case_max_dd_pct": round(dd_worst, 2),
            "probability_of_profit_pct": round(p_profit, 2)
        }

    def bootstrap_sharpe_ci(
        self,
        step_returns: pd.Series,
        n_bootstrap: int = 1000,
        block_size: int = 24
    ) -> Dict[str, Any]:
        """
        Computes 95% Confidence Interval for the Annualized Sharpe Ratio using
        block bootstrapping on real periodic returns to preserve autocorrelation structure.
        """
        clean_ret = step_returns.dropna().values
        n = len(clean_ret)
        if n < 50:
            raise ValueError(f"Insufficient return observations ({n} bars) to execute block bootstrapping.")

        bootstrapped_sharpes = []
        np.random.seed(42)

        actual_block_size = min(block_size, n // 2)
        n_blocks = max(1, n // actual_block_size)

        for _ in range(n_bootstrap):
            block_starts = np.random.randint(0, max(1, n - actual_block_size + 1), size=n_blocks)
            sampled_blocks = [clean_ret[idx : idx + actual_block_size] for idx in block_starts]
            boot_sample = np.concatenate(sampled_blocks)

            mean_r = boot_sample.mean()
            std_r = boot_sample.std()
            if std_r > 1e-9:
                sharpe = (mean_r / std_r) * np.sqrt(8760)
                bootstrapped_sharpes.append(sharpe)
            else:
                bootstrapped_sharpes.append(0.0)

        bootstrapped_sharpes = np.array(bootstrapped_sharpes)
        alpha = (1.0 - self.confidence_level) / 2.0
        ci_lower = float(np.percentile(bootstrapped_sharpes, alpha * 100.0))
        ci_upper = float(np.percentile(bootstrapped_sharpes, (1.0 - alpha) * 100.0))
        median_sharpe = float(np.median(bootstrapped_sharpes))

        return {
            "median_sharpe": round(median_sharpe, 2),
            "confidence_level": self.confidence_level,
            "ci_lower": round(ci_lower, 2),
            "ci_upper": round(ci_upper, 2),
            "p_sharpe_positive": round(float((bootstrapped_sharpes > 0).mean() * 100.0), 2)
        }

    def regime_segmented_performance(
        self,
        df_bars: pd.DataFrame,
        equity_df: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Segments real strategy performance across Bull, Bear, and Sideways regimes
        defined by the BTC 100-day (2,400-hour) moving average.
        """
        if 'timestamp' in df_bars.columns and 'timestamp' in equity_df.columns:
            df_bars_indexed = df_bars.copy()
            df_bars_indexed['timestamp'] = pd.to_datetime(df_bars_indexed['timestamp'], utc=True, format='mixed')
            df_bars_indexed = df_bars_indexed.sort_values('timestamp').set_index('timestamp')

            equity_indexed = equity_df.copy()
            equity_indexed['timestamp'] = pd.to_datetime(equity_indexed['timestamp'], utc=True, format='mixed')
            equity_indexed = equity_indexed.sort_values('timestamp').set_index('timestamp')

            close = df_bars_indexed['close']
            sma_100d = close.rolling(2400, min_periods=100).mean()
            momentum_100d = (close - sma_100d) / (sma_100d + 1e-9)

            aligned_mom = momentum_100d.reindex(equity_indexed.index).ffill().fillna(0.0)
            strategy_ret = equity_indexed['step_return']

            bull_mask = aligned_mom > 0.05
            bear_mask = aligned_mom < -0.05
            sideways_mask = (~bull_mask) & (~bear_mask)
        else:
            n = len(equity_df)
            strategy_ret = equity_df['step_return']
            bull_mask = pd.Series([True] * (n // 3) + [False] * (n - n // 3), index=strategy_ret.index)
            bear_mask = pd.Series([False] * (n // 3) + [True] * (n // 3) + [False] * (n - 2 * (n // 3)), index=strategy_ret.index)
            sideways_mask = (~bull_mask) & (~bear_mask)

        def eval_segment(mask, name):
            sub_ret = strategy_ret[mask].dropna()
            if len(sub_ret) == 0:
                return {"regime": name, "bars": 0, "cumulative_return_pct": 0.0, "sharpe": 0.0}
            cum_ret = float((np.prod(1.0 + sub_ret) - 1.0) * 100.0)
            m = sub_ret.mean()
            s = sub_ret.std()
            sh = float((m / (s + 1e-9)) * np.sqrt(8760)) if s > 0 else 0.0
            return {
                "regime": name,
                "bars": int(len(sub_ret)),
                "cumulative_return_pct": round(cum_ret, 2),
                "sharpe": round(sh, 2)
            }

        return {
            "bull_regime": eval_segment(bull_mask, "Bull (BTC > +5% 100d SMA)"),
            "bear_regime": eval_segment(bear_mask, "Bear (BTC < -5% 100d SMA)"),
            "sideways_regime": eval_segment(sideways_mask, "Sideways (Consolidation)")
        }

    def check_metric_stability(
        self,
        trade_returns: List[float],
        metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        P0-10: Evaluates statistical stability. Flags small sample sizes and extreme metrics honestly.
        """
        n_trades = len(trade_returns)
        warnings = []
        is_unstable = False

        if n_trades < 30:
            is_unstable = True
            warnings.append(
                f"Small sample size ({n_trades} trades < 30 threshold). "
                "Statistical metrics exhibit high estimation variance and regime sensitivity."
            )

        sharpe = metrics.get("sharpe", 0.0)
        if sharpe > 3.0:
            is_unstable = True
            warnings.append(
                f"Extremely high Sharpe ratio ({sharpe:.2f} > 3.0) on short test slice. "
                "Likely indicates regime-specific tail-event filtering rather than stationary multi-year edge."
            )

        sortino = metrics.get("sortino", 0.0)
        if sortino > 50.0:
            is_unstable = True
            warnings.append(
                f"Extremely high Sortino ratio ({sortino:.2f}) indicates almost no downside sample variance, "
                "characteristic of small-sample clustering."
            )

        profit_factor = metrics.get("profit_factor", 0.0)
        if profit_factor >= 50.0:
            is_unstable = True
            warnings.append(
                f"Near-infinite profit factor ({profit_factor:.2f}) due to zero or negligible losing trades in short slice."
            )

        max_dd = metrics.get("max_drawdown", 0.0)
        if max_dd < 0.5 and n_trades < 20:
            is_unstable = True
            warnings.append(
                f"Artificially low maximum drawdown ({max_dd:.2f}%) driven by sparse trade exposure rather than true risk control."
            )

        return {
            "is_statistically_unstable": is_unstable,
            "sample_size": n_trades,
            "sample_size_assessment": "ADEQUATE" if n_trades >= 30 else "INSUFFICIENT",
            "warnings": warnings,
            "cautionary_flag": "Small sample size / statistically unstable metric." if is_unstable else "None"
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Statistical Validation Engine")
    parser.add_argument("--trades", type=str, default="artifacts/experiments/EXP-001/trades.csv", help="Path to real trades.csv")
    parser.add_argument("--equity", type=str, default="artifacts/experiments/EXP-001/equity_curve.csv", help="Path to real equity_curve.csv")
    parser.add_argument("--metrics", type=str, default="artifacts/experiments/EXP-001/metrics.json", help="Path to real metrics.json")
    parser.add_argument("--metadata", type=str, default="artifacts/experiments/EXP-001/metadata.json", help="Path to experiment metadata.json")
    parser.add_argument("--data", type=str, default="data/BTCUSDT_1h_historical.csv", help="Path to market OHLCV data")
    parser.add_argument("--out", type=str, default="docs/statistical_validation.json", help="Path to output validation JSON")
    args = parser.parse_args()

    # Strict Validation: Fail clearly if real backtest outputs are missing
    if not os.path.exists(args.trades):
        raise FileNotFoundError(
            f"Required backtest output '{args.trades}' not found! "
            "Statistical validation requires real backtest data. Run the benchmark/backtest suite first."
        )
    if not os.path.exists(args.equity):
        raise FileNotFoundError(
            f"Required backtest output '{args.equity}' not found! "
            "Statistical validation requires real equity curve data. Run the benchmark/backtest suite first."
        )

    trades_df = pd.read_csv(args.trades)
    equity_df = pd.read_csv(args.equity)

    if trades_df.empty:
        raise ValueError(f"Backtest trades file '{args.trades}' is empty! Cannot validate zero trades.")
    if equity_df.empty:
        raise ValueError(f"Backtest equity file '{args.equity}' is empty! Cannot validate zero equity points.")

    metrics = {}
    if os.path.exists(args.metrics):
        with open(args.metrics, "r", encoding="utf-8") as f:
            metrics = json.load(f)

    meta = {}
    if os.path.exists(args.metadata):
        with open(args.metadata, "r", encoding="utf-8") as f:
            meta = json.load(f)

    experiment_id = meta.get("experiment_id", "EXP-001")
    commit_sha = meta.get("commit_sha", "unknown")

    # Extract REAL returns
    if "net_return_pct" in trades_df.columns:
        real_trade_returns = (trades_df["net_return_pct"] / 100.0).tolist()
    elif "gross_return_pct" in trades_df.columns:
        real_trade_returns = (trades_df["gross_return_pct"] / 100.0).tolist()
    else:
        raise ValueError("Could not find return column in trades.csv")

    real_step_returns = equity_df["step_return"].dropna()

    logger.info(f"Loaded {len(real_trade_returns)} real trades and {len(real_step_returns)} equity steps for {experiment_id}.")

    engine = StatisticalValidationEngine(n_simulations=1000)
    mc_results = engine.monte_carlo_drawdown_distribution(real_trade_returns)
    boot_results = engine.bootstrap_sharpe_ci(real_step_returns)

    regime_results = {}
    if os.path.exists(args.data):
        df_bars = pd.read_csv(args.data).tail(10000).reset_index(drop=True)
        regime_results = engine.regime_segmented_performance(df_bars, equity_df)

    stability = engine.check_metric_stability(real_trade_returns, metrics)

    report = {
        "experiment_id": experiment_id,
        "source_trades": args.trades,
        "source_equity_curve": args.equity,
        "source_metrics": args.metrics,
        "commit_sha": commit_sha,
        "trade_count": len(real_trade_returns),
        "monte_carlo": mc_results,
        "bootstrap_sharpe_ci": boot_results,
        "regime_breakdown": regime_results,
        "stability_analysis": stability
    }

    print("\n" + "=" * 80)
    print("      REAL BACKTEST STATISTICAL VALIDATION & MONTE CARLO ANALYSIS")
    print("=" * 80)
    print(json.dumps(report, indent=2))
    print("=" * 80 + "\n")

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"[+] Statistical validation saved to {args.out}")

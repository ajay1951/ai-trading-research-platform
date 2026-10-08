"""
training/p3_1_cost_benchmark.py
===============================
P3-1 Advanced Execution Cost Benchmark Runner.

Executes experiments EXP-P3-01-COST-001 through EXP-P3-01-COST-007
across the 13-asset crypto universe using 5-fold Purged Walk-Forward CV.

Evaluates:
- Gross vs Net Return, Sharpe, Sortino, Max Drawdown
- Cost decomposition (Fees, Spread, Slippage, Market Impact, Delay)
- Asset-level cost & turnover ranking (13 assets)
- BTC regime cost attribution (Bull, Sideways, Bear)
- Volatility and liquidity tier profiling
- Break-even transaction cost analysis
- Rebalance frequency interactions (18H, 24H, 36H, 48H)
"""

import os
import sys
import json
import logging
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from lightgbm import LGBMClassifier

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.splitting import TemporalSplitter
from features.technical import TechnicalFeaturePipeline
from evaluation.cross_sectional import CrossSectionalRanker
from evaluation.transaction_costs import (
    TransactionCostEngine,
    CostModelConfig,
    CostModelProfile,
    TradeCostBreakdown,
    LiquidityTier,
    SCENARIO_CONFIGS
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("P3_1_CostBenchmark")

UNIVERSE_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "NEARUSDT",
    "LTCUSDT", "DOTUSDT", "SUIUSDT"
]


class P3CostBenchmarkRunner:
    """
    Orchestrates execution of P3-1 cost intelligence experiments.
    Strictly point-in-time and zero-lookahead.
    """

    def __init__(
        self,
        data_dir: str = "data",
        symbols: List[str] = UNIVERSE_SYMBOLS,
        sample_bars: int = 12000,
        n_splits: int = 5,
        embargo_pct: float = 0.01,
        results_dir: str = "results/cost",
        artifacts_dir: str = "artifacts/cost"
    ):
        self.data_dir = data_dir
        self.symbols = symbols
        self.sample_bars = sample_bars
        self.n_splits = n_splits
        self.embargo_pct = embargo_pct
        self.results_dir = results_dir
        self.artifacts_dir = artifacts_dir
        self.pipeline = TechnicalFeaturePipeline()

        os.makedirs(self.results_dir, exist_ok=True)
        os.makedirs(self.artifacts_dir, exist_ok=True)

    def load_universe_panel(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, pd.DataFrame]]:
        """
        Loads and aligns OHLCV data across the 13-asset universe.
        Returns:
            prices_df (close), high_df, low_df, quote_vol_df, asset_features_dict
        """
        logger.info(f"Loading OHLCV data for {len(self.symbols)} universe assets...")
        asset_dfs: Dict[str, pd.DataFrame] = {}
        close_dict: Dict[str, pd.Series] = {}
        high_dict: Dict[str, pd.Series] = {}
        low_dict: Dict[str, pd.Series] = {}
        qv_dict: Dict[str, pd.Series] = {}

        for sym in self.symbols:
            csv_path = os.path.join(self.data_dir, f"{sym}_1h_historical.csv")
            if not os.path.exists(csv_path):
                logger.warning(f"File missing for {sym}: {csv_path}")
                continue

            df = pd.read_csv(csv_path)
            ts_col = 'timestamp' if 'timestamp' in df.columns else df.columns[0]
            df['timestamp'] = pd.to_datetime(df[ts_col], utc=True, format='mixed')
            df = df.sort_values('timestamp').tail(self.sample_bars).reset_index(drop=True)

            features = self.pipeline.transform(df, dropna=False)

            # Target: forward 4h return > +0.2%
            forward_ret = (df['close'].shift(-4) - df['close']) / df['close']
            df['target'] = (forward_ret > 0.002).astype(int)

            if 'quote_asset_volume' in df.columns:
                df['quote_volume'] = df['quote_asset_volume']
            elif 'volume' in df.columns:
                df['quote_volume'] = df['volume'] * df['close']
            else:
                df['quote_volume'] = 50_000_000.0

            full_df = pd.concat([df[['timestamp', 'open', 'high', 'low', 'close', 'quote_volume', 'target']], features], axis=1)
            full_df = full_df.dropna().reset_index(drop=True).set_index('timestamp')

            asset_dfs[sym] = full_df
            close_dict[sym] = full_df['close']
            high_dict[sym] = full_df['high']
            low_dict[sym] = full_df['low']
            qv_dict[sym] = full_df['quote_volume']

        prices_df = pd.DataFrame(close_dict).dropna().sort_index()
        high_df = pd.DataFrame(high_dict).reindex(prices_df.index).ffill()
        low_df = pd.DataFrame(low_dict).reindex(prices_df.index).ffill()
        qv_df = pd.DataFrame(qv_dict).reindex(prices_df.index).ffill()

        logger.info(f"Loaded panel: {len(prices_df)} timestamps across {len(prices_df.columns)} assets.")
        return prices_df, high_df, low_df, qv_df, asset_dfs

    def generate_wfo_predictions(
        self,
        prices_df: pd.DataFrame,
        asset_dfs: Dict[str, pd.DataFrame]
    ) -> List[Tuple[int, pd.DataFrame, pd.DataFrame, List[pd.Timestamp]]]:
        """
        Executes 5-fold purged walk-forward model training and generates OOS prediction probabilities.
        Returns list of (fold_id, test_prices, weights_lo_df, valid_test_timestamps).
        """
        dummy_df = pd.DataFrame(index=prices_df.index)
        splits = TemporalSplitter.purged_walk_forward_split(dummy_df, n_splits=self.n_splits, embargo_pct=self.embargo_pct)

        wfo_folds = []

        for train_slice, test_slice, meta in splits:
            fold_id = meta["fold"]
            train_idx = train_slice.index
            test_idx = test_slice.index

            asset_models: Dict[str, Tuple[LGBMClassifier, StandardScaler, List[str]]] = {}
            for sym, df_asset in asset_dfs.items():
                train_sub = df_asset.reindex(train_idx).dropna()
                if len(train_sub) < 100:
                    continue

                feature_cols = [c for c in train_sub.columns if c not in ['open', 'high', 'low', 'close', 'quote_volume', 'target']]
                X_tr = train_sub[feature_cols].values
                y_tr = train_sub['target'].values

                scaler = StandardScaler()
                X_tr_scaled = scaler.fit_transform(X_tr)

                model = LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=42 + fold_id, verbose=-1)
                model.fit(X_tr_scaled, y_tr)

                asset_models[sym] = (model, scaler, feature_cols)

            weights_lo_list = []
            valid_test_timestamps = []

            for t_stamp in test_idx:
                preds_t: Dict[str, float] = {}
                for sym, (model, scaler, feature_cols) in asset_models.items():
                    if t_stamp in asset_dfs[sym].index:
                        row = asset_dfs[sym].loc[t_stamp]
                        feat_vals = row[feature_cols].values.reshape(1, -1)
                        if not np.isnan(feat_vals).any():
                            feat_scaled = scaler.transform(feat_vals)
                            prob_up = model.predict_proba(feat_scaled)[0, 1]
                            preds_t[sym] = float(prob_up)

                if len(preds_t) >= 4:
                    w_lo = CrossSectionalRanker.rank_assets(preds_t, top_n=2, bottom_n=2, allow_short=False)
                    weights_lo_list.append(w_lo)
                    valid_test_timestamps.append(t_stamp)

            weights_lo_df = pd.DataFrame(weights_lo_list, index=valid_test_timestamps)
            test_prices = prices_df.reindex(valid_test_timestamps)

            wfo_folds.append((fold_id, test_prices, weights_lo_df, valid_test_timestamps))

        return wfo_folds

    def evaluate_portfolio_under_cost_model(
        self,
        test_prices: pd.DataFrame,
        weights_df: pd.DataFrame,
        high_df: pd.DataFrame,
        low_df: pd.DataFrame,
        qv_df: pd.DataFrame,
        cost_engine: TransactionCostEngine,
        rebalance_interval_bars: int = 48
    ) -> Dict[str, Any]:
        """
        Simulates portfolio returns with rebalance cadence and realistic execution costs.
        """
        # 1. Apply rebalance cadence
        sched_weights = weights_df.copy()
        if rebalance_interval_bars > 1:
            for i in range(len(sched_weights)):
                if i % rebalance_interval_bars != 0:
                    sched_weights.iloc[i] = sched_weights.iloc[i - 1]

        common_idx = test_prices.index.intersection(sched_weights.index)
        aligned_prices = test_prices.loc[common_idx].sort_index()
        aligned_weights = sched_weights.loc[common_idx].sort_index()

        symbols = [s for s in aligned_prices.columns if s in aligned_weights.columns]
        p_mat = aligned_prices[symbols].values
        w_mat = aligned_weights[symbols].values
        n_bars, n_symbols = p_mat.shape

        # 2. Compute dynamic execution costs
        step_costs_pct, trade_logs = cost_engine.compute_portfolio_rebalance_costs(
            prices_df=aligned_prices,
            weights_df=aligned_weights,
            high_df=high_df,
            low_df=low_df,
            quote_volume_df=qv_df,
            portfolio_capital=10_000.0
        )

        # 3. Simulate step returns
        gross_step_returns = []
        net_step_returns = []
        turnover_list = []
        current_weights = np.zeros(n_symbols)

        for t in range(n_bars - 1):
            target_w = w_mat[t]
            p_now = p_mat[t]
            p_next = p_mat[t + 1]

            delta_w = target_w - current_weights
            bar_turnover = float(np.sum(np.abs(delta_w)))
            turnover_list.append(bar_turnover)

            with np.errstate(divide='ignore', invalid='ignore'):
                asset_rets = np.where(p_now > 0, (p_next - p_now) / p_now, 0.0)
                asset_rets = np.nan_to_num(asset_rets, nan=0.0)

            gross_bar_ret = float(np.sum(current_weights * asset_rets))
            cost_bar_ret = float(step_costs_pct[t])
            net_bar_ret = gross_bar_ret - cost_bar_ret

            gross_step_returns.append(gross_bar_ret)
            net_step_returns.append(net_bar_ret)
            current_weights = target_w.copy()

        gross_arr = np.array(gross_step_returns)
        net_arr = np.array(net_step_returns)
        costs_arr = np.array(step_costs_pct[:len(gross_arr)])
        turnover_arr = np.array(turnover_list)

        # Calculate metrics
        cum_gross = np.prod(1.0 + gross_arr) - 1.0 if len(gross_arr) > 0 else 0.0
        cum_net = np.prod(1.0 + net_arr) - 1.0 if len(net_arr) > 0 else 0.0
        total_costs_pct = float(np.sum(costs_arr))

        # Sharpe & Sortino (annualized 8760 hours)
        gross_mean, gross_std = np.mean(gross_arr), np.std(gross_arr)
        net_mean, net_std = np.mean(net_arr), np.std(net_arr)

        gross_sharpe = float((gross_mean / gross_std) * np.sqrt(8760)) if gross_std > 1e-8 else 0.0
        net_sharpe = float((net_mean / net_std) * np.sqrt(8760)) if net_std > 1e-8 else 0.0

        downside_diff = np.minimum(net_arr, 0.0)
        downside_std = np.std(downside_diff)
        net_sortino = float((net_mean / downside_std) * np.sqrt(8760)) if downside_std > 1e-8 else 0.0

        # Drawdown
        cum_curve = np.cumprod(1.0 + net_arr)
        running_max = np.maximum.accumulate(cum_curve)
        drawdowns = (cum_curve - running_max) / running_max
        max_dd = float(np.abs(np.min(drawdowns))) if len(drawdowns) > 0 else 0.0

        # Cost decomposition
        tot_fee = sum(t.fee_dollars for t in trade_logs)
        tot_spread = sum(t.spread_dollars for t in trade_logs)
        tot_slip = sum(t.slippage_dollars for t in trade_logs)
        tot_impact = sum(t.impact_dollars for t in trade_logs)
        tot_delay = sum(t.delay_dollars for t in trade_logs)
        tot_dollars = sum(t.total_cost_dollars for t in trade_logs)

        total_notional = sum(t.notional for t in trade_logs)
        avg_cost_bps = (tot_dollars / total_notional * 10000.0) if total_notional > 0 else 0.0

        return {
            "gross_return_pct": round(cum_gross * 100.0, 2),
            "net_return_pct": round(cum_net * 100.0, 2),
            "total_costs_pct": round(total_costs_pct * 100.0, 2),
            "gross_sharpe": round(gross_sharpe, 2),
            "net_sharpe": round(net_sharpe, 2),
            "net_sortino": round(net_sortino, 2),
            "max_drawdown": round(max_dd, 4),
            "total_turnover": round(float(np.sum(turnover_arr)), 2),
            "trades_count": len(trade_logs),
            "avg_cost_bps": round(avg_cost_bps, 2),
            "cost_dollars": {
                "total": round(tot_dollars, 2),
                "fee": round(tot_fee, 2),
                "spread": round(tot_spread, 2),
                "slippage": round(tot_slip, 2),
                "impact": round(tot_impact, 2),
                "delay": round(tot_delay, 2)
            },
            "cost_contribution_pct": {
                "fee": round(tot_fee / max(1e-5, tot_dollars) * 100.0, 1),
                "spread": round(tot_spread / max(1e-5, tot_dollars) * 100.0, 1),
                "slippage": round(tot_slip / max(1e-5, tot_dollars) * 100.0, 1),
                "impact": round(tot_impact / max(1e-5, tot_dollars) * 100.0, 1),
                "delay": round(tot_delay / max(1e-5, tot_dollars) * 100.0, 1)
            },
            "trade_logs": trade_logs
        }

    def run_all_experiments(self) -> Dict[str, Any]:
        """
        Executes EXP-P3-01-COST-001 through 007.
        """
        prices_df, high_df, low_df, qv_df, asset_dfs = self.load_universe_panel()
        wfo_folds = self.generate_wfo_predictions(prices_df, asset_dfs)

        all_results = {}

        # -------------------------------------------------------------
        # EXP-P3-01-COST-001 through 005: Model Comparison & Scenarios
        # -------------------------------------------------------------
        profiles_to_test = [
            ("EXP-P3-01-COST-001", CostModelProfile.FIXED_12BPS, "Fixed 12 bps Baseline"),
            ("EXP-P3-01-COST-002", CostModelProfile.SPREAD_FEE, "Spread + Fee Model"),
            ("EXP-P3-01-COST-003", CostModelProfile.SPREAD_SLIPPAGE_FEE, "Spread + Slippage + Fee Model"),
            ("EXP-P3-01-COST-004", CostModelProfile.ADVANCED_BASE, "Full Advanced Base Model"),
            ("EXP-P3-01-COST-005_OPT", CostModelProfile.ADVANCED_OPTIMISTIC, "Advanced Optimistic Scenario"),
            ("EXP-P3-01-COST-005_CON", CostModelProfile.ADVANCED_CONSERVATIVE, "Advanced Conservative Scenario"),
            ("EXP-P3-01-COST-005_STR", CostModelProfile.ADVANCED_STRESSED, "Advanced Stressed Scenario"),
        ]

        comparison_records = []

        for exp_id, profile, desc in profiles_to_test:
            logger.info(f"Running {exp_id}: {desc}...")
            cfg = SCENARIO_CONFIGS[profile]
            engine = TransactionCostEngine(cfg)

            fold_summaries = []
            all_exp_trades: List[TradeCostBreakdown] = []

            for fold_id, test_prices, weights_lo_df, _ in wfo_folds:
                eval_res = self.evaluate_portfolio_under_cost_model(
                    test_prices, weights_lo_df, high_df, low_df, qv_df, engine, rebalance_interval_bars=48
                )
                eval_res["fold"] = fold_id
                all_exp_trades.extend(eval_res.pop("trade_logs"))
                fold_summaries.append(eval_res)

            # Aggregate WFO metrics
            avg_gross = np.mean([f["gross_return_pct"] for f in fold_summaries])
            avg_net = np.mean([f["net_return_pct"] for f in fold_summaries])
            avg_sharpe = np.mean([f["net_sharpe"] for f in fold_summaries])
            avg_max_dd = np.mean([f["max_drawdown"] for f in fold_summaries])
            avg_cost_bps = np.mean([f["avg_cost_bps"] for f in fold_summaries])
            total_turnover = np.sum([f["total_turnover"] for f in fold_summaries])

            rec = {
                "experiment_id": exp_id,
                "profile": profile.value,
                "description": desc,
                "avg_gross_return_pct": round(float(avg_gross), 2),
                "avg_net_return_pct": round(float(avg_net), 2),
                "avg_net_sharpe": round(float(avg_sharpe), 2),
                "avg_max_drawdown": round(float(avg_max_dd), 4),
                "avg_cost_bps": round(float(avg_cost_bps), 2),
                "total_turnover": round(float(total_turnover), 2),
                "folds": fold_summaries
            }
            comparison_records.append(rec)
            all_results[exp_id] = rec

            # Persist experiment artifact
            exp_dir = os.path.join(self.artifacts_dir, exp_id)
            os.makedirs(exp_dir, exist_ok=True)
            with open(os.path.join(exp_dir, "summary.json"), "w") as f:
                json.dump(rec, f, indent=2)

        # -------------------------------------------------------------
        # EXP-P3-01-COST-006: Asset-Level Cost Sensitivity (13 Assets)
        # -------------------------------------------------------------
        logger.info("Running EXP-P3-01-COST-006: Asset-Level Cost Attribution...")
        base_engine = TransactionCostEngine(SCENARIO_CONFIGS[CostModelProfile.ADVANCED_BASE])
        asset_trades: Dict[str, List[TradeCostBreakdown]] = {s: [] for s in self.symbols}

        for _, test_prices, weights_lo_df, _ in wfo_folds:
            res = self.evaluate_portfolio_under_cost_model(
                test_prices, weights_lo_df, high_df, low_df, qv_df, base_engine, rebalance_interval_bars=48
            )
            for tb in res["trade_logs"]:
                if tb.symbol in asset_trades:
                    asset_trades[tb.symbol].append(tb)

        asset_cost_records = []
        for sym, tbs in asset_trades.items():
            if tbs:
                bps_list = [t.total_cost_bps for t in tbs]
                dols_list = [t.total_cost_dollars for t in tbs]
                asset_cost_records.append({
                    "symbol": sym,
                    "trade_count": len(tbs),
                    "avg_cost_bps": round(float(np.mean(bps_list)), 2),
                    "median_cost_bps": round(float(np.median(bps_list)), 2),
                    "p95_cost_bps": round(float(np.percentile(bps_list, 95)), 2),
                    "max_cost_bps": round(float(np.max(bps_list)), 2),
                    "total_cost_dollars": round(float(np.sum(dols_list)), 2),
                    "liquidity_tier": tbs[0].liquidity_tier.value
                })
            else:
                asset_cost_records.append({
                    "symbol": sym,
                    "trade_count": 0,
                    "avg_cost_bps": 0.0,
                    "median_cost_bps": 0.0,
                    "p95_cost_bps": 0.0,
                    "max_cost_bps": 0.0,
                    "total_cost_dollars": 0.0,
                    "liquidity_tier": "UNKNOWN"
                })

        asset_cost_records.sort(key=lambda x: x["avg_cost_bps"], reverse=True)
        all_results["EXP-P3-01-COST-006"] = asset_cost_records

        # -------------------------------------------------------------
        # EXP-P3-01-COST-007: Rebalance Cadence Interaction (18H, 24H, 36H, 48H)
        # -------------------------------------------------------------
        logger.info("Running EXP-P3-01-COST-007: Rebalance Cadence Comparison...")
        cadences = [18, 24, 36, 48]
        cadence_records = []

        for cad in cadences:
            fold_res = []
            for fold_id, test_prices, weights_lo_df, _ in wfo_folds:
                eval_res = self.evaluate_portfolio_under_cost_model(
                    test_prices, weights_lo_df, high_df, low_df, qv_df, base_engine, rebalance_interval_bars=cad
                )
                eval_res.pop("trade_logs")
                fold_res.append(eval_res)

            avg_g = np.mean([f["gross_return_pct"] for f in fold_res])
            avg_n = np.mean([f["net_return_pct"] for f in fold_res])
            avg_sh = np.mean([f["net_sharpe"] for f in fold_res])
            avg_dd = np.mean([f["max_drawdown"] for f in fold_res])
            tot_to = np.sum([f["total_turnover"] for f in fold_res])
            avg_cb = np.mean([f["avg_cost_bps"] for f in fold_res])

            cadence_records.append({
                "cadence_hours": cad,
                "gross_return_pct": round(float(avg_g), 2),
                "net_return_pct": round(float(avg_n), 2),
                "net_sharpe": round(float(avg_sh), 2),
                "max_drawdown": round(float(avg_dd), 4),
                "total_turnover": round(float(tot_to), 2),
                "avg_cost_bps": round(float(avg_cb), 2)
            })

        all_results["EXP-P3-01-COST-007"] = cadence_records

        # -------------------------------------------------------------
        # Regime-Level Cost Analysis (Bull, Sideways, Bear)
        # -------------------------------------------------------------
        logger.info("Computing BTC Regime Cost Attribution...")
        btc_prices = prices_df["BTCUSDT"]
        btc_20d_ret = btc_prices.pct_change(20 * 24).fillna(0.0)

        regime_trades: Dict[str, List[float]] = {"BULL": [], "SIDEWAYS": [], "BEAR": []}
        for tbs in asset_trades.values():
            for t in tbs:
                ts = pd.Timestamp(t.timestamp)
                if ts in btc_20d_ret.index:
                    r20 = btc_20d_ret.loc[ts]
                    if r20 > 0.05:
                        regime_trades["BULL"].append(t.total_cost_bps)
                    elif r20 < -0.05:
                        regime_trades["BEAR"].append(t.total_cost_bps)
                    else:
                        regime_trades["SIDEWAYS"].append(t.total_cost_bps)

        regime_records = {}
        for reg, bpss in regime_trades.items():
            if bpss:
                regime_records[reg] = {
                    "avg_cost_bps": round(float(np.mean(bpss)), 2),
                    "median_cost_bps": round(float(np.median(bpss)), 2),
                    "p95_cost_bps": round(float(np.percentile(bpss, 95)), 2),
                    "trade_count": len(bpss)
                }

        all_results["regime_costs"] = regime_records

        # -------------------------------------------------------------
        # Break-Even Cost Analysis
        # -------------------------------------------------------------
        # Calculate break-even cost C* in bps where Net Sharpe = 0
        fixed_rec = all_results["EXP-P3-01-COST-001"]
        gross_ret = fixed_rec["avg_gross_return_pct"]
        tot_turnover = fixed_rec["total_turnover"]
        # Break-even bps per unit turnover
        be_bps = (gross_ret / max(1.0, tot_turnover)) * 100.0 if tot_turnover > 0 else 0.0

        all_results["break_even"] = {
            "break_even_cost_bps": round(float(be_bps), 2),
            "base_cost_bps": all_results["EXP-P3-01-COST-004"]["avg_cost_bps"],
            "margin_of_safety_bps": round(float(be_bps - all_results["EXP-P3-01-COST-004"]["avg_cost_bps"]), 2)
        }

        # -------------------------------------------------------------
        # Save JSON Summaries to results/cost/
        # -------------------------------------------------------------
        with open(os.path.join(self.results_dir, "p3_1_cost_comparison.json"), "w") as f:
            json.dump(comparison_records, f, indent=2)

        with open(os.path.join(self.results_dir, "p3_1_asset_costs.json"), "w") as f:
            json.dump(asset_cost_records, f, indent=2)

        with open(os.path.join(self.results_dir, "p3_1_regime_costs.json"), "w") as f:
            json.dump(regime_records, f, indent=2)

        with open(os.path.join(self.results_dir, "p3_1_sensitivity.json"), "w") as f:
            json.dump(cadence_records, f, indent=2)

        with open(os.path.join(self.results_dir, "p3_1_break_even.json"), "w") as f:
            json.dump(all_results["break_even"], f, indent=2)

        logger.info("All P3-1 experiments successfully completed & artifacts saved!")
        return all_results


if __name__ == "__main__":
    runner = P3CostBenchmarkRunner()
    results = runner.run_all_experiments()
    print("\n================ P3-1 BENCHMARK SUMMARY ================")
    for rec in results.get("EXP-P3-01-COST-001", {}):
        pass

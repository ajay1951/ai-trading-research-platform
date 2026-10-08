"""
Volatility-Aware Position Sizing Engine (P1-3)
==============================================
Provides strictly causal point-in-time volatility estimation and position sizing:
1. Rolling Realized Volatility: window=168 hours (7 days), annualized via sqrt(24 * 365).
2. Inverse Volatility Weighting (EXP-CS-P13-IV): w_i = (1/sigma_i) / sum(1/sigma_j).
3. Volatility-Capped Sizing (EXP-CS-P13-IV-CAP): clips inverse volatility weights to [25%, 75%].
4. Strict causal integrity: historical volatility uses only information available at or before timestamp t.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple


class VolatilitySizingEngine:
    @staticmethod
    def compute_historical_volatility(
        prices_df: pd.DataFrame,
        window: int = 168,
        min_periods: int = 24
    ) -> pd.DataFrame:
        """
        Computes point-in-time rolling realized volatility on historical log returns.

        :param prices_df: DataFrame of historical close prices indexed by timestamp.
        :param window: Rolling lookback window in bars (default 168 bars = 7 days).
        :param min_periods: Minimum required bars to produce valid volatility.
        :return: DataFrame of annualized volatilities strictly aligned to timestamps.
        """
        log_ret = np.log(prices_df / prices_df.shift(1))
        rolling_std = log_ret.rolling(window=window, min_periods=min_periods).std()
        ann_vol = rolling_std * np.sqrt(24.0 * 365.0)
        return ann_vol

    @staticmethod
    def size_portfolio(
        weights_df: pd.DataFrame,
        volatility_df: pd.DataFrame,
        mode: str = "equal",
        min_weight_cap: float = 0.25,
        max_weight_cap: float = 0.75,
        eps: float = 1e-6
    ) -> pd.DataFrame:
        """
        Applies volatility-aware sizing to already-selected Top-N assets without modifying rankings.

        :param weights_df: Input un-sized target weights (e.g. equal weights 50%/50%).
        :param volatility_df: Historical realized volatility panel aligned to weights_df.
        :param mode: 'equal', 'inverse_vol', or 'iv_capped'.
        :param min_weight_cap: Minimum allowed asset weight for iv_capped (default 0.25).
        :param max_weight_cap: Maximum allowed asset weight for iv_capped (default 0.75).
        :param eps: Epsilon to prevent zero division.
        :return: Sized weights DataFrame with sum(weights) == 1.0 across active assets.
        """
        if mode == "equal":
            return weights_df.copy()

        aligned_vol = volatility_df.reindex(weights_df.index).ffill()
        w_values = weights_df.values
        v_values = aligned_vol.values
        out_values = np.zeros_like(w_values, dtype=float)

        n_rows, n_cols = w_values.shape
        for r in range(n_rows):
            row_w = w_values[r]
            active_indices = np.where(row_w > 0)[0]
            n_active = len(active_indices)
            if n_active == 0:
                continue
            if n_active == 1:
                out_values[r, active_indices[0]] = 1.0
                continue

            row_v = v_values[r]
            vols = row_v[active_indices]
            if np.isnan(vols).any() or np.isinf(vols).any() or (vols <= eps).any():
                out_values[r, active_indices] = 1.0 / n_active
                continue

            raw_inv = 1.0 / (vols + eps)
            sum_inv = np.sum(raw_inv)
            if sum_inv <= eps:
                out_values[r, active_indices] = 1.0 / n_active
                continue

            norm_w = raw_inv / sum_inv
            if mode == "inverse_vol":
                out_values[r, active_indices] = norm_w
            elif mode == "iv_capped":
                if n_active == 2:
                    w0 = np.clip(norm_w[0], min_weight_cap, max_weight_cap)
                    w1 = 1.0 - w0
                    out_values[r, active_indices[0]] = w0
                    out_values[r, active_indices[1]] = w1
                else:
                    clipped = np.clip(norm_w, min_weight_cap, max_weight_cap)
                    sum_clip = np.sum(clipped)
                    out_values[r, active_indices] = clipped / sum_clip
            else:
                raise ValueError(f"Unknown sizing mode: {mode}")

        return pd.DataFrame(out_values, index=weights_df.index, columns=weights_df.columns)

    @staticmethod
    def compute_cap_diagnostics(
        weights_df: pd.DataFrame,
        volatility_df: pd.DataFrame,
        min_weight_cap: float = 0.25,
        max_weight_cap: float = 0.75,
        eps: float = 1e-6
    ) -> Dict[str, Any]:
        """
        Computes granular cap-activation statistics and diagnostics comparing raw IV vs final capped weights.
        """
        aligned_vol = volatility_df.reindex(weights_df.index).ffill()
        decision_records = []

        total_rebalances = 0
        cap_activations = 0
        upper_hits = 0
        lower_hits = 0

        max_raw_weight = 0.0
        min_raw_weight = 1.0
        max_final_weight = 0.0
        min_final_weight = 1.0

        for t_stamp in weights_df.index:
            row_w = weights_df.loc[t_stamp]
            active_assets = row_w[row_w > 0].index.tolist()

            if len(active_assets) != 2:
                continue

            total_rebalances += 1
            row_v = aligned_vol.loc[t_stamp]
            vols = {sym: float(row_v.get(sym, np.nan)) for sym in active_assets}

            if any(pd.isna(v) or v <= eps or np.isinf(v) for v in vols.values()):
                # Fallback equal weights
                raw_w = {sym: 0.50 for sym in active_assets}
                capped_w = {sym: 0.50 for sym in active_assets}
                decision_records.append({
                    "timestamp": str(t_stamp),
                    "assets": active_assets,
                    "volatilities": vols,
                    "raw_weights": raw_w,
                    "capped_weights": capped_w,
                    "cap_active": False,
                    "cap_type": "None (Fallback EQ)"
                })
                continue

            raw_inv = {sym: 1.0 / (vols[sym] + eps) for sym in active_assets}
            sum_inv = sum(raw_inv.values())
            raw_w = {sym: raw_inv[sym] / sum_inv for sym in active_assets}

            sym_a, sym_b = active_assets[0], active_assets[1]
            w_a_raw = raw_w[sym_a]
            w_b_raw = raw_w[sym_b]

            max_raw_weight = max(max_raw_weight, w_a_raw, w_b_raw)
            min_raw_weight = min(min_raw_weight, w_a_raw, w_b_raw)

            # Check if cap bound is hit
            is_active = False
            cap_type = "None"

            if w_a_raw > max_weight_cap + 1e-5 or w_b_raw > max_weight_cap + 1e-5:
                is_active = True
                cap_activations += 1
                upper_hits += 1
                lower_hits += 1
                cap_type = "Binding (Upper/Lower Cap Triggered)"

            w_a_capped = float(np.clip(w_a_raw, min_weight_cap, max_weight_cap))
            w_b_capped = float(1.0 - w_a_capped)

            max_final_weight = max(max_final_weight, w_a_capped, w_b_capped)
            min_final_weight = min(min_final_weight, w_a_capped, w_b_capped)

            decision_records.append({
                "timestamp": str(t_stamp),
                "assets": active_assets,
                "volatilities": {k: round(v, 4) for k, v in vols.items()},
                "raw_weights": {k: round(v, 4) for k, v in raw_w.items()},
                "capped_weights": {sym_a: round(w_a_capped, 4), sym_b: round(w_b_capped, 4)},
                "cap_lower_bound": min_weight_cap,
                "cap_upper_bound": max_weight_cap,
                "cap_active": is_active,
                "cap_type": cap_type
            })

        act_rate = (cap_activations / max(1, total_rebalances)) * 100.0

        return {
            "total_rebalance_events": total_rebalances,
            "cap_activation_count": cap_activations,
            "cap_activation_rate_pct": round(act_rate, 2),
            "upper_cap_hits": upper_hits,
            "lower_cap_hits": lower_hits,
            "max_raw_weight_pct": round(max_raw_weight * 100.0, 2),
            "min_raw_weight_pct": round(min_raw_weight * 100.0, 2),
            "max_final_weight_pct": round(max_final_weight * 100.0, 2),
            "min_final_weight_pct": round(min_final_weight * 100.0, 2),
            "is_cap_binding": (cap_activations > 0),
            "diagnostics_sample": decision_records[:10],
            "all_decisions": decision_records
        }

    @staticmethod
    def compute_risk_contributions(
        returns_df: pd.DataFrame,
        weights_df: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Calculates component risk contributions (percentage of portfolio variance) for each asset.
        """
        aligned_w = weights_df.reindex(returns_df.index).ffill().fillna(0.0)
        mean_weights = aligned_w.mean()
        active_assets = mean_weights[mean_weights > 0.001].index.tolist()

        if len(active_assets) == 0:
            return {}

        cov_matrix = returns_df[active_assets].cov() * 8760.0 # annualized
        w_vec = mean_weights[active_assets].values

        port_var = float(w_vec @ cov_matrix.values @ w_vec)
        port_vol = np.sqrt(max(port_var, 1e-9))

        if port_vol <= 1e-6:
            return {}

        marginal_contrib = (cov_matrix.values @ w_vec) / port_vol
        component_contrib = w_vec * marginal_contrib
        pct_contrib = (component_contrib / port_vol) * 100.0

        results = {}
        for idx, sym in enumerate(active_assets):
            results[sym] = {
                "mean_weight_pct": round(float(w_vec[idx] * 100.0), 2),
                "marginal_risk_contrib": round(float(marginal_contrib[idx]), 4),
                "percentage_risk_contrib": round(float(pct_contrib[idx]), 2)
            }

        return {
            "portfolio_annualized_volatility": round(float(port_vol * 100.0), 2),
            "asset_risk_contributions": results
        }

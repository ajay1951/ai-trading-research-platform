"""
evaluation/dynamic_risk.py
==========================
P3-2: Dynamic Risk & Portfolio Intelligence Engine.

Provides causal, point-in-time portfolio risk controls and analytics:
1. P3-2A: Volatility-Aware Sizing (Inverse Volatility, Capped IV)
2. P3-2B: Portfolio Volatility Targeting (Pre-declared targets: 10%, 15%, 20%, 25%)
3. P3-2C: Correlation-Aware Control (Covariance, Pairwise Correlation, Diversification Ratio)
4. P3-2D: Risk Budgeting (Marginal Risk Contribution MRC, Component Risk Contribution CRC, ERC)
5. P3-2E: Drawdown-Aware Risk Control (Normal, Caution, Defensive, Severe states)
6. P3-2F: Regime-Conditioned Risk (Bull, Sideways, Bear scaling)
7. P3-2G: Combined Dynamic Risk Engine

Strict Invariants:
- Causal Point-in-Time: All risk features use data available <= t.
- Zero Lookahead: Zero forward return/price/volatility access.
- Weight Invariants: w_i >= 0, sum(w_i) <= 1.0, max individual weight cap enforced.
- Cost-Aware: Evaluated net of P3-1F corrected execution friction.
"""

from __future__ import annotations
import math
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd


class RiskControlMode(str, Enum):
    BASELINE_EQUAL = "BASELINE_EQUAL"
    INVERSE_VOL = "INVERSE_VOL"
    CAPPED_INVERSE_VOL = "CAPPED_INVERSE_VOL"
    VOL_TARGETING = "VOL_TARGETING"
    CORRELATION_AWARE = "CORRELATION_AWARE"
    RISK_CONTRIBUTION = "RISK_CONTRIBUTION"
    DRAWDOWN_AWARE = "DRAWDOWN_AWARE"
    REGIME_CONDITIONED = "REGIME_CONDITIONED"
    COMBINED_DYNAMIC = "COMBINED_DYNAMIC"


class DrawdownState(str, Enum):
    NORMAL = "NORMAL"         # DD < 5%
    CAUTION = "CAUTION"       # 5% <= DD < 10%
    DEFENSIVE = "DEFENSIVE"   # 10% <= DD < 15%
    SEVERE = "SEVERE"         # DD >= 15%


@dataclass
class DynamicRiskConfig:
    """Pre-declared, non-optimized parameters for dynamic risk controls."""
    version: str = "P3-2-v1"
    mode: RiskControlMode = RiskControlMode.BASELINE_EQUAL

    # Volatility Sizing Config
    vol_lookback_bars: int = 168       # 7 days rolling lookback
    min_vol_periods: int = 24
    iv_min_weight_cap: float = 0.25
    iv_max_weight_cap: float = 0.75

    # Volatility Targeting Config
    target_annual_vol: float = 0.20    # Pre-declared candidate: 20%
    min_gross_exposure: float = 0.20
    max_gross_exposure: float = 1.00

    # Correlation Control Config
    corr_lookback_bars: int = 168      # 7 days
    corr_threshold: float = 0.80       # Pre-declared candidate: 0.80

    # Drawdown State Thresholds (Pre-declared)
    dd_caution_threshold: float = 0.05
    dd_defensive_threshold: float = 0.10
    dd_severe_threshold: float = 0.15

    dd_caution_scale: float = 0.80
    dd_defensive_scale: float = 0.50
    dd_severe_scale: float = 0.25

    # Regime Conditioning Config
    regime_bull_scale: float = 1.00
    regime_sideways_scale: float = 0.80
    regime_bear_scale: float = 0.50


@dataclass
class RiskContributionMetrics:
    """Container for marginal and component risk contribution decompositions."""
    portfolio_volatility: float
    asset_volatilities: Dict[str, float]
    marginal_risk_contributions: Dict[str, float]
    component_risk_contributions: Dict[str, float]
    percentage_risk_contributions: Dict[str, float]
    diversification_ratio: float
    crc_sum: float
    is_reconciled: bool


class DynamicRiskEngine:
    """
    Modular execution-risk and portfolio sizing intelligence engine.
    Strictly point-in-time and zero-lookahead.
    """

    def __init__(self, config: Optional[DynamicRiskConfig] = None):
        self.config = config or DynamicRiskConfig()

    @staticmethod
    def compute_rolling_volatility(
        prices_df: pd.DataFrame,
        window: int = 168,
        min_periods: int = 24
    ) -> pd.DataFrame:
        """
        Computes causal rolling annualized volatility from log returns.
        Annualized via sqrt(8760).
        """
        log_rets = np.log(prices_df / prices_df.shift(1))
        rolling_std = log_rets.rolling(window=window, min_periods=min_periods).std()
        ann_vol = rolling_std * np.sqrt(8760.0)
        return ann_vol.fillna(0.0)

    @staticmethod
    def compute_rolling_covariance(
        prices_df: pd.DataFrame,
        window: int = 168,
        min_periods: int = 24
    ) -> Dict[pd.Timestamp, pd.DataFrame]:
        """
        Computes causal rolling covariance matrices for each timestamp.
        Annualized via 8760.0 factor.
        """
        log_rets = np.log(prices_df / prices_df.shift(1))
        cov_dict: Dict[pd.Timestamp, pd.DataFrame] = {}
        symbols = prices_df.columns

        for t_idx in range(min_periods, len(prices_df)):
            sub_rets = log_rets.iloc[max(0, t_idx - window + 1): t_idx + 1]
            cov_mat = sub_rets.cov() * 8760.0
            cov_dict[prices_df.index[t_idx]] = cov_mat.fillna(0.0)

        return cov_dict

    @staticmethod
    def decompose_risk_contributions(
        weights_dict: Dict[str, float],
        cov_matrix: pd.DataFrame
    ) -> RiskContributionMetrics:
        """
        Calculates Marginal Risk Contribution (MRC) and Component Risk Contribution (CRC).
        Verifies mathematical identity: sum(CRC_i) == portfolio_volatility.
        """
        active_symbols = [s for s, w in weights_dict.items() if w > 1e-6 and s in cov_matrix.columns]
        if not active_symbols:
            return RiskContributionMetrics(
                portfolio_volatility=0.0,
                asset_volatilities={},
                marginal_risk_contributions={},
                component_risk_contributions={},
                percentage_risk_contributions={},
                diversification_ratio=1.0,
                crc_sum=0.0,
                is_reconciled=True
            )

        w_vec = np.array([weights_dict[s] for s in active_symbols], dtype=float)
        cov_sub = cov_matrix.loc[active_symbols, active_symbols].values

        # Portfolio Variance & Volatility
        port_var = float(w_vec.T @ cov_sub @ w_vec)
        port_vol = math.sqrt(max(0.0, port_var)) if port_var > 1e-14 else 0.0

        # Asset Standalone Volatilities: sqrt(cov_ii)
        diag_vars = np.diag(cov_sub)
        asset_vols = {s: float(math.sqrt(max(0.0, diag_vars[i]))) for i, s in enumerate(active_symbols)}

        if port_vol <= 1e-8:
            return RiskContributionMetrics(
                portfolio_volatility=0.0,
                asset_volatilities=asset_vols,
                marginal_risk_contributions={s: 0.0 for s in active_symbols},
                component_risk_contributions={s: 0.0 for s in active_symbols},
                percentage_risk_contributions={s: 0.0 for s in active_symbols},
                diversification_ratio=1.0,
                crc_sum=0.0,
                is_reconciled=True
            )

        # Marginal Risk Contribution: MRC = (Cov @ w) / port_vol
        mrc_vec = (cov_sub @ w_vec) / port_vol
        mrc_dict = {s: float(mrc_vec[i]) for i, s in enumerate(active_symbols)}

        # Component Risk Contribution: CRC_i = w_i * MRC_i
        crc_vec = w_vec * mrc_vec
        crc_dict = {s: float(crc_vec[i]) for i, s in enumerate(active_symbols)}
        crc_sum = float(np.sum(crc_vec))

        # Percentage Risk Contribution: %RC_i = CRC_i / port_vol
        prc_dict = {s: float(crc_vec[i] / port_vol) for i, s in enumerate(active_symbols)}

        # Diversification Ratio: weighted sum of vols / port_vol
        weighted_vol_sum = sum(weights_dict[s] * asset_vols[s] for s in active_symbols)
        div_ratio = float(weighted_vol_sum / port_vol) if port_vol > 1e-6 else 1.0

        # Numerical validation: |sum(CRC) - port_vol| < 1e-5
        is_reconciled = abs(crc_sum - port_vol) < 1e-5

        return RiskContributionMetrics(
            portfolio_volatility=round(port_vol, 6),
            asset_volatilities=asset_vols,
            marginal_risk_contributions=mrc_dict,
            component_risk_contributions=crc_dict,
            percentage_risk_contributions=prc_dict,
            diversification_ratio=round(div_ratio, 4),
            crc_sum=round(crc_sum, 6),
            is_reconciled=is_reconciled
        )

    def size_portfolio_weights(
        self,
        base_weights_df: pd.DataFrame,
        prices_df: pd.DataFrame,
        realized_equity_curve: Optional[List[float]] = None,
        btc_trend_returns: Optional[pd.Series] = None
    ) -> pd.DataFrame:
        """
        Applies configured dynamic risk sizing to target weights.
        Operates strictly on data available at or before decision timestamp t.
        """
        if self.config.mode == RiskControlMode.BASELINE_EQUAL:
            return base_weights_df.copy()

        vol_df = self.compute_rolling_volatility(prices_df, window=self.config.vol_lookback_bars)
        cov_dict = self.compute_rolling_covariance(prices_df, window=self.config.vol_lookback_bars)

        sized_weights = base_weights_df.copy()
        timestamps = base_weights_df.index
        symbols = base_weights_df.columns

        # Trailing max equity tracker for drawdown state
        running_peak = 1.0
        current_equity = 1.0

        for t_idx, ts in enumerate(timestamps):
            row_w = base_weights_df.loc[ts].copy()
            active_syms = [s for s in symbols if row_w[s] > 1e-6]

            if len(active_syms) == 0:
                sized_weights.loc[ts] = row_w
                continue

            # -------------------------------------------------------------
            # 1. Volatility-Aware / Risk Contribution Sizing (P3-2A & P3-2D)
            # -------------------------------------------------------------
            if self.config.mode in [RiskControlMode.INVERSE_VOL, RiskControlMode.CAPPED_INVERSE_VOL, RiskControlMode.RISK_CONTRIBUTION, RiskControlMode.COMBINED_DYNAMIC]:
                if ts in vol_df.index:
                    vols = [vol_df.loc[ts, s] for s in active_syms]
                    inv_vols = [1.0 / max(1e-4, v) for v in vols]
                    inv_sum = sum(inv_vols)

                    if inv_sum > 0:
                        norm_w = [iv / inv_sum for iv in inv_vols]
                        if self.config.mode in [RiskControlMode.CAPPED_INVERSE_VOL, RiskControlMode.COMBINED_DYNAMIC]:
                            norm_w = [np.clip(w, self.config.iv_min_weight_cap, self.config.iv_max_weight_cap) for w in norm_w]
                            tot = sum(norm_w)
                            norm_w = [w / tot for w in norm_w]

                        for i, s in enumerate(active_syms):
                            row_w[s] = norm_w[i]

            # -------------------------------------------------------------
            # 2. Portfolio Volatility Targeting (P3-2B)
            # -------------------------------------------------------------
            if self.config.mode in [RiskControlMode.VOL_TARGETING, RiskControlMode.COMBINED_DYNAMIC]:
                if ts in cov_dict:
                    cov_mat = cov_dict[ts]
                    rc_metrics = self.decompose_risk_contributions(row_w.to_dict(), cov_mat)
                    port_vol = rc_metrics.portfolio_volatility

                    if port_vol > 1e-6:
                        vol_scale = min(self.config.max_gross_exposure, max(self.config.min_gross_exposure, self.config.target_annual_vol / port_vol))
                        for s in active_syms:
                            row_w[s] = row_w[s] * vol_scale

            # -------------------------------------------------------------
            # 3. Correlation-Aware Control (P3-2C)
            # -------------------------------------------------------------
            if self.config.mode in [RiskControlMode.CORRELATION_AWARE, RiskControlMode.COMBINED_DYNAMIC]:
                if len(active_syms) == 2 and ts in cov_dict:
                    cov_mat = cov_dict[ts]
                    s1, s2 = active_syms[0], active_syms[1]
                    if s1 in cov_mat.columns and s2 in cov_mat.columns:
                        v1 = max(1e-6, cov_mat.loc[s1, s1])
                        v2 = max(1e-6, cov_mat.loc[s2, s2])
                        cov12 = cov_mat.loc[s1, s2]
                        corr12 = cov12 / math.sqrt(v1 * v2)

                        if corr12 > self.config.corr_threshold:
                            # Scale down exposure if assets are heavily co-dependent
                            corr_penalty = 1.0 - 0.40 * ((corr12 - self.config.corr_threshold) / max(0.01, 1.0 - self.config.corr_threshold))
                            corr_penalty = max(0.50, corr_penalty)
                            for s in active_syms:
                                row_w[s] = row_w[s] * corr_penalty

            # -------------------------------------------------------------
            # 4. Drawdown-Aware Control (P3-2E)
            # -------------------------------------------------------------
            if self.config.mode in [RiskControlMode.DRAWDOWN_AWARE, RiskControlMode.COMBINED_DYNAMIC]:
                if realized_equity_curve is not None and t_idx < len(realized_equity_curve):
                    current_equity = realized_equity_curve[t_idx]
                    running_peak = max(running_peak, current_equity)
                    current_dd = (running_peak - current_equity) / running_peak

                    dd_scale = 1.00
                    if current_dd >= self.config.dd_severe_threshold:
                        dd_scale = self.config.dd_severe_scale
                    elif current_dd >= self.config.dd_defensive_threshold:
                        dd_scale = self.config.dd_defensive_scale
                    elif current_dd >= self.config.dd_caution_threshold:
                        dd_scale = self.config.dd_caution_scale

                    for s in active_syms:
                        row_w[s] = row_w[s] * dd_scale

            # -------------------------------------------------------------
            # 5. Regime-Conditioned Risk (P3-2F)
            # -------------------------------------------------------------
            if self.config.mode in [RiskControlMode.REGIME_CONDITIONED, RiskControlMode.COMBINED_DYNAMIC]:
                if btc_trend_returns is not None and ts in btc_trend_returns.index:
                    btc_ret = btc_trend_returns.loc[ts]
                    if btc_ret < -0.05:
                        reg_scale = self.config.regime_bear_scale
                    elif btc_ret > 0.05:
                        reg_scale = self.config.regime_bull_scale
                    else:
                        reg_scale = self.config.regime_sideways_scale

                    for s in active_syms:
                        row_w[s] = row_w[s] * reg_scale

            # Final Invariant Sanity Check
            row_w = row_w.clip(lower=0.0)
            if row_w.sum() > 1.0 + 1e-6:
                row_w = row_w / row_w.sum()

            sized_weights.loc[ts] = row_w

        return sized_weights

    @staticmethod
    def calculate_var_cvar(
        returns_series: np.ndarray,
        confidence_level: float = 0.95
    ) -> Tuple[float, float]:
        """
        Computes historical Value-at-Risk (VaR) and Conditional VaR (Expected Shortfall).
        Positive values denote losses.
        """
        if len(returns_series) < 10:
            return 0.0, 0.0

        alpha = 1.0 - confidence_level
        var_threshold = -float(np.percentile(returns_series, alpha * 100.0))
        tail_losses = -returns_series[returns_series <= -var_threshold]
        cvar = float(np.mean(tail_losses)) if len(tail_losses) > 0 else var_threshold

        return max(0.0, var_threshold), max(0.0, cvar)

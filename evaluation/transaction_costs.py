"""
evaluation/transaction_costs.py
===============================
P3-1: Advanced Transaction Cost, Liquidity & Execution-Cost Intelligence Layer.

Replaces simplistic fixed-cost assumptions with a research-grade, causal,
point-in-time execution-cost intelligence engine.

Estimates:
1. Exchange Fees (Maker / Taker tiering)
2. Bid/Ask Spread (Corwin-Schultz High-Low Estimator & Volatility-Volume Proxy)
3. Slippage (Volatility- and Liquidity-Adjusted Dynamic Friction)
4. Market Impact (Square-Root Participation Rate Model)
5. Liquidity Classification (Point-in-Time Score: HIGH, MEDIUM, LOW, EXTREME)
6. Execution Delay Costs (Decision-to-Fill Price Drift)

Strict Invariants:
- Zero Lookahead: All inputs at time t derived solely from data available <= t.
- Zero Double-Counting: Clear mathematical separation of all friction components.
- Monetary Precision: Clean Decimal / floating-point accounting.
"""

from __future__ import annotations
import math
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Union
import numpy as np
import pandas as pd


# =============================================================================
# Domain Enums & Configurations
# =============================================================================

class LiquidityTier(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    EXTREME = "EXTREME"


class OrderExecutionType(str, Enum):
    MAKER = "MAKER"
    TAKER = "TAKER"


class CostModelProfile(str, Enum):
    FIXED_12BPS = "FIXED_12BPS"
    SPREAD_FEE = "SPREAD_FEE"
    SPREAD_SLIPPAGE_FEE = "SPREAD_SLIPPAGE_FEE"
    ADVANCED_BASE = "ADVANCED_BASE"
    ADVANCED_OPTIMISTIC = "ADVANCED_OPTIMISTIC"
    ADVANCED_CONSERVATIVE = "ADVANCED_CONSERVATIVE"
    ADVANCED_STRESSED = "ADVANCED_STRESSED"
    # P3-1F Corrected Non-Double-Counted Profiles
    P3_1F_BASE = "P3_1F_BASE"
    P3_1F_OPTIMISTIC = "P3_1F_OPTIMISTIC"
    P3_1F_CONSERVATIVE = "P3_1F_CONSERVATIVE"
    P3_1F_STRESSED = "P3_1F_STRESSED"


@dataclass
class CostModelConfig:
    """Versioned configuration for execution-cost estimation."""
    version: str = "P3-1-v1"
    profile: CostModelProfile = CostModelProfile.P3_1F_BASE

    # 1. Fee Assumptions (Basis Points)
    maker_fee_bps: float = 4.0        # 0.04%
    taker_fee_bps: float = 6.0        # 0.06%
    default_order_type: OrderExecutionType = OrderExecutionType.TAKER

    # 2. Spread Assumptions
    min_spread_bps: float = 1.0       # Minimum floor (0.01%)
    max_spread_bps: float = 50.0      # Maximum cap (0.50%)
    spread_vol_scale: float = 0.35    # Scaling factor for vol-volume spread proxy

    # 3. Slippage Assumptions
    base_slippage_bps: float = 2.0    # 0.02% baseline
    slippage_vol_beta: float = 0.50   # Volatility sensitivity factor
    slippage_liq_beta: float = 0.50   # Illiquidity sensitivity factor
    max_slippage_bps: float = 40.0    # Ceiling for slippage

    # 4. Market Impact Assumptions (Square-root model)
    impact_gamma: float = 0.10        # Participation impact coefficient
    max_impact_bps: float = 60.0      # Ceiling for market impact

    # 5. Delay Cost Assumptions
    include_delay_cost: bool = False  # False for P3-1F (eliminates t+1 double-counting)
    delay_bars: int = 1               # t+1 bar open execution baseline

    # 6. Lookback Windows
    rolling_vol_window: int = 24      # 24 hours rolling volatility
    rolling_vol_benchmark: float = 0.015 # Typical 1h volatility baseline (~1.5%)
    rolling_volume_window: int = 24   # 24 hours rolling quote volume


# Pre-defined Scenario Configurations
SCENARIO_CONFIGS: Dict[CostModelProfile, CostModelConfig] = {
    CostModelProfile.FIXED_12BPS: CostModelConfig(
        profile=CostModelProfile.FIXED_12BPS,
        maker_fee_bps=4.0,
        taker_fee_bps=4.0,
        base_slippage_bps=2.0,
        min_spread_bps=0.0,
        max_spread_bps=0.0,
        impact_gamma=0.0,
        include_delay_cost=False
    ),
    CostModelProfile.SPREAD_FEE: CostModelConfig(
        profile=CostModelProfile.SPREAD_FEE,
        maker_fee_bps=4.0,
        taker_fee_bps=6.0,
        base_slippage_bps=0.0,
        impact_gamma=0.0,
        include_delay_cost=False
    ),
    CostModelProfile.SPREAD_SLIPPAGE_FEE: CostModelConfig(
        profile=CostModelProfile.SPREAD_SLIPPAGE_FEE,
        maker_fee_bps=4.0,
        taker_fee_bps=6.0,
        base_slippage_bps=2.0,
        impact_gamma=0.0,
        include_delay_cost=False
    ),
    CostModelProfile.ADVANCED_OPTIMISTIC: CostModelConfig(
        profile=CostModelProfile.ADVANCED_OPTIMISTIC,
        maker_fee_bps=2.0,
        taker_fee_bps=4.0,
        base_slippage_bps=1.0,
        spread_vol_scale=0.20,
        impact_gamma=0.05,
        include_delay_cost=True
    ),
    CostModelProfile.ADVANCED_BASE: CostModelConfig(
        profile=CostModelProfile.ADVANCED_BASE,
        maker_fee_bps=4.0,
        taker_fee_bps=6.0,
        base_slippage_bps=2.0,
        spread_vol_scale=0.35,
        impact_gamma=0.10,
        include_delay_cost=True
    ),
    CostModelProfile.ADVANCED_CONSERVATIVE: CostModelConfig(
        profile=CostModelProfile.ADVANCED_CONSERVATIVE,
        maker_fee_bps=5.0,
        taker_fee_bps=8.0,
        base_slippage_bps=4.0,
        spread_vol_scale=0.50,
        impact_gamma=0.20,
        include_delay_cost=True
    ),
    CostModelProfile.ADVANCED_STRESSED: CostModelConfig(
        profile=CostModelProfile.ADVANCED_STRESSED,
        maker_fee_bps=6.0,
        taker_fee_bps=10.0,
        base_slippage_bps=8.0,
        spread_vol_scale=0.80,
        impact_gamma=0.35,
        include_delay_cost=True
    ),
    # P3-1F Corrected Configurations (Zero Delay Double-Counting)
    CostModelProfile.P3_1F_OPTIMISTIC: CostModelConfig(
        version="P3-1F-v1",
        profile=CostModelProfile.P3_1F_OPTIMISTIC,
        maker_fee_bps=2.0,
        taker_fee_bps=4.0,
        base_slippage_bps=1.0,
        spread_vol_scale=0.20,
        impact_gamma=0.05,
        include_delay_cost=False
    ),
    CostModelProfile.P3_1F_BASE: CostModelConfig(
        version="P3-1F-v1",
        profile=CostModelProfile.P3_1F_BASE,
        maker_fee_bps=4.0,
        taker_fee_bps=6.0,
        base_slippage_bps=2.0,
        spread_vol_scale=0.35,
        impact_gamma=0.10,
        include_delay_cost=False
    ),
    CostModelProfile.P3_1F_CONSERVATIVE: CostModelConfig(
        version="P3-1F-v1",
        profile=CostModelProfile.P3_1F_CONSERVATIVE,
        maker_fee_bps=5.0,
        taker_fee_bps=8.0,
        base_slippage_bps=4.0,
        spread_vol_scale=0.50,
        impact_gamma=0.20,
        include_delay_cost=False
    ),
    CostModelProfile.P3_1F_STRESSED: CostModelConfig(
        version="P3-1F-v1",
        profile=CostModelProfile.P3_1F_STRESSED,
        maker_fee_bps=6.0,
        taker_fee_bps=10.0,
        base_slippage_bps=8.0,
        spread_vol_scale=0.80,
        impact_gamma=0.35,
        include_delay_cost=False
    ),
}


# =============================================================================
# Trade Cost Breakdown Model
# =============================================================================

@dataclass
class TradeCostBreakdown:
    """Granular, explainable decomposition of execution friction for a single trade."""
    symbol: str
    timestamp: str
    side: str
    quantity: float
    reference_price: float
    notional: float

    # Cost Components in Basis Points (bps)
    fee_bps: float
    spread_bps: float
    slippage_bps: float
    impact_bps: float
    delay_bps: float
    total_cost_bps: float

    # Cost Components in Currency ($)
    fee_dollars: float
    spread_dollars: float
    slippage_dollars: float
    impact_dollars: float
    delay_dollars: float
    total_cost_dollars: float

    # Context Metrics
    participation_rate: float
    liquidity_score: float
    liquidity_tier: LiquidityTier
    realized_volatility: float
    order_type: OrderExecutionType

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": str(self.timestamp),
            "side": self.side,
            "quantity": round(self.quantity, 6),
            "reference_price": round(self.reference_price, 4),
            "notional": round(self.notional, 2),
            "fee_bps": round(self.fee_bps, 2),
            "spread_bps": round(self.spread_bps, 2),
            "slippage_bps": round(self.slippage_bps, 2),
            "impact_bps": round(self.impact_bps, 2),
            "delay_bps": round(self.delay_bps, 2),
            "total_cost_bps": round(self.total_cost_bps, 2),
            "fee_dollars": round(self.fee_dollars, 4),
            "spread_dollars": round(self.spread_dollars, 4),
            "slippage_dollars": round(self.slippage_dollars, 4),
            "impact_dollars": round(self.impact_dollars, 4),
            "delay_dollars": round(self.delay_dollars, 4),
            "total_cost_dollars": round(self.total_cost_dollars, 4),
            "participation_rate": round(self.participation_rate, 6),
            "liquidity_score": round(self.liquidity_score, 1),
            "liquidity_tier": self.liquidity_tier.value,
            "realized_volatility": round(self.realized_volatility, 6),
            "order_type": self.order_type.value,
        }


# =============================================================================
# Component Models
# =============================================================================

class FeeModel:
    """Calculates exchange maker/taker fees with strict one-way/round-trip semantics."""

    def __init__(self, config: CostModelConfig):
        self.config = config

    def calculate_fee(
        self,
        notional: float,
        order_type: Optional[OrderExecutionType] = None
    ) -> Tuple[float, float]:
        """Returns (fee_bps, fee_dollars)."""
        if notional <= 0:
            return 0.0, 0.0
        
        otype = order_type or self.config.default_order_type
        fee_bps = self.config.maker_fee_bps if otype == OrderExecutionType.MAKER else self.config.taker_fee_bps
        # Use Decimal for exact monetary precision to eliminate float epsilon
        fee_dollars = float(round(Decimal(str(notional)) * Decimal(str(fee_bps)) / Decimal("10000"), 8))
        return float(fee_bps), fee_dollars


class SpreadModel:
    """
    Estimates causal point-in-time bid/ask half-spread cost.
    Uses Corwin-Schultz 2-bar High-Low estimator with fallback to volatility-volume proxy.
    """

    def __init__(self, config: CostModelConfig):
        self.config = config

    def estimate_spread_bps(
        self,
        high_now: float,
        low_now: float,
        high_prev: Optional[float],
        low_prev: Optional[float],
        realized_vol_24h: float,
        rolling_24h_quote_volume: float
    ) -> float:
        """
        Estimates full bid-ask spread in bps.
        Guarantees zero-lookahead (uses only current and prior bar).
        """
        if self.config.profile == CostModelProfile.FIXED_12BPS:
            return 0.0

        # Try Corwin-Schultz (2012) 2-bar estimator if previous bar is valid
        cs_spread = None
        if high_prev is not None and low_prev is not None and high_prev > low_prev > 0 and high_now > low_now > 0:
            try:
                # 2-period high and low
                h2 = max(high_now, high_prev)
                l2 = min(low_now, low_prev)

                gamma = (math.log(h2 / l2)) ** 2
                beta = (math.log(high_now / low_now)) ** 2 + (math.log(high_prev / low_prev)) ** 2

                # Corwin-Schultz alpha formula
                denom = 3.0 - 2.0 * math.sqrt(2.0)
                alpha_val = (math.sqrt(2.0 * beta) - math.sqrt(beta)) / denom - math.sqrt(gamma / denom)

                if alpha_val > 0:
                    cs_spread = 2.0 * (math.exp(alpha_val) - 1.0) / (1.0 + math.exp(alpha_val)) * 10000.0
            except (ValueError, ZeroDivisionError, OverflowError):
                cs_spread = None

        if cs_spread is not None and not math.isnan(cs_spread) and cs_spread > 0:
            spread_bps = cs_spread
        else:
            # Fallback: Volatility / sqrt(Quote Volume in Millions) proxy
            vol_mil = max(1.0, rolling_24h_quote_volume / 1_000_000.0)
            spread_bps = self.config.spread_vol_scale * (realized_vol_24h * 10000.0) / math.sqrt(vol_mil)

        # Enforce bounds
        return float(np.clip(spread_bps, self.config.min_spread_bps, self.config.max_spread_bps))

    def calculate_spread_cost(
        self,
        notional: float,
        spread_bps: float
    ) -> Tuple[float, float]:
        """
        For an aggressive/market order crossing the book, the cost is the half-spread.
        Returns (spread_cost_bps, spread_cost_dollars).
        """
        if notional <= 0:
            return 0.0, 0.0
        half_spread_bps = 0.5 * spread_bps
        spread_dollars = notional * (half_spread_bps / 10000.0)
        return half_spread_bps, spread_dollars


class SlippageModel:
    """Calculates dynamic slippage scaled by market volatility and illiquidity."""

    def __init__(self, config: CostModelConfig):
        self.config = config

    def calculate_slippage(
        self,
        notional: float,
        realized_vol_24h: float,
        rolling_24h_quote_volume: float,
        benchmark_vol: float = 0.015,
        benchmark_volume: float = 50_000_000.0
    ) -> Tuple[float, float]:
        """Returns (slippage_bps, slippage_dollars)."""
        if notional <= 0 or self.config.base_slippage_bps <= 0:
            return 0.0, 0.0

        # Volatility multiplier: increases with above-normal volatility
        vol_ratio = max(0.0, (realized_vol_24h - benchmark_vol) / max(1e-5, benchmark_vol))
        vol_factor = 1.0 + self.config.slippage_vol_beta * vol_ratio

        # Illiquidity multiplier: increases when volume drops below benchmark
        vol_ratio_liq = max(0.0, (benchmark_volume - rolling_24h_quote_volume) / max(1.0, benchmark_volume))
        liq_factor = 1.0 + self.config.slippage_liq_beta * vol_ratio_liq

        slippage_bps = self.config.base_slippage_bps * vol_factor * liq_factor
        slippage_bps = float(np.clip(slippage_bps, 0.0, self.config.max_slippage_bps))
        slippage_dollars = notional * (slippage_bps / 10000.0)
        return slippage_bps, slippage_dollars


class MarketImpactModel:
    """
    Square-Root Market Impact Model:
    Impact_bps = gamma * sigma_bps * sqrt(order_notional / rolling_24h_volume)
    """

    def __init__(self, config: CostModelConfig):
        self.config = config

    def calculate_market_impact(
        self,
        notional: float,
        realized_vol_24h: float,
        rolling_24h_quote_volume: float
    ) -> Tuple[float, float, float]:
        """Returns (impact_bps, impact_dollars, participation_rate)."""
        if notional <= 0 or self.config.impact_gamma <= 0 or rolling_24h_quote_volume <= 0:
            return 0.0, 0.0, 0.0

        participation_rate = notional / max(1.0, rolling_24h_quote_volume)
        vol_bps = realized_vol_24h * 10000.0

        # Monotonic square-root impact
        impact_bps = self.config.impact_gamma * vol_bps * math.sqrt(min(1.0, participation_rate))
        impact_bps = float(np.clip(impact_bps, 0.0, self.config.max_impact_bps))
        impact_dollars = notional * (impact_bps / 10000.0)

        return impact_bps, impact_dollars, participation_rate


class LiquidityModel:
    """Assesses point-in-time asset liquidity score and discrete tier."""

    @staticmethod
    def evaluate_liquidity(
        rolling_24h_quote_volume: float,
        realized_vol_24h: float
    ) -> Tuple[float, LiquidityTier]:
        """
        Returns (score [0-100], LiquidityTier).
        Classification:
        HIGH: > $100M/day (Score 80-100)
        MEDIUM: $20M-$100M/day (Score 50-80)
        LOW: $5M-$20M/day (Score 20-50)
        EXTREME / Illiquid: < $5M/day (Score 0-20)
        """
        vol_m = rolling_24h_quote_volume / 1_000_000.0

        if vol_m >= 100.0:
            tier = LiquidityTier.HIGH
            score = min(100.0, 80.0 + (vol_m - 100.0) / 20.0)
        elif vol_m >= 20.0:
            tier = LiquidityTier.MEDIUM
            score = 50.0 + (vol_m - 20.0) / 80.0 * 30.0
        elif vol_m >= 5.0:
            tier = LiquidityTier.LOW
            score = 20.0 + (vol_m - 5.0) / 15.0 * 30.0
        else:
            tier = LiquidityTier.EXTREME
            score = max(0.0, (vol_m / 5.0) * 20.0)

        # High volatility penalizes liquidity score slightly
        if realized_vol_24h > 0.03: # >3% hourly vol
            score = max(0.0, score - 10.0)

        return round(float(score), 1), tier


class DelayCostModel:
    """Measures decision-to-fill price drift caused by execution delay."""

    def __init__(self, config: CostModelConfig):
        self.config = config

    def calculate_delay_cost(
        self,
        notional: float,
        decision_price: float,
        fill_price: float,
        side: str
    ) -> Tuple[float, float]:
        """
        Computes adverse execution drift:
        For BUY: price increase is an adverse delay cost.
        For SELL: price decrease is an adverse delay cost.
        Returns (delay_bps, delay_dollars).
        """
        if not self.config.include_delay_cost or notional <= 0 or decision_price <= 0 or fill_price <= 0:
            return 0.0, 0.0

        if side.upper() == "BUY":
            drift_pct = (fill_price - decision_price) / decision_price
        else:
            drift_pct = (decision_price - fill_price) / decision_price

        # Delay cost only measures adverse slippage drift (non-negative)
        delay_bps = max(0.0, drift_pct * 10000.0)
        delay_dollars = notional * (delay_bps / 10000.0)
        return delay_bps, delay_dollars


# =============================================================================
# Composite Transaction Cost Engine
# =============================================================================

class TransactionCostEngine:
    """
    Unified execution-cost intelligence engine.
    Orchestrates Fee, Spread, Slippage, Market Impact, Liquidity, and Delay models.
    """

    def __init__(self, config: Optional[CostModelConfig] = None):
        self.config = config or CostModelConfig()
        self.fee_model = FeeModel(self.config)
        self.spread_model = SpreadModel(self.config)
        self.slippage_model = SlippageModel(self.config)
        self.impact_model = MarketImpactModel(self.config)
        self.liquidity_model = LiquidityModel()
        self.delay_model = DelayCostModel(self.config)

    def estimate_trade_cost(
        self,
        symbol: str,
        timestamp: Any,
        side: str,
        quantity: float,
        reference_price: float,
        market_context: Dict[str, Any],
        order_type: Optional[OrderExecutionType] = None
    ) -> TradeCostBreakdown:
        """
        Decomposes execution friction for an individual trade.
        All inputs must be causal (t <= decision time).
        """
        notional = float(quantity * reference_price)
        if notional <= 0 or reference_price <= 0:
            raise ValueError(f"Invalid trade parameters: quantity={quantity}, price={reference_price}")

        high_now = float(market_context.get("high", reference_price))
        low_now = float(market_context.get("low", reference_price))
        high_prev = market_context.get("high_prev")
        low_prev = market_context.get("low_prev")
        realized_vol = float(market_context.get("realized_vol_24h", self.config.rolling_vol_benchmark))
        quote_vol_24h = float(market_context.get("rolling_24h_quote_volume", 50_000_000.0))
        fill_price = float(market_context.get("fill_price", reference_price))

        # 1. Liquidity Tier
        liq_score, liq_tier = self.liquidity_model.evaluate_liquidity(quote_vol_24h, realized_vol)

        # 2. Component Costs
        if self.config.profile == CostModelProfile.FIXED_12BPS:
            # Fixed 12 bps baseline (6 bps one-way fee+slippage)
            fee_bps = 4.0
            fee_dollars = notional * 0.0004
            spread_bps = 0.0
            spread_dollars = 0.0
            slippage_bps = 2.0
            slippage_dollars = notional * 0.0002
            impact_bps = 0.0
            impact_dollars = 0.0
            delay_bps = 0.0
            delay_dollars = 0.0
            total_bps = 6.0 # 6 bps one-way = 12 bps round-trip
            total_dollars = notional * 0.0006
            participation_rate = notional / max(1.0, quote_vol_24h)
        else:
            fee_bps, fee_dollars = self.fee_model.calculate_fee(notional, order_type)
            
            raw_spread = self.spread_model.estimate_spread_bps(
                high_now, low_now, high_prev, low_prev, realized_vol, quote_vol_24h
            )
            spread_bps, spread_dollars = self.spread_model.calculate_spread_cost(notional, raw_spread)

            slippage_bps, slippage_dollars = self.slippage_model.calculate_slippage(
                notional, realized_vol, quote_vol_24h, self.config.rolling_vol_benchmark
            )

            impact_bps, impact_dollars, participation_rate = self.impact_model.calculate_market_impact(
                notional, realized_vol, quote_vol_24h
            )

            delay_bps, delay_dollars = self.delay_model.calculate_delay_cost(
                notional, reference_price, fill_price, side
            )

            total_bps = fee_bps + spread_bps + slippage_bps + impact_bps + delay_bps
            total_dollars = fee_dollars + spread_dollars + slippage_dollars + impact_dollars + delay_dollars

        return TradeCostBreakdown(
            symbol=symbol,
            timestamp=str(timestamp),
            side=side.upper(),
            quantity=quantity,
            reference_price=reference_price,
            notional=notional,
            fee_bps=fee_bps,
            spread_bps=spread_bps,
            slippage_bps=slippage_bps,
            impact_bps=impact_bps,
            delay_bps=delay_bps,
            total_cost_bps=total_bps,
            fee_dollars=fee_dollars,
            spread_dollars=spread_dollars,
            slippage_dollars=slippage_dollars,
            impact_dollars=impact_dollars,
            delay_dollars=delay_dollars,
            total_cost_dollars=total_dollars,
            participation_rate=participation_rate,
            liquidity_score=liq_score,
            liquidity_tier=liq_tier,
            realized_volatility=realized_vol,
            order_type=order_type or self.config.default_order_type
        )

    def compute_portfolio_rebalance_costs(
        self,
        prices_df: pd.DataFrame,
        weights_df: pd.DataFrame,
        high_df: Optional[pd.DataFrame] = None,
        low_df: Optional[pd.DataFrame] = None,
        quote_volume_df: Optional[pd.DataFrame] = None,
        portfolio_capital: float = 10_000.0
    ) -> Tuple[np.ndarray, List[TradeCostBreakdown]]:
        """
        Vectorized/Bar-by-bar calculation of transaction costs across portfolio rebalances.
        Returns:
            step_cost_pct: Array of step cost percentages per bar (shape: T).
            trade_logs: List of all individual TradeCostBreakdown records.
        """
        common_idx = prices_df.index.intersection(weights_df.index)
        aligned_prices = prices_df.loc[common_idx].sort_index()
        aligned_weights = weights_df.loc[common_idx].sort_index()

        symbols = [s for s in aligned_prices.columns if s in aligned_weights.columns]
        n_bars = len(aligned_prices)
        n_symbols = len(symbols)

        p_mat = aligned_prices[symbols].values
        w_mat = aligned_weights[symbols].values

        h_mat = high_df.loc[common_idx, symbols].values if high_df is not None else p_mat * 1.002
        l_mat = low_df.loc[common_idx, symbols].values if low_df is not None else p_mat * 0.998
        qv_mat = quote_volume_df.loc[common_idx, symbols].values if quote_volume_df is not None else np.full_like(p_mat, 50_000_000.0)

        # Precompute 24h rolling volatility for each symbol causally
        vol_mat = np.zeros_like(p_mat)
        for j in range(n_symbols):
            rets = pd.Series(p_mat[:, j]).pct_change().fillna(0.0)
            vol_mat[:, j] = rets.rolling(self.config.rolling_vol_window, min_periods=2).std().fillna(self.config.rolling_vol_benchmark).values

        step_cost_pct = np.zeros(n_bars)
        trade_logs: List[TradeCostBreakdown] = []

        current_weights = np.zeros(n_symbols)

        for t in range(n_bars - 1):
            target_w = w_mat[t]
            delta_w = target_w - current_weights

            bar_cost_dollars = 0.0
            turnover_sum = 0.0

            for j in range(n_symbols):
                dw = delta_w[j]
                if abs(dw) > 1e-6:
                    turnover_sum += abs(dw)
                    side = "BUY" if dw > 0 else "SELL"
                    trade_notional = abs(dw) * portfolio_capital
                    p_now = p_mat[t, j]
                    p_next = p_mat[t + 1, j] # fill price (t+1 open proxy)
                    q_trade = trade_notional / max(1e-5, p_now)

                    ctx = {
                        "high": h_mat[t, j],
                        "low": l_mat[t, j],
                        "high_prev": h_mat[t - 1, j] if t > 0 else None,
                        "low_prev": l_mat[t - 1, j] if t > 0 else None,
                        "realized_vol_24h": vol_mat[t, j],
                        "rolling_24h_quote_volume": qv_mat[t, j],
                        "fill_price": p_next
                    }

                    tb = self.estimate_trade_cost(
                        symbol=symbols[j],
                        timestamp=common_idx[t],
                        side=side,
                        quantity=q_trade,
                        reference_price=p_now,
                        market_context=ctx
                    )
                    trade_logs.append(tb)
                    bar_cost_dollars += tb.total_cost_dollars

            # Record step cost percentage against portfolio equity
            step_cost_pct[t] = bar_cost_dollars / max(1.0, portfolio_capital)
            current_weights = target_w.copy()

        return step_cost_pct, trade_logs

"""
Risk Management: Position Sizing Engine
=======================================
Implements Volatility Parity and Kelly Fraction sizing:
- ATR-based sizing: Size inversely proportional to volatility
- Capital-per-slot capping
- Maximum leverage constraints
"""

import numpy as np


class PositionSizer:
    def __init__(self, target_risk_pct_per_trade: float = 0.015, max_leverage: float = 3.0):
        self.target_risk_pct = target_risk_pct_per_trade
        self.max_leverage = max_leverage

    def calculate_atr_size(
        self,
        equity: float,
        price: float,
        atr: float,
        atr_multiplier: float = 2.0,
        max_slot_notional: float = 500.0
    ) -> float:
        """
        Calculates position size so that a stop loss of (atr_multiplier * atr)
        risks exactly target_risk_pct of total portfolio equity.
        """
        if equity <= 0.0 or price <= 0.0 or atr <= 0.0:
            return 0.0

        risk_dollars = equity * self.target_risk_pct
        stop_distance = atr * atr_multiplier
        if stop_distance <= 0.0:
            return 0.0

        raw_size = risk_dollars / stop_distance
        raw_notional = raw_size * price

        # Capped by maximum slot notional
        capped_notional = min(raw_notional, max_slot_notional, equity * self.max_leverage)
        final_size = capped_notional / price
        return float(final_size)

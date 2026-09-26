"""
Risk Management: Exposure Management
====================================
Monitors and enforces gross and net portfolio exposure:
- Gross Exposure = sum(abs(notional)) / equity
- Net Exposure = sum(signed_notional) / equity
- Single-asset concentration cap
"""

from typing import Dict, Any, List


class ExposureManager:
    def __init__(self, max_gross_exposure: float = 1.0, max_single_asset_pct: float = 0.35):
        self.max_gross = max_gross_exposure
        self.max_single_asset = max_single_asset_pct

    def check_exposure(
        self,
        equity: float,
        current_positions: Dict[str, Dict[str, Any]],
        new_symbol: str,
        new_notional: float,
        is_short: bool = False
    ) -> bool:
        """
        Returns True if new position satisfies gross exposure and concentration limits.
        """
        if equity <= 0.0:
            return False

        current_gross = sum(
            abs(float(p.get("size", 0.0)) * float(p.get("entry_price", 0.0)))
            for p in current_positions.values()
        )

        projected_gross = current_gross + abs(new_notional)
        if (projected_gross / equity) > self.max_gross:
            return False

        # Concentration check for symbol
        existing_symbol_notional = 0.0
        if new_symbol in current_positions:
            p = current_positions[new_symbol]
            existing_symbol_notional = abs(float(p.get("size", 0.0)) * float(p.get("entry_price", 0.0)))

        projected_symbol_notional = existing_symbol_notional + abs(new_notional)
        if (projected_symbol_notional / equity) > self.max_single_asset:
            return False

        return True

"""
Risk Management: Drawdown & Capital Protection
==============================================
Monitors high-water mark, trailing drawdown, and enforces daily loss limits.
"""

from typing import Tuple


class DrawdownMonitor:
    def __init__(self, max_drawdown_limit: float = 0.20, daily_loss_limit: float = 0.05):
        self.max_drawdown_limit = max_drawdown_limit
        self.daily_loss_limit = daily_loss_limit
        self.high_water_mark: float = 0.0
        self.day_start_equity: float = 0.0

    def update_equity(self, current_equity: float) -> Tuple[bool, str]:
        """
        Updates equity and returns (is_safe, reason).
        If drawdown or daily loss threshold is breached, returns is_safe=False.
        """
        if self.high_water_mark == 0.0:
            self.high_water_mark = current_equity
            self.day_start_equity = current_equity

        if current_equity > self.high_water_mark:
            self.high_water_mark = current_equity

        # Check total drawdown from high-water mark
        current_drawdown = (self.high_water_mark - current_equity) / self.high_water_mark
        if current_drawdown >= self.max_drawdown_limit:
            return False, f"Maximum drawdown threshold reached: {current_drawdown * 100:.1f}% >= {self.max_drawdown_limit * 100:.1f}%"

        # Check daily loss limit
        if self.day_start_equity > 0.0:
            daily_loss = (self.day_start_equity - current_equity) / self.day_start_equity
            if daily_loss >= self.daily_loss_limit:
                return False, f"Daily loss limit reached: {daily_loss * 100:.1f}% >= {self.daily_loss_limit * 100:.1f}%"

        return True, "Within safe operational thresholds"

    def reset_daily_baseline(self, current_equity: float):
        """Resets daily loss baseline at 00:00 UTC."""
        self.day_start_equity = current_equity

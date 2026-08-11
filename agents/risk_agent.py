import logging

logger = logging.getLogger("RiskAgent")

class RiskAgent:
    """
    The Advanced Institutional Risk Shield.
    Handles Global Kill Switches, Trailing Stops, Funding Rates, 
    and Dynamic Slippage along with Kelly Criterion sizing.
    """
    def __init__(self, target_daily_volatility=0.02, max_allocation=0.20):
        self.target_daily_volatility = target_daily_volatility
        self.max_allocation = max_allocation
        
        # Kill Switch threshold: e.g. 5% sudden drop
        self.KILL_SWITCH_THRESHOLD = -0.05 
        
        # Funding rate threshold: if paying > 0.05% every 8hrs, block trades
        self.MAX_FUNDING_RATE = 0.0005 

    def check_kill_switch(self, price_change_15m: float) -> bool:
        """
        Detects Flash Crashes. If price dropped drastically in 15 mins,
        trigger the global kill switch.
        """
        if price_change_15m <= self.KILL_SWITCH_THRESHOLD:
            logger.critical(f"[KILL SWITCH] Flash Crash detected (Drop: {price_change_15m*100:.2f}%). HALTING ALL TRADING.")
            return True
        return False

    def check_funding_rate(self, current_funding_rate: float, side: str) -> bool:
        """
        Prevents bleeding capital to Binance Futures holding fees.
        If we are going LONG, and funding rate is highly positive (Longs pay Shorts), veto.
        """
        if side == "LONG" and current_funding_rate > self.MAX_FUNDING_RATE:
            logger.warning(f"[RISK] Funding rate too high ({current_funding_rate*100:.3f}%). Blocking LONG.")
            return False
        if side == "SHORT" and current_funding_rate < -self.MAX_FUNDING_RATE:
            logger.warning(f"[RISK] Funding rate too negative ({current_funding_rate*100:.3f}%). Blocking SHORT.")
            return False
        return True

    def calculate_trailing_stop(self, entry_price: float, current_price: float, side: str, trail_percent: float = 0.02) -> float:
        """
        Calculates the new trailing stop price.
        """
        if side == "LONG":
            highest_price = max(entry_price, current_price)
            stop_price = highest_price * (1 - trail_percent)
            return stop_price
        elif side == "SHORT":
            lowest_price = min(entry_price, current_price)
            stop_price = lowest_price * (1 + trail_percent)
            return stop_price
        return 0.0

    def calculate_dynamic_slippage(self, current_atr: float, current_price: float) -> float:
        """
        Widens slippage margin during high volatility to ensure execution.
        """
        volatility_pct = current_atr / current_price if current_price > 0 else 0
        # Base slippage 0.1%, scales up with ATR
        slippage = 0.001 + (volatility_pct * 0.5) 
        return min(slippage, 0.01) # Cap at 1% max slippage

    def calculate_position_size(self, final_confidence: float, current_atr: float, current_price: float):
        """
        Calculates Kelly Criterion proxy allocation based on Orchestrator's confidence.
        """
        base_allocation = self.max_allocation * abs(final_confidence)
        
        asset_volatility_pct = current_atr / current_price if current_price > 0 else 0
        if asset_volatility_pct == 0:
            return 0.0
            
        volatility_scalar = self.target_daily_volatility / asset_volatility_pct
        volatility_scalar = min(volatility_scalar, 1.0)
        
        final_allocation = base_allocation * volatility_scalar
        return min(final_allocation, self.max_allocation)

    async def execute(self, parameters, context):
        """Dashboard compatibility method."""
        return {
            "risk_assessment": {
                "var": {"var": 0.015, "confidence": 0.95}
            },
            "max_drawdown": 0.05,
            "trade_limits": {"stop_loss": -0.02, "take_profit": "Trailing"}
        }

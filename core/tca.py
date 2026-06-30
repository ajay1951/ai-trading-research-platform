from typing import Dict, Any

class TradeCostAnalysis:
    """
    Trade Cost Analysis (TCA) Engine.
    Evaluates execution quality by comparing filled prices to arrival prices.
    """
    
    @staticmethod
    def calculate_slippage(action: str, arrival_price: float, fill_price: float) -> float:
        """
        Calculates slippage in basis points (bps).
        Positive = Bad (cost), Negative = Good (price improvement).
        """
        if arrival_price == 0:
            return 0.0
            
        if action == "BUY":
            slippage_pct = (fill_price - arrival_price) / arrival_price
        elif action == "SELL":
            slippage_pct = (arrival_price - fill_price) / arrival_price
        else:
            return 0.0
            
        return float(slippage_pct * 10000) # Convert to bps

    @staticmethod
    def calculate_market_impact(action: str, fill_qty: float, daily_volume: float) -> float:
        """
        Estimates market impact (cost) based on order size vs daily volume.
        Simplified square-root model.
        """
        if daily_volume <= 0:
            return 0.0
            
        participation_rate = fill_qty / daily_volume
        # Simple heuristic: impact scales with sqrt of participation rate
        impact_bps = (participation_rate ** 0.5) * 100 
        return float(impact_bps)

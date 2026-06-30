from typing import Dict, Any
from core.memory import SharedMemory
from core.tca import TradeCostAnalysis

class TCAAgent:
    """
    Trade Cost Analysis Agent.
    Runs post-execution to evaluate slippage and market impact.
    Provides feedback to the RL Agent.
    """
    def __init__(self, memory: SharedMemory):
        self.memory = memory

    async def execute(self, parameters: Dict, context: Dict) -> Dict:
        """
        Evaluates the execution quality of the completed trade.
        """
        algo_res = context.get("algo", {})
        exec_res = context.get("execution", {}).get("trade_details", {})
        
        if not algo_res or algo_res.get("status") != "ALGO_COMPLETE":
             return {"status": "NO_TRADE", "reason": "No completed algo execution to analyze."}
             
        action = exec_res.get("action")
        arrival_price = exec_res.get("price")
        avg_fill_price = algo_res.get("average_fill_price")
        total_filled = algo_res.get("total_filled")
        symbol = exec_res.get("symbol", parameters.get("symbol", "UNKNOWN"))
        
        # Calculate TCA metrics
        slippage_bps = TradeCostAnalysis.calculate_slippage(action, arrival_price, avg_fill_price)
        
        # Mock daily volume for market impact
        mock_daily_volume = total_filled * 100 
        market_impact_bps = TradeCostAnalysis.calculate_market_impact(action, total_filled, mock_daily_volume)
        
        result = {
            "symbol": symbol,
            "action": action,
            "arrival_price": arrival_price,
            "avg_fill_price": avg_fill_price,
            "slippage_bps": round(slippage_bps, 2),
            "market_impact_bps": round(market_impact_bps, 2),
            "total_cost_bps": round(slippage_bps + market_impact_bps, 2),
            "algo_used": algo_res.get("algo_type")
        }
        
        # Publish feedback for RL Agent and Review Agent
        self.memory.publish("tca_report", result, sender="tca")
        
        return result

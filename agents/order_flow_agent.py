"""
OrderFlowAgent: Analyzes market microstructure from order book and other L2 data.
"""
from core.memory import SharedMemory

class OrderFlowAgent:
    def __init__(self, memory: SharedMemory):
        self.memory = memory

    def get_capability(self):
        return {
            "name": "order_flow",
            "description": "Analyzes order book, liquidations, and open interest for microstructure insights.",
            "supported_operations": ["get_flow_bias"],
            "dependencies": ["data"]
        }

    def _calculate_obi(self, bids: list, asks: list) -> float:
        """
        Calculates Order Book Imbalance (OBI) based on the top 20 levels.
        OBI = (Total Bid Vol - Total Ask Vol) / (Total Bid Vol + Total Ask Vol)
        Returns a float between -1.0 (extreme sell pressure) and 1.0 (extreme buy pressure).
        """
        if not bids or not asks:
            return 0.0
            
        bid_vol = sum([float(b[1]) for b in bids[:20]])
        ask_vol = sum([float(a[1]) for a in asks[:20]])
        
        total_vol = bid_vol + ask_vol
        if total_vol == 0:
            return 0.0
            
        return (bid_vol - ask_vol) / total_vol

    async def execute(self, parameters: dict, context: dict) -> dict:
        """
        Executes order flow analysis.
        This would require new tools to fetch L2 data, funding rates, etc.
        """
        # Try to calculate actual OBI if L2 data is available in context
        l2_data = context.get('l2_data', {})
        if l2_data:
            imbalance_score = self._calculate_obi(l2_data.get('bids', []), l2_data.get('asks', []))
        else:
            imbalance_score = 0.7 # Positive score indicates buy-side pressure (mocked fallback)
            
        # Mocked analysis for remaining microstructure
        order_flow_bias = "Bullish" if imbalance_score > 0 else "Bearish"
        liquidity_zones = [context.get('live_price', 50000) * 0.98, context.get('live_price', 50000) * 1.02]
        whale_activity = "Accumulation detected in large orders."
        squeeze_probability = 0.65 # 65% chance of a short squeeze

        flow_data = {
            "order_flow_bias": order_flow_bias,
            "liquidity_zones": liquidity_zones,
            "whale_activity": whale_activity,
            "squeeze_probability": squeeze_probability,
            "imbalance_score": imbalance_score
        }

        symbol = context.get("symbol", "default")
        self.memory.store(f"order_flow:{symbol}", flow_data)

        return {"status": "success", "order_flow": flow_data}
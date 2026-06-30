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

    async def execute(self, parameters: dict, context: dict) -> dict:
        """
        Executes order flow analysis.
        This would require new tools to fetch L2 data, funding rates, etc.
        """
        # Mocked analysis for demonstration
        order_flow_bias = "Bullish"
        liquidity_zones = [context.get('live_price', 50000) * 0.98, context.get('live_price', 50000) * 1.02]
        whale_activity = "Accumulation detected in large orders."
        squeeze_probability = 0.65 # 65% chance of a short squeeze
        imbalance_score = 0.7 # Positive score indicates buy-side pressure

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
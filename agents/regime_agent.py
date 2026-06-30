from typing import Dict, Any
from core.memory import SharedMemory
from models.regime_models import RegimeModel

class RegimeAgent:
    """
    Market Regime Agent.
    Detects the current market environment (e.g., Bull/Bear, High/Low Volatility).
    This context is crucial for quant and risk agents to adapt their models.
    """
    def __init__(self, memory: SharedMemory):
        self.memory = memory

    async def execute(self, parameters: Dict, context: Dict) -> Dict:
        """
        Executes regime detection based on available market data.
        """
        symbol = parameters.get("symbol", "UNKNOWN")
        
        # Get market data from context
        market_data = {}
        if "data" in context and "market" in context["data"]:
            market_data = context["data"]["market"]
            
        # We need historical prices to detect regime.
        # Fallback to simulated if not available in real-time data agent yet.
        historical_prices = market_data.get("historical_prices", [])
        
        if not historical_prices:
             # Just a fallback mock if DataAgent doesn't return full historical arrays
             historical_prices = [market_data.get("current_price", 100.0) * (1 + (i * 0.001)) for i in range(-30, 1)]
             
        regime_result = RegimeModel.detect_regime(historical_prices)
        
        # Publish to shared memory for other agents to see globally
        self.memory.publish("market_regime_update", regime_result, sender="regime")
        
        return {
            "symbol": symbol,
            "regime": regime_result
        }

from typing import Dict, Any
import numpy as np
from core.memory import SharedMemory
from models.portfolio_models import PortfolioOptimization

class CIOAgent:
    """
    Chief Investment Officer Agent.
    Allocates capital across multiple strategies and assets to maximize fund-level Sharpe ratio.
    Passes target weights down to the Portfolio Management Agent.
    """
    def __init__(self, memory: SharedMemory):
        self.memory = memory
        self.risk_tolerance = 1.5 # Configurable risk appetite

    async def execute(self, parameters: Dict, context: Dict) -> Dict:
        """
        Ingests supervisor signals and creates a fund-level capital allocation.
        """
        # In a real system, the CIO agent would look at the entire universe of signals.
        # Since this pipeline typically processes one symbol at a time in prototype mode,
        # we simulate fund-level awareness by looking at the supervisor's signal.
        
        supervisor_res = context.get("supervisor", {})
        final_signal = supervisor_res.get("final_signal", "HOLD")
        confidence = supervisor_res.get("final_confidence", 0.0)
        symbol = parameters.get("symbol", "UNKNOWN")
        
        # Mock expected returns and covariance based on the signal
        expected_return = 0.0
        if final_signal == "BUY":
            expected_return = 0.05 * confidence
        elif final_signal == "SELL":
            expected_return = -0.05 * confidence
            
        # Example of applying Markowitz (simulated with 1 asset vs Cash)
        # Asset 0: Cash (0 variance, 0 expected return)
        # Asset 1: The current symbol
        expected_returns = np.array([0.0, expected_return])
        cov_matrix = np.array([
            [0.0, 0.0],
            [0.0, 0.04] # Mock 20% volatility squared
        ])
        
        target_weights = PortfolioOptimization.calculate_target_weights(expected_returns, cov_matrix, self.risk_tolerance)
        
        # Target weight for the specific symbol
        symbol_target_weight = float(target_weights[1])
        
        decision = {
            "symbol": symbol,
            "target_weight": symbol_target_weight,
            "cash_weight": float(target_weights[0]),
            "expected_return_proxy": expected_return,
            "reason": f"Optimized target weight for {symbol} is {symbol_target_weight*100:.1f}% based on {confidence:.1f} confidence."
        }
        
        self.memory.publish("cio_allocation", decision, sender="cio")
        return decision

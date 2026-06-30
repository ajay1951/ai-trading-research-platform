import numpy as np
from typing import List, Dict

class FactorModels:
    """
    Institutional Alpha Factor Models.
    Calculates statistical factors used for weighting and alpha generation.
    """
    
    @staticmethod
    def calculate_momentum_factor(prices: List[float], window: int = 14) -> float:
        """
        Calculates time-series momentum factor (Z-score of returns).
        """
        if len(prices) < window + 1:
            return 0.0
            
        returns = np.diff(prices) / prices[:-1]
        recent_return = returns[-1]
        historical_returns = returns[-window:]
        
        mean_ret = np.mean(historical_returns)
        std_ret = np.std(historical_returns)
        
        if std_ret == 0:
            return 0.0
            
        z_score = (recent_return - mean_ret) / std_ret
        return float(z_score)
        
    @staticmethod
    def calculate_mean_reversion_factor(prices: List[float], window: int = 20) -> float:
        """
        Calculates mean reversion factor based on deviation from SMA.
        Negative value indicates oversold (buy signal), positive indicates overbought.
        """
        if len(prices) < window:
            return 0.0
            
        sma = np.mean(prices[-window:])
        current_price = prices[-1]
        
        # Percentage deviation
        deviation = (current_price - sma) / sma
        # Invert so positive factor = buy signal (reverting up)
        return float(-deviation * 100)

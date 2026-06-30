import numpy as np
from typing import Dict, List, Any

class RegimeModel:
    """
    Market Regime Detection Model.
    In production, this would use Hidden Markov Models (HMM) or Gaussian Mixture Models.
    For this implementation, we use a rolling volatility and trend heuristic.
    """
    
    @staticmethod
    def detect_regime(prices: List[float]) -> Dict[str, Any]:
        """
        Detects the current market regime based on a list of closing prices.
        Returns the regime state and confidence.
        """
        if len(prices) < 20:
            return {"state": "UNKNOWN", "confidence": 0.0, "details": "Insufficient data"}
            
        returns = np.diff(prices) / prices[:-1]
        
        # Volatility: Annualized standard deviation of daily returns (assuming daily data)
        volatility = np.std(returns) * np.sqrt(365)
        
        # Trend: SMA crossover proxy (fast vs slow)
        short_sma = np.mean(prices[-10:])
        long_sma = np.mean(prices[-20:])
        trend_up = short_sma > long_sma
        
        if volatility > 0.6: # High vol threshold
            state = "HIGH_VOL_BULL" if trend_up else "HIGH_VOL_BEAR"
        else:
            state = "LOW_VOL_BULL" if trend_up else "LOW_VOL_BEAR"
            
        # Mock confidence based on the strength of the trend and vol deviation
        trend_strength = abs(short_sma - long_sma) / long_sma
        confidence = min(0.5 + (trend_strength * 10), 0.95)
        
        return {
            "state": state,
            "confidence": float(confidence),
            "volatility_annualized": float(volatility),
            "trend_strength": float(trend_strength)
        }

import pandas as pd

class RegimeAgent:
    """
    The 'Master Switch' Regime Classifier.
    Analyzes macro timeframes to determine if the market is trending or ranging.
    """
    def __init__(self):
        pass
        
    def classify(self, df: pd.DataFrame) -> str:
        """
        Takes a daily dataframe and classifies the current market regime.
        Returns: 'TRENDING_BULL', 'TRENDING_BEAR', or 'RANGING'.
        """
        if len(df) < 200:
            return "RANGING" # Default safe state
            
        # 1. Calculate ADX (Average Directional Index) proxy using Volatility
        volatility = df['close'].pct_change().rolling(14).std().iloc[-1]
        
        # 2. Calculate 200 EMA slope
        ema_200 = df['close'].ewm(span=200, adjust=False).mean()
        slope = (ema_200.iloc[-1] - ema_200.iloc[-5]) / ema_200.iloc[-5]
        
        # Thresholds drastically lowered to allow 5-minute ticks to pass
        if slope > 0.00001:
            return "TRENDING_BULL"
        elif slope < -0.00001:
            return "TRENDING_BEAR"
        else:
            return "RANGING"

class QuantAgent:
    """
    The Mathematician (Multi-Timeframe Version).
    Analyzes Z-Scores across the 1m, 1h, 1d, 1w, and 1mo timelines simultaneously.
    """
    def __init__(self, z_score_threshold_or_memory=2.0):
        if hasattr(z_score_threshold_or_memory, 'store'):
            self.memory = z_score_threshold_or_memory
            self.z_score_threshold = 2.0
        else:
            self.z_score_threshold = z_score_threshold_or_memory

    def analyze(self, state_dict):
        """
        Takes the full MTF state dictionary and returns a blended macro/micro probability.
        """
        macro_score = state_dict.get('1mo_z_score', 0.0) + state_dict.get('1w_z_score', 0.0)
        base_score = state_dict.get('1d_z_score', 0.0)
        
        # If macro z-score is highly negative, price is artificially suppressed -> Strong Buy
        # If micro volatility is spiking, throttle the conviction
        
        combined_z_score = (macro_score * 0.4) + (base_score * 0.6)
        
        if combined_z_score < -self.z_score_threshold:
            return 1.0
        elif combined_z_score > self.z_score_threshold:
            return -1.0
        else:
            return -combined_z_score / self.z_score_threshold

    async def execute(self, parameters, context):
        """Dashboard compatibility method with real indicators."""
        import pandas as pd
        import numpy as np
        from models.technical_indicators import TechnicalIndicators
        
        market_data = context.get("data", {}).get("data", {}).get("market", {})
        closes = market_data.get("close_prices", [])
        
        if not closes or len(closes) < 30:
            return {
                "signal": "HOLD",
                "confidence": 0.5,
                "reasons": ["Insufficient data to calculate indicators"]
            }
            
        prices = pd.Series(closes)
        rsi = TechnicalIndicators.rsi(prices, 14)
        macd_line, signal_line, _ = TechnicalIndicators.macd(prices)
        
        current_rsi = rsi.iloc[-1]
        current_macd = macd_line.iloc[-1]
        current_signal = signal_line.iloc[-1]
        
        reasons = []
        confidence = 0.5
        signal = "HOLD"
        
        if current_rsi < 35 and current_macd > current_signal:
            signal = "BUY"
            confidence = 0.85
            reasons.append(f"RSI is oversold ({current_rsi:.1f})")
            reasons.append("MACD bullish crossover")
        elif current_rsi > 65 and current_macd < current_signal:
            signal = "SELL"
            confidence = 0.85
            reasons.append(f"RSI is overbought ({current_rsi:.1f})")
            reasons.append("MACD bearish crossover")
        elif current_rsi < 45:
            signal = "BUY"
            confidence = 0.65
            reasons.append(f"RSI leans oversold ({current_rsi:.1f})")
        elif current_rsi > 55:
            signal = "SELL"
            confidence = 0.65
            reasons.append(f"RSI leans overbought ({current_rsi:.1f})")
        else:
            signal = "HOLD"
            confidence = 0.50
            reasons.append(f"RSI is neutral ({current_rsi:.1f})")
            
        return {
            "signal": signal,
            "confidence": round(confidence, 2),
            "reasons": reasons,
            "indicators": {
                "rsi": round(current_rsi, 2) if not pd.isna(current_rsi) else 50,
                "macd": round(current_macd, 2) if not pd.isna(current_macd) else 0,
                "macd_signal": round(current_signal, 2) if not pd.isna(current_signal) else 0
            }
        }

# Alias for main.py compatibility
QuantitativeAnalysisAgent = QuantAgent

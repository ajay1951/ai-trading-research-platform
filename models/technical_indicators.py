"""
Technical Indicators Library
Reusable TA calculations using NumPy/Pandas.
"""
import numpy as np
import pandas as pd
from typing import Tuple, List


class TechnicalIndicators:
    """Collection of technical indicator calculations."""
    
    @staticmethod
    def sma(prices: pd.Series, period: int = 20) -> pd.Series:
        """Simple Moving Average."""
        return prices.rolling(window=period).mean()
    
    @staticmethod
    def ema(prices: pd.Series, period: int = 20) -> pd.Series:
        """Exponential Moving Average."""
        return prices.ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def rsi(prices: pd.Series, period: int = 14) -> pd.Series:
        """Relative Strength Index."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    @staticmethod
    def macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """MACD indicator. Returns (macd_line, signal_line, histogram)."""
        ema_fast = prices.ewm(span=fast, adjust=False).mean()
        ema_slow = prices.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram
    
    @staticmethod
    def bollinger_bands(prices: pd.Series, period: int = 20, std_dev: float = 2) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Bollinger Bands. Returns (upper, middle, lower)."""
        middle = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        return upper, middle, lower
    
    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """Average True Range."""
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()
    
    @staticmethod
    def volume_ma(volume: pd.Series, period: int = 20) -> pd.Series:
        """Volume Moving Average."""
        return volume.rolling(window=period).mean()
    
    @staticmethod
    def stochastic(high: pd.Series, low: pd.Series, close: pd.Series, k_period: int = 14, d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
        """Stochastic Oscillator %K and %D."""
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()
        k = 100 * ((close - lowest_low) / (highest_high - lowest_low))
        d = k.rolling(window=d_period).mean()
        return k, d
    
    @staticmethod
    def momentum(prices: pd.Series, period: int = 14) -> pd.Series:
        """Price momentum (rate of change)."""
        return prices.diff(periods=period) / prices.shift(period) * 100

    @staticmethod
    def pairs_trading_signal(prices_a: pd.Series, prices_b: pd.Series, period: int = 20, threshold: float = 2.0) -> Tuple[pd.Series, str]:
        """
        Calculates rolling Z-score of price spread for pairs trading.
        Returns the zscore series and the current trading signal.
        """
        spread = prices_a - prices_b
        rolling_mean = spread.rolling(window=period).mean()
        rolling_std = spread.rolling(window=period).std()
        
        # Avoid division by zero
        rolling_std = rolling_std.replace(0, np.nan)
        zscore = (spread - rolling_mean) / rolling_std
        
        current_z = zscore.iloc[-1] if not zscore.empty else np.nan
        
        if pd.isna(current_z):
            signal = "HOLD"
        elif current_z >= threshold:
            signal = "SHORT A / LONG B"
        elif current_z <= -threshold:
            signal = "LONG A / SHORT B"
        else:
            signal = "HOLD"
            
        return zscore, signal

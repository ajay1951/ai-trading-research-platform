"""
Momentum Feature Engineering
============================
Point-in-Time causal momentum metrics:
- Relative Strength Index (RSI)
- Moving Average Convergence Divergence (MACD)
- Rate of Change (ROC)
- Fast/Slow Stochastic Oscillator (%K, %D)
- Donchian Channel Position
"""

import numpy as np
import pandas as pd


def compute_momentum_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes momentum indicators strictly based on historical data.
    """
    feat = pd.DataFrame(index=df.index)
    close = df["close"]
    high = df["high"]
    low = df["low"]

    # 1. RSI (14 period)
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, np.nan)
    feat["rsi_14"] = 100.0 - (100.0 / (1.0 + rs))

    # 2. MACD (12, 26, 9)
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema_12 - ema_26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    feat["macd"] = macd_line / close.replace(0, np.nan)
    feat["macd_signal"] = signal_line / close.replace(0, np.nan)
    feat["macd_hist"] = (macd_line - signal_line) / close.replace(0, np.nan)

    # 3. Rate of Change (ROC)
    feat["roc_6"] = (close - close.shift(6)) / close.shift(6).replace(0, np.nan)
    feat["roc_12"] = (close - close.shift(12)) / close.shift(12).replace(0, np.nan)
    feat["roc_24"] = (close - close.shift(24)) / close.shift(24).replace(0, np.nan)

    # 4. Stochastic Oscillator (%K, %D)
    low_14 = low.rolling(window=14).min()
    high_14 = high.rolling(window=14).max()
    feat["stoch_k"] = 100.0 * (close - low_14) / (high_14 - low_14 + 1e-8)
    feat["stoch_d"] = feat["stoch_k"].rolling(window=3).mean()

    # 5. Donchian Channel Position [0, 1]
    low_20 = low.rolling(window=20).min()
    high_20 = high.rolling(window=20).max()
    feat["donchian_pos_20"] = (close - low_20) / (high_20 - low_20 + 1e-8)

    return feat

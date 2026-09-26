"""
Volatility Feature Engineering
==============================
Point-in-Time causal volatility metrics:
- Rolling standard deviation of returns
- Average True Range (ATR)
- Parkinson Volatility (Extreme value estimator)
- Garman-Klass Volatility
- Bollinger Bandwidth
"""

import numpy as np
import pandas as pd


def compute_volatility_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes volatility indicators strictly based on historical data.
    """
    feat = pd.DataFrame(index=df.index)
    close = df["close"]
    high = df["high"]
    low = df["low"]

    # 1. Rolling realized volatility of returns
    ret = close.pct_change()
    feat["volatility_12"] = ret.rolling(window=12).std()
    feat["volatility_24"] = ret.rolling(window=24).std()
    feat["volatility_48"] = ret.rolling(window=48).std()

    # 2. Average True Range (ATR)
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    atr_14 = tr.rolling(window=14).mean()
    feat["atr_14"] = atr_14
    feat["atr_norm"] = atr_14 / close.replace(0, np.nan)

    # 3. Parkinson Volatility (uses High/Low range)
    # sigma_p = sqrt( 1 / (4 * ln(2)) * ln(H/L)^2 )
    hl_ratio = np.log(high / low.replace(0, np.nan))
    feat["parkinson_vol_24"] = np.sqrt(
        (1.0 / (4.0 * np.log(2.0))) * (hl_ratio ** 2).rolling(window=24).mean()
    )

    # 4. Bollinger Bandwidth
    sma_20 = close.rolling(window=20).mean()
    std_20 = close.rolling(window=20).std()
    upper = sma_20 + (2.0 * std_20)
    lower = sma_20 - (2.0 * std_20)
    feat["bollinger_bandwidth"] = (upper - lower) / sma_20.replace(0, np.nan)

    return feat

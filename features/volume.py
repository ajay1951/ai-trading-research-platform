"""
Volume Feature Engineering
==========================
Point-in-Time causal volume metrics:
- Volume Change (relative to rolling moving average)
- Volume Z-Score
- VWAP Deviation (Price distance from rolling VWAP)
- On-Balance Volume (OBV) trend
"""

import numpy as np
import pandas as pd


def compute_volume_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes volume indicators strictly based on historical data.
    """
    feat = pd.DataFrame(index=df.index)
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # 1. Volume relative to moving average
    vol_sma_20 = volume.rolling(window=20).mean()
    feat["volume_ratio_20"] = volume / vol_sma_20.replace(0, np.nan)

    # 2. Volume Z-Score
    vol_std_20 = volume.rolling(window=20).std()
    feat["volume_zscore_20"] = (volume - vol_sma_20) / vol_std_20.replace(0, np.nan)

    # 3. Rolling VWAP Deviation (Typical price * Volume)
    typical_price = (high + low + close) / 3.0
    cum_vol = volume.rolling(window=24).sum()
    cum_pv = (typical_price * volume).rolling(window=24).sum()
    vwap_24 = cum_pv / cum_vol.replace(0, np.nan)
    feat["vwap_deviation_24"] = (close - vwap_24) / vwap_24.replace(0, np.nan)

    # 4. On-Balance Volume (OBV) normalized by rolling std
    direction = np.sign(close.diff()).fillna(0.0)
    obv = (direction * volume).cumsum()
    obv_sma = obv.rolling(window=20).mean()
    obv_std = obv.rolling(window=20).std()
    feat["obv_zscore_20"] = (obv - obv_sma) / obv_std.replace(0, np.nan)

    return feat

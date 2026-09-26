"""
Price Feature Engineering
=========================
Point-in-Time causal price features with zero lookahead:
- Returns (pct_change)
- Log returns
- Normalized bar spread ((high - low) / close)
- Normalized body ratio ((close - open) / (high - low + 1e-8))
"""

import numpy as np
import pandas as pd


def compute_price_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes point-in-time causal price features.
    Assumes df contains 'open', 'high', 'low', 'close'.
    """
    feat = pd.DataFrame(index=df.index)
    
    # 1. Simple returns
    feat["return_1"] = df["close"].pct_change(1)
    feat["return_3"] = df["close"].pct_change(3)
    feat["return_6"] = df["close"].pct_change(6)
    feat["return_12"] = df["close"].pct_change(12)
    feat["return_24"] = df["close"].pct_change(24)

    # 2. Log returns
    feat["log_return_1"] = np.log(df["close"] / df["close"].shift(1))

    # 3. Bar structure features
    high_low_spread = df["high"] - df["low"]
    feat["bar_spread"] = high_low_spread / df["close"].replace(0, np.nan)
    feat["body_ratio"] = (df["close"] - df["open"]) / (high_low_spread + 1e-8)
    feat["upper_wick_ratio"] = (df["high"] - np.maximum(df["open"], df["close"])) / (high_low_spread + 1e-8)
    feat["lower_wick_ratio"] = (np.minimum(df["open"], df["close"]) - df["low"]) / (high_low_spread + 1e-8)

    return feat

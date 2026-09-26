"""
Unified Technical Feature Pipeline
==================================
Combines price, volatility, momentum, and volume features with strict point-in-time causality.
"""

from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np

from features.price import compute_price_features
from features.volatility import compute_volatility_features
from features.momentum import compute_momentum_features
from features.volume import compute_volume_features


class TechnicalFeaturePipeline:
    """
    Standardized quantitative feature extraction pipeline.
    Ensures zero forward lookahead and complete point-in-time alignment.
    """

    FEATURE_REGISTRY: Dict[str, Dict[str, Any]] = {
        "return_1": {"domain": "price", "lookback": 1, "formula": "close[t]/close[t-1] - 1"},
        "return_3": {"domain": "price", "lookback": 3, "formula": "close[t]/close[t-3] - 1"},
        "return_12": {"domain": "price", "lookback": 12, "formula": "close[t]/close[t-12] - 1"},
        "bar_spread": {"domain": "price", "lookback": 1, "formula": "(high - low) / close"},
        "body_ratio": {"domain": "price", "lookback": 1, "formula": "(close - open) / (high - low)"},
        "volatility_24": {"domain": "volatility", "lookback": 24, "formula": "std(returns, 24)"},
        "atr_norm": {"domain": "volatility", "lookback": 14, "formula": "atr(14) / close"},
        "parkinson_vol_24": {"domain": "volatility", "lookback": 24, "formula": "sqrt(1/(4*ln2) * mean(ln(H/L)^2))"},
        "bollinger_bandwidth": {"domain": "volatility", "lookback": 20, "formula": "(upper - lower) / sma"},
        "rsi_14": {"domain": "momentum", "lookback": 14, "formula": "100 - (100 / (1 + RS))"},
        "macd_hist": {"domain": "momentum", "lookback": 26, "formula": "(MACD - Signal) / close"},
        "roc_12": {"domain": "momentum", "lookback": 12, "formula": "(close[t] - close[t-12]) / close[t-12]"},
        "stoch_k": {"domain": "momentum", "lookback": 14, "formula": "(close - min(low,14)) / (max(high,14) - min(low,14))"},
        "donchian_pos_20": {"domain": "momentum", "lookback": 20, "formula": "(close - min(low,20)) / (max(high,20) - min(low,20))"},
        "volume_ratio_20": {"domain": "volume", "lookback": 20, "formula": "volume / sma(volume, 20)"},
        "volume_zscore_20": {"domain": "volume", "lookback": 20, "formula": "(volume - mean(volume)) / std(volume)"},
        "vwap_deviation_24": {"domain": "volume", "lookback": 24, "formula": "(close - vwap_24) / vwap_24"},
        "obv_zscore_20": {"domain": "volume", "lookback": 20, "formula": "(obv - mean(obv)) / std(obv)"}
    }

    def __init__(self, include_domains: Optional[List[str]] = None):
        self.include_domains = include_domains or ["price", "volatility", "momentum", "volume"]

    def transform(self, df: pd.DataFrame, dropna: bool = True) -> pd.DataFrame:
        """
        Extracts features from OHLCV dataframe.
        """
        req = ["open", "high", "low", "close", "volume"]
        for c in req:
            if c not in df.columns:
                raise ValueError(f"Input dataframe missing required column: '{c}'")

        feature_blocks = []

        if "price" in self.include_domains:
            feature_blocks.append(compute_price_features(df))
        if "volatility" in self.include_domains:
            feature_blocks.append(compute_volatility_features(df))
        if "momentum" in self.include_domains:
            feature_blocks.append(compute_momentum_features(df))
        if "volume" in self.include_domains:
            feature_blocks.append(compute_volume_features(df))

        X = pd.concat(feature_blocks, axis=1)

        if dropna:
            X = X.dropna()

        return X

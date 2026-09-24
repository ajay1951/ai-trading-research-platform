import numpy as np
import pandas as pd

class MomentumScreener:
    """
    Cross-Sectional Momentum & Relative Strength Screener.
    V1: Point-in-time safe, vectorized rank calculations.
    """
    def __init__(self, rs_window=168, vol_short=24, vol_long=480, breakout_window=480):
        self.rs_window = rs_window          # 7 days (168 hours)
        self.vol_short = vol_short          # 24 hours
        self.vol_long = vol_long            # 20 days (480 hours)
        self.breakout_window = breakout_window # 20 days (480 hours)

    def compute_cross_sectional_scores(self, closes_df, volumes_df, highs_df, lows_df, btc_symbol="BTCUSDT"):
        """
        Computes point-in-time momentum scores for all assets across the entire history.
        Returns a DataFrame of momentum scores with the same index/columns as closes_df.
        """
        print("[+] Vectorizing Cross-Sectional Momentum Scores...", flush=True)
        
        # 1. Calculate 7-Day Asset Returns & BTC Relative Strength
        returns_7d = closes_df.pct_change(periods=self.rs_window)
        btc_ret_7d = returns_7d[btc_symbol] if btc_symbol in returns_7d.columns else pd.Series(0, index=closes_df.index)
        
        # RS = Asset 7d return - BTC 7d return
        rs_df = returns_7d.sub(btc_ret_7d, axis=0)
        # Normalize RS using sigmoid/tanh-like clipping
        rs_norm = np.tanh(rs_df * 3.0) # -1 to +1
        
        # 2. Volume Expansion Factor (VEF: 24h Vol / 20d Avg Vol)
        vol_24h = volumes_df.rolling(window=self.vol_short, min_periods=1).mean()
        vol_20d = volumes_df.rolling(window=self.vol_long, min_periods=1).mean()
        vef_raw = (vol_24h / vol_20d.replace(0, np.nan)).fillna(1.0)
        # Normalize VEF: 1.0 = baseline, 2.5+ = high surge
        vef_norm = np.clip((vef_raw - 1.0) / 2.0, 0.0, 1.0)
        
        # 3. Donchian Breakout Score (Position within 20-Day Range: 0 to 1)
        high_20d = highs_df.rolling(window=self.breakout_window, min_periods=1).max()
        low_20d = lows_df.rolling(window=self.breakout_window, min_periods=1).min()
        range_20d = (high_20d - low_20d).replace(0, np.nan)
        breakout_score = ((closes_df - low_20d) / range_20d).fillna(0.5)
        breakout_norm = np.clip(breakout_score, 0.0, 1.0)
        
        # 4. Composite Momentum Score
        # 45% Weight to RS vs BTC + 30% Volume Spike + 25% Proximity to 20-Day High
        composite_score = (0.45 * rs_norm) + (0.30 * vef_norm) + (0.25 * breakout_norm)
        
        # Zero out BTCUSDT so it is never selected as a breakout altcoin
        if btc_symbol in composite_score.columns:
            composite_score[btc_symbol] = -999.0
            
        return composite_score, rs_df, breakout_norm

    def select_top_runners(self, score_row, rs_row, breakout_row, top_k=2, min_rs=0.02, min_breakout=0.65):
        """
        Filters and selects the top K momentum breakout runners for a single timestamp row.
        Returns a list of selected asset symbols.
        """
        # Exclude assets that fail basic momentum criteria
        valid_mask = (rs_row > min_rs) & (breakout_row >= min_breakout) & (score_row > 0.20)
        eligible = score_row[valid_mask]
        
        if eligible.empty:
            return [] # No coin qualified -> Hold 100% Cash!
            
        # Select top K highest scores
        top_assets = eligible.nlargest(top_k).index.tolist()
        return top_assets

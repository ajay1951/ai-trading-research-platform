import pandas as pd
import numpy as np
import os
import logging

logger = logging.getLogger(__name__)

class QuantFeatureEngineer:
    """
    Universal Multi-Timeframe Mathematical Engine (MTF).
    V2: Strictly Point-In-Time safe.
    """
    
    def __init__(self, asset_name="BTCUSDT", data_dir="data", base_timeframe="5m"):
        self.asset_name = asset_name
        self.data_dir = data_dir
        self.base_timeframe = base_timeframe
        
        # Load the base dataframe (Execution Frequency)
        self.df = self._query_timeframe(self.base_timeframe)
        if self.df is not None:
            self.df = self.df.sort_values('timestamp')
        
    def _query_timeframe(self, timeframe):
        filepath = os.path.join(self.data_dir, f"{self.asset_name}_{timeframe}_historical.csv")
        try:
            df = pd.read_csv(filepath)
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, format='ISO8601', errors='coerce')
            df = df.dropna(subset=['timestamp']).sort_values('timestamp')
            return df
        except Exception:
            return None

    def _merge_higher_timeframe(self, df_tf, feature_name):
        """
        Safely merges a higher timeframe feature onto the base timeframe.
        CRITICAL: Shifts the feature by 1 in the higher timeframe BEFORE merging
        to prevent lookahead bias (e.g., getting a full day's mean at 00:05).
        """
        if df_tf is None or self.df is None:
            self.df[feature_name] = 0.0
            return
            
        # Shift the feature down by 1 so the timestamp now holds the completely 
        # closed, finished data from the previous period.
        df_tf[feature_name] = df_tf[feature_name].shift(1)
        
        # Extract just timestamp and feature, drop NaNs caused by the shift/rolling
        df_merge = df_tf[['timestamp', feature_name]].dropna()
        
        # Merge asof backward. At 00:05, this looks for the closest timestamp <= 00:05 in df_merge.
        # It finds 00:00, which holds the shifted (finished) data from the prior period.
        self.df = pd.merge_asof(self.df, df_merge, on='timestamp', direction='backward')
        
        # Fill any initial NaNs before the first higher-timeframe period finished
        self.df[feature_name] = self.df[feature_name].ffill().fillna(0.0)

    def calculate_macro_trend(self):
        """Extracts Z-Scores for Macro timeframes (> 1d)"""
        if self.df is None: return self
        timeframes = {'1mo': 12, '1w': 52, '3d': 120}
        
        for tf, window in timeframes.items():
            df_tf = self._query_timeframe(tf)
            if df_tf is not None and len(df_tf) > window:
                roll_mean = df_tf['close'].rolling(window).mean()
                roll_std = df_tf['close'].rolling(window).std()
                # Calculate feature
                df_tf[f'{tf}_z_score'] = (df_tf['close'] - roll_mean) / roll_std.replace(0, 1)
                # Safely merge
                self._merge_higher_timeframe(df_tf, f'{tf}_z_score')
            else:
                self.df[f'{tf}_z_score'] = 0.0
                
        return self

    def calculate_base_trend(self):
        """Extracts trend and ATR on the base timeframe or 1d"""
        if self.df is None: return self
        
        # 1d Trend
        df_1d = self._query_timeframe("1d")
        if df_1d is not None and len(df_1d) > 200:
            roll_mean = df_1d['close'].rolling(200).mean()
            roll_std = df_1d['close'].rolling(200).std()
            df_1d['1d_z_score'] = (df_1d['close'] - roll_mean) / roll_std.replace(0, 1)
            self._merge_higher_timeframe(df_1d, '1d_z_score')
        else:
            self.df['1d_z_score'] = 0.0
        
        # ATR on the BASE timeframe (e.g., 5m ATR for 5m trading)
        high_low = self.df['high'] - self.df['low']
        high_close = np.abs(self.df['high'] - self.df['close'].shift())
        low_close = np.abs(self.df['low'] - self.df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        self.df['ATR_14'] = tr.rolling(14).mean().fillna(0)
        
        return self

    def calculate_intermediate_volatility(self):
        """Extracts Volatility for Intermediate timeframes (< 1d, >= 1h)"""
        if self.df is None: return self
        timeframes = {'12h': 60, '8h': 90, '6h': 120, '4h': 180, '2h': 360, '1h': 720}
        
        for tf, window in timeframes.items():
            df_tf = self._query_timeframe(tf)
            if df_tf is not None and len(df_tf) > window:
                df_tf[f'{tf}_volatility'] = df_tf['close'].pct_change().rolling(window).std()
                self._merge_higher_timeframe(df_tf, f'{tf}_volatility')
            else:
                self.df[f'{tf}_volatility'] = 0.0
                
        return self

    def calculate_micro_structure(self):
        """Extracts Volume Spikes for Micro timeframes (< 1h)"""
        if self.df is None: return self
        timeframes = {'30m': 48, '15m': 96, '5m': 288, '3m': 480, '1m': 1440}
        
        for tf, window in timeframes.items():
            df_tf = self._query_timeframe(tf)
            if df_tf is not None and len(df_tf) > window:
                roll_vol = df_tf['volume'].rolling(window).mean()
                df_tf[f'{tf}_volume_spike'] = df_tf['volume'] / roll_vol.replace(0, 1)
                
                if tf == self.base_timeframe:
                    # Native resolution, no need to shift-merge, just assign directly
                    self.df[f'{tf}_volume_spike'] = df_tf[f'{tf}_volume_spike'].fillna(1.0)
                else:
                    self._merge_higher_timeframe(df_tf, f'{tf}_volume_spike')
            else:
                self.df[f'{tf}_volume_spike'] = 1.0
                
        return self

    def merge_sentiment(self):
        if self.df is None: return self
        filepath = os.path.join(self.data_dir, f"{self.asset_name}_sentiment_2019_2026.csv")
        try:
            sent_df = pd.read_csv(filepath)
            sent_df['timestamp'] = pd.to_datetime(sent_df['timestamp'], utc=True, format='ISO8601', errors='coerce')
            sent_df = sent_df.sort_values('timestamp')
            
            # Since this is daily sentiment, we shift it by 1 day before merging asof
            sent_df['sentiment_score'] = sent_df['sentiment_score'].shift(1)
            sent_df = sent_df[['timestamp', 'sentiment_score']].dropna()
            
            self.df = pd.merge_asof(self.df, sent_df, on='timestamp', direction='backward')
            self.df['sentiment_score'] = self.df['sentiment_score'].ffill().fillna(0.0)
        except Exception:
            self.df['sentiment_score'] = 0.0
            
        return self

    def calculate_advanced_ohlcv(self):
        """Calculates RSI, MACD, BB_Width, and Log Returns directly on the base timeframe."""
        if self.df is None: return self
        
        # Log Returns
        self.df['log_return'] = np.log(self.df['close'] / self.df['close'].shift(1)).fillna(0.0)
        
        # RSI 14
        delta = self.df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss.replace(0, 1)
        self.df['RSI_14'] = 100 - (100 / (1 + rs))
        self.df['RSI_14'] = self.df['RSI_14'].fillna(50.0)
        
        # MACD (12, 26, 9)
        ema12 = self.df['close'].ewm(span=12, adjust=False).mean()
        ema26 = self.df['close'].ewm(span=26, adjust=False).mean()
        self.df['MACD'] = ema12 - ema26
        macd_signal = self.df['MACD'].ewm(span=9, adjust=False).mean()
        self.df['MACD_hist'] = self.df['MACD'] - macd_signal
        self.df['MACD_hist'] = self.df['MACD_hist'].fillna(0.0)
        
        # Bollinger Bands Width (20, 2)
        roll_mean20 = self.df['close'].rolling(20).mean()
        roll_std20 = self.df['close'].rolling(20).std()
        upper_band = roll_mean20 + (roll_std20 * 2)
        lower_band = roll_mean20 - (roll_std20 * 2)
        self.df['BB_Width'] = (upper_band - lower_band) / roll_mean20.replace(0, 1)
        self.df['BB_Width'] = self.df['BB_Width'].fillna(0.0)
        
        return self

    def merge_derivatives(self):
        """Merges Funding Rate and Open Interest safely without lookahead bias."""
        if self.df is None: return self
        asset_csv_name = self.asset_name.replace("/", "")
        
        # Funding Rate
        fund_path = os.path.join(self.data_dir, f"{asset_csv_name}_funding.csv")
        try:
            df_fund = pd.read_csv(fund_path)
            df_fund['timestamp'] = pd.to_datetime(df_fund['timestamp'], utc=True, format='ISO8601', errors='coerce')
            df_fund = df_fund.sort_values('timestamp').dropna()
            # Funding is usually paid every 8h. We shift by 1 to ensure the rate is locked in
            df_fund['funding_rate'] = df_fund['funding_rate'].shift(1)
            df_fund = df_fund.dropna()
            self.df = pd.merge_asof(self.df, df_fund, on='timestamp', direction='backward')
            self.df['funding_rate'] = self.df['funding_rate'].ffill().fillna(0.0)
        except Exception:
            self.df['funding_rate'] = 0.0
            
        # Open Interest
        oi_path = os.path.join(self.data_dir, f"{asset_csv_name}_oi.csv")
        try:
            df_oi = pd.read_csv(oi_path)
            df_oi['timestamp'] = pd.to_datetime(df_oi['timestamp'], utc=True, format='ISO8601', errors='coerce')
            df_oi = df_oi.sort_values('timestamp').dropna()
            # OI is fetched at 5m resolution. Shift by 1 to avoid current-candle leakage
            df_oi['open_interest'] = df_oi['open_interest'].shift(1)
            df_oi = df_oi.dropna()
            self.df = pd.merge_asof(self.df, df_oi, on='timestamp', direction='backward')
            self.df['open_interest'] = self.df['open_interest'].ffill().fillna(0.0)
        except Exception:
            self.df['open_interest'] = 0.0
            
        return self

    def merge_macro_economic_data(self):
        """Merges Daily Macro-Economic Indicators (DXY, SPX, TNX) safely."""
        if self.df is None: return self
        try:
            import yfinance as yf
            macro_path = os.path.join(self.data_dir, "macro_daily.csv")
            
            # Use offline macro_daily.csv if present. Only download if file is completely missing.
            if not os.path.exists(macro_path):
                tickers = ['DX-Y.NYB', '^GSPC', '^TNX']
                macro_data = yf.download(tickers, start="2019-01-01", progress=False)['Close']
                macro_data = macro_data.ffill().dropna()
                # yfinance returns alphabetical columns: DX-Y.NYB, ^GSPC, ^TNX
                macro_data.columns = ['DXY', 'SPX', 'TNX']
                macro_data.index = pd.to_datetime(macro_data.index, utc=True)
                macro_data.to_csv(macro_path)
            
            macro_df = pd.read_csv(macro_path)
            macro_df['timestamp'] = pd.to_datetime(macro_df['Date'], utc=True)
            macro_df = macro_df.drop('Date', axis=1).sort_values('timestamp')
            
            # CRITICAL: Shift by 1 to prevent lookahead bias (today's close isn't known until tomorrow)
            macro_df['DXY'] = macro_df['DXY'].shift(1)
            macro_df['SPX'] = macro_df['SPX'].shift(1)
            macro_df['TNX'] = macro_df['TNX'].shift(1)
            macro_df = macro_df.dropna()
            
            self.df = pd.merge_asof(self.df, macro_df, on='timestamp', direction='backward')
            # Use bfill for the very first few days of 2019 so scaling doesn't fail on 0.0
            self.df['DXY'] = self.df['DXY'].ffill().bfill()
            self.df['SPX'] = self.df['SPX'].ffill().bfill()
            self.df['TNX'] = self.df['TNX'].ffill().bfill()
            
        except Exception as e:
            logger.warning(f"Failed to merge macro data: {e}")
            self.df['DXY'] = 0.0
            self.df['SPX'] = 0.0
            self.df['TNX'] = 0.0
            
        return self

    def get_features(self):
        if self.df is None: return pd.DataFrame()
        
        if 'timestamp' in self.df.columns:
            self.df = self.df.set_index('timestamp')
            
        return self.df

    def close(self):
        pass

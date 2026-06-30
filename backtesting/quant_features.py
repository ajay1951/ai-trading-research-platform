import pandas as pd
import numpy as np
import os

class QuantFeatureEngineer:
    """
    Universal Multi-Timeframe Mathematical Engine (MTF).
    Ingests all 15 timeframes to give the AI complete market X-ray vision.
    """
    
    def __init__(self, asset_name="BTCUSDT", data_dir="data"):
        self.asset_name = asset_name
        self.data_dir = data_dir
        
        # Load the base 1d dataframe (Execution Frequency)
        self.df = self._query_timeframe("1d")
        if self.df is not None:
            self.df['date'] = self.df['timestamp'].dt.date
        
    def _query_timeframe(self, timeframe):
        filepath = os.path.join(self.data_dir, f"{self.asset_name}_{timeframe}_historical.csv")
        try:
            df = pd.read_csv(filepath)
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, format='ISO8601', errors='coerce')
            df = df.dropna(subset=['timestamp']).sort_values('timestamp')
            df['date'] = df['timestamp'].dt.date
            return df
        except Exception:
            # Silently return None if a timeframe is completely missing
            return None

    def calculate_macro_trend(self):
        """Extracts Z-Scores for Macro timeframes (> 1d)"""
        if self.df is None: return self
        timeframes = {'1mo': 12, '1w': 52, '3d': 120}
        
        for tf, window in timeframes.items():
            df_tf = self._query_timeframe(tf)
            if df_tf is not None and len(df_tf) > window:
                roll_mean = df_tf['close'].rolling(window).mean()
                roll_std = df_tf['close'].rolling(window).std()
                df_tf[f'{tf}_z_score'] = ((df_tf['close'] - roll_mean) / roll_std).fillna(0)
                
                # Merge daily aggregate (last known value per day)
                daily_val = df_tf.groupby('date')[f'{tf}_z_score'].last().reset_index()
                self.df = pd.merge(self.df, daily_val, on='date', how='left')
                self.df[f'{tf}_z_score'] = self.df[f'{tf}_z_score'].ffill().fillna(0)
            else:
                self.df[f'{tf}_z_score'] = 0.0
                
        return self

    def calculate_base_trend(self):
        """Extracts Base 1d trend and ATR"""
        if self.df is None: return self
        roll_mean = self.df['close'].rolling(200).mean()
        roll_std = self.df['close'].rolling(200).std()
        self.df['1d_z_score'] = ((self.df['close'] - roll_mean) / roll_std).fillna(0)
        
        # Add ATR for risk agent
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
                df_tf[f'{tf}_volatility'] = df_tf['close'].pct_change().rolling(window).std().fillna(0)
                daily_vol = df_tf.groupby('date')[f'{tf}_volatility'].mean().reset_index()
                self.df = pd.merge(self.df, daily_vol, on='date', how='left')
                self.df[f'{tf}_volatility'] = self.df[f'{tf}_volatility'].ffill().fillna(0)
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
                # Calculate if volume is X times higher than the rolling average
                roll_vol = df_tf['volume'].rolling(window).mean()
                df_tf[f'{tf}_volume_spike'] = (df_tf['volume'] / roll_vol.replace(0, 1)).fillna(1.0)
                daily_spike = df_tf.groupby('date')[f'{tf}_volume_spike'].max().reset_index()
                self.df = pd.merge(self.df, daily_spike, on='date', how='left')
                self.df[f'{tf}_volume_spike'] = self.df[f'{tf}_volume_spike'].ffill().fillna(1.0)
            else:
                self.df[f'{tf}_volume_spike'] = 1.0
                
        return self

    def merge_sentiment(self):
        if self.df is None: return self
        filepath = os.path.join(self.data_dir, f"{self.asset_name}_sentiment_2019_2026.csv")
        try:
            sent_df = pd.read_csv(filepath)
            sent_df['timestamp'] = pd.to_datetime(sent_df['timestamp'], utc=True, format='ISO8601', errors='coerce')
            sent_df['date'] = sent_df['timestamp'].dt.date
            
            daily_sentiment = sent_df.groupby('date')['sentiment_score'].mean().reset_index()
            self.df = pd.merge(self.df, daily_sentiment, on='date', how='left')
            self.df['sentiment_score'] = self.df['sentiment_score'].ffill().fillna(0.0)
        except Exception:
            self.df['sentiment_score'] = 0.0
            
        return self

    def get_features(self):
        if self.df is None: return pd.DataFrame()
        
        if 'timestamp' in self.df.columns:
            self.df = self.df.set_index('timestamp')
            
        if 'date' in self.df.columns:
            return self.df.drop(columns=['date'])
        return self.df

    def close(self):
        pass

import os
import sys
import time

sys.path.append(r"c:\Users\ajayg\ai_crypto_bot\backtesting")
from quant_features import QuantFeatureEngineer

data_dir = r"c:\Users\ajayg\ai_crypto_bot\data"
t0 = time.time()
print("Testing 1h QuantFeatureEngineer on BTCUSDT...")
engineer = QuantFeatureEngineer(asset_name="BTCUSDT", data_dir=data_dir, base_timeframe="1h")
engineer.calculate_macro_trend()
engineer.calculate_base_trend()
engineer.calculate_intermediate_volatility()
engineer.calculate_micro_structure()
engineer.merge_sentiment()
df = engineer.get_features()
print(f"Loaded {len(df)} 1h rows in {time.time() - t0:.2f}s")
print("Columns:", len(df.columns))
print("Sample timestamp:", df.index[0], "to", df.index[-1])

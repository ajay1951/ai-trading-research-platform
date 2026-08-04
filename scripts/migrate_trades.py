import pandas as pd
import os

file_path = "data/live_trades.csv"

if os.path.exists(file_path):
    print(f"Migrating {file_path}...")
    df = pd.read_csv(file_path)
    if 'pnl' not in df.columns:
        df['pnl'] = "0.00"
        df.to_csv(file_path, index=False)
        print("Successfully added 'pnl' column to existing trades.")
    else:
        print("'pnl' column already exists.")
else:
    print(f"{file_path} does not exist. Nothing to migrate.")

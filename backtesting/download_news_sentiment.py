import os
import glob
import pandas as pd
from datetime import datetime
from tqdm import tqdm
try:
    import kaggle
except OSError:
    print("[!] Kaggle API key not found. Please ensure kaggle.json is in your ~/.kaggle/ folder.")
    exit(1)

from transformers import pipeline

def load_csv_safely(file_path):
    print(f"    -> Loading {file_path}")
    try:
        # Some Kaggle CSVs have bad lines or encoding issues
        df = pd.read_csv(file_path, on_bad_lines='skip', encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(file_path, on_bad_lines='skip', encoding='ISO-8859-1')
    except Exception as e:
        print(f"       [!] Failed to load {file_path}: {e}")
        return pd.DataFrame()

    text_cols = [c for c in df.columns if 'title' in c.lower() or 'headline' in c.lower() or 'text' in c.lower()]
    date_cols = [c for c in df.columns if 'date' in c.lower() or 'time' in c.lower() or 'published' in c.lower()]
    
    if not text_cols or not date_cols:
        return pd.DataFrame()
        
    df = df[[date_cols[0], text_cols[0]]].dropna()
    df.columns = ['timestamp', 'headline']
    return df

def download_and_process_news():
    print("="*60)
    print("Starting Frankenstein Data Merge & FinBERT Analyzer")
    print("="*60)
    
    download_dir = "data_temp"
    os.makedirs(download_dir, exist_ok=True)
    
    datasets = [
        "oliviervha/crypto-news", # 2014 to 2023
        "n107hoangtuong/news-crypto", # 2024 to early 2026?
        "kyrylokamennyk/argus-crypto-news-analysis" # April 2026 to June 16 2026
    ]
    
    all_dfs = []
    
    for ds in datasets:
        print(f"\n[1] Downloading Kaggle Dataset: {ds}...")
        kaggle.api.dataset_download_files(ds, path=download_dir, unzip=True)
        
    print("\n[2] Loading and merging datasets...")
    # Load all CSVs
    for f in glob.glob(os.path.join(download_dir, "*.csv")):
        df = load_csv_safely(f)
        if not df.empty:
            all_dfs.append(df)
            
    # Load all Parquets
    for f in glob.glob(os.path.join(download_dir, "*.parquet")):
        print(f"    -> Loading {f}")
        try:
            df = pd.read_parquet(f)
            text_cols = [c for c in df.columns if 'title' in c.lower() or 'headline' in c.lower() or 'text' in c.lower()]
            date_cols = [c for c in df.columns if 'date' in c.lower() or 'time' in c.lower() or 'published' in c.lower()]
            if text_cols and date_cols:
                df = df[[date_cols[0], text_cols[0]]].dropna()
                df.columns = ['timestamp', 'headline']
                all_dfs.append(df)
        except Exception as e:
            pass

    if not all_dfs:
        print("[!] No valid data found to merge.")
        return
        
    mega_df = pd.concat(all_dfs, ignore_index=True)
    
    print("\n[3] Cleaning and standardizing dates...")
    mega_df['timestamp'] = pd.to_datetime(mega_df['timestamp'], errors='coerce', utc=True)
    mega_df = mega_df.dropna(subset=['timestamp'])
    
    # Drop exact duplicate headlines
    mega_df = mega_df.drop_duplicates(subset=['headline'])
    mega_df = mega_df.sort_values('timestamp')
    
    print(f" -> Unified Dataset: {len(mega_df)} total unique headlines.")
    print(f" -> Date Range: {mega_df['timestamp'].min()} to {mega_df['timestamp'].max()}")
    
    coins = {
        'BTC': ['bitcoin', 'btc'],
        'ETH': ['ethereum', 'eth'],
        'SOL': ['solana', 'sol'],
        'XRP': ['ripple', 'xrp'],
        'BNB': ['binance coin', 'bnb', 'binance']
    }
    
    print("\n[4] Initializing FinBERT Sentiment AI (This may take a while to load)...")
    # Using ProsusAI/finbert
    sentiment_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert")
    
    def get_finbert_score(text):
        # Finbert returns [{'label': 'positive', 'score': 0.94}]
        # We need to cap text length because BERT max tokens is 512
        try:
            # truncate text roughly to avoid crash
            short_text = str(text)[:1500] 
            res = sentiment_pipeline(short_text)[0]
            label = res['label']
            score = res['score']
            if label == 'positive':
                return score
            elif label == 'negative':
                return -score
            else:
                return 0.0
        except Exception:
            return 0.0

    print("\n[5] Filtering & Scoring per coin...")
    # Setup tqdm for pandas
    tqdm.pandas()
    
    out_dir = "data"
    os.makedirs(out_dir, exist_ok=True)
    
    for coin, keywords in coins.items():
        pattern = '|'.join([rf'\b{kw}\b' for kw in keywords])
        coin_df = mega_df[mega_df['headline'].str.contains(pattern, case=False, na=False)].copy()
        
        print(f"\n -> {coin}: Found {len(coin_df)} matching headlines. Running FinBERT scoring...")
        
        if len(coin_df) > 0:
            # We use progress_apply to show a progress bar because FinBERT is slow
            coin_df['sentiment_score'] = coin_df['headline'].progress_apply(get_finbert_score)
            
            out_name = os.path.join(out_dir, f"{coin}USDT_sentiment_2019_2026.csv")
            coin_df.to_csv(out_name, index=False)
            print(f"    [OK] Saved to {out_name}")
            
    print("\n[6] Cleaning up temp raw datasets...")
    try:
        for f in glob.glob(os.path.join(download_dir, "*")):
            os.remove(f)
        os.rmdir(download_dir)
        print(" -> Temp files deleted successfully.")
    except Exception as e:
        print(" -> Could not delete all temp files.")
        
    print("\n[OK] All FinBERT Processing Complete!")

if __name__ == "__main__":
    download_and_process_news()

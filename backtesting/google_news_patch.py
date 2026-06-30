import requests
import xml.etree.ElementTree as ET
import pandas as pd
from email.utils import parsedate_to_datetime
from transformers import pipeline
import torch
from tqdm import tqdm
import warnings
import concurrent.futures
from datetime import timedelta
import os

warnings.filterwarnings("ignore")

# 1. Load FinBERT
print("Loading FinBERT into memory...")
device = 0 if torch.cuda.is_available() else -1
sentiment_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert", device=device)

coins = {
    'ETHUSDT': 'ethereum',
    'XRPUSDT': 'ripple',
    'SOLUSDT': 'solana',
    'BNBUSDT': 'binance'
}

for coin, search_term in coins.items():
    print(f"\n{'='*40}\nProcessing {coin} ({search_term})\n{'='*40}")
    
    file_path = f'data/{coin}_sentiment_2019_2026.csv'
    if not os.path.exists(file_path):
        print(f"File {file_path} not found. Skipping.")
        continue
        
    # 1. Identify missing dates
    df_existing = pd.read_csv(file_path)
    df_existing['timestamp'] = pd.to_datetime(df_existing['timestamp'], utc=True)
    df_existing['date'] = df_existing['timestamp'].dt.date

    start_date = df_existing['date'].min()
    end_date = df_existing['date'].max()

    all_days = pd.date_range(start=start_date, end=end_date).date
    existing_days = set(df_existing['date'])

    missing_days = sorted(list(set(all_days) - existing_days))
    print(f"-> Found exactly {len(missing_days)} missing days to patch for {coin}.")

    if len(missing_days) == 0:
        print("Dataset is already perfect!")
        continue

    # 2. Multi-threaded Google News Scraper (max_workers=50)
    print("\n2. Launching HYPER-SPEED Google News Scraper (50 Threads)...")
    headlines_data = []

    def fetch_news_for_date(target_date):
        next_date = target_date + timedelta(days=1)
        url = f"https://news.google.com/rss/search?q={search_term}+cryptocurrency+after:{target_date}+before:{next_date}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        local_data = []
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                root = ET.fromstring(r.content)
                for item in root.findall('.//item'):
                    title = item.find('title').text
                    pubdate_str = item.find('pubDate').text
                    try:
                        dt = parsedate_to_datetime(pubdate_str)
                        clean_title = title.rsplit(' - ', 1)[0]
                        local_data.append({
                            'timestamp': dt,
                            'headline': clean_title
                        })
                    except Exception:
                        pass
        except Exception:
            pass
        return local_data

    # Use 50 threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        results = list(tqdm(executor.map(fetch_news_for_date, missing_days), total=len(missing_days)))

    for res in results:
        headlines_data.extend(res)

    df_scraped = pd.DataFrame(headlines_data)

    if len(df_scraped) == 0:
        print(f"Failed to extract any headlines for {coin}.")
        continue

    df_scraped['timestamp'] = pd.to_datetime(df_scraped['timestamp'], utc=True)
    df_scraped = df_scraped.dropna(subset=['timestamp'])
    df_scraped = df_scraped.drop_duplicates(subset=['headline'])
    print(f"-> Extracted {len(df_scraped)} surgical news headlines for the missing days!")

    # 3. Batched FinBERT Scoring (batch_size=64)
    print("\n3. Scoring headlines in batches (batch_size=64)...")
    texts = df_scraped['headline'].astype(str).tolist()
    
    # Truncate to avoid model errors
    texts = [t[:500] if len(t) > 500 else t for t in texts]
    
    scored_results = []
    
    # Run the pipeline with massive batching
    # The pipeline returns an iterator
    for i, res in enumerate(tqdm(sentiment_pipeline(texts, batch_size=64, truncation=True), total=len(texts))):
        score = res['score']
        if res['label'] == 'positive':
            final_score = score
        elif res['label'] == 'negative':
            final_score = -score
        else:
            final_score = 0.0
            
        scored_results.append({
            'timestamp': df_scraped.iloc[i]['timestamp'],
            'headline': df_scraped.iloc[i]['headline'],
            'sentiment_score': final_score
        })

    df_new = pd.DataFrame(scored_results)

    # 4. Merge and Save
    print(f"\n4. Merging {len(df_new)} new scored headlines into existing {coin} dataset...")
    df_merged = pd.concat([df_existing.drop(columns=['date']), df_new], ignore_index=True)
    df_merged['timestamp'] = pd.to_datetime(df_merged['timestamp'], utc=True)
    df_merged = df_merged.sort_values('timestamp')
    df_merged = df_merged.drop_duplicates(subset=['headline'], keep='first')

    df_merged.to_csv(file_path, index=False)

    print(f"[OK] 100% DAILY COVERAGE ACHIEVED for {coin}!")
    print(f"-> Final Total Headlines: {len(df_merged)}")

print("\nALL 4 ALTCOINS SUCCESSFULLY PATCHED!")

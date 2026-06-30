import requests
import json
import xml.etree.ElementTree as ET
import pandas as pd
from email.utils import parsedate_to_datetime
from transformers import pipeline
import torch
from tqdm import tqdm
import warnings
import time

warnings.filterwarnings("ignore")

print("1. Querying Wayback Machine for CoinTelegraph RSS snapshots...")
cdx_url = "http://web.archive.org/cdx/search/cdx?url=https://cointelegraph.com/rss&from=20250604&to=20260409&output=json&fl=timestamp,original"

try:
    res = requests.get(cdx_url)
    res.raise_for_status()
    data = res.json()
except Exception as e:
    print(f"Error hitting CDX API: {e}")
    exit(1)

# data[0] is headers ['timestamp', 'original']
if len(data) <= 1:
    print("No snapshots found in this range!")
    exit(0)

# To prevent overloading the archive and speeding up processing, 
# we'll just grab one snapshot per day. RSS feeds hold ~30-50 items so daily is perfect.
snapshots = data[1:]
daily_snapshots = {}
for snap in snapshots:
    timestamp, original = snap
    day = timestamp[:8] # YYYYMMDD
    if day not in daily_snapshots:
        daily_snapshots[day] = snap

print(f"Found {len(snapshots)} total snapshots. Filtered to {len(daily_snapshots)} daily snapshots to scrape.")

headlines_data = []

print("2. Downloading and Parsing Historical XML...")
# Wrap in tqdm for progress bar
for day, snap in tqdm(daily_snapshots.items(), total=len(daily_snapshots)):
    timestamp, original = snap
    # 'id_' tells wayback machine to return the raw file without the HTML wrapper
    raw_url = f"http://web.archive.org/web/{timestamp}id_/{original}"
    
    try:
        r = requests.get(raw_url, timeout=10)
        r.raise_for_status()
        
        # Parse XML
        root = ET.fromstring(r.content)
        for item in root.findall('.//item'):
            title_elem = item.find('title')
            pubdate_elem = item.find('pubDate')
            
            if title_elem is not None and pubdate_elem is not None:
                title = title_elem.text
                pubdate_str = pubdate_elem.text
                
                try:
                    dt = parsedate_to_datetime(pubdate_str)
                    headlines_data.append({
                        'timestamp': dt,
                        'headline': title
                    })
                except Exception:
                    pass
    except Exception as e:
        # Ignore dead snapshots
        continue
    
    # Tiny sleep to respect Wayback Machine rate limits
    time.sleep(0.5)

df_scraped = pd.DataFrame(headlines_data)

if len(df_scraped) == 0:
    print("Failed to extract any headlines.")
    exit(1)

df_scraped['timestamp'] = pd.to_datetime(df_scraped['timestamp'], utc=True)
df_scraped = df_scraped.dropna(subset=['timestamp'])

# Filter out of bounds
start_gap = pd.to_datetime('2025-06-04', utc=True)
end_gap = pd.to_datetime('2026-04-10', utc=True)
df_gap = df_scraped[(df_scraped['timestamp'] >= start_gap) & (df_scraped['timestamp'] <= end_gap)].copy()

df_gap = df_gap.drop_duplicates(subset=['headline'])
print(f"\n-> Successfully extracted {len(df_gap)} unique headlines from the Wayback Machine!")

print("\n3. Loading FinBERT to score missing headlines...")
device = 0 if torch.cuda.is_available() else -1
sentiment_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert", device=device)

results = []
print("Scoring gap headlines...")
for _, row in tqdm(df_gap.iterrows(), total=len(df_gap)):
    text = str(row['headline'])
    if pd.isna(text) or text.strip() == "":
        continue
        
    try:
        res = sentiment_pipeline(text[:500])[0]
        score = res['score']
        if res['label'] == 'positive':
            final_score = score
        elif res['label'] == 'negative':
            final_score = -score
        else:
            final_score = 0.0
            
        results.append({
            'timestamp': row['timestamp'],
            'headline': text,
            'sentiment_score': final_score
        })
    except Exception as e:
        continue

df_new = pd.DataFrame(results)

print(f"\n4. Merging {len(df_new)} new scored headlines into existing BTC dataset...")
df_existing = pd.read_csv('data/BTCUSDT_sentiment_2019_2026.csv')
df_existing['timestamp'] = pd.to_datetime(df_existing['timestamp'], utc=True)

df_merged = pd.concat([df_existing, df_new], ignore_index=True)
df_merged = df_merged.sort_values('timestamp')
df_merged = df_merged.drop_duplicates(subset=['headline'], keep='first')

df_merged.to_csv('data/BTCUSDT_sentiment_2019_2026.csv', index=False)

print("\n[OK] FINAL GAP PATCHED using the Internet Archive!")
print(f"-> New Total BTC Headlines: {len(df_merged)}")

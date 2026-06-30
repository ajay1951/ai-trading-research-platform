import pandas as pd
from datasets import load_dataset
from transformers import pipeline
from tqdm import tqdm
import torch
import warnings
warnings.filterwarnings("ignore")

print("1. Loading HuggingFace dataset 'edaschau/bitcoin_news'...")
ds = load_dataset('edaschau/bitcoin_news', split='train')

print("2. Converting to Pandas and filtering for 2024-09-16 to 2026-04-09...")
df_hf = ds.to_pandas()
df_hf['date_time'] = pd.to_datetime(df_hf['date_time'], utc=True, errors='coerce')
df_hf = df_hf.dropna(subset=['date_time'])

# Filter for the massive blind spot
start_gap = pd.to_datetime('2024-09-15', utc=True)
end_gap = pd.to_datetime('2026-04-10', utc=True)
df_gap = df_hf[(df_hf['date_time'] >= start_gap) & (df_hf['date_time'] <= end_gap)].copy()

# Deduplicate by title to save processing time
df_gap = df_gap.drop_duplicates(subset=['title'])
print(f"-> Found {len(df_gap)} headlines missing in the gap!")

if len(df_gap) == 0:
    print("No headlines found in this gap for this dataset.")
    exit(0)

print("\n3. Loading FinBERT to score missing headlines...")
device = 0 if torch.cuda.is_available() else -1
sentiment_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert", device=device)

results = []
print("Scoring gap headlines...")
for _, row in tqdm(df_gap.iterrows(), total=len(df_gap)):
    text = str(row['title'])
    if pd.isna(text) or text.strip() == "":
        continue
        
    try:
        # FinBERT expects max 512 tokens
        res = sentiment_pipeline(text[:500])[0]
        score = res['score']
        # Convert label to numerical mapping
        if res['label'] == 'positive':
            final_score = score
        elif res['label'] == 'negative':
            final_score = -score
        else: # neutral
            final_score = 0.0
            
        results.append({
            'timestamp': row['date_time'],
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

print("\n[OK] Gap perfectly patched and CSV saved!")
print(f"-> New Total BTC Headlines: {len(df_merged)}")

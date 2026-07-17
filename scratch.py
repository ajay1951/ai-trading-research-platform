import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

def analyze_history():
    print("Fetching BTC history...")
    ticker = yf.Ticker("BTC-USD")
    
    # Calculate date 7 years ago
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7*365)
    
    # Fetch data
    df = ticker.history(start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"), interval="1mo")
    
    if df.empty:
        print("No data found.")
        return
        
    print(f"Total months: {len(df)}")
    
    # Analyze yearly high/lows
    df['Year'] = df.index.year
    yearly_stats = df.groupby('Year').agg({
        'High': 'max',
        'Low': 'min',
        'Close': 'last'
    })
    
    print("\nYearly Stats:")
    for year, row in yearly_stats.iterrows():
        print(f"Year {year}: Low = ${row['Low']:,.0f}, High = ${row['High']:,.0f}, Close = ${row['Close']:,.0f}")
        
    # Overall High and Low
    all_time_high = df['High'].max()
    all_time_low = df['Low'].min()
    
    print(f"\n7-Year Low: ${all_time_low:,.0f}")
    print(f"7-Year High: ${all_time_high:,.0f}")

if __name__ == "__main__":
    analyze_history()

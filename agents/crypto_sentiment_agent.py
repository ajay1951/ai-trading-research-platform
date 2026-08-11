import logging
import feedparser
from textblob import TextBlob
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CryptoSentimentAgent")

class CryptoSentimentAgent:
    def __init__(self):
        """
        Initializes the Sentiment Agent using 100% free public RSS feeds
        and a local NLP engine (TextBlob) instead of expensive OpenAI calls.
        """
        # We use CoinDesk and CryptoPanic free RSS feeds
        self.news_sources = [
            "https://www.coindesk.com/arc/outboundfeeds/rss/",
            "https://cointelegraph.com/rss",
            "https://cryptopanic.com/news/rss/"
        ]
        
        # Keywords that represent extreme market danger
        self.panic_keywords = ["hacked", "bankrupt", "sec sues", "arrested", "stolen", "collapse", "liquidated"]

    def analyze_market_sentiment(self, symbol="BTC") -> dict:
        """
        Scans global news headlines for the specific symbol.
        Returns a sentiment score (-1.0 to 1.0) and a boolean VETO flag.
        """
        logger.info(f"[NLP] Scanning global news feeds for {symbol}...")
        
        total_polarity = 0.0
        headline_count = 0
        veto_triggered = False
        veto_reason = ""

        try:
            for feed_url in self.news_sources:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:20]: # Check top 20 headlines per source
                    title = entry.title.lower()
                    
                    # Only analyze headlines relevant to our coin (or general macro)
                    base_coin = symbol.replace("USDT", "").lower()
                    if base_coin in title or "crypto" in title or "bitcoin" in title:
                        
                        # 1. Check for catastrophic Black Swan events (VETO)
                        if any(panic_word in title for panic_word in self.panic_keywords):
                            veto_triggered = True
                            veto_reason = f"CRITICAL: Panic keyword found in headline: '{title}'"
                            logger.error(f"[VETO OVERRIDE] {veto_reason}")
                            break # No need to keep reading, market is crashing
                        
                        # 2. Perform Natural Language Processing (NLP) math
                        blob = TextBlob(entry.title)
                        total_polarity += blob.sentiment.polarity
                        headline_count += 1
                        
                if veto_triggered:
                    break
                    
            if headline_count == 0:
                average_sentiment = 0.0
            else:
                average_sentiment = total_polarity / headline_count
                
            return {
                "sentiment_score": round(average_sentiment, 3), # E.g., 0.45 (Bullish) or -0.80 (Bearish)
                "veto": veto_triggered,
                "veto_reason": veto_reason,
                "analyzed_articles": headline_count
            }
            
        except Exception as e:
            logger.error(f"Failed to fetch news sentiment: {e}")
            return {"sentiment_score": 0.0, "veto": False, "veto_reason": "", "analyzed_articles": 0}

if __name__ == "__main__":
    # Test the agent
    agent = CryptoSentimentAgent()
    result = agent.analyze_market_sentiment("BTCUSDT")
    print(f"\n--- Sentiment Analysis Result ---")
    print(f"Score: {result['sentiment_score']} (-1 to 1)")
    print(f"Veto Active: {result['veto']}")
    if result['veto']:
        print(f"Reason: {result['veto_reason']}")

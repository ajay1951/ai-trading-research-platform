"""
Real-Time Data Retrieval Agent
Fetches market data via REST and WebSocket, news wires, SEC filings.
"""
import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
import os, re, aiohttp, requests
import ccxt
import feedparser
from bs4 import BeautifulSoup
from core.memory import SharedMemory
from crewai.tools import BaseTool

@dataclass
class MarketData:
    """Normalized market data structure."""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    exchange: str
    timeframe: str = "1h"


class WebSocketMarketData:
    """
    WebSocket client for real-time market data.
    Supports Binance, Coinbase, and other exchanges via CCXT.
    """
    def __init__(self):
        self._connections: Dict[str, Any] = {}
        self._callbacks: List[Callable] = []
        self._running = False

    async def connect(self, exchange_id: str = "binance", symbols: List[str] = None):
        """Connect to exchange WebSocket for real-time data."""
        # This is a simplified version - in production would use exchange-native WS
        try:
            exchange = getattr(ccxt, exchange_id)({
                'enableRateLimit': True,
            })
            # For demo, we simulate WS with REST polling
            # Real implementation would use exchange.websocket endpoints
            self._connections[exchange_id] = exchange
            return True
        except Exception as e:
            print(f"WebSocket connect error: {e}")
            return False

    async def subscribe_ticker(self, symbol: str, callback: Callable):
        """Subscribe to ticker updates."""
        self._callbacks.append(callback)

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> List[MarketData]:
        """Fetch OHLCV data from multiple sources with fallbacks."""
        import ccxt.async_support as ccxt_async
        
        ohlcv = None
        exchange_name = "N/A"

        # 1. Try crypto exchanges via CCXT
        if '/' in symbol:
            binance_config = {'enableRateLimit': True}
            if os.getenv('BINANCE_API_KEY') and os.getenv('BINANCE_API_SECRET'):
                binance_config['apiKey'] = os.getenv('BINANCE_API_KEY')
                binance_config['secret'] = os.getenv('BINANCE_API_SECRET')

            exchanges_to_try = [
                ccxt_async.binance(binance_config),
                ccxt_async.kraken({'enableRateLimit': True}),
                ccxt_async.kucoin({'enableRateLimit': True})
            ]
            
            for exchange in exchanges_to_try:
                try:
                    ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
                    if ohlcv:
                        exchange_name = exchange.id
                        break
                except Exception:
                    pass # Silently try next exchange
                finally:
                    await exchange.close()
        
        # 2. Fallback to yfinance
        if not ohlcv:
            try:
                import yfinance as yf
                yf_symbol = symbol.replace('/', '-')
                if yf_symbol.endswith('-USDT'):
                    yf_symbol = yf_symbol.replace('-USDT', '-USD')
                
                yf_interval_map = {"1d": ("100d", "1d"), "4h": ("60d", "1h"), "1h": ("60d", "1h"), "15m": ("60d", "15m")}
                yf_period, yf_interval = yf_interval_map.get(timeframe, ("100d", "1d"))
                
                ticker = yf.Ticker(yf_symbol)
                df = ticker.history(period=yf_period, interval=yf_interval).tail(limit)
                if not df.empty:
                    ohlcv = [[int(i.timestamp() * 1000), r['Open'], r['High'], r['Low'], r['Close'], r['Volume']] for i, r in df.iterrows()]
                    exchange_name = "yfinance"
            except Exception:
                pass # Silently fail

        if not ohlcv:
            return []

        # Convert to MarketData objects
        return [MarketData(symbol=symbol, timestamp=datetime.fromtimestamp(c[0]/1000), open=c[1], high=c[2], low=c[3], close=c[4], volume=c[5], exchange=exchange_name, timeframe=timeframe) for c in ohlcv]


class NewsAPIClient:
    """Client for news APIs and RSS feeds."""
    def __init__(self):
        # Updated to use format strings for dynamic symbol insertion
        self._sources = [
            "https://news.google.com/rss/search?q={symbol}%20cryptocurrency&hl=en-US&gl=US&ceid=US:en",
            "https://cointelegraph.com/rss/tag/{symbol}",
            "https://www.coindesk.com/arc/outboundfeeds/rss/", # Generic crypto news
        ]

    async def _fetch_gnews(self, symbol: str, limit: int = 10) -> List[Dict]:
        """Fetch news from GNews.io API."""
        api_key = os.getenv("GNEWS_API_KEY")
        if not api_key:
            return []

        # Prepare query for GNews
        query = f'"{symbol.split("/")[0]}" cryptocurrency'
        url = f"https://gnews.io/api/v4/search?q={query}&lang=en&max={limit}&apikey={api_key}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    articles = []
                    for article in data.get("articles", []):
                        articles.append({
                            "title": article.get("title"),
                            "url": article.get("url"),
                            "source": article.get("source", {}).get("name"),
                            "published": article.get("publishedAt"),
                            "body": article.get("description", "")[:500]
                        })
                    if articles:
                        print("Fetched news from GNews.io")
                    return articles
        except Exception as e:
            print(f"GNews fetch failed: {e}. Ensure network/DNS can reach gnews.io.")
            return []

    async def fetch_crypto_news(self, symbol: str = "BTC", limit: int = 10) -> List[Dict]:
        """Fetch latest crypto news from GNews, DDGS, and fall back to RSS feeds."""
        news = []
        
        # 1. Try GNews.io first if API key is present
        if os.getenv("GNEWS_API_KEY"):
            news = await self._fetch_gnews(symbol, limit)

        # 2. If GNews fails or key not present, try DuckDuckGo Search
        if not news:
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
            
            try:
                with DDGS(timeout=20) as ddgs:
                    # Make the query more specific
                    query = f'"{symbol.split("/")[0]}" cryptocurrency news OR "crypto ETF" OR "crypto whale"'
                    # Run synchronous ddgs code in an executor to avoid blocking the event loop
                    loop = asyncio.get_running_loop()
                    results = await loop.run_in_executor(None, lambda: list(ddgs.news(query, max_results=limit)))
                    for r in results:
                        news.append({
                            "title": r.get("title"),
                            "url": r.get("url"),
                            "source": r.get("source"),
                            "published": r.get("date"),
                            "body": r.get("body", "")[:500]
                        })
                    if news:
                        print("Fetched news from DuckDuckGo Search.")
            except Exception as e:
                # Don't return an error yet, just log it and try RSS. This can happen if the library has issues.
                print(f"DDGS news search raised an exception: {e}. Falling back to RSS.")
                news = []

        # 3. If other sources fail, try RSS feeds
        if not news:
            print("DDGS returned no results. Trying RSS feeds...")
            # Prepare symbol for URL (e.g., 'BTC/USDT' -> 'btc')
            rss_symbol = symbol.split('/')[0].lower()
            
            for source_url in self._sources:
                try:
                    # Format URL with the symbol if needed
                    formatted_url = source_url.format(symbol=rss_symbol)
                    feed = feedparser.parse(formatted_url)
                    
                    for entry in feed.entries:
                        # Basic filtering to see if the symbol is mentioned in title or summary
                        title = entry.get("title", "")
                        summary = entry.get("summary", "")
                        if rss_symbol in title.lower() or rss_symbol in summary.lower():
                            news.append({
                                "title": title,
                                "url": entry.link,
                                "source": feed.feed.get("title", "RSS"),
                                "published": entry.get("published"),
                                "body": re.sub('<[^<]+?>', '', summary)[:500] # Strip HTML from summary
                            })
                        if len(news) >= limit:
                            break
                except Exception as e:
                    print(f"Failed to parse RSS feed {source_url}: {e}")
                
                if len(news) >= limit:
                    break
        
        # Add conceptual sentiment scoring to news items
        for item in news:
            title_body = (item.get('title', '') + ' ' + item.get('body', '')).lower()
            positive_words = ['bullish', 'rally', 'gain', 'up', 'high', 'optimistic', 'etf approval', 'record', 'boom']
            negative_words = ['bearish', 'crash', 'down', 'low', 'pessimistic', 'ban', 'regulation', 'fear', 'drop']
            
            score = 0
            for word in positive_words:
                if word in title_body: score += 1
            for word in negative_words:
                if word in title_body: score -= 1
            
            item['sentiment_score'] = score
            if score > 0: item['sentiment'] = 'Positive'
            elif score < 0: item['sentiment'] = 'Negative'
            else: item['sentiment'] = 'Neutral'

        if not news:
            return [{"error": "All news sources failed or returned no results"}]
            
        return news[:limit]

    async def fetch_fear_greed_index(self) -> Dict: # Keep it async, use aiohttp
        """Fetch Crypto Fear & Greed Index."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.alternative.me/fng/", timeout=10) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                return {
                    "value": int(data['data'][0]['value']),
                    "classification": data['data'][0]['value_classification'],
                    "timestamp": data['data'][0]['timestamp']
                }
        except Exception as e:
            return {"error": str(e)}


class SECAPIClient:
    """Client for SEC EDGAR filings."""

    def __init__(self):
        self.session = requests.Session()

    def fetch_filings(self, ticker: str, filing_type: str = "10-K", limit: int = 5) -> List[Dict]:
        """Fetch SEC filings using Financial Modeling Prep (FMP)."""
        try:
            api_key = os.getenv("FMP_API_KEY")
            if not api_key:
                return [{"error": "FMP_API_KEY missing in .env file"}]

            url = f"https://financialmodelingprep.com/api/v3/sec_filings/{ticker}?type={filing_type}&page=0&apikey={api_key}"
            resp = self.session.get(url, timeout=10)
            if resp.status_code != 200:
                return [{"error": f"FMP API returned status {resp.status_code}"}]
            data = resp.json()
            
            return [{
                "type": item.get("type"),
                "date": item.get("fillingDate"),
                "link": item.get("finalLink"),
                "ticker": ticker
            } for item in data[:limit]]
        except Exception as e:
            return [{"error": str(e)}]

    def parse_filing_text(self, filing_url: str) -> str:
        """Download and parse filing text."""
        try:
            resp = self.session.get(filing_url, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            # Extract main text content
            text = soup.get_text(separator='\n', strip=True)
            return text[:5000]  # Truncate for LLM consumption
        except Exception as e:
            return f"Error parsing filing: {e}"


class FetchMarketDataTool(BaseTool):
    """Tool for fetching market data."""
    name: str = "Fetch Market Data"
    description: str = "Fetch OHLCV and ticker data for a cryptocurrency symbol from multiple exchanges."

    async def _run(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> str:
        ws_client = WebSocketMarketData()
        try:
            ohlcv = await ws_client.fetch_ohlcv(symbol, timeframe, limit)
            if not ohlcv:
                return f"No data retrieved for {symbol}"

            latest = ohlcv[-1]
            result = {
                "symbol": symbol,
                "exchange": latest.exchange,
                "timeframe": timeframe,
                "last_price": latest.close,
                "open": latest.open,
                "high": latest.high,
                "low": latest.low,
                "volume": latest.volume,
                "timestamp": latest.timestamp.isoformat(),
                "candles_count": len(ohlcv),
                "close_prices": [c.close for c in ohlcv],
                "highs": [c.high for c in ohlcv],
                "lows": [c.low for c in ohlcv],
                "volumes": [c.volume for c in ohlcv],
                "timestamps": [c.timestamp.isoformat() for c in ohlcv]
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Data fetch error: {str(e)}"


class FetchNewsTool(BaseTool):
    """Tool for fetching news and sentiment."""
    name: str = "Fetch Financial News"
    description: str = "Fetch latest news articles and sentiment for a cryptocurrency or stock symbol."

    async def _run(self, symbol: str, limit: int = 10) -> str:
        client = NewsAPIClient()
        try:
            news = await client.fetch_crypto_news(symbol, limit)

            # If news fetching returns an error, propagate it as a JSON error object
            if news and isinstance(news, list) and "error" in news[0]:
                return json.dumps({"error": f"Failed to fetch news: {news[0]['error']}"})

            fng = await client.fetch_fear_greed_index()

            # Aggregate news sentiment
            aggregated_sentiment = "Neutral"
            aggregated_score = 0
            if news:
                aggregated_score = sum(n.get('sentiment_score', 0) for n in news)
                if aggregated_score > 2: aggregated_sentiment = "Positive"
                elif aggregated_score < -2: aggregated_sentiment = "Negative"

            result = {
                "symbol": symbol,
                "news": news[:5] if news else [],
                "fear_greed_index": fng.get("value"),
                "sentiment_classification": fng.get("classification", "Unknown"),
                "aggregated_news_sentiment": aggregated_sentiment,
                "aggregated_news_score": aggregated_score
            }

            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"error": f"News tool failed: {str(e)}"})


class FetchSECFilingsTool(BaseTool):
    """Tool for fetching SEC EDGAR filings."""
    name: str = "Fetch SEC Filings"
    description: str = "Fetch SEC filings (10-K, 10-Q, 8-K) for a publicly traded company by ticker symbol."

    def _run(self, ticker: str, filing_type: str = "10-K", limit: int = 3) -> str:
        client = SECAPIClient()
        try:
            filings = client.fetch_filings(ticker, filing_type, limit)
            if not filings or "error" in filings[0]:
                return f"No {filing_type} filings found for {ticker} or API error."

            result = {
                "ticker": ticker,
                "filing_type": filing_type,
                "filings": filings
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"SEC fetch error: {str(e)}"

class FindTrendingAssetsTool(BaseTool):
    """Tool to find top trending crypto assets."""
    name: str = "Find Trending Crypto Assets"
    description: str = "Finds top trending crypto assets by 24h volume or price change on a major exchange."

    async def _run(self, exchange_id: str = "binance", top_n: int = 10, sort_by: str = "volume") -> str:
        import ccxt.async_support as ccxt_async
        exchange = getattr(ccxt_async, exchange_id)()
        try:
            if not exchange.has['fetchTickers']:
                return json.dumps({"error": f"Exchange {exchange_id} does not support fetchTickers."})
            
            tickers = await exchange.fetch_tickers()
            
            # Filter for USDT pairs and valid data
            usdt_pairs = {s: t for s, t in tickers.items() if '/USDT' in s and t.get('quoteVolume') and t.get('percentage')}
            
            if sort_by == 'change':
                # Sort by absolute percentage change
                sorted_pairs = sorted(usdt_pairs.values(), key=lambda t: abs(t['percentage']), reverse=True)
            else: # Default to volume
                sorted_pairs = sorted(usdt_pairs.values(), key=lambda t: t['quoteVolume'], reverse=True)
            
            top_assets = [{"symbol": t['symbol'], "volume_24h": t['quoteVolume'], "change_24h": t['percentage']} for t in sorted_pairs[:top_n]]
            
            return json.dumps(top_assets)
        except Exception as e:
            return json.dumps({"error": str(e)})
        finally:
            await exchange.close()


# Singleton tool instances
fetch_market_data = FetchMarketDataTool()
fetch_news = FetchNewsTool()
fetch_sec_filings = FetchSECFilingsTool()
find_trending_assets = FindTrendingAssetsTool()


class RealTimeDataAgent:
    """
    Real-Time Data Retrieval Agent.
    Fetches market data, news, and SEC filings.
    """

    def __init__(self, memory: Optional[SharedMemory] = None):
        self.memory = memory or SharedMemory()
        self.ws_client = WebSocketMarketData()
        self.news_client = NewsAPIClient()
        self.sec_client = SECAPIClient()
        self.tools = {
            "market_data": fetch_market_data,
            "news": fetch_news,
            "sec_filings": fetch_sec_filings,
            "trending": find_trending_assets
        }

    async def execute(self, parameters: Dict, context: Dict) -> Dict:
        """Execute data retrieval based on query parameters."""
        symbol = parameters.get("symbol")
        if not symbol:
            query = parameters.get("query", "")
            words = query.split()
            symbol = next((w for w in words if "/" in w or (w.isupper() and len(w) <= 10)), "BTC/USDT")

        result = {
            "agent": "data_retrieval",
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "data": {}
        }

        try:
            # Fetch market data
            market_data = await self.tools["market_data"]._run(symbol)
            try:
                result["data"]["market"] = json.loads(market_data) if isinstance(market_data, str) else market_data
            except json.JSONDecodeError:
                result["data"]["market"] = {"error": market_data}

            # Fetch news
            news_data = await self.tools["news"]._run(symbol)
            try:
                result["data"]["news"] = json.loads(news_data) if isinstance(news_data, str) else news_data
            except json.JSONDecodeError:
                result["data"]["news"] = {"error": news_data}

            # If stock ticker (not crypto), try SEC filings
            # Run the synchronous tool in an executor to avoid blocking
            if "/" not in symbol and len(symbol) <= 5:
                loop = asyncio.get_running_loop()
                sec_data = await loop.run_in_executor(None, self.tools["sec_filings"]._run, symbol)
                try:
                    result["data"]["sec"] = json.loads(sec_data) if isinstance(sec_data, str) else sec_data
                except json.JSONDecodeError:
                    result["data"]["sec"] = {"error": sec_data}

            # Store to shared memory
            self.memory.store(f"data:{symbol}", result, agent="data")
            
            # Publish updates for TUI
            self.memory.publish("market_data_update", result["data"]["market"], sender="data")
            self.memory.publish("sentiment_update", {"sentiment": result["data"]["news"].get("sentiment_classification", "Neutral"), "fear_greed": result["data"]["news"].get("fear_greed_index", 50)}, sender="data")

        except Exception as e:
            result["error"] = str(e)

        return result

    def get_capability(self) -> Dict:
        return {
            "name": "data_retrieval",
            "description": "Fetches real-time market data, news, and SEC filings",
            "supported_operations": ["fetch_market_data", "fetch_news", "fetch_filings"],
            "dependencies": []
        }

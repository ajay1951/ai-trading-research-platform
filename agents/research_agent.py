"""
Fundamental Research Agent
Analyzes SEC filings, earnings reports, and news sentiment.
"""
import re
import json
import os
from typing import Any, Dict, List, Optional, ClassVar
from dataclasses import dataclass, field
from datetime import datetime
from collections import Counter
from core.memory import SharedMemory
from crewai.tools import BaseTool

try:
    from groq import Groq
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False


@dataclass
class SentimentScore:
    """Sentiment analysis result."""
    score: float  # -1 to 1
    classification: str  # Bullish, Bearish, Neutral
    confidence: float
    keywords: List[str] = field(default_factory=list)


@dataclass
class EarningsAnalysis:
    """Earnings report analysis."""
    symbol: str
    revenue: Optional[float]
    net_income: Optional[float]
    eps: Optional[float]
    surprise_pct: Optional[float]
    guidance: Optional[str]
    sentiment: SentimentScore


class SentimentAnalysisTool(BaseTool):
    """Tool for analyzing sentiment in text."""
    name: str = "Analyze Sentiment"
    description: str = "Analyze sentiment of financial text (news, filings, earnings calls). Returns Bullish, Bearish, or Neutral with confidence score."

    # Simple keyword-based sentiment lexicon - use ClassVar to exclude from Pydantic fields
    BULLISH_WORDS: ClassVar[List[str]] = [
        'growth', 'profit', 'increase', 'strong', 'beat', 'exceed', 'outperform',
        'upgrade', 'buy', 'bullish', 'positive', 'up', 'gain', 'rally', 'surge',
        'record', 'high', 'opportunity', 'optimistic', 'raised', 'momentum'
    ]

    BEARISH_WORDS: ClassVar[List[str]] = [
        'loss', 'decline', 'weak', 'miss', 'underperform', 'downgrade', 'sell',
        'bearish', 'negative', 'down', 'fall', 'drop', 'plunge', 'crash',
        'concern', 'risk', 'warning', 'layoff', 'restructuring', 'debt', 'bankruptcy'
    ]

    def _run(self, text: str, source: str = "general") -> str:
        """
        Analyze sentiment of input text.
        """
        if not text or len(text.strip()) < 10:
            return json.dumps({
                "score": 0.0,
                "classification": "Neutral",
                "confidence": 0.0,
                "keywords": []
            })

        text_lower = text.lower()

        # Count keyword occurrences
        bullish_count = sum(1 for word in self.BULLISH_WORDS if word in text_lower)
        bearish_count = sum(1 for word in self.BEARISH_WORDS if word in text_lower)
        total_count = bullish_count + bearish_count

        if total_count == 0:
            score = 0.0
            classification = "Neutral"
            confidence = 0.0
            keywords = []
        else:
            score = (bullish_count - bearish_count) / total_count
            if score > 0.2:
                classification = "Bullish"
            elif score < -0.2:
                classification = "Bearish"
            else:
                classification = "Neutral"
            confidence = abs(score)
            keywords = [w for w in self.BULLISH_WORDS + self.BEARISH_WORDS if w in text_lower][:5]

        result = {
            "score": round(score, 2),
            "classification": classification,
            "confidence": round(confidence, 2),
            "keywords": keywords,
            "source": source
        }

        return json.dumps(result)


class AnalyzeEarningsTool(BaseTool):
    """Tool for analyzing earnings reports and SEC filings."""
    name: str = "Analyze Earnings Report"
    description: str = "Analyze earnings report text, extract key metrics, and determine sentiment."

    def _run(self, filing_text: str, symbol: str = "") -> str:
        """
        Extract financial metrics and sentiment from earnings/filing text.
        """
        try:
            text = filing_text[:10000]  # Limit size

            # Extract key metrics using regex patterns
            patterns = {
                'revenue': r'revenue[^\d]*\$?([\d,]+\.?\d*)\s*(?:million|billion|M|B)?',
                'net_income': r'net income[^\d]*\$?([\d,]+\.?\d*)',
                'eps': r'earnings per share[^\d]*\$?([\d,]+\.?\d*)',
                'surprise': r'surprise[^\d]*([+-]?[\d,]+\.?\d*)%'
            }

            metrics = {}
            for key, pattern in patterns.items():
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    metrics[key] = match.group(1).replace(',', '')

            # Determine guidance
            guidance = "Neutral"
            if any(word in text.lower() for word in ['raise', 'increase', 'higher', 'beat']):
                guidance = "Positive"
            elif any(word in text.lower() for word in ['lower', 'reduce', 'cut', 'miss']):
                guidance = "Negative"

            # Calculate sentiment
            sentiment_tool = SentimentAnalysisTool()
            sentiment_raw = sentiment_tool._run(text, source="earnings")
            sentiment = json.loads(sentiment_raw) if isinstance(sentiment_raw, str) else sentiment_raw

            result = {
                "symbol": symbol,
                "financials": metrics,
                "guidance": guidance,
                "sentiment": sentiment,
                "analysis_timestamp": datetime.now().isoformat()
            }

            return json.dumps(result)
        except Exception as e:
            return json.dumps({"error": str(e)})


class MacroSummarizerTool(BaseTool):
    """Tool for aggregating macroeconomic sentiment from multiple news sources."""
    name: str = "Summarize Macro Sentiment"
    description: str = "Aggregate sentiment from multiple news articles to determine overall market outlook."

    def _run(self, news_batch_json: str) -> str:
        """
        news_batch_json: JSON array of news articles with title/body
        Returns aggregated sentiment.
        """
        try:
            news_batch = json.loads(news_batch_json) if isinstance(news_batch_json, str) else news_batch_json
            if not news_batch:
                return json.dumps({
                    "overall_sentiment": "Neutral",
                    "confidence": 0.0,
                    "article_count": 0
                })

            sentiment_tool = SentimentAnalysisTool()
            sentiments = []
            keywords = []

            for article in news_batch[:10]:  # Max 10 articles
                text = f"{article.get('title', '')} {article.get('body', '')}"
                sentiment_raw = sentiment_tool._run(text, source="news")
                sentiment = json.loads(sentiment_raw) if isinstance(sentiment_raw, str) else sentiment_raw
                sentiments.append(sentiment)
                keywords.extend(sentiment.get('keywords', []))

            # Aggregate
            avg_score = sum(s['score'] for s in sentiments) / len(sentiments)
            avg_conf = sum(s['confidence'] for s in sentiments) / len(sentiments)

            if avg_score > 0.2:
                overall = "Bullish"
            elif avg_score < -0.2:
                overall = "Bearish"
            else:
                overall = "Neutral"

            # Top keywords
            keyword_counts = Counter(keywords)
            top_keywords = [kw for kw, _ in keyword_counts.most_common(10)]

            # Generate Narrative using Groq if available
            narrative = "No narrative available."
            if HAS_GROQ and os.getenv("GROQ_API_KEY"):
                try:
                    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
                    headlines = "\\n".join([f"- {a.get('title', '')}" for a in news_batch[:10]])
                    prompt = f"Write a 2-3 sentence executive market narrative based on these recent headlines. Focus on the core drivers and sentiment. Keep it punchy and professional:\n{headlines}"
                    
                    chat_completion = client.chat.completions.create(
                        messages=[{"role": "user", "content": prompt}],
                        model="llama3-8b-8192",
                    )
                    narrative = chat_completion.choices[0].message.content.strip()
                except Exception as e:
                    narrative = f"Narrative generation failed: {str(e)}"

            result = {
                "overall_sentiment": overall,
                "sentiment_score": round(avg_score, 2),
                "confidence": round(avg_conf, 2),
                "article_count": len(news_batch),
                "top_keywords": top_keywords,
                "narrative": narrative
            }

            return json.dumps(result)
        except Exception as e:
            return json.dumps({"error": str(e)})


class FundamentalResearchAgent:
    """
    Fundamental Research Agent.
    Analyzes SEC filings, earnings reports, and market sentiment.
    """

    def __init__(self, memory: Optional[SharedMemory] = None):
        self.memory = memory or SharedMemory()
        self.tools = {
            "sentiment": SentimentAnalysisTool(),
            "earnings": AnalyzeEarningsTool(),
            "macro": MacroSummarizerTool()
        }

    def execute(self, parameters: Dict, context: Dict) -> Dict:
        """Execute fundamental research."""
        symbol = parameters.get("symbol", "BTC/USDT")
        result = {
            "agent": "fundamental_research",
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "research": {}
        }

        try:
            # Get data from context
            data_context = context.get("data", {})
            news_data = data_context.get("news", {})
            sec_data = data_context.get("sec", {})

            # Analyze news sentiment
            articles = news_data.get("news", []) if isinstance(news_data, dict) else []
            if articles:
                macro_raw = self.tools["macro"]._run(json.dumps(articles))
                macro_sentiment = json.loads(macro_raw) if isinstance(macro_raw, str) else macro_raw
                result["research"]["macro_sentiment"] = macro_sentiment

            # Analyze SEC filings if available
            filings = sec_data.get("filings", []) if isinstance(sec_data, dict) else []
            if filings:
                # Would need to fetch actual filing text
                # For now, use placeholder
                result["research"]["sec_analysis"] = {
                    "filings_reviewed": len(filings),
                    "latest_filing": filings[0] if filings else None,
                    "analysis": "SEC filings processed"
                }

            # Determine overall sentiment
            sentiment = "Neutral"
            if "macro_sentiment" in result["research"]:
                macro_sent = result["research"]["macro_sentiment"]
                if isinstance(macro_sent, dict):
                    sentiment = macro_sent.get("overall_sentiment", "Neutral")

            result["research"]["overall_sentiment"] = sentiment

            # Store to shared memory
            self.memory.store(f"research:{symbol}", result, agent="research")

        except Exception as e:
            result["error"] = str(e)

        return result

    def analyze_earnings(self, symbol: str, filing_text: str) -> EarningsAnalysis:
        """Dedicated method for earnings analysis."""
        raw = self.tools["earnings"]._run(filing_text, symbol)
        data = json.loads(raw) if isinstance(raw, str) else raw

        if "error" in data:
            return EarningsAnalysis(
                symbol=symbol,
                revenue=None, net_income=None, eps=None,
                surprise_pct=None, guidance="Unknown",
                sentiment=SentimentScore(0, "Neutral", 0.0)
            )

        sentiment = data.get("sentiment", {})
        return EarningsAnalysis(
            symbol=symbol,
            revenue=float(data.get("financials", {}).get("revenue", 0)) if data.get("financials", {}).get("revenue") else None,
            net_income=float(data.get("financials", {}).get("net_income", 0)) if data.get("financials", {}).get("net_income") else None,
            eps=float(data.get("financials", {}).get("eps", 0)) if data.get("financials", {}).get("eps") else None,
            surprise_pct=float(data.get("financials", {}).get("surprise", 0)) if data.get("financials", {}).get("surprise") else None,
            guidance=data.get("guidance", "Neutral"),
            sentiment=SentimentScore(
                score=sentiment.get("score", 0),
                classification=sentiment.get("classification", "Neutral"),
                confidence=sentiment.get("confidence", 0)
            )
        )

    def get_capability(self) -> Dict:
        return {
            "name": "fundamental_research",
            "description": "Analyzes earnings, SEC filings, and macro sentiment",
            "supported_operations": ["analyze_earnings", "macro_sentiment", "sec_filing_analysis"],
            "dependencies": ["data_retrieval"]
        }

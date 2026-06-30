"""
Natural Language Interface
Parses user queries and routes them to the orchestrator.
Generates human-readable responses from results.
"""
import re
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ParsedQuery:
    """Structured representation of a parsed query."""
    intent: str
    entities: Dict[str, Any]
    timeframe: Optional[str] = None
    metrics: List[str] = None
    raw_query: str = ""


class NaturalLanguageInterface:
    """
    Handles natural language input from users.
    Parses intent, extracts entities, and generates responses.
    """

    # Entity patterns
    TICKER_PATTERN = r'\b([A-Z]{2,5}(?:[/-][A-Z]{2,5})?)\b'
    TIMEFRAME_PATTERNS = {
        '1h': ['1h', '1 hour', 'hourly'],
        '4h': ['4h', '4 hour', 'four hours'],
        '1d': ['1d', '1 day', 'daily', 'day'],
        '1w': ['1w', '1 week', 'weekly', 'week'],
        '1m': ['1m', '1 month', 'monthly', 'monthly'],
    }
    METRIC_PATTERNS = {
        'price': ['price', 'current', 'now', 'value'],
        'volume': ['volume', 'vol', 'trading volume'],
        'rsi': ['rsi', 'relative strength'],
        'macd': ['macd'],
        'volatility': ['volatility', 'vol'],
        'news': ['news', 'headlines'],
        'sentiment': ['sentiment', 'mood', 'fear', 'greed'],
        'risk': ['risk', 'var', 'exposure'],
        'earnings': ['earnings', 'revenue', 'profit'],
    }

    def __init__(self):
        self._compiled_ticker = re.compile(self.TICKER_PATTERN)
        self._compiled_metrics = {k: re.compile('|'.join(v), re.IGNORECASE) for k, v in self.METRIC_PATTERNS.items()}

    def parse_query(self, query: str) -> ParsedQuery:
        """
        Parse a natural language query into structured components.
        """
        query_lower = query.lower()
        entities = {}

        # Extract ticker symbols
        tickers = self._extract_tickers(query)
        if tickers:
            entities['tickers'] = tickers
            entities['symbol'] = tickers[0]  # Primary symbol

        # Extract timeframe
        timeframe = self._extract_timeframe(query_lower)
        if timeframe:
            entities['timeframe'] = timeframe

        # Extract metrics
        metrics = self._extract_metrics(query_lower)
        if metrics:
            entities['metrics'] = metrics

        # Determine intent
        intent = self._determine_intent(query_lower, metrics)

        return ParsedQuery(
            intent=intent,
            entities=entities,
            timeframe=timeframe,
            metrics=metrics,
            raw_query=query
        )

    def _extract_tickers(self, query: str) -> List[str]:
        """Extract cryptocurrency ticker symbols."""
        matches = self._compiled_ticker.findall(query)
        # Filter out common false positives
        filtered = []
        for m in matches:
            # Clean up: remove trailing punctuation
            m_clean = m.rstrip('.,!?;:')
            # Allow symbols like 'BTC/USDT'. isalpha() was too restrictive.
            if len(m_clean) >= 3:
                filtered.append(m_clean.upper())
        return list(set(filtered))

    def _extract_timeframe(self, query: str) -> Optional[str]:
        """Extract timeframe from query."""
        for tf, patterns in self.TIMEFRAME_PATTERNS.items():
            for p in patterns:
                if p in query:
                    return tf
        return None

    def _extract_metrics(self, query: str) -> List[str]:
        """Extract requested metrics."""
        metrics = []
        for metric, pattern in self._compiled_metrics.items():
            if pattern.search(query):
                metrics.append(metric)
        return metrics

    def _determine_intent(self, query: str, metrics: List[str]) -> str:
        """Determine the primary intent of the query."""
        intent_keywords = {
            'analyze': ['analyze', 'analysis', 'check', 'evaluate', 'assess', 'what'],
            'trade': ['buy', 'sell', 'trade', 'execute', 'order', 'purchase'],
            'risk': ['risk', 'var', 'exposure', 'portfolio', 'drawdown'],
            'monitor': ['monitor', 'watch', 'track', 'alert'],
            'backtest': ['backtest', 'test', 'historical', 'past'],
        }

        scores = {}
        for intent, keywords in intent_keywords.items():
            score = sum(1 for kw in keywords if kw in query)
            scores[intent] = score

        best_intent = max(scores, key=scores.get)
        if scores[best_intent] == 0:
            # Default based on metrics
            if 'risk' in metrics:
                return 'risk'
            elif 'news' in metrics or 'sentiment' in metrics:
                return 'monitor'
            else:
                return 'analyze'

        return best_intent

    def generate_response(self, results: Dict[str, Any], query: ParsedQuery) -> str:
        """
        Generate a human-readable response from query results.
        """
        if not results.get('success'):
            errors = results.get('errors', [])
            return f"Query failed. Errors: {', '.join(errors)}"

        output = []
        output.append("=" * 60)
        output.append(f"ANALYSIS REPORT: {query.raw_query}")
        output.append(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        output.append("=" * 60)

        agent_results = results.get('results', {})

        # Order of presentation
        presentation_order = ['data', 'research', 'quant', 'risk', 'execution']

        for agent_type in presentation_order:
            if agent_type in agent_results:
                result = agent_results[agent_type]
                output.append(f"\n[{agent_type.upper()}]")
                output.append(self._format_agent_result(agent_type, result))
                output.append("")

        # Summary
        output.append("\n" + "=" * 60)
        output.append("SUMMARY")
        output.append("=" * 60)
        output.append(self._generate_summary(agent_results))

        return "\n".join(output)

    def _format_agent_result(self, agent_type: str, result: Any) -> str:
        """Format individual agent result for display."""
        if isinstance(result, dict):
            lines = []
            for key, value in result.items():
                if key not in ['timestamp', 'agent']:
                    lines.append(f"  {key}: {value}")
            return "\n".join(lines)
        return str(result)

    def _generate_summary(self, results: Dict[str, Any]) -> str:
        """Generate executive summary from all results."""
        summary_parts = []

        # Extract key signals
        signals = []
        for agent, result in results.items():
            if isinstance(result, dict):
                if 'signal' in result:
                    signals.append(f"{agent}: {result['signal']}")
                if 'recommendation' in result:
                    signals.append(f"{agent}: {result['recommendation']}")

        if signals:
            summary_parts.append("Key Findings:")
            for s in signals:
                summary_parts.append(f"  - {s}")

        if not summary_parts:
            summary_parts.append("Analysis complete. Review individual agent outputs for details.")

        return "\n".join(summary_parts)


# Global interface instance
nl_interface = NaturalLanguageInterface()

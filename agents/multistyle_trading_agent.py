"""
Multi-Style Trading Agent

Generates institutional-grade trading roadmaps for multiple trading styles simultaneously.
This agent is the core of the trade planning and opportunity intelligence platform.
"""
import asyncio
from typing import Dict, Any, List
from datetime import datetime
import pandas as pd
import numpy as np

from core.memory import SharedMemory
from models.technical_indicators import TechnicalIndicators

class MultiStyleTradingAgent:
    """
    Analyzes a given symbol across Scalping, Intraday, Swing, and Position trading
    styles to produce a complete trading roadmap.
    """
    def __init__(self, memory: SharedMemory):
        self.memory = memory

    def _generate_trade_setup(self, direction: str, style: str, kind: str, price: float, atr: float, conf: float) -> Dict:
        """Generates a trade setup using real price and ATR data."""
        if direction == "BUY":
            # ATR-based setup
            sl_dist = atr * 1.5
            entry = price
            sl = entry - sl_dist
            tp1 = entry + (sl_dist * 1.0)
            tp2 = entry + (sl_dist * 2.0)
            tp3 = entry + (sl_dist * 3.0)
            direction_str = "Long"
        elif direction == "SELL":
            sl_dist = atr * 1.5
            entry = price
            sl = entry + sl_dist
            tp1 = entry - (sl_dist * 1.0)
            tp2 = entry - (sl_dist * 2.0)
            tp3 = entry - (sl_dist * 3.0)
            direction_str = "Short"
        else: # HOLD
            return { "direction": "Neutral", "reasoning": "Market conditions are not favorable for a trade." }

        rr = abs((tp2 - entry) / (entry - sl)) if (entry - sl) != 0 else 0

        duration_map = {
            "scalping": "1-4 hours",
            "intraday": "1-2 days",
            "swing": "1-2 weeks",
            "position": "1-3 months"
        }
        
        return {
            "direction": direction_str,
            "entry_zone": f"{entry:,.2f}",
            "stop_loss": f"{sl:,.2f}",
            "tp1": f"{tp1:,.2f}",
            "tp2": f"{tp2:,.2f}",
            "tp3": f"{tp3:,.2f}",
            "risk_reward_ratio": f"{rr:.2f}:1",
            "confidence_score": conf,
            "probability_score": max(0.4, conf - 0.1),
            "risk_level": "Medium" if sl_dist / price < 0.05 else "High",
            "reasoning": f"{kind} setup for {style} based on technical analysis.",
            "expected_duration": duration_map.get(style, "Unknown"),
            "market_conditions_required": "Volume confirmation and momentum alignment.",
            "trade_management": {
                "at_1r": "Move stop to breakeven.",
                "at_tp1": "Close 25% of position, move stop to entry.",
                "at_tp2": "Close 50% of remaining position, trail stop.",
                "at_tp3": "Close all remaining positions."
            }
        }

    async def _analyze_style(self, style: str, symbol: str, price: float, quant_data: Dict, atr: float) -> Dict:
        """Calculates analysis for a given trading style using quant signals."""
        signal = quant_data.get("signal", "HOLD")
        confidence = quant_data.get("confidence", 0.5)
        
        # Adjust signal slightly for different styles if needed
        # (For now, we propagate the main signal, but in a real system we'd use MTF data)
        
        roadmap = {
            "immediate_trade": self._generate_trade_setup(signal, style, "Immediate", price, atr, confidence),
            "next_trade": self._generate_trade_setup(signal, style, "Next", price * 0.98 if signal == "BUY" else price * 1.02, atr, max(0.1, confidence-0.1)),
            "alternative_trade": self._generate_trade_setup("SELL" if signal == "BUY" else "BUY", style, "Alternative", price, atr, 1 - confidence),
            "recovery_trade": self._generate_trade_setup(signal, style, "Recovery", price * 0.95 if signal == "BUY" else price * 1.05, atr, max(0.1, confidence-0.2)),
        }
        
        if style == "position":
            roadmap["future_trade"] = roadmap.pop("next_trade")
            roadmap["long_term_trade"] = roadmap.pop("alternative_trade")
            roadmap.pop("recovery_trade")

        return roadmap

    def _get_support_resistance(self, prices: pd.Series, highs: pd.Series, lows: pd.Series) -> Dict:
        """Calculates real S/R levels based on recent highs and lows."""
        if len(highs) < 20:
            return {}
            
        current_price = prices.iloc[-1]
        recent_highs = highs.tail(30)
        recent_lows = lows.tail(30)
        
        maj_sup1 = recent_lows.min()
        maj_res1 = recent_highs.max()
        
        maj_sup2 = recent_lows.quantile(0.25)
        maj_res2 = recent_highs.quantile(0.75)
        
        return {
            "major_supports": [f"{maj_sup1:,.2f}", f"{maj_sup2:,.2f}"],
            "major_resistances": [f"{maj_res1:,.2f}", f"{maj_res2:,.2f}"],
            "liquidity_zones": [f"Above {maj_res1 * 1.005:,.2f}", f"Below {maj_sup1 * 0.995:,.2f}"],
            "breakout_levels": f"{maj_res2:,.2f}",
            "breakdown_levels": f"{maj_sup2:,.2f}",
            "order_blocks": [f"Bullish @ {maj_sup1 * 1.01:,.2f}", f"Bearish @ {maj_res1 * 0.99:,.2f}"],
            "fair_value_gaps": [f"FVG at {(maj_sup1+current_price)/2:,.2f}"],
            "premium_zones": f"Above {maj_res2:,.2f}",
            "discount_zones": f"Below {maj_sup2:,.2f}",
        }

    def _rank_opportunities(self, roadmaps: Dict) -> Dict:
        """Ranks all generated opportunities."""
        all_setups = []
        for style, roadmap in roadmaps.items():
            for trade_type, setup in roadmap.items():
                if setup.get("direction") not in ["Neutral", None]:
                    all_setups.append({
                        "style": style,
                        "trade_type": trade_type,
                        **setup
                    })

        if not all_setups:
            return {}

        highest_confidence = sorted(all_setups, key=lambda x: x['confidence_score'], reverse=True)[0]
        best_rr_str = max(all_setups, key=lambda x: float(x['risk_reward_ratio'].split(':')[0]))['risk_reward_ratio']
        best_rr = next(s for s in all_setups if s['risk_reward_ratio'] == best_rr_str)
        highest_prob = sorted(all_setups, key=lambda x: x['probability_score'], reverse=True)[0]
        
        safest = sorted(all_setups, key=lambda x: (x['risk_level'] == 'Low', x['confidence_score']), reverse=True)[0] if any(s['risk_level'] == 'Low' for s in all_setups) else highest_confidence
        aggressive = sorted(all_setups, key=lambda x: (x['risk_level'] == 'High', float(x['risk_reward_ratio'].split(':')[0])), reverse=True)[0] if any(s['risk_level'] == 'High' for s in all_setups) else highest_confidence

        def format_ranking_entry(setup):
            return {
                "symbol": setup.get('symbol'),
                "style": setup.get('style'),
                "direction": setup.get('direction'),
                "entry": setup.get('entry_zone'),
                "confidence_score": setup.get('confidence_score'),
                "risk_reward_ratio": setup.get('risk_reward_ratio')
            }

        return {
            "best_scalping_setup": format_ranking_entry(next((s for s in all_setups if s['style'] == 'scalping'), all_setups[0])),
            "best_intraday_setup": format_ranking_entry(next((s for s in all_setups if s['style'] == 'intraday'), all_setups[0])),
            "best_swing_setup": format_ranking_entry(next((s for s in all_setups if s['style'] == 'swing'), all_setups[0])),
            "best_position_setup": format_ranking_entry(next((s for s in all_setups if s['style'] == 'position'), all_setups[0])),
            "highest_confidence_setup": format_ranking_entry(highest_confidence),
            "best_risk_reward_setup": format_ranking_entry(best_rr),
            "safest_setup": format_ranking_entry(safest),
            "most_aggressive_setup": format_ranking_entry(aggressive),
            "highest_probability_setup": format_ranking_entry(highest_prob),
        }

    def _generate_executive_summary(self, rankings: Dict, symbol: str, current_price: float, quant_data: Dict) -> Dict:
        """Generates an executive summary based on real analysis."""
        if not rankings:
            return {"market_bias": "Undetermined"}

        best_current = rankings.get('highest_confidence_setup', {})
        best_rr = rankings.get('best_risk_reward_setup', {})
        
        signal = quant_data.get("signal", "HOLD")
        if signal == "BUY": bias = "Bullish"
        elif signal == "SELL": bias = "Bearish"
        else: bias = "Neutral"

        return {
            "market_bias": bias,
            "market_regime": "Trending" if bias != "Neutral" else "Ranging",
            "best_current_opportunity": f"{best_current.get('style', 'N/A').title()} {best_current.get('direction', 'N/A')} @ {best_current.get('entry', 'N/A')}",
            "best_future_opportunity": f"Watch for {best_current.get('style', 'N/A').title()} continuation.",
            "highest_confidence_setup": f"{best_current.get('style', 'N/A').title()} {best_current.get('direction', 'N/A')} (Confidence: {best_current.get('confidence_score', 0)*100:.0f}%)",
            "best_risk_reward_setup": f"{best_rr.get('style', 'N/A').title()} {best_rr.get('direction', 'N/A')} (R/R: {best_rr.get('risk_reward_ratio', 'N/A')})",
            "key_risk_factors": "Follow technical invalidation levels strictly.",
            "key_support_levels": f"{current_price * 0.95:,.2f}",
            "key_resistance_levels": f"{current_price * 1.05:,.2f}",
        }

    async def execute(self, parameters: Dict, context: Dict) -> Dict:
        symbol = parameters.get("symbol", "BTC/USDT")
        
        market_data = context.get("data", {}).get("data", {}).get("market", {})
        closes = market_data.get("close_prices", [])
        highs = market_data.get("highs", [])
        lows = market_data.get("lows", [])
        
        if closes:
            live_price = closes[-1]
            atr = 100 # Default ATR fallback
            if len(closes) > 14:
                tr_series = pd.Series([h-l for h, l in zip(highs, lows)])
                atr = tr_series.rolling(14).mean().iloc[-1]
        else:
            live_price = self.memory.get(f"data:{symbol}:price", 50000.0)
            atr = 500.0
            
        self.memory.store(f"data:{symbol}:price", live_price)
        
        quant_data = context.get("quant", {})

        # --- 1. Run all trading-style engines in parallel ---
        styles = ["scalping", "intraday", "swing", "position"]
        analysis_tasks = [self._analyze_style(style, symbol, live_price, quant_data, atr) for style in styles]
        style_results = await asyncio.gather(*analysis_tasks)
        
        roadmaps = dict(zip(styles, style_results))

        # --- 2. Support & Resistance Engine ---
        if closes and len(closes) > 20:
            support_resistance = self._get_support_resistance(pd.Series(closes), pd.Series(highs), pd.Series(lows))
        else:
            support_resistance = {}

        # --- 3. Opportunity Ranking Engine ---
        rankings = self._rank_opportunities(roadmaps)

        # --- 4. Supervisor Agent Upgrade (Generate Executive Summary) ---
        summary = self._generate_executive_summary(rankings, symbol, live_price, quant_data)

        # --- 5. Add News Data from Context ---
        news_data = context.get("data", {}).get("data", {}).get("news", {})
        news_items = news_data.get("news", []) if isinstance(news_data, dict) else (news_data if isinstance(news_data, list) else [])

        # Get narrative from research agent
        narrative = context.get("research", {}).get("research", {}).get("macro_sentiment", {}).get("narrative", "No narrative available.")

        # --- 6. Assemble Final API Response ---
        final_result = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "market_bias": summary.get("market_bias"),
            "market_regime": summary.get("market_regime"),
            "news": news_items,
            "narrative": narrative,
            "support_resistance_levels": support_resistance,
            **roadmaps,
            "rankings": rankings,
            "summary": summary
        }

        self.memory.store(f"multistyle:{symbol}", final_result, agent="multistyle")
        return final_result

    def get_capability(self) -> Dict:
        return {
            "name": "multistyle_trade_planning",
            "description": "Generates comprehensive trading roadmaps for scalping, intraday, swing, and position styles.",
            "supported_operations": ["generate_roadmap"],
            "dependencies": ["data", "quant"]
        }
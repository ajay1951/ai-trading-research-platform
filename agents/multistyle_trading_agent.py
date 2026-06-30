"""
Multi-Style Trading Agent

Generates institutional-grade trading roadmaps for multiple trading styles simultaneously.
This agent is the core of the trade planning and opportunity intelligence platform.
"""
import asyncio
import random
from typing import Dict, Any, List
from datetime import datetime, timedelta

from core.memory import SharedMemory

class MultiStyleTradingAgent:
    """
    Analyzes a given symbol across Scalping, Intraday, Swing, and Position trading
    styles to produce a complete trading roadmap.
    """
    def __init__(self, memory: SharedMemory):
        self.memory = memory

    def _generate_dummy_setup(self, direction: str, style: str, kind: str, price: float) -> Dict:
        """Generates a placeholder trade setup with a realistic structure."""
        if direction == "Long":
            entry = price * random.uniform(0.98, 0.995)
            sl = entry * random.uniform(0.97, 0.98)
            tp1 = entry * random.uniform(1.01, 1.02)
            tp2 = entry * random.uniform(1.025, 1.04)
            tp3 = entry * random.uniform(1.045, 1.06)
        elif direction == "Short":
            entry = price * random.uniform(1.005, 1.02)
            sl = entry * random.uniform(1.02, 1.03)
            tp1 = entry * random.uniform(0.98, 0.99)
            tp2 = entry * random.uniform(0.96, 0.975)
            tp3 = entry * random.uniform(0.94, 0.955)
        else: # Neutral
            return { "direction": "Neutral", "reasoning": "Market conditions are not favorable for a trade." }

        rr = abs((tp2 - entry) / (entry - sl)) if (entry - sl) != 0 else 0

        return {
            "direction": direction,
            "entry_zone": f"{entry:,.2f}",
            "stop_loss": f"{sl:,.2f}",
            "tp1": f"{tp1:,.2f}",
            "tp2": f"{tp2:,.2f}",
            "tp3": f"{tp3:,.2f}",
            "risk_reward_ratio": f"{rr:.2f}:1",
            "confidence_score": round(random.uniform(0.65, 0.95), 2),
            "probability_score": round(random.uniform(0.60, 0.85), 2),
            "risk_level": random.choice(["Low", "Medium", "High"]),
            "reasoning": f"Placeholder {kind} setup for {style} based on simulated analysis.",
            "expected_duration": f"{random.randint(1, 4)} {random.choice(['hours', 'days'])}",
            "market_conditions_required": "Volume confirmation and timeframe alignment.",
            "trade_management": {
                "at_1r": "Move stop to breakeven.",
                "at_tp1": "Close 25% of position, move stop to entry.",
                "at_tp2": "Close 50% of remaining position, trail stop.",
                "at_tp3": "Close all remaining positions."
            }
        }

    async def _analyze_style(self, style: str, symbol: str, price: float) -> Dict:
        """Simulates analysis for a given trading style."""
        await asyncio.sleep(random.uniform(0.1, 0.3)) # Simulate async work
        
        directions = ["Long", "Short", "Neutral"]
        
        roadmap = {
            "immediate_trade": self._generate_dummy_setup(random.choice(directions), style, "Immediate", price),
            "next_trade": self._generate_dummy_setup(random.choice(directions), style, "Next", price),
            "alternative_trade": self._generate_dummy_setup(random.choice(directions), style, "Alternative", price),
            "recovery_trade": self._generate_dummy_setup(random.choice(directions), style, "Recovery", price),
        }
        
        # Position trading has a different structure
        if style == "position":
            roadmap["future_trade"] = roadmap.pop("next_trade")
            roadmap["long_term_trade"] = roadmap.pop("alternative_trade")
            roadmap.pop("recovery_trade")

        return roadmap

    def _get_support_resistance(self, price: float) -> Dict:
        """Generates placeholder S/R levels and other zones."""
        return {
            "major_supports": [f"{price * 0.95:,.2f}", f"{price * 0.90:,.2f}"],
            "major_resistances": [f"{price * 1.05:,.2f}", f"{price * 1.10:,.2f}"],
            "liquidity_zones": [f"Above {price * 1.055:,.2f}", f"Below {price * 0.945:,.2f}"],
            "breakout_levels": f"{price * 1.06:,.2f}",
            "breakdown_levels": f"{price * 0.89:,.2f}",
            "order_blocks": [f"Bullish @ {price * 0.96:,.2f}", f"Bearish @ {price * 1.04:,.2f}"],
            "fair_value_gaps": [f"FVG at {price * 0.98:,.2f}"],
            "premium_zones": f"Above {price * 1.02:,.2f}",
            "discount_zones": f"Below {price * 0.98:,.2f}",
        }

    def _rank_opportunities(self, roadmaps: Dict) -> Dict:
        """Ranks all generated opportunities based on simulated scores."""
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

        # Sort by different criteria
        highest_confidence = sorted(all_setups, key=lambda x: x['confidence_score'], reverse=True)[0]
        best_rr_str = max(all_setups, key=lambda x: float(x['risk_reward_ratio'].split(':')[0]))['risk_reward_ratio']
        best_rr = next(s for s in all_setups if s['risk_reward_ratio'] == best_rr_str)
        highest_prob = sorted(all_setups, key=lambda x: x['probability_score'], reverse=True)[0]
        
        safest = sorted(all_setups, key=lambda x: (x['risk_level'] == 'Low', x['confidence_score']), reverse=True)[0]
        aggressive = sorted(all_setups, key=lambda x: (x['risk_level'] == 'High', float(x['risk_reward_ratio'].split(':')[0])), reverse=True)[0]

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

    def _generate_executive_summary(self, rankings: Dict, symbol: str) -> Dict:
        """Generates a 30-second executive summary."""
        if not rankings:
            return {"market_bias": "Undetermined"}

        best_current = rankings.get('highest_confidence_setup', {})
        best_rr = rankings.get('best_risk_reward_setup', {})

        return {
            "market_bias": "Slightly Bullish",
            "market_regime": "Volatile Accumulation",
            "best_current_opportunity": f"{best_current.get('style', 'N/A').title()} {best_current.get('direction', 'N/A')} @ {best_current.get('entry', 'N/A')}",
            "best_future_opportunity": "Watch for Swing Trading breakout confirmation.",
            "highest_confidence_setup": f"{best_current.get('style', 'N/A').title()} {best_current.get('direction', 'N/A')} (Confidence: {best_current.get('confidence_score', 0)*100:.0f}%)",
            "best_risk_reward_setup": f"{best_rr.get('style', 'N/A').title()} {best_rr.get('direction', 'N/A')} (R/R: {best_rr.get('risk_reward_ratio', 'N/A')})",
            "key_risk_factors": "Macroeconomic news, potential for high volatility.",
            "key_support_levels": f"{self.memory.get(f'data:{symbol}:price', 100) * 0.95:,.2f}",
            "key_resistance_levels": f"{self.memory.get(f'data:{symbol}:price', 100) * 1.05:,.2f}",
        }

    async def execute(self, parameters: Dict, context: Dict) -> Dict:
        """
        Main execution function for the agent.
        Receives a symbol, runs all style analyses, and returns a structured roadmap.
        """
        symbol = parameters.get("symbol", "BTC/USDT")
        
        # In a real scenario, we'd fetch live data. Here we simulate it.
        # The context from the orchestrator would provide this.
        live_price = context.get("live_price", self.memory.get(f"data:{symbol}:price", random.uniform(30000, 70000)))
        self.memory.store(f"data:{symbol}:price", live_price)

        # --- 1. Run all trading-style engines in parallel ---
        styles = ["scalping", "intraday", "swing", "position"]
        analysis_tasks = [self._analyze_style(style, symbol, live_price) for style in styles]
        style_results = await asyncio.gather(*analysis_tasks)
        
        roadmaps = dict(zip(styles, style_results))

        # --- 2. Support & Resistance Engine ---
        support_resistance = self._get_support_resistance(live_price)

        # --- 3. Opportunity Ranking Engine ---
        rankings = self._rank_opportunities(roadmaps)

        # --- 4. Supervisor Agent Upgrade (Generate Executive Summary) ---
        # The supervisor would do more, but we can generate the summary here as requested.
        summary = self._generate_executive_summary(rankings, symbol)

        # --- 5. Add News Data from Context ---
        # The 'data' agent runs as a dependency, and its result is in the context.
        news_data = context.get("data", {}).get("data", {}).get("news", {})

        # --- 6. Assemble Final API Response ---
        final_result = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "market_bias": summary.get("market_bias"),
            "market_regime": summary.get("market_regime"),
            "news": news_data.get("news", []),
            "support_resistance_levels": support_resistance,
            **roadmaps,
            "rankings": rankings,
            "summary": summary
        }

        # Store the result in memory for other components to access
        self.memory.store(f"multistyle:{symbol}", final_result, agent="multistyle")

        return final_result

    def get_capability(self) -> Dict:
        return {
            "name": "multistyle_trade_planning",
            "description": "Generates comprehensive trading roadmaps for scalping, intraday, swing, and position styles.",
            "supported_operations": ["generate_roadmap"],
            "dependencies": ["data"]
        }
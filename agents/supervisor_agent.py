"""
Supervisor Agent
Reviews and synthesizes outputs from all other agents to form a final,
risk-adjusted conclusion. It acts as the final checkpoint.
"""
from core.memory import SharedMemory
from typing import Dict, Any

class SupervisorAgent:
    """
    An agent that reviews outputs from other agents, checks for conflicts,
    and synthesizes a final, consolidated result.
    """

    def __init__(self, memory: SharedMemory):
        self.memory = memory

    def execute(self, parameters: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the supervisor's review and synthesis process.
        1. Gathers results from quant, research, and risk agents from context.
        2. Checks for conflicts between signals and sentiments.
        3. Synthesizes a final, consolidated recommendation.
        """
        quant_res = context.get("quant", {})
        research_res = context.get("research", {})
        risk_res = context.get("risk", {})

        # Extract key findings
        quant_signal_info = quant_res.get("analysis", {}).get("signal", {})
        quant_signal = quant_signal_info.get("signal", "HOLD")
        quant_confidence = quant_signal_info.get("confidence", 0.5)

        research_sentiment_info = research_res.get("research", {}).get("macro_sentiment", {})
        sentiment = research_sentiment_info.get("overall_sentiment", "Neutral")

        risk_level = risk_res.get("risk_assessment", {}).get("risk_level", "UNKNOWN")

        # --- Conflict Detection ---
        conflict = self._detect_conflict(quant_signal, sentiment)

        # --- Consolidation ---
        return self._consolidate(
            quant_signal, quant_confidence, sentiment, risk_level, conflict
        )

    def _detect_conflict(self, quant_signal: str, sentiment: str) -> bool:
        """Detects conflicts between quantitative signals and qualitative sentiment."""
        is_bullish_signal = quant_signal == "BUY"
        is_bearish_signal = quant_signal == "SELL"
        
        is_bullish_sentiment = sentiment == "Bullish"
        is_bearish_sentiment = sentiment == "Bearish"

        # A BUY signal conflicts with Bearish sentiment.
        if is_bullish_signal and is_bearish_sentiment:
            return True
        # A SELL signal conflicts with Bullish sentiment.
        if is_bearish_signal and is_bullish_sentiment:
            return True
            
        return False

    def _consolidate(self, quant_signal: str, quant_confidence: float, sentiment: str, risk_level: str, conflict: bool) -> Dict[str, Any]:
        """Synthesizes the final output from all agent results."""
        final_signal = quant_signal
        final_confidence = quant_confidence
        
        reasons = []

        if conflict:
            # If there's a conflict, downgrade the signal to HOLD and reduce confidence
            final_signal = "HOLD"
            # Confidence is reduced, reflecting uncertainty
            final_confidence = max(0.3, quant_confidence * 0.5) 
            reasons.append(f"Conflict: Quant signal '{quant_signal}' vs. Research sentiment '{sentiment}'.")
        else:
            reasons.append(f"Quant and Research are aligned (Signal: {quant_signal}, Sentiment: {sentiment}).")

        if risk_level in ["HIGH", "VERY_HIGH"] and final_signal == "BUY":
            final_signal = "HOLD"
            final_confidence = max(0.4, final_confidence * 0.75)
            reasons.append(f"Overriding BUY signal due to {risk_level} risk assessment.")

        return {
            "status": "consolidated",
            "final_signal": final_signal,
            "final_confidence": final_confidence,
            "reasoning": " ".join(reasons),
            "conflict_detected": conflict
        }
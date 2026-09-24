import logging
from agents.crypto_sentiment_agent import CryptoSentimentAgent
from agents.onchain_agent import OnChainAgent

logger = logging.getLogger("AgentOrchestrator")

class AgentOrchestrator:
    def __init__(self):
        """
        The Master Consensus Engine.
        Combines the Mathematical Transformer, the Qualitative Sentiment Agent,
        and the On-Chain Agent to make a final, flawless trading decision.
        """
        self.sentiment_agent = CryptoSentimentAgent()
        self.onchain_agent = OnChainAgent()
        
        # Minimum final confidence required to take a trade
        self.TRADE_THRESHOLD = 0.70

    def evaluate_trade(self, symbol: str, transformer_prediction: float) -> dict:
        """
        Evaluates a potential trade by seeking consensus among all AI Agents.
        transformer_prediction: Base score from the PyTorch Neural Network (0.0 to 1.0)
        """
        logger.info(f"[Orchestrator] Evaluating {symbol} | Base Math Score: {transformer_prediction:.2f}")
        
        # 1. Fetch Qualitative Context
        sentiment_data = self.sentiment_agent.analyze_market_sentiment(symbol)
        onchain_data = self.onchain_agent.check_exchange_inflows(symbol)
        
        # 2. Check for VETOs (Absolute Chaos Prevention)
        if sentiment_data["veto"]:
            logger.warning(f"[Orchestrator VETO] Sentiment Agent blocked trade: {sentiment_data['veto_reason']}")
            return self._cancel_trade("Sentiment Veto")
            
        if onchain_data["whale_dump_warning"]:
            logger.warning(f"[Orchestrator VETO] OnChain Agent blocked trade: Massive Whale Dump detected.")
            return self._cancel_trade("OnChain Veto")
            
        import math
        
        # 3. Apply Consensus Multipliers using Log-Odds (Logit) Transformation
        # Avoid log(0) or division by zero
        p = max(0.001, min(0.999, transformer_prediction))
        logit = math.log(p / (1 - p))
        
        # Scale the modifiers for logit space
        sentiment_logit_modifier = sentiment_data["sentiment_score"] * 0.5
        onchain_logit_modifier = onchain_data["onchain_multiplier"] * 2.0
        
        final_logit = logit + sentiment_logit_modifier + onchain_logit_modifier
        
        # Sigmoid function to return to probability space [0, 1]
        final_confidence = 1 / (1 + math.exp(-final_logit))
        
        # For tracing backwards compatibility
        sentiment_multiplier = sentiment_data["sentiment_score"] * 0.15
        onchain_multiplier = onchain_data["onchain_multiplier"]
        
        # 4. Final Decision
        action = "HOLD"
        if final_confidence >= self.TRADE_THRESHOLD:
            action = "LONG"
        elif final_confidence <= (1 - self.TRADE_THRESHOLD):
            action = "SHORT"
            
        logger.info(f"[Orchestrator Decision] Action: {action} | Final Confidence: {final_confidence:.2f}")
        
        # Build the Reasoning Trace for the Dashboard
        reasoning_trace = {
            "action": action,
            "final_confidence": round(final_confidence, 2),
            "breakdown": {
                "transformer_base": round(transformer_prediction, 2),
                "sentiment_modifier": round(sentiment_multiplier, 2),
                "onchain_modifier": round(onchain_multiplier, 2)
            },
            "veto_active": False
        }
        
        return reasoning_trace

    def _cancel_trade(self, reason: str) -> dict:
        return {
            "action": "HOLD",
            "final_confidence": 0.0,
            "breakdown": {
                "transformer_base": 0.0,
                "sentiment_modifier": 0.0,
                "onchain_modifier": 0.0
            },
            "veto_active": True,
            "veto_reason": reason
        }

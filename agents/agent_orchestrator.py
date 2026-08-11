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
            
        # 3. Apply Consensus Multipliers
        # Sentiment Score is -1 to 1. We scale it to a max +/- 15% modifier.
        sentiment_multiplier = sentiment_data["sentiment_score"] * 0.15 
        onchain_multiplier = onchain_data["onchain_multiplier"]
        
        final_confidence = transformer_prediction + sentiment_multiplier + onchain_multiplier
        
        # Cap confidence between 0 and 1
        final_confidence = max(0.0, min(1.0, final_confidence))
        
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

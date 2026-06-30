from typing import Dict, Any
from core.memory import SharedMemory

class ComplianceAgent:
    """
    Compliance Agent for Pre-Trade Risk checks.
    Ensures that portfolio decisions do not violate institutional mandates.
    """
    def __init__(self, memory: SharedMemory):
        self.memory = memory
        # Institutional limits (Hardcoded for now, could be dynamic)
        self.max_position_usd = 250000.0  # Max exposure per symbol
        self.restricted_symbols = ["XRP/USDT"] # Example restricted list
        
    async def execute(self, parameters: Dict, context: Dict) -> Dict:
        """
        Validates the proposed trade from the portfolio agent.
        """
        portfolio_decision = context.get("portfolio", {})
        action = portfolio_decision.get("action", "NONE")
        
        if action == "NONE" or action == "HOLD":
            return {"status": "APPROVED", "reason": "No trade to validate."}
            
        symbol = portfolio_decision.get("symbol", parameters.get("symbol", "N/A"))
        amount_usd = portfolio_decision.get("amount", 0)
        
        # 1. Restricted Symbol Check
        if symbol in self.restricted_symbols:
            decision = {
                "status": "REJECTED",
                "reason": f"Symbol {symbol} is on the restricted list.",
                "original_action": action
            }
            self.memory.publish("compliance_alert", decision, sender="compliance")
            return decision
            
        # 2. Max Position Check
        if amount_usd > self.max_position_usd:
            decision = {
                "status": "REJECTED",
                "reason": f"Proposed amount ${amount_usd:,.2f} exceeds max position limit ${self.max_position_usd:,.2f}.",
                "original_action": action
            }
            self.memory.publish("compliance_alert", decision, sender="compliance")
            return decision
            
        decision = {
            "status": "APPROVED",
            "reason": "Trade passed all pre-trade compliance checks.",
            "symbol": symbol,
            "action": action,
            "amount_usd": amount_usd
        }
        
        return decision

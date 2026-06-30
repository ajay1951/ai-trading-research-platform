"""
Portfolio Management Agent
Determines trade size and manages portfolio risk based on a supervisor's signal.
Can optionally integrate with an RL agent for optimal sizing.
"""
from core.memory import SharedMemory
from models.risk_models import PortfolioAnalyzer
from typing import Dict, Any
import json
import os

class PortfolioManagementAgent:
    """
    An agent that determines trade size based on portfolio state and risk parameters.
    """

    def __init__(self, memory: SharedMemory):
        self.memory = memory
        self.analyzer = PortfolioAnalyzer()
        self.portfolio_file = "portfolio.json"
        self.notional_capital = 100000.0  # Starting capital
        self.rl_enabled = False # Flag to enable RL integration

    def _load_portfolio(self) -> Dict[str, Any]:
        """Loads the current portfolio state from a JSON file."""
        if not os.path.exists(self.portfolio_file):
            return {"cash": self.notional_capital, "assets": {}}
        try:
            with open(self.portfolio_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {"cash": self.notional_capital, "assets": {}}

    def execute(self, parameters: Dict, context: Dict) -> Dict:
        """
        Determines the parameters for a trade (action, amount) based on the
        supervisor's signal and current portfolio state.
        """
        supervisor_res = context.get("supervisor", {})
        final_signal = supervisor_res.get("final_signal", "HOLD")
        confidence = supervisor_res.get("final_confidence", 0.0)
        symbol = parameters.get("symbol", "BTC/USDT")

        # --- RL Integration (Conceptual) ---
        rl_agent_decision = None
        if self.rl_enabled:
            # Attempt to get a decision from the RLAgent if it exists and is trained
            rl_agent_instance = self.memory.get("agent_instance:rl_agent") # This will now likely be None
            if rl_agent_instance and rl_agent_instance.is_trained:
                # Pass relevant context to the RL agent for its state
                rl_agent_decision = rl_agent_instance.predict_action(context) # Simplified call
                self.memory.store(f"rl_decision:{symbol}", rl_agent_decision, agent="portfolio")

        portfolio = self._load_portfolio()
        cash = portfolio.get("cash", 0)
        assets = portfolio.get("assets", {})

        # Default action is to do nothing
        trade_decision = {
            "action": "NONE",
            "symbol": symbol,
            "amount": 0,
            "reason": "Signal is HOLD or confidence is below execution threshold."
        }

        if rl_agent_decision and rl_agent_decision.get("action") in ["BUY", "SELL"]:
            # If RL agent provides a decision, use it
            trade_decision["action"] = rl_agent_decision["action"]
            trade_decision["amount"] = rl_agent_decision["amount"] * self.notional_capital # RL amount is % of capital
            trade_decision["reason"] = f"RL Agent decision: {rl_agent_decision['reason']}"
            # Override confidence if RL provides it
            confidence = rl_agent_decision.get("confidence", confidence)
        else:
        # Fallback to rule-based sizing if RL is not enabled or not providing a clear signal
            cio_res = context.get("cio", {})
            target_weight = cio_res.get("target_weight", 0.0)
            
            # --- Position Sizing Logic (CIO Target Matching) ---
            total_portfolio_value = cash
            current_position_value = 0.0
            
            # In context, get live price
            live_price = None
            if "data" in context and "market" in context["data"]:
                live_price = context["data"]["market"].get("current_price")
                
            if live_price and symbol in assets:
                current_position_value = assets[symbol].get('amount', 0) * live_price
                
            total_portfolio_value += current_position_value
            
            target_position_value = total_portfolio_value * target_weight
            difference = target_position_value - current_position_value
            
            if difference > 10.0:  # Minimum threshold to trade (e.g., $10)
                if difference > cash:
                    difference = cash # Can't buy more than we have cash for
                trade_decision = {
                    "action": "BUY",
                    "symbol": symbol,
                    "amount": difference, 
                    "reason": f"CIO Target {target_weight*100:.1f}%. Increasing position by ${difference:,.2f}."
                }
            elif difference < -10.0:
                amount_to_sell_usd = abs(difference)
                # Cap at current position value
                if amount_to_sell_usd > current_position_value:
                    amount_to_sell_usd = current_position_value
                    
                if live_price:
                    amount_to_sell_crypto = amount_to_sell_usd / live_price
                    trade_decision = {
                        "action": "SELL",
                        "symbol": symbol,
                        "amount": amount_to_sell_crypto, 
                        "reason": f"CIO Target {target_weight*100:.1f}%. Decreasing position by ${amount_to_sell_usd:,.2f}."
                    }
                else:
                     trade_decision["reason"] = "SELL signal received from CIO, but live price is missing."
            else:
                trade_decision["reason"] = f"Current weight aligns closely with CIO target {target_weight*100:.1f}%. No action needed."
        
        self.memory.store(f"portfolio_decision:{symbol}", trade_decision, agent="portfolio")
        return trade_decision
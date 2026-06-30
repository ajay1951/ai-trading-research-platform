"""
Execution Agent
Responsible for placing, monitoring, and managing trades based on finalized signals.
"""
import json
import os
from datetime import datetime
from typing import Dict, Any
from core.memory import SharedMemory
from core.oms import oms

class ExecutionAgent:
    """
    An agent that simulates trade execution based on signals from the supervisor.
    In a real system, this would interact with exchange APIs via an Order Management System.
    """
    def __init__(self, memory: SharedMemory, live_trading: bool = False):
        self.memory = memory
        self.mode = "LIVE" if live_trading else "PAPER"
        self.trade_log_file = "paper_trades_log.json"
        self.portfolio_file = "portfolio.json"

    def _log_trade(self, trade_details: Dict):
        """Logs a trade to the paper trading log file."""
        trades = []
        if os.path.exists(self.trade_log_file):
            try:
                with open(self.trade_log_file, 'r') as f:
                    trades = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                trades = []
        
        trades.append(trade_details)

        with open(self.trade_log_file, 'w') as f:
            json.dump(trades, f, indent=2)

    def _update_portfolio(self, trade_details: Dict):
        """Updates the virtual portfolio state."""
        portfolio = {"cash": 100000.0, "assets": {}}
        if os.path.exists(self.portfolio_file):
            try:
                with open(self.portfolio_file, 'r') as f:
                    portfolio = json.load(f)
            except Exception:
                pass
                
        symbol = trade_details["symbol"]
        action = trade_details["action"]
        amount = trade_details["amount"]
        amount_usd = trade_details["amount_usd"]
        
        if action == "BUY":
            if portfolio["cash"] >= amount_usd:
                portfolio["cash"] -= amount_usd
                if symbol not in portfolio["assets"]:
                    portfolio["assets"][symbol] = {"amount": 0, "avg_entry": 0}
                
                # Update average entry
                prev_amt = portfolio["assets"][symbol]["amount"]
                prev_val = prev_amt * portfolio["assets"][symbol]["avg_entry"]
                new_val = amount * trade_details["price"]
                portfolio["assets"][symbol]["avg_entry"] = (prev_val + new_val) / (prev_amt + amount)
                portfolio["assets"][symbol]["amount"] += amount
        elif action == "SELL":
            if symbol in portfolio["assets"] and portfolio["assets"][symbol]["amount"] >= amount:
                portfolio["assets"][symbol]["amount"] -= amount
                portfolio["cash"] += amount_usd
                if portfolio["assets"][symbol]["amount"] <= 0.00001:
                    del portfolio["assets"][symbol]
                    
        with open(self.portfolio_file, 'w') as f:
            json.dump(portfolio, f, indent=2)

    async def execute(self, parameters: Dict, context: Dict) -> Dict:
        """
        Receives a final signal from the context and executes a trade if conditions are met.
        """
        portfolio_decision = context.get("portfolio", {})
        action = portfolio_decision.get("action", "NONE")
        
        if action == "NONE" or action == "HOLD":
            return {"status": "No action taken based on portfolio decision."}
            
        # Check Compliance first
        compliance_decision = context.get("compliance", {})
        comp_status = compliance_decision.get("status", "APPROVED")
        if comp_status == "REJECTED":
            return {"status": f"Execution aborted: {compliance_decision.get('reason', 'Compliance rejected.')}"}
            
        symbol = portfolio_decision.get("symbol", parameters.get("symbol", "N/A"))
        
        # In the context, 'data' or 'quant' might hold the price. Let's try to extract it safely.
        live_price = None
        if "data" in context and "market" in context["data"]:
            live_price = context["data"]["market"].get("current_price")
        if not live_price:
            # Fallback for dashboard backend analysis loop context
            live_price = context.get("shared_memory", {}).get("live_price") or parameters.get("live_price")
            
        if not live_price:
            return {"status": "Cannot execute: Live price is unknown."}
            
        # Determine amounts
        if action == "BUY":
            trade_amount_usd = portfolio_decision.get("amount", 0)
            trade_amount_crypto = trade_amount_usd / live_price
        elif action == "SELL":
            trade_amount_crypto = portfolio_decision.get("amount", 0)
            trade_amount_usd = trade_amount_crypto * live_price
        else:
            return {"status": "Invalid action"}

        if trade_amount_usd <= 0 or trade_amount_crypto <= 0:
            return {"status": "Trade amount too small."}

        risk_assessment = context.get("risk", {}).get("risk_assessment", {})

        trade_details = {
            "timestamp": datetime.now().isoformat(), 
            "symbol": symbol,
            "action": action, 
            "price": live_price, 
            "amount": trade_amount_crypto,
            "amount_usd": trade_amount_usd, 
            "reason": portfolio_decision.get("reason", "N/A"),
            "stop_loss": risk_assessment.get("trade_limits", {}).get("stop_loss"),
            "take_profit": risk_assessment.get("trade_limits", {}).get("take_profit"),
        }

        # Create parent order in OMS
        order_id = oms.create_order(symbol, action, trade_amount_crypto)

        # We no longer fill it instantly. We route it to the Algo Agent.
        trade_details["order_id"] = order_id
        trade_details["oms_status"] = "PENDING_ALGO"
        status_message = f"Order routed to Algo Agent: {action} {trade_amount_crypto:.4f} {symbol.split('/')[0]}"

        self.memory.publish("trade_executed", trade_details, sender="execution")
        return {"status": status_message, "trade_details": trade_details}
"""
Performance Review Agent
Analyzes historical trade performance to provide feedback.
"""
from core.memory import SharedMemory
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List
import statistics

class PerformanceReviewAgent:
    """
    An agent that analyzes the performance of past trades to generate feedback.
    """

    def __init__(self, memory: SharedMemory):
        self.memory = memory
        self.trade_log_file = "paper_trades_log.json"
        self.strategies = ["Pairs Trading", "Trend Following", "Mean Reversion"]

    def _load_trades(self) -> List[Dict]:
        """Loads trade history from the log file."""
        if not os.path.exists(self.trade_log_file):
            return []
        try:
            with open(self.trade_log_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def execute(self, parameters: Dict, context: Dict) -> Dict:
        """
        Executes the performance review process.
        """
        trades = self._load_trades()
        if not trades:
            return {"status": "No trades available to review.", "metrics": {}}

        # --- Enhanced Performance Calculation ---
        # Pair buy and sell trades to calculate profit/loss
        paired_trades = []
        buy_trades_unmatched = [t for t in trades if t.get('action') == 'BUY']
        
        for trade in trades:
            if trade.get('action') == 'SELL':
                # Find the most recent unmatched buy (FIFO)
                if buy_trades_unmatched:
                    buy_trade = buy_trades_unmatched.pop(0)
                    
                    buy_price = float(buy_trade.get('price', 0))
                    sell_price = float(trade.get('price', 0))
                    buy_amount = float(buy_trade.get('amount', 0))
                    
                    profit = (sell_price * buy_amount) - (buy_price * buy_amount)
                    profit_pct = (profit / (buy_price * buy_amount)) * 100 if (buy_price * buy_amount) > 0 else 0
                    
                    paired_trades.append({
                        'timestamp': trade.get('timestamp', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                        'strategy': trade.get('strategy', 'Unknown'),
                        'buy_price': buy_price,
                        'sell_price': sell_price,
                        'profit': profit,
                        'profit_pct': profit_pct,
                        'is_win': profit > 0
                    })

        total_paired_trades = len(paired_trades)
        if total_paired_trades == 0:
            return {"status": "Not enough completed trades to review.", "metrics": {}}

        wins = sum(1 for t in paired_trades if t['is_win'])
        losses = total_paired_trades - wins
        win_rate = (wins / total_paired_trades) if total_paired_trades > 0 else 0

        avg_profit_pct = sum(t['profit_pct'] for t in paired_trades) / total_paired_trades
        avg_win_pct = sum(t['profit_pct'] for t in paired_trades if t['is_win']) / wins if wins > 0 else 0
        avg_loss_pct = sum(t['profit_pct'] for t in paired_trades if not t['is_win']) / losses if losses > 0 else 0

        feedback = f"Strategy is {'profitable' if win_rate > 0.5 else 'underperforming'}. "
        if win_rate > 0.6: feedback += "Excellent win rate. "
        elif win_rate < 0.4: feedback += "Win rate is low, review entry/exit criteria. "
        if avg_win_pct > 0 and abs(avg_loss_pct) > 0 and avg_win_pct < abs(avg_loss_pct):
            feedback += "Risk/Reward ratio is unfavorable (average losses are larger than average wins)."

        performance_summary = {
            "total_completed_trades": total_paired_trades,
            "win_rate": f"{win_rate:.2%}",
            "average_profit_pct": f"{avg_profit_pct:.2f}%",
            "average_win_pct": f"{avg_win_pct:.2f}%",
            "average_loss_pct": f"{avg_loss_pct:.2f}%",
            "feedback": feedback
        }

        # Publish feedback for other agents to potentially use
        self.memory.publish("performance_review_update", performance_summary, sender="performance_review")
        self.memory.store("performance_review", performance_summary, agent="performance_review")
        
        # --- Capital Rotation Logic ---
        if parameters.get("action") == "rotate_capital" or "rotate" in str(parameters):
            rotation_result = self.rotate_capital(paired_trades)
            performance_summary["capital_rotation"] = rotation_result
        
        return performance_summary

    def _calculate_sharpe_ratio(self, returns: List[float]) -> float:
        """Calculates a simplified Sharpe ratio from a list of returns."""
        if len(returns) < 2:
            return sum(returns) / 100.0 if returns else 0.0
            
        mean_return = statistics.mean(returns)
        stdev_return = statistics.stdev(returns)
        
        if stdev_return == 0:
            return 0.0
            
        return mean_return / stdev_return

    def rotate_capital(self, paired_trades: List[Dict]) -> Dict:
        """
        Evaluates 14-day rolling Sharpe ratio of strategies.
        Cuts capital by 50% for Sharpe < 0.5, reallocates to max Sharpe strategy.
        """
        # Fetch current weights
        weights = self.memory.get("capital_weights")
        if not weights:
            # Seed equal weights
            weights = {strat: 1.0 / len(self.strategies) for strat in self.strategies}
            
        cutoff_date = datetime.now() - timedelta(days=14)
        
        # Group returns by strategy
        strategy_returns = {strat: [] for strat in self.strategies}
        for t in paired_trades:
            strat = t.get('strategy')
            if strat in self.strategies:
                trade_time = datetime.strptime(t['timestamp'], "%Y-%m-%d %H:%M:%S")
                if trade_time >= cutoff_date:
                    strategy_returns[strat].append(t['profit_pct'])
                    
        # Calculate Sharpe for each
        sharpes = {}
        for strat, rets in strategy_returns.items():
            sharpes[strat] = self._calculate_sharpe_ratio(rets)
            
        # Find top performer
        top_strategy = max(sharpes.items(), key=lambda x: x[1])[0]
        
        # Reallocation logic
        freed_capital = 0.0
        for strat, sharpe in sharpes.items():
            if sharpe < 0.5 and strat != top_strategy:
                trim = weights[strat] * 0.5
                weights[strat] -= trim
                freed_capital += trim
                
        # Reallocate to top performer
        weights[top_strategy] += freed_capital
        
        # Normalize just in case of floating point drift
        total_weight = sum(weights.values())
        if total_weight > 0:
            for strat in weights:
                weights[strat] /= total_weight
                
        # Store and publish
        self.memory.store("capital_weights", weights, agent="performance_review")
        self.memory.publish("capital_weights_update", weights, sender="performance_review")
        
        return {
            "sharpe_ratios": sharpes,
            "new_weights": weights,
            "reallocated_capital": freed_capital,
            "top_strategy": top_strategy
        }
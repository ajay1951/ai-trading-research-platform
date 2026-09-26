import pytest
from datetime import datetime, timedelta
from agents.performance_review_agent import PerformanceReviewAgent
from core.memory import SharedMemory

def test_capital_rotation():
    memory = SharedMemory()
    memory.clear()
    
    agent = PerformanceReviewAgent(memory)
    
    # Generate mock trades
    now = datetime.now()
    recent = (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    
    # Pairs Trading: Consistent small gains (High Sharpe)
    # Trend Following: Volatile, mostly losses (Low Sharpe < 0.5)
    # Mean Reversion: Zero trades, Sharpe 0.0 (Low Sharpe < 0.5)
    
    paired_trades = [
        # Pairs Trading (High Sharpe: mean 2.0, stdev small)
        {'timestamp': recent, 'strategy': 'Pairs Trading', 'profit_pct': 2.0},
        {'timestamp': recent, 'strategy': 'Pairs Trading', 'profit_pct': 2.1},
        {'timestamp': recent, 'strategy': 'Pairs Trading', 'profit_pct': 1.9},
        {'timestamp': recent, 'strategy': 'Pairs Trading', 'profit_pct': 2.0},
        
        # Trend Following (Low Sharpe: mean -2.0, stdev large)
        {'timestamp': recent, 'strategy': 'Trend Following', 'profit_pct': -2.0},
        {'timestamp': recent, 'strategy': 'Trend Following', 'profit_pct': -5.0},
        {'timestamp': recent, 'strategy': 'Trend Following', 'profit_pct': 1.0},
        {'timestamp': recent, 'strategy': 'Trend Following', 'profit_pct': -10.0},
    ]
    
    result = agent.rotate_capital(paired_trades)
    
    sharpes = result["sharpe_ratios"]
    weights = result["new_weights"]
    
    assert sharpes["Pairs Trading"] > 0.5, "Pairs Trading Sharpe should be > 0.5"
    assert sharpes["Trend Following"] < 0.5, "Trend Following Sharpe should be < 0.5"
    assert sharpes["Mean Reversion"] < 0.5, "Mean Reversion Sharpe should be 0.0"
    
    assert result["top_strategy"] == "Pairs Trading", "Top strategy incorrectly identified"
    
    # Initial weights: 1/3 each (0.3333...)
    # Trend Following cut by 50%: 0.1666...
    # Mean Reversion cut by 50%: 0.1666...
    # Freed capital: 0.1666... + 0.1666... = 0.3333...
    # Pairs Trading gets freed capital: 0.3333... + 0.3333... = 0.6666...
    
    assert weights["Trend Following"] == pytest.approx(1/6), f"Trend Following weight wrong: {weights['Trend Following']}"
    assert weights["Mean Reversion"] == pytest.approx(1/6), f"Mean Reversion weight wrong: {weights['Mean Reversion']}"
    assert weights["Pairs Trading"] == pytest.approx(2/3), f"Pairs Trading weight wrong: {weights['Pairs Trading']}"
    
    assert sum(weights.values()) == pytest.approx(1.0), "Weights do not sum to 1.0"

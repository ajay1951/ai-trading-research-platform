import pytest
import sys
import os
import numpy as np

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from agents.risk_agent import RiskAgent

def test_risk_agent_nan_handling():
    agent = RiskAgent(target_daily_volatility_or_memory=0.02)
    
    # Testing that it handles 0 ATR without crashing
    allocation_zero = agent.calculate_position_size(0.9, 0.0, 50000)
    assert allocation_zero == 0.0
    
    # Testing normal logic
    allocation_normal = agent.calculate_position_size(0.9, 2500, 50000)
    # ATR is 5%, Target is 2% -> scalar is 0.4
    # Max allocation is 0.20 * 0.9 = 0.18
    # Final = 0.18 * 0.4 = 0.072
    assert abs(allocation_normal - 0.072) < 0.0001

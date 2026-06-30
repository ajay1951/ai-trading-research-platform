class RiskAgent:
    """
    The Shield.
    Enforces Inverse Volatility (ATR) Sizing and acts as a Kelly Criterion proxy.
    Its sole purpose is capital preservation and keeping portfolio volatility flat.
    """
    def __init__(self, target_daily_volatility=0.02, max_allocation=0.20):
        # Target portfolio volatility (e.g. 2% daily)
        self.target_daily_volatility = target_daily_volatility
        
        # Absolute maximum % of portfolio allowed to be risked on 1 coin (Kelly proxy)
        self.max_allocation = max_allocation

    def calculate_position_size(self, meta_agent_confidence, current_atr, current_price):
        """
        Calculates the exact % of the portfolio to allocate to a trade.
        Takes the Meta-Agent's raw confidence and mathematically shrinks it 
        if the market is acting dangerously (ATR spike).
        """
        # 1. Base allocation based on raw confidence magnitude (0.0 to 1.0)
        # E.g. 0.8 confidence * 20% max allocation = 16% base allocation
        base_allocation = self.max_allocation * abs(meta_agent_confidence)
        
        # 2. Measure current asset volatility
        # If ATR is $5,000 and price is $50,000, volatility is 10%
        asset_volatility_pct = current_atr / current_price
        
        if asset_volatility_pct == 0:
            return 0.0 # Prevent division by zero
            
        # 3. Inverse Volatility Scalar
        # If asset vol is 10% and target is 2%, scalar is 0.2 (Shrink size by 80%!)
        volatility_scalar = self.target_daily_volatility / asset_volatility_pct
        
        # Cap scalar at 1.0 so we don't over-leverage in dead markets
        volatility_scalar = min(volatility_scalar, 1.0)
        
        # 4. Final Risk-Adjusted Allocation
        final_allocation = base_allocation * volatility_scalar
        
        return min(final_allocation, self.max_allocation)

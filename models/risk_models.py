"""
Risk Models Library
Value at Risk, stress testing, and portfolio risk calculations.
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from scipy import stats


@dataclass
class VaRResult:
    """Value at Risk calculation result."""
    var_95: float
    var_99: float
    method: str
    lookback_days: int
    portfolio_value: float
    max_loss_expected: float
    confidence_interval: Tuple[float, float] = None


@dataclass
class StressScenario:
    """Stress test scenario definition."""
    name: str
    description: str
    shock_pct: float
    probability: float = 0.01
    asset_impacts: Optional[Dict[str, float]] = None  # asset -> shock multiplier


@dataclass
class StressTestResult:
    """Stress test result."""
    scenario: str
    portfolio_impact_pct: float
    portfolio_impact_value: float
    severity: str
    passed: bool = True


class ValueAtRisk:
    """Value at Risk calculator with multiple methodologies."""
    
    def __init__(self, returns: pd.Series, portfolio_value: float = 100000):
        """
        returns: series of daily returns (as decimals, e.g., 0.01 for 1%)
        portfolio_value: total portfolio value
        """
        self.returns = returns.dropna()
        self.portfolio_value = portfolio_value
    
    def historical_var(self, confidence: float = 0.95) -> float:
        """Historical simulation VaR."""
        percentile = (1 - confidence) * 100
        return -np.percentile(self.returns, percentile)
    
    def parametric_var(self, confidence: float = 0.95) -> float:
        """Parametric VaR assuming normal distribution."""
        mean = self.returns.mean()
        std = self.returns.std()
        z_score = stats.norm.ppf(1 - confidence)
        return -(mean + z_score * std)
    
    def monte_carlo_var(self, confidence: float = 0.95, simulations: int = 10000) -> float:
        """Monte Carlo simulation VaR (bootstrap)."""
        sim_returns = np.random.choice(self.returns, size=simulations, replace=True)
        percentile = (1 - confidence) * 100
        return -np.percentile(sim_returns, percentile)
    
    def calculate(self, confidence: float = 0.95, method: str = "historical") -> VaRResult:
        """Calculate VaR using specified method."""
        methods = {
            "historical": self.historical_var,
            "parametric": self.parametric_var,
            "monte_carlo": self.monte_carlo_var
        }
        
        if method not in methods:
            raise ValueError(f"Unknown method: {method}. Use: {list(methods.keys())}")
        
        var = methods[method](confidence)
        max_loss = self.portfolio_value * var
        
        # Also calculate 99% VaR
        var_99 = self.historical_var(0.99)
        
        return VaRResult(
            var_95=round(var * 100, 2),
            var_99=round(var_99 * 100, 2),
            method=method,
            lookback_days=len(self.returns),
            portfolio_value=self.portfolio_value,
            max_loss_expected=round(max_loss, 2)
        )
    
    def expected_shortfall(self, confidence: float = 0.95) -> float:
        """Expected Shortfall (Conditional VaR) - average loss beyond VaR."""
        var = self.historical_var(confidence)
        tail_losses = self.returns[self.returns <= -var]
        if len(tail_losses) > 0:
            return -tail_losses.mean()
        return -var
    
    def plot_returns_distribution(self):
        """Plot returns distribution with VaR threshold."""
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.hist(self.returns, bins=50, density=True, alpha=0.7, color='#00d4ff')
        var_95 = self.historical_var(0.95)
        ax.axvline(-var_95, color='red', linestyle='--', label=f'95% VaR: {-var_95:.2%}')
        ax.set_xlabel('Daily Return')
        ax.set_ylabel('Density')
        ax.legend()
        ax.set_title('Returns Distribution with VaR Threshold')
        return fig


class StressTester:
    """Portfolio stress testing engine."""
    
    # Predefined historical scenarios
    HISTORICAL_SCENARIOS = {
        "2008_financial_crisis": StressScenario(
            name="2008 Financial Crisis",
            description="Peak-to-trough decline during 2008 crisis (~50%)",
            shock_pct=-0.50,
            probability=0.01
        ),
        "2020_covid_crash": StressScenario(
            name="COVID-19 Crash",
            description="March 2020 COVID sell-off (~35%)",
            shock_pct=-0.35,
            probability=0.03
        ),
        "2018_crypto_winter": StressScenario(
            name="2018 Crypto Winter",
            description="BTC bear market from 2018 (~80%)",
            shock_pct=-0.80,
            probability=0.02
        ),
        "flash_crash": StressScenario(
            name="Flash Crash",
            description="Single-day flash crash event (~15%)",
            shock_pct=-0.15,
            probability=0.10
        ),
        "moderate_recession": StressScenario(
            name="Moderate Recession",
            description="Typical recession drawdown (~25%)",
            shock_pct=-0.25,
            probability=0.15
        ),
        "inflation_shock": StressScenario(
            name="Inflation Shock",
            description="Unexpected inflation spike impact (~15%)",
            shock_pct=-0.15,
            probability=0.10
        )
    }
    
    def __init__(self, portfolio: Dict[str, float]):
        """
        portfolio: dict mapping asset symbols to position values
        """
        self.portfolio = portfolio
        self.total_value = sum(portfolio.values())
    
    def apply_scenario(self, scenario: StressScenario) -> StressTestResult:
        """Apply a stress scenario to the portfolio."""
        # If asset-specific impacts defined, calculate weighted impact
        if scenario.asset_impacts:
            weighted_impact = 0
            for asset, value in self.portfolio.items():
                pct_of_portfolio = value / self.total_value
                asset_shock = scenario.asset_impacts.get(asset, scenario.shock_pct)
                weighted_impact += pct_of_portfolio * asset_shock
            impact_pct = weighted_impact
        else:
            impact_pct = scenario.shock_pct
        
        impact_value = self.total_value * impact_pct
        
        # Determine if scenario is acceptable (e.g., loss < 20%)
        passed = abs(impact_pct) < 0.20
        
        # Classify severity
        abs_impact = abs(impact_pct)
        if abs_impact >= 0.40:
            severity = "severe"
        elif abs_impact >= 0.20:
            severity = "moderate"
        else:
            severity = "mild"
        
        return StressTestResult(
            scenario=scenario.name,
            portfolio_impact_pct=round(impact_pct * 100, 2),
            portfolio_impact_value=round(impact_value, 2),
            severity=severity,
            passed=passed
        )
    
    def run_all_scenarios(self, scenario_names: Optional[List[str]] = None) -> List[StressTestResult]:
        """Run all or selected predefined scenarios."""
        if scenario_names is None:
            scenarios = list(self.HISTORICAL_SCENARIOS.values())
        else:
            scenarios = [self.HISTORICAL_SCENARIOS[name] for name in scenario_names 
                        if name in self.HISTORICAL_SCENARIOS]
        
        results = []
        for scenario in scenarios:
            results.append(self.apply_scenario(scenario))
        
        # Sort by absolute impact
        results.sort(key=lambda x: abs(x.portfolio_impact_pct), reverse=True)
        return results
    
    def custom_scenario(self, name: str, description: str, shock_pct: float, 
                        asset_impacts: Optional[Dict[str, float]] = None) -> StressTestResult:
        """Create and run a custom scenario."""
        scenario = StressScenario(name, description, shock_pct, asset_impacts=asset_impacts)
        return self.apply_scenario(scenario)


class PortfolioAnalyzer:
    """Portfolio exposure and concentration analysis."""
    
    @staticmethod
    def calculate_concentration(weights: Dict[str, float]) -> float:
        """
        Calculate Herfindahl-Hirschman Index (HHI) for concentration.
        HHI ranges from 1/N (perfectly diversified) to 1.0 (single asset).
        Returns value 0-10000 (commonly scaled).
        """
        if not weights:
            return 0
        n = len(weights)
        hhi = sum(w**2 for w in weights.values())
        return hhi * 10000  # Scale to 0-10000
    
    @staticmethod
    def max_position_size(weights: Dict[str, float]) -> Tuple[str, float]:
        """Find largest position."""
        if not weights:
            return None, 0
        max_asset = max(weights, key=weights.get)
        return max_asset, weights[max_asset]
    
    @staticmethod
    def sector_exposure(weights: Dict[str, float], sector_map: Dict[str, str]) -> Dict[str, float]:
        """Aggregate exposure by sector."""
        sector_weights = {}
        for asset, weight in weights.items():
            sector = sector_map.get(asset, "Unknown")
            sector_weights[sector] = sector_weights.get(sector, 0) + weight
        return sector_weights
    
    @staticmethod
    def risk_contribution(returns: pd.DataFrame, weights: Dict[str, float]) -> Dict[str, float]:
        """
        Calculate marginal risk contribution of each asset.
        Returns percentage of total risk from each asset.
        """
        if returns.empty or not weights:
            return {}
        
        # Align weights with columns
        assets = list(weights.keys())
        w_array = np.array([weights.get(col, 0) for col in returns.columns])
        
        # Portfolio volatility
        cov_matrix = returns.cov().values
        port_vol = np.sqrt(w_array.T @ cov_matrix @ w_array)
        
        if port_vol == 0:
            return {a: 0 for a in assets}
        
        # Marginal contribution to risk
        mcr = (cov_matrix @ w_array) / port_vol
        rc = w_array * mcr  # Risk contribution
        total_rc = rc.sum()
        
        return {asset: rc[i] / total_rc if total_rc > 0 else 0 
                for i, asset in enumerate(assets)}


class RiskMetrics:
    """Common risk metrics calculations."""
    
    @staticmethod
    def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.02, periods: int = 252) -> float:
        """Annualized Sharpe ratio."""
        excess_returns = returns - (risk_free_rate / periods)
        if excess_returns.std() == 0:
            return 0
        return (excess_returns.mean() / excess_returns.std()) * np.sqrt(periods)
    
    @staticmethod
    def sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.02, periods: int = 252) -> float:
        """Sortino ratio (downside risk only)."""
        excess_returns = returns - (risk_free_rate / periods)
        downside_returns = excess_returns[excess_returns < 0]
        if len(downside_returns) == 0 or downside_returns.std() == 0:
            return 0
        downside_std = downside_returns.std()
        return (excess_returns.mean() / downside_std) * np.sqrt(periods)
    
    @staticmethod
    def max_drawdown(returns: pd.Series) -> Tuple[float, int, int]:
        """
        Calculate maximum drawdown.
        Returns (max_dd_pct, peak_idx, trough_idx)
        """
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        
        max_dd = drawdown.min()
        trough_idx = drawdown.idxmin()
        peak_idx = running_max[:trough_idx].idxmax() if trough_idx in drawdown.index else None
        
        return abs(max_dd), peak_idx, trough_idx
    
    @staticmethod
    def calmar_ratio(returns: pd.Series, periods: int = 252) -> float:
        """Calmar ratio (annualized return / max drawdown)."""
        annual_return = returns.mean() * periods
        max_dd, _, _ = RiskMetrics.max_drawdown(returns)
        if max_dd == 0:
            return float('inf')
        return annual_return / max_dd
    
    @staticmethod
    def volatility(returns: pd.Series, periods: int = 252) -> float:
        """Annualized volatility."""
        return returns.std() * np.sqrt(periods)
    
    @staticmethod
    def beta(returns: pd.Series, market_returns: pd.Series) -> float:
        """Portfolio beta relative to market."""
        if len(returns) != len(market_returns):
            raise ValueError("Returns and market returns must have same length")
        covariance = returns.cov(market_returns)
        market_variance = market_returns.var()
        return covariance / market_variance if market_variance != 0 else 0

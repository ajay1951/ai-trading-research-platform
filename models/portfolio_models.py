import numpy as np
from typing import List, Dict

class PortfolioOptimization:
    """
    Portfolio Optimization Models (Markowitz Mean-Variance).
    """
    
    @staticmethod
    def calculate_target_weights(expected_returns: np.ndarray, covariance_matrix: np.ndarray, risk_tolerance: float = 1.0) -> np.ndarray:
        """
        Simplified Mean-Variance optimization to determine target weights.
        Maximizes return - risk_tolerance * variance.
        For demonstration, we use a naive inverse-variance weighting combined with expected returns.
        """
        num_assets = len(expected_returns)
        if num_assets == 0:
            return np.array([])
            
        if num_assets == 1:
            return np.array([1.0])
            
        # Simplified inverse variance weighting adjusted by expected returns
        variances = np.diag(covariance_matrix)
        # Avoid division by zero
        variances = np.where(variances < 1e-6, 1e-6, variances)
        
        inv_variances = 1.0 / variances
        weights = inv_variances * (1.0 + (expected_returns * risk_tolerance))
        
        # Normalize weights to sum to 1
        weights = np.maximum(weights, 0) # No shorting in this basic version
        weight_sum = np.sum(weights)
        
        if weight_sum > 0:
            return weights / weight_sum
        return np.ones(num_assets) / num_assets


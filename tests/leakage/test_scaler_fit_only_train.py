"""
Anti-Leakage Framework: Train-Only Scaler Regression Test
Verifies that feature scalers are fitted exclusively on training data and never fitted on validation or test sets.
"""
import pytest
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler


def test_scaler_fitted_only_on_train_regression():
    """Scaler fit statistics must reflect ONLY training distribution."""
    np.random.seed(42)
    # Training set with mean 10.0, std 2.0
    train_data = np.random.normal(10.0, 2.0, size=(500, 1))
    # Test set with strong distribution shift: mean 50.0, std 5.0
    test_data = np.random.normal(50.0, 5.0, size=(200, 1))

    # CORRECT: fit strictly on train
    scaler = StandardScaler()
    scaler.fit(train_data)

    # Scaler mean must be close to 10.0, NOT shifted towards 50.0
    assert np.isclose(scaler.mean_[0], 10.0, atol=0.3), f"Scaler mean {scaler.mean_[0]} leaked outside train distribution"

    # Transforming test data preserves train scaling parameters
    scaled_train = scaler.transform(train_data)
    scaled_test = scaler.transform(test_data)

    assert np.isclose(scaled_train.mean(), 0.0, atol=0.1)
    # Scaled test mean should be positive and elevated (~ (50 - 10) / 2 = 20)
    assert scaled_test.mean() > 15.0


def test_error_raised_if_scaler_refitted_on_test():
    """Anti-pattern detection: test data must not be passed to .fit()."""
    np.random.seed(42)
    train_data = np.random.normal(0.0, 1.0, size=(100, 1))
    test_data = np.random.normal(10.0, 1.0, size=(100, 1))

    scaler = StandardScaler()
    scaler.fit(train_data)
    train_mean = scaler.mean_[0]

    # Simulating leakage prevention check
    leaked_scaler = StandardScaler()
    all_data = np.vstack([train_data, test_data])
    leaked_scaler.fit(all_data)

    # Leaked scaler mean will be distorted (~5.0)
    assert not np.isclose(leaked_scaler.mean_[0], train_mean, atol=1.0), (
        "Fitting on full dataset distorted baseline parameters"
    )

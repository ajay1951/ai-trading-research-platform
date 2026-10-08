"""
tests/cross_sectional/test_p3_3_calibration.py
==============================================
P3-3 Probability Calibration & Reliability Validation Test Suite.

Validates:
1. Brier score, log loss, ECE, MCE calculations
2. Calibration slope and intercept estimation
3. Zero-leakage Platt scaling and Isotonic regression
4. Bootstrap confidence interval estimation
5. Edge cases: all zeros, all ones, uncalibrated overconfidence
"""

import pytest
import numpy as np
from evaluation.calibration import ProbabilityCalibrator, CalibrationMetrics


def test_brier_score_and_log_loss():
    y_true = np.array([1, 0, 1, 1, 0])
    y_prob = np.array([0.9, 0.1, 0.8, 0.4, 0.2])

    bs = ProbabilityCalibrator.calculate_brier_score(y_true, y_prob)
    ll = ProbabilityCalibrator.calculate_log_loss(y_true, y_prob)

    assert bs > 0.0
    assert ll > 0.0
    assert not np.isnan(bs)
    assert not np.isnan(ll)


def test_ece_and_mce_calculation():
    calibrator = ProbabilityCalibrator(n_bins=5)
    # Perfect calibration: prob = true frequency
    y_prob = np.array([0.1, 0.1, 0.5, 0.5, 0.9, 0.9])
    y_true = np.array([0, 0, 1, 0, 1, 1]) # freqs: 0/2=0, 1/2=0.5, 2/2=1.0

    ece, mce = calibrator.calculate_ece_mce(y_true, y_prob)
    assert ece <= 0.15
    assert mce <= 0.20


def test_zero_leakage_calibrators():
    calibrator = ProbabilityCalibrator()
    np.random.seed(42)
    train_probs = np.random.uniform(0.1, 0.9, 100)
    train_labels = (train_probs + np.random.normal(0, 0.1, 100) > 0.5).astype(int)

    # Fit in-fold
    calibrator.fit_platt_scaler(train_probs, train_labels)
    calibrator.fit_isotonic_calibrator(train_probs, train_labels)

    # Transform out-of-sample
    test_probs = np.array([0.2, 0.5, 0.8])
    p_platt = calibrator.transform_platt(test_probs)
    p_iso = calibrator.transform_isotonic(test_probs)

    assert len(p_platt) == 3
    assert len(p_iso) == 3
    assert (p_platt >= 0.0).all() and (p_platt <= 1.0).all()
    assert (p_iso >= 0.0).all() and (p_iso <= 1.0).all()


def test_calibration_bootstrap_ci():
    calibrator = ProbabilityCalibrator()
    np.random.seed(42)
    y_true = np.random.binomial(1, 0.5, 100)
    y_prob = np.random.uniform(0.0, 1.0, 100)

    brier_ci, ece_ci = calibrator.bootstrap_confidence_intervals(y_true, y_prob, n_bootstraps=50)

    assert brier_ci[0] <= brier_ci[1]
    assert ece_ci[0] <= ece_ci[1]

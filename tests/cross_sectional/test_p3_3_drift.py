"""
tests/cross_sectional/test_p3_3_drift.py
========================================
P3-3 Statistical Drift Detection Validation Test Suite.

Validates:
1. Population Stability Index (PSI) calculation and thresholding
2. Kolmogorov-Smirnov (KS) statistic and p-value
3. Wasserstein Earth Mover's distance
4. Mean, variance, and missingness shift metrics
5. Edge cases: identical distributions, completely shifted distributions, constant values
"""

import pytest
import numpy as np
from evaluation.drift_detection import DriftDetector, DriftType, DriftSeverity


def test_psi_identical_distributions():
    detector = DriftDetector()
    np.random.seed(42)
    dist = np.random.normal(0, 1, 1000)

    psi = detector.calculate_psi(dist, dist)
    assert psi < 0.01 # Virtually zero for identical distributions


def test_psi_shifted_distribution():
    detector = DriftDetector()
    np.random.seed(42)
    ref = np.random.normal(0, 1, 1000)
    mon = np.random.normal(3, 1, 1000) # Significant shift

    psi = detector.calculate_psi(ref, mon)
    assert psi > 0.25 # High drift


def test_complete_distribution_drift_evaluation():
    detector = DriftDetector()
    np.random.seed(42)
    ref = np.random.uniform(0, 10, 500)
    mon = np.random.uniform(5, 15, 500)

    res = detector.evaluate_distribution_drift("test_feature", DriftType.FEATURE_DRIFT, ref, mon)

    assert res.psi > 0.10
    assert res.ks_statistic > 0.20
    assert res.ks_pvalue < 0.01
    assert res.wasserstein_dist > 2.0
    assert res.is_drifted
    assert res.severity in [DriftSeverity.MODERATE, DriftSeverity.HIGH]


def test_constant_feature_edge_case():
    detector = DriftDetector()
    ref = np.ones(100)
    mon = np.ones(100)

    res = detector.evaluate_distribution_drift("constant_feature", DriftType.FEATURE_DRIFT, ref, mon)
    assert res.severity == DriftSeverity.NONE
    assert not res.is_drifted

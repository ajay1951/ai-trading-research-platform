"""
evaluation/drift_detection.py
=============================
P3-3 Statistical Drift & Distribution Monitoring Engine.

Provides:
1. Statistical Divergence Metrics: Population Stability Index (PSI),
   Kolmogorov-Smirnov (KS) test, Wasserstein Distance, Mean/Std/Missingness Shifts.
2. Feature Drift Monitoring: Audits all input feature distributions against causal historical reference windows.
3. Prediction Drift Monitoring: Audits model probability distributions, positive rate, entropy, and output stability.
4. Performance Drift Monitoring: Evaluates rolling hit rate, Brier score, log loss, and predictive Sharpe.
5. Structured Drift Event Logging.
"""

from __future__ import annotations
import math
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp, wasserstein_distance


class DriftSeverity(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class DriftType(str, Enum):
    FEATURE_DRIFT = "FEATURE_DRIFT"
    PREDICTION_DRIFT = "PREDICTION_DRIFT"
    PERFORMANCE_DRIFT = "PERFORMANCE_DRIFT"
    REGIME_DRIFT = "REGIME_DRIFT"


@dataclass
class DriftMetricResult:
    """Detailed summary of a statistical drift comparison."""
    entity_name: str
    drift_type: DriftType
    psi: float
    ks_statistic: float
    ks_pvalue: float
    wasserstein_dist: float
    mean_shift_zscore: float
    std_ratio: float
    missingness_shift: float
    severity: DriftSeverity
    reference_sample_size: int
    monitoring_sample_size: int
    is_drifted: bool


@dataclass
class DriftEvent:
    """Structured machine-readable log of a drift alert."""
    timestamp: str
    model_id: str
    entity_name: str
    drift_type: DriftType
    metric_name: str
    observed_value: float
    threshold: float
    severity: DriftSeverity
    reference_window: str
    monitoring_window: str
    message: str


class DriftDetector:
    """
    Computes statistical distribution divergence and manages causal drift detection.
    """

    def __init__(
        self,
        psi_moderate_threshold: float = 0.10,
        psi_high_threshold: float = 0.25,
        ks_pvalue_threshold: float = 0.01,
        n_bins: int = 10,
        eps: float = 1e-6
    ):
        self.psi_mod_th = psi_moderate_threshold
        self.psi_high_th = psi_high_threshold
        self.ks_p_th = ks_pvalue_threshold
        self.n_bins = n_bins
        self.eps = eps

    def calculate_psi(
        self,
        reference: np.ndarray,
        monitoring: np.ndarray
    ) -> float:
        """
        Computes Population Stability Index (PSI) using quantile binning from reference.
        """
        ref_valid = reference[~np.isnan(reference)]
        mon_valid = monitoring[~np.isnan(monitoring)]

        if len(ref_valid) < 10 or len(mon_valid) < 10:
            return 0.0

        # Create quantile breakpoints on reference distribution
        quantiles = np.linspace(0.0, 100.0, self.n_bins + 1)
        bins = np.percentile(ref_valid, quantiles)
        bins[0] = -np.inf
        bins[-1] = np.inf
        bins = np.unique(bins)

        if len(bins) <= 2:
            return 0.0

        ref_counts, _ = np.histogram(ref_valid, bins=bins)
        mon_counts, _ = np.histogram(mon_valid, bins=bins)

        ref_pct = (ref_counts + self.eps) / (len(ref_valid) + self.eps * len(ref_counts))
        mon_pct = (mon_counts + self.eps) / (len(mon_valid) + self.eps * len(mon_counts))

        psi_val = np.sum((mon_pct - ref_pct) * np.log(mon_pct / ref_pct))
        return float(max(0.0, psi_val))

    def evaluate_distribution_drift(
        self,
        entity_name: str,
        drift_type: DriftType,
        reference_data: np.ndarray,
        monitoring_data: np.ndarray
    ) -> DriftMetricResult:
        """
        Runs complete battery of divergence metrics (PSI, KS, Wasserstein, Mean/Std shifts).
        """
        ref_arr = np.asarray(reference_data, dtype=float)
        mon_arr = np.asarray(monitoring_data, dtype=float)

        ref_clean = ref_arr[~np.isnan(ref_arr)]
        mon_clean = mon_arr[~np.isnan(mon_arr)]

        ref_miss = float(np.mean(np.isnan(ref_arr))) if len(ref_arr) > 0 else 0.0
        mon_miss = float(np.mean(np.isnan(mon_arr))) if len(mon_arr) > 0 else 0.0
        miss_shift = mon_miss - ref_miss

        if len(ref_clean) < 5 or len(mon_clean) < 5:
            return DriftMetricResult(
                entity_name=entity_name,
                drift_type=drift_type,
                psi=0.0,
                ks_statistic=0.0,
                ks_pvalue=1.0,
                wasserstein_dist=0.0,
                mean_shift_zscore=0.0,
                std_ratio=1.0,
                missingness_shift=round(miss_shift, 4),
                severity=DriftSeverity.NONE,
                reference_sample_size=len(ref_clean),
                monitoring_sample_size=len(mon_clean),
                is_drifted=False
            )

        # 1. PSI
        psi = self.calculate_psi(ref_clean, mon_clean)

        # 2. Kolmogorov-Smirnov Test
        ks_res = ks_2samp(ref_clean, mon_clean)
        ks_stat = float(ks_res.statistic)
        ks_pval = float(ks_res.pvalue)

        # 3. Wasserstein Distance
        wd = float(wasserstein_distance(ref_clean, mon_clean))

        # 4. Mean & Std shifts
        ref_mean, ref_std = float(np.mean(ref_clean)), float(np.std(ref_clean))
        mon_mean, mon_std = float(np.mean(mon_clean)), float(np.std(mon_clean))

        mean_shift_z = (mon_mean - ref_mean) / max(1e-6, ref_std)
        std_ratio = mon_std / max(1e-6, ref_std)

        # Classify Severity
        if psi > self.psi_high_th or (ks_pval < 1e-4 and ks_stat > 0.30):
            severity = DriftSeverity.HIGH
            is_drifted = True
        elif psi > self.psi_mod_th or (ks_pval < self.ks_p_th and ks_stat > 0.15):
            severity = DriftSeverity.MODERATE
            is_drifted = True
        elif ks_pval < self.ks_p_th:
            severity = DriftSeverity.LOW
            is_drifted = False
        else:
            severity = DriftSeverity.NONE
            is_drifted = False

        return DriftMetricResult(
            entity_name=entity_name,
            drift_type=drift_type,
            psi=round(psi, 4),
            ks_statistic=round(ks_stat, 4),
            ks_pvalue=round(ks_pval, 6),
            wasserstein_dist=round(wd, 4),
            mean_shift_zscore=round(mean_shift_z, 4),
            std_ratio=round(std_ratio, 4),
            missingness_shift=round(miss_shift, 4),
            severity=severity,
            reference_sample_size=len(ref_clean),
            monitoring_sample_size=len(mon_clean),
            is_drifted=is_drifted
        )

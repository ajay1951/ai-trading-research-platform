"""
evaluation/calibration.py
=========================
P3-3 Probability Calibration & Reliability Engine.

Provides:
1. Calibration Metrics: Brier Score, Log Loss, Expected Calibration Error (ECE),
   Maximum Calibration Error (MCE), Calibration Slope, Calibration Intercept.
2. Reliability Diagrams & Calibration Curves across pre-declared probability bins.
3. Zero-Leakage Post-Processing Calibrators (Platt Scaling, Isotonic Regression).
4. Bootstrap Confidence Intervals for calibration metrics.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression


@dataclass
class CalibrationMetrics:
    """Container for probability calibration metrics."""
    brier_score: float
    log_loss: float
    expected_calibration_error: float
    maximum_calibration_error: float
    calibration_slope: float
    calibration_intercept: float
    brier_ci_95: Tuple[float, float]
    ece_ci_95: Tuple[float, float]
    sample_size: int
    is_well_calibrated: bool


@dataclass
class CalibrationCurveBin:
    """Single bin in a reliability diagram."""
    bin_index: int
    bin_lower: float
    bin_upper: float
    mean_predicted_prob: float
    observed_frequency: float
    sample_count: int
    calibration_error: float


class ProbabilityCalibrator:
    """
    Computes diagnostic calibration metrics and fits zero-leakage calibration transforms.
    """

    def __init__(self, n_bins: int = 10, eps: float = 1e-15):
        self.n_bins = n_bins
        self.eps = eps
        self.platt_model: Optional[LogisticRegression] = None
        self.isotonic_model: Optional[IsotonicRegression] = None

    @staticmethod
    def calculate_brier_score(y_true: np.ndarray, y_prob: np.ndarray) -> float:
        """Computes mean squared error between probability and binary label."""
        if len(y_true) == 0:
            return 0.0
        return float(np.mean((y_prob - y_true) ** 2))

    @staticmethod
    def calculate_log_loss(y_true: np.ndarray, y_prob: np.ndarray, eps: float = 1e-15) -> float:
        """Computes cross-entropy loss."""
        if len(y_true) == 0:
            return 0.0
        p_clipped = np.clip(y_prob, eps, 1.0 - eps)
        loss = -np.mean(y_true * np.log(p_clipped) + (1.0 - y_true) * np.log(1.0 - p_clipped))
        return float(loss)

    def compute_calibration_curve(
        self,
        y_true: np.ndarray,
        y_prob: np.ndarray
    ) -> List[CalibrationCurveBin]:
        """
        Partitions probabilities into fixed equal-width bins and measures observed frequencies.
        """
        bins = np.linspace(0.0, 1.0, self.n_bins + 1)
        curve_bins: List[CalibrationCurveBin] = []

        for m in range(self.n_bins):
            lower, upper = bins[m], bins[m + 1]
            if m == self.n_bins - 1:
                mask = (y_prob >= lower) & (y_prob <= upper)
            else:
                mask = (y_prob >= lower) & (y_prob < upper)

            count = int(np.sum(mask))
            if count > 0:
                mean_prob = float(np.mean(y_prob[mask]))
                obs_freq = float(np.mean(y_true[mask]))
                cal_err = abs(obs_freq - mean_prob)
            else:
                mean_prob = (lower + upper) / 2.0
                obs_freq = 0.0
                cal_err = 0.0

            curve_bins.append(CalibrationCurveBin(
                bin_index=m,
                bin_lower=round(float(lower), 2),
                bin_upper=round(float(upper), 2),
                mean_predicted_prob=round(mean_prob, 4),
                observed_frequency=round(obs_freq, 4),
                sample_count=count,
                calibration_error=round(cal_err, 4)
            ))

        return curve_bins

    def calculate_ece_mce(
        self,
        y_true: np.ndarray,
        y_prob: np.ndarray
    ) -> Tuple[float, float]:
        """
        Computes Expected Calibration Error (ECE) and Maximum Calibration Error (MCE).
        """
        curve_bins = self.compute_calibration_curve(y_true, y_prob)
        total_samples = len(y_true)
        if total_samples == 0:
            return 0.0, 0.0

        ece = sum((b.sample_count / total_samples) * b.calibration_error for b in curve_bins if b.sample_count > 0)
        mce = max((b.calibration_error for b in curve_bins if b.sample_count > 0), default=0.0)

        return float(ece), float(mce)

    def calculate_slope_intercept(
        self,
        y_true: np.ndarray,
        y_prob: np.ndarray
    ) -> Tuple[float, float]:
        """
        Computes logistic calibration slope and intercept.
        Perfect calibration: slope = 1.0, intercept = 0.0.
        """
        if len(np.unique(y_true)) < 2:
            return 1.0, 0.0

        p_clipped = np.clip(y_prob, 1e-4, 1.0 - 1e-4)
        logits = np.log(p_clipped / (1.0 - p_clipped)).reshape(-1, 1)

        lr = LogisticRegression(solver='lbfgs', C=1e5)
        lr.fit(logits, y_true)

        slope = float(lr.coef_[0][0])
        intercept = float(lr.intercept_[0])
        return slope, intercept

    def bootstrap_confidence_intervals(
        self,
        y_true: np.ndarray,
        y_prob: np.ndarray,
        n_bootstraps: int = 200,
        random_seed: int = 42
    ) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        """
        Computes 95% bootstrap confidence intervals for Brier Score and ECE.
        """
        if len(y_true) < 20:
            return (0.0, 0.0), (0.0, 0.0)

        rng = np.random.RandomState(random_seed)
        n = len(y_true)
        brier_samples = []
        ece_samples = []

        for _ in range(n_bootstraps):
            idx = rng.randint(0, n, n)
            bs = self.calculate_brier_score(y_true[idx], y_prob[idx])
            ece, _ = self.calculate_ece_mce(y_true[idx], y_prob[idx])
            brier_samples.append(bs)
            ece_samples.append(ece)

        brier_ci = (float(np.percentile(brier_samples, 2.5)), float(np.percentile(brier_samples, 97.5)))
        ece_ci = (float(np.percentile(ece_samples, 2.5)), float(np.percentile(ece_samples, 97.5)))

        return brier_ci, ece_ci

    def evaluate_calibration(
        self,
        y_true: np.ndarray,
        y_prob: np.ndarray
    ) -> CalibrationMetrics:
        """
        Comprehensive calibration assessment.
        """
        bs = self.calculate_brier_score(y_true, y_prob)
        ll = self.calculate_log_loss(y_true, y_prob)
        ece, mce = self.calculate_ece_mce(y_true, y_prob)
        slope, intercept = self.calculate_slope_intercept(y_true, y_prob)
        b_ci, e_ci = self.bootstrap_confidence_intervals(y_true, y_prob)

        # Well calibrated if ECE <= 0.08 and 0.70 <= slope <= 1.30
        is_well_calibrated = (ece <= 0.08) and (0.70 <= slope <= 1.30)

        return CalibrationMetrics(
            brier_score=round(bs, 4),
            log_loss=round(ll, 4),
            expected_calibration_error=round(ece, 4),
            maximum_calibration_error=round(mce, 4),
            calibration_slope=round(slope, 4),
            calibration_intercept=round(intercept, 4),
            brier_ci_95=(round(b_ci[0], 4), round(b_ci[1], 4)),
            ece_ci_95=(round(e_ci[0], 4), round(e_ci[1], 4)),
            sample_size=len(y_true),
            is_well_calibrated=is_well_calibrated
        )

    # -------------------------------------------------------------------------
    # Zero-Leakage Calibrator Fitting (Strictly on In-Fold Training Data)
    # -------------------------------------------------------------------------

    def fit_platt_scaler(self, train_y_prob: np.ndarray, train_y_true: np.ndarray) -> None:
        """Fits Platt sigmoid scaling on training probabilities without OOS leakage."""
        if len(np.unique(train_y_true)) < 2:
            return
        p_clipped = np.clip(train_y_prob, 1e-4, 1.0 - 1e-4)
        logits = np.log(p_clipped / (1.0 - p_clipped)).reshape(-1, 1)
        self.platt_model = LogisticRegression(solver='lbfgs', C=1e5)
        self.platt_model.fit(logits, train_y_true)

    def transform_platt(self, y_prob: np.ndarray) -> np.ndarray:
        """Applies fitted Platt scaling to uncalibrated probabilities."""
        if self.platt_model is None:
            return y_prob
        p_clipped = np.clip(y_prob, 1e-4, 1.0 - 1e-4)
        logits = np.log(p_clipped / (1.0 - p_clipped)).reshape(-1, 1)
        return self.platt_model.predict_proba(logits)[:, 1]

    def fit_isotonic_calibrator(self, train_y_prob: np.ndarray, train_y_true: np.ndarray) -> None:
        """Fits isotonic regression on training probabilities."""
        self.isotonic_model = IsotonicRegression(out_of_bounds='clip', y_min=0.0, y_max=1.0)
        self.isotonic_model.fit(train_y_prob, train_y_true)

    def transform_isotonic(self, y_prob: np.ndarray) -> np.ndarray:
        """Applies fitted isotonic calibration."""
        if self.isotonic_model is None:
            return y_prob
        return self.isotonic_model.transform(y_prob)

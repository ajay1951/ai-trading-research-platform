"""
Data Engineering: OHLCV Quality Validation Engine
=================================================
Validates market data for quantitative research:
- Price validity (high >= low, open/close within [low, high], price > 0)
- Missing candles & exchange timestamp gaps
- Duplicate timestamps
- Out-of-order timestamps
- Volume anomalies (negative volume, extreme volume spikes)
- Timezone & UTC standardization
"""

import os
import sys
import json
import logging
import argparse
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
import pandas as pd
import numpy as np

logger = logging.getLogger("DataValidator")

TIMEFRAME_DELTAS = {
    '1m': pd.Timedelta(minutes=1),
    '3m': pd.Timedelta(minutes=3),
    '5m': pd.Timedelta(minutes=5),
    '15m': pd.Timedelta(minutes=15),
    '30m': pd.Timedelta(minutes=30),
    '1h': pd.Timedelta(hours=1),
    '2h': pd.Timedelta(hours=2),
    '4h': pd.Timedelta(hours=4),
    '6h': pd.Timedelta(hours=6),
    '8h': pd.Timedelta(hours=8),
    '12h': pd.Timedelta(hours=12),
    '1d': pd.Timedelta(days=1),
}

@dataclass
class ValidationReport:
    symbol: str
    timeframe: str
    total_rows: int
    start_time: str
    end_time: str
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    metrics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


class OHLCVValidator:
    def __init__(self, timeframe: str = '1h', allow_gaps: bool = False, max_gap_tolerance: int = 100):
        self.timeframe = timeframe.lower()
        self.expected_delta = TIMEFRAME_DELTAS.get(self.timeframe, pd.Timedelta(hours=1))
        self.allow_gaps = allow_gaps
        self.max_gap_tolerance = max_gap_tolerance

    def validate(self, df: pd.DataFrame, symbol: str = "UNKNOWN") -> Tuple[bool, ValidationReport]:
        errors = []
        warnings = []
        metrics = {}

        if df.empty:
            errors.append("Dataset is completely empty.")
            report = ValidationReport(
                symbol=symbol,
                timeframe=self.timeframe,
                total_rows=0,
                start_time="",
                end_time="",
                is_valid=False,
                errors=errors,
                warnings=warnings,
                metrics=metrics
            )
            return False, report

        # 1. Column standardization & existence check
        df = df.copy()
        # Find timestamp column
        ts_col = None
        for col in ['timestamp', 'time', 'datetime', 'Date', 'Timestamp']:
            if col in df.columns:
                ts_col = col
                break
        
        if ts_col is None and isinstance(df.index, pd.DatetimeIndex):
            df['timestamp'] = df.index
            ts_col = 'timestamp'
        elif ts_col is None:
            errors.append("No timestamp or DatetimeIndex found in dataframe.")
            return False, ValidationReport(symbol, self.timeframe, len(df), "", "", False, errors, warnings, metrics)

        # Standardize column names to lower
        rename_map = {}
        for c in df.columns:
            cl = c.lower()
            if cl in ['open', 'high', 'low', 'close', 'volume']:
                rename_map[c] = cl
        df = df.rename(columns=rename_map)

        req_cols = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = [c for c in req_cols if c not in df.columns]
        if missing_cols:
            errors.append(f"Missing required OHLCV columns: {missing_cols}")
            return False, ValidationReport(symbol, self.timeframe, len(df), "", "", False, errors, warnings, metrics)

        # 2. Timezone & DateTime formatting
        try:
            if not pd.api.types.is_datetime64_any_dtype(df[ts_col]):
                # Attempt to parse
                if pd.api.types.is_numeric_dtype(df[ts_col]):
                    sample = float(df[ts_col].iloc[0])
                    unit = 'ms' if sample > 1e11 else 's'
                    df['timestamp'] = pd.to_datetime(df[ts_col], unit=unit, utc=True)
                else:
                    df['timestamp'] = pd.to_datetime(df[ts_col], utc=True, format='mixed')
            else:
                if df[ts_col].dt.tz is None:
                    df['timestamp'] = df[ts_col].dt.tz_localize('UTC')
                else:
                    df['timestamp'] = df[ts_col].dt.tz_convert('UTC')
        except Exception:
            # Fallback if format='mixed' not supported or general parse
            try:
                df['timestamp'] = pd.to_datetime(df[ts_col], utc=True)
            except Exception as e:
                errors.append(f"Failed to parse timestamps into UTC: {e}")
                return False, ValidationReport(symbol, self.timeframe, len(df), "", "", False, errors, warnings, metrics)

        start_time = str(df['timestamp'].min())
        end_time = str(df['timestamp'].max())
        total_rows = len(df)
        metrics['total_rows'] = total_rows
        metrics['start_time'] = start_time
        metrics['end_time'] = end_time

        # 3. Duplicate timestamp check
        duplicates = df['timestamp'].duplicated().sum()
        metrics['duplicate_timestamps'] = int(duplicates)
        if duplicates > 0:
            errors.append(f"Found {duplicates} duplicate timestamps.")

        # 4. Out-of-order timestamp check
        is_sorted = df['timestamp'].is_monotonic_increasing
        metrics['is_chronological'] = bool(is_sorted)
        if not is_sorted:
            errors.append("Timestamps are not strictly monotonically increasing (out of order).")

        # 5. Missing candle / Gap detection
        # Sort for gap analysis
        df_sorted = df.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
        time_diffs = df_sorted['timestamp'].diff()
        expected_sec = self.expected_delta.total_seconds()
        
        # Check gaps where diff > expected_delta
        gaps = time_diffs[time_diffs > self.expected_delta]
        metrics['detected_gaps_count'] = len(gaps)
        total_missing_candles = 0
        gap_details = []
        
        if len(gaps) > 0:
            for idx in gaps.index:
                actual_sec = time_diffs[idx].total_seconds()
                missing_cnt = int(round(actual_sec / expected_sec)) - 1
                total_missing_candles += max(0, missing_cnt)
                if len(gap_details) < 5:
                    gap_details.append({
                        "after": str(df_sorted['timestamp'].iloc[idx-1]),
                        "until": str(df_sorted['timestamp'].iloc[idx]),
                        "missing_bars": missing_cnt
                    })
            metrics['estimated_missing_candles'] = total_missing_candles
            metrics['sample_gaps'] = gap_details
            
            if total_missing_candles > 0:
                msg = f"Detected {len(gaps)} gaps representing approx {total_missing_candles} missing candles."
                if self.allow_gaps and total_missing_candles <= self.max_gap_tolerance:
                    warnings.append(msg)
                else:
                    errors.append(msg)

        # 6. Price Integrity & Logic Checks
        # Non-positive prices
        non_positive = ((df['open'] <= 0) | (df['high'] <= 0) | (df['low'] <= 0) | (df['close'] <= 0)).sum()
        metrics['non_positive_prices'] = int(non_positive)
        if non_positive > 0:
            errors.append(f"Found {non_positive} rows with non-positive price (<= 0).")

        # High/Low violations: high must be >= low, open, close
        high_low_violation = (df['high'] < df['low']).sum()
        open_high_violation = (df['open'] > df['high']).sum()
        close_high_violation = (df['close'] > df['high']).sum()
        open_low_violation = (df['open'] < df['low']).sum()
        close_low_violation = (df['close'] < df['low']).sum()
        
        total_integrity_violations = int(high_low_violation + open_high_violation + close_high_violation + open_low_violation + close_low_violation)
        metrics['price_integrity_violations'] = total_integrity_violations
        if total_integrity_violations > 0:
            errors.append(f"Found {total_integrity_violations} price hierarchy violations (e.g. High < Low or Close > High).")

        # 7. NaN / Null counts
        null_counts = df[req_cols].isnull().sum().to_dict()
        metrics['null_counts'] = {k: int(v) for k, v in null_counts.items()}
        total_nulls = sum(null_counts.values())
        if total_nulls > 0:
            errors.append(f"Found {total_nulls} null/NaN values across OHLCV fields: {null_counts}")

        # 8. Volume Anomaly Detection
        negative_vol = (df['volume'] < 0).sum()
        metrics['negative_volume_count'] = int(negative_vol)
        if negative_vol > 0:
            errors.append(f"Found {negative_vol} rows with negative volume.")

        # Zero volume check
        zero_vol = (df['volume'] == 0).sum()
        metrics['zero_volume_count'] = int(zero_vol)
        zero_pct = (zero_vol / total_rows) * 100.0 if total_rows > 0 else 0
        metrics['zero_volume_pct'] = round(zero_pct, 2)
        if zero_pct > 20.0:
            warnings.append(f"High percentage of zero volume bars: {zero_pct:.2f}%.")

        is_valid = len(errors) == 0
        report = ValidationReport(
            symbol=symbol,
            timeframe=self.timeframe,
            total_rows=total_rows,
            start_time=start_time,
            end_time=end_time,
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            metrics=metrics
        )
        return is_valid, report


def validate_file(file_path: str, timeframe: str = '1h') -> ValidationReport:
    """Helper to validate a CSV file directly."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    df = pd.read_csv(file_path)
    base_name = os.path.basename(file_path)
    symbol = base_name.split('_')[0] if '_' in base_name else "DATASET"
    
    validator = OHLCVValidator(timeframe=timeframe)
    _, report = validator.validate(df, symbol=symbol)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OHLCV Data Quality Validator")
    parser.add_argument("--file", type=str, required=True, help="Path to CSV file")
    parser.add_argument("--timeframe", type=str, default="1h", help="Timeframe (e.g. 1m, 15m, 1h, 1d)")
    parser.add_argument("--out", type=str, default=None, help="Optional output JSON report path")
    args = parser.parse_args()

    report = validate_file(args.file, timeframe=args.timeframe)
    json_out = report.to_json(indent=2)
    print(json_out)

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, 'w') as f:
            f.write(json_out)
        print(f"Report saved to {args.out}")

    sys.exit(0 if report.is_valid else 1)

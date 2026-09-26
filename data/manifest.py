"""
Data Engineering: Dataset Manifest & Versioning Engine
======================================================
Generates reproducible SHA-256 manifests for quantitative datasets:
- Cryptographic checksum of raw data files
- Explicit train/val/test date ranges
- Versioned ID tagging
- Verification against modified/corrupted files
"""

import os
import sys
import json
import hashlib
import argparse
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
import pandas as pd

from data.validator import OHLCVValidator

MANIFEST_DIR = os.path.join(os.path.dirname(__file__), "manifests")


def compute_sha256(file_path: str) -> str:
    """Computes SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


class DatasetManifestGenerator:
    def __init__(self, output_dir: str = MANIFEST_DIR):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_manifest(self, file_path: str, timeframe: str = "1h", version: str = "v1", 
                          notes: str = "") -> Dict[str, Any]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Dataset file not found: {file_path}")

        file_size_bytes = os.path.getsize(file_path)
        sha256 = compute_sha256(file_path)
        
        # Load and validate data
        df = pd.read_csv(file_path)
        base_name = os.path.basename(file_path)
        symbol = base_name.split('_')[0] if '_' in base_name else "DATASET"
        
        validator = OHLCVValidator(timeframe=timeframe)
        is_valid, validation_report = validator.validate(df, symbol=symbol)

        dataset_id = f"{symbol}-{timeframe}-{version}"
        manifest = {
            "dataset_id": dataset_id,
            "version": version,
            "symbol": symbol,
            "timeframe": timeframe,
            "file_name": base_name,
            "relative_path": os.path.relpath(file_path, os.path.dirname(os.path.dirname(__file__))),
            "file_size_bytes": file_size_bytes,
            "sha256": sha256,
            "row_count": len(df),
            "columns": list(df.columns),
            "date_range": {
                "start": validation_report.start_time,
                "end": validation_report.end_time
            },
            "validation_summary": {
                "is_valid": is_valid,
                "errors_count": len(validation_report.errors),
                "warnings_count": len(validation_report.warnings),
                "metrics": validation_report.metrics
            },
            "notes": notes,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }

        manifest_file = os.path.join(self.output_dir, f"{dataset_id}.json")
        with open(manifest_file, "w") as f:
            json.dump(manifest, f, indent=2)

        return manifest

    def verify_manifest(self, manifest_path: str) -> Tuple[bool, str]:
        """Verifies if the dataset file matches its stored manifest checksum."""
        if not os.path.exists(manifest_path):
            return False, f"Manifest not found: {manifest_path}"

        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        project_root = os.path.dirname(os.path.dirname(__file__))
        target_file = os.path.join(project_root, manifest.get("relative_path", ""))
        
        if not os.path.exists(target_file):
            return False, f"Target file does not exist: {target_file}"

        current_hash = compute_sha256(target_file)
        expected_hash = manifest.get("sha256")
        
        if current_hash != expected_hash:
            return False, f"Checksum mismatch! Expected {expected_hash}, found {current_hash}."

        return True, "Dataset matches manifest checksum exactly."


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dataset Manifest Generator")
    parser.add_argument("--file", type=str, required=True, help="Path to CSV dataset")
    parser.add_argument("--timeframe", type=str, default="1h", help="Timeframe (e.g. 1h, 15m)")
    parser.add_argument("--version", type=str, default="v1", help="Version tag (e.g. v1, v2)")
    parser.add_argument("--notes", type=str, default="", help="Optional notes on data origin")
    args = parser.parse_args()

    generator = DatasetManifestGenerator()
    manifest = generator.generate_manifest(args.file, timeframe=args.timeframe, version=args.version, notes=args.notes)
    print(f"Manifest successfully generated: {manifest['dataset_id']}")
    print(json.dumps(manifest, indent=2))

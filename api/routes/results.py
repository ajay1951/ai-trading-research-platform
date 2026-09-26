"""
API Route: Results & Benchmark Metrics
"""
import os
import json
from typing import Dict, Any
from fastapi import APIRouter

router = APIRouter(tags=["Results"])


@router.get("/results")
async def get_results() -> Dict[str, Any]:
    """Retrieves standardized benchmark metrics from results/metrics.json."""
    metrics_path = os.path.join(os.path.dirname(__file__), "..", "..", "results", "metrics.json")
    if os.path.exists(metrics_path):
        with open(metrics_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"error": "metrics.json not found"}

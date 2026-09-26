"""
API Route: Experiment Tracking & Manifest Registry
"""
import os
import glob
import yaml
from typing import List
from fastapi import APIRouter
from api.schemas import ExperimentMetadata

router = APIRouter(tags=["Experiments"])


@router.get("/experiments", response_model=List[ExperimentMetadata])
async def list_experiments():
    """Lists all registered experiments from data/manifests/."""
    manifests_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "manifests")
    experiments = []

    for path in glob.glob(os.path.join(manifests_dir, "*.yaml")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                experiments.append(ExperimentMetadata(
                    experiment_id=data.get("experiment_id", os.path.basename(path)),
                    description=data.get("description", ""),
                    model=data.get("model", {}).get("name", "unknown"),
                    dataset=data.get("dataset", {}).get("name", "unknown"),
                    assets=data.get("assets", []),
                    timeframe=data.get("timeframe", "1h"),
                    metrics=data.get("metrics", {})
                ))
        except Exception:
            continue

    return experiments

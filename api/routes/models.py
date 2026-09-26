"""
API Route: Model Registry
"""
from typing import List
from fastapi import APIRouter
from api.schemas import ModelCard

router = APIRouter(tags=["Models"])

REGISTERED_MODELS = [
    ModelCard(
        model_id="lgb-universe-v1",
        name="LightGBM Cross-Sectional",
        architecture="Gradient Boosted Decision Trees",
        parameters={"num_leaves": 31, "learning_rate": 0.03, "n_estimators": 100},
        status="production"
    ),
    ModelCard(
        model_id="lstm-temporal-v1",
        name="PyTorch LSTM Sequential",
        architecture="2-Layer Recurrent Neural Network",
        parameters={"sequence_length": 24, "hidden_size": 64, "num_layers": 2},
        status="benchmark_baseline"
    ),
    ModelCard(
        model_id="rf-technical-v1",
        name="Random Forest Classifier",
        architecture="Ensemble Decision Trees",
        parameters={"n_estimators": 100, "max_depth": 5},
        status="benchmark_baseline"
    ),
    ModelCard(
        model_id="transformer-temporal-v1",
        name="Self-Attention Transformer",
        architecture="Multi-Head Temporal Attention",
        parameters={"d_model": 64, "nhead": 4, "num_layers": 2},
        status="experimental"
    )
]


@router.get("/models", response_model=List[ModelCard])
async def list_models():
    """Lists registered model cards and deployment status."""
    return REGISTERED_MODELS

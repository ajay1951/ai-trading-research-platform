"""
API Data Schemas & Pydantic Validation Models
"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "healthy"})
    timestamp: str
    version: str
    redis_connected: bool
    database_connected: bool


class ExperimentMetadata(BaseModel):
    experiment_id: str
    description: str
    model: str
    dataset: str
    assets: List[str]
    timeframe: str
    metrics: Dict[str, Any]


class ModelCard(BaseModel):
    model_id: str
    name: str
    architecture: str
    parameters: Dict[str, Any]
    status: str


class BacktestRequest(BaseModel):
    model_name: str = "lightgbm"
    asset: str = "BTC"
    timeframe: str = "1h"
    initial_capital: float = 10000.0
    maker_fee: float = 0.0004
    slippage: float = 0.0002


class BacktestResponse(BaseModel):
    status: str
    asset: str
    model: str
    net_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    total_trades: int
    win_rate_pct: float
    profit_factor: float
    cost_deducted_usd: float

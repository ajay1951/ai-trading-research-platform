"""
API Integration & Contract Tests
================================
Tests FastAPI endpoints for proper HTTP status codes, schema validation, and headers.
"""
import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_api_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "2.0.0"
    assert "X-Request-ID" in response.headers


def test_api_models_endpoint():
    response = client.get("/api/v1/models")
    assert response.status_code == 200
    models = response.json()
    assert isinstance(models, list)
    assert len(models) >= 3
    model_names = [m["name"] for m in models]
    assert any("LightGBM" in name for name in model_names)


def test_api_experiments_endpoint():
    response = client.get("/api/v1/experiments")
    assert response.status_code == 200
    experiments = response.json()
    assert isinstance(experiments, list)
    assert len(experiments) >= 2


def test_api_results_endpoint():
    response = client.get("/api/v1/results")
    assert response.status_code == 200
    data = response.json()
    assert "execution_cost_model" in data
    assert "single_asset_benchmarks" in data


def test_api_backtest_run_endpoint():
    payload = {
        "model_name": "lightgbm",
        "asset": "BTC",
        "timeframe": "1h",
        "initial_capital": 10000.0,
        "maker_fee": 0.0004,
        "slippage": 0.0002
    }
    response = client.post("/api/v1/backtests/run", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert "net_return_pct" in data
    assert data["cost_deducted_usd"] > 0.0

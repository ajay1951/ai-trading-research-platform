"""
Load Testing Suite (Locust)
===========================
Measures requests/sec, P50, P95, and P99 latency against the backend API.
Target:
locust -f load-tests/locustfile.py --headless -u 50 -r 10 --run-time 1m --host http://localhost:8000
"""
from locust import HttpUser, task, between


class TradingPlatformUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task(3)
    def test_health_check(self):
        """High frequency health check ping."""
        self.client.get("/api/v1/health")

    @task(2)
    def test_get_results(self):
        """Fetch standardized benchmark metrics."""
        self.client.get("/api/v1/results")

    @task(1)
    def test_list_models(self):
        """Query model registry."""
        self.client.get("/api/v1/models")

    @task(1)
    def test_list_experiments(self):
        """Query experiment manifests."""
        self.client.get("/api/v1/experiments")

    @task(1)
    def test_run_backtest(self):
        """Simulate backtest request."""
        payload = {
            "model_name": "lightgbm",
            "asset": "BTC",
            "timeframe": "1h",
            "initial_capital": 10000.0,
            "maker_fee": 0.0004,
            "slippage": 0.0002
        }
        self.client.post("/api/v1/backtests/run", json=payload)

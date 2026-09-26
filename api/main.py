"""
FastAPI Production Application
==============================
Backend service layer for the AI Trading Research Platform.
"""
import time
import uuid
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import health, experiments, models, backtests, results, research

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("APIGateway")

app = FastAPI(
    title="AI Trading Research Platform API",
    description="Institutional quantitative experimentation, model registry, and backtesting engine.",
    version="2.0.0"
)

# Security: Explicit CORS configuration (no wildcard)
import os
raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
allowed_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

REQUEST_COUNT = Counter("api_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("api_request_duration_seconds", "HTTP request latency in seconds", ["method", "endpoint"])


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """Injects X-Request-ID, logs latency, and records Prometheus metrics."""
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    response = await call_next(request)
    
    duration = time.time() - start_time
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{duration:.4f}s"
    
    endpoint = request.url.path
    status_str = str(response.status_code)
    REQUEST_COUNT.labels(method=request.method, endpoint=endpoint, status=status_str).inc()
    REQUEST_LATENCY.labels(method=request.method, endpoint=endpoint).observe(duration)
    
    logger.info(f"[{request_id}] {request.method} {endpoint} completed in {duration:.4f}s ({status_str})")
    return response


# Prometheus Observability Endpoint
@app.get("/metrics", tags=["Observability"])
def get_metrics():
    """Exposes real-time Prometheus application metrics."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Include Versioned API Routers
app.include_router(health.router, prefix="/api/v1")
app.include_router(experiments.router, prefix="/api/v1")
app.include_router(models.router, prefix="/api/v1")
app.include_router(backtests.router, prefix="/api/v1")
app.include_router(results.router, prefix="/api/v1")
app.include_router(research.router, prefix="/api/v1")


@app.get("/")
def root():
    return {
        "service": "AI Trading Research Platform API",
        "version": "2.0.0",
        "documentation": "/docs",
        "endpoints": [
            "/api/v1/health",
            "/api/v1/experiments",
            "/api/v1/models",
            "/api/v1/backtests/run",
            "/api/v1/results",
            "/api/v1/research/summary"
        ]
    }

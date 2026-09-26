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

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """Injects X-Request-ID and measures request latency."""
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    response = await call_next(request)
    
    duration = time.time() - start_time
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{duration:.4f}s"
    
    logger.info(f"[{request_id}] {request.method} {request.url.path} completed in {duration:.4f}s ({response.status_code})")
    return response


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

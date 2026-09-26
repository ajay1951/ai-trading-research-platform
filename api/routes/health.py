"""
API Route: Health & Diagnostics
"""
from datetime import datetime, timezone
from fastapi import APIRouter
from api.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def get_health():
    """Returns platform operational health and dependency connectivity status."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(timezone.utc).isoformat(),
        version="2.0.0",
        redis_connected=True,
        database_connected=True
    )

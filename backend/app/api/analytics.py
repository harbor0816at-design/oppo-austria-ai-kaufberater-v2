from fastapi import APIRouter, Request, Response

from app.rate_limit import enforce_rate_limit
from app.schemas import AnalyticsEventCreate

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.post("/events", status_code=204)
async def record_event(data: AnalyticsEventCreate, request: Request):
    await enforce_rate_limit(
        request,
        bucket="analytics",
        limit=request.app.state.settings.analytics_rate_limit_per_minute,
        window_seconds=60,
    )
    request.app.state.analytics_service.record(data)
    return Response(status_code=204)

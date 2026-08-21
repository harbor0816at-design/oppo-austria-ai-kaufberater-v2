from fastapi import APIRouter, Request, Response

from app.schemas import AnalyticsEventCreate

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.post("/events", status_code=204)
def record_event(data: AnalyticsEventCreate, request: Request):
    request.app.state.analytics_service.record(data)
    return Response(status_code=204)

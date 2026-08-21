from fastapi import APIRouter, HTTPException, Request

from app.rate_limit import enforce_rate_limit
from app.schemas import AnalyticsEventCreate, LeadSubscribeRequest

router = APIRouter(prefix="/api/leads", tags=["leads"])


@router.post("/subscribe")
async def subscribe(data: LeadSubscribeRequest, request: Request):
    await enforce_rate_limit(
        request,
        bucket="lead",
        limit=request.app.state.settings.lead_rate_limit_per_hour,
        window_seconds=3600,
    )

    product = await request.app.state.fact_service.get(data.target_sku)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    try:
        lead = request.app.state.lead_service.subscribe(data)
        request.app.state.analytics_service.record(
            AnalyticsEventCreate(
                event_name="launch_subscribe_success",
                session_id=data.session_id or "anonymous",
                payload={"channel": data.channel},
            )
        )
        return lead.model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

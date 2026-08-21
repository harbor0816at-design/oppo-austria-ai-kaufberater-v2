from fastapi import APIRouter, HTTPException, Request

from app.schemas import AnalyticsEventCreate, LeadSubscribeRequest

router = APIRouter(prefix="/api/leads", tags=["leads"])


@router.post("/subscribe")
def subscribe(data: LeadSubscribeRequest, request: Request):
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

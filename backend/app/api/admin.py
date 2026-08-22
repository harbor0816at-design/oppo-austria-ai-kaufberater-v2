from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile

from app.auth import require_admin
from app.schemas import (
    FaqItemCreate,
    HeroReorderItem,
    HeroSlideCreate,
    HeroSlideUpdate,
    ProductFactSchema,
)

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


@router.get("/status")
def admin_status(request: Request):
    admin_data_configured = request.app.state.admin_persistence.enabled
    review_configured = request.app.state.review_persistence.enabled
    return {
        "status": "ok",
        "ai_configured": request.app.state.deepseek.configured,
        "faq_configured": request.app.state.faq_service.configured,
        "admin_data_configured": admin_data_configured,
        "admin_data_reachable": admin_data_configured,
        "conversation_review_configured": review_configured,
        "source_b_provider": request.app.state.settings.source_b_provider,
    }


@router.get("/analytics/dashboard")
def analytics_dashboard(request: Request, days: int = 7):
    return request.app.state.analytics_service.dashboard(days)


@router.get("/analytics/summary")
def analytics_summary(request: Request):
    return request.app.state.analytics_service.summary()


@router.get("/conversations")
async def list_conversations(
    request: Request,
    days: int = 7,
    limit: int = 100,
    search: str = "",
):
    if not request.app.state.review_persistence.enabled:
        raise HTTPException(status_code=503, detail="Conversation review is not configured")
    return await request.app.state.review_persistence.acall(
        "conversation_list",
        {"days": days, "limit": limit, "search": search},
    ) or []


@router.get("/conversations/{session_id}")
async def get_conversation(session_id: str, request: Request):
    row = await request.app.state.review_persistence.acall(
        "conversation_get",
        {"session_id": session_id},
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return row


@router.get("/faq-candidates")
async def list_faq_candidates(
    request: Request,
    status: str = "new",
    limit: int = 100,
    search: str = "",
):
    if not request.app.state.review_persistence.enabled:
        raise HTTPException(status_code=503, detail="FAQ candidate review is not configured")
    return await request.app.state.review_persistence.acall(
        "faq_candidate_list",
        {"status": status, "limit": limit, "search": search},
    ) or []


@router.post("/faq-candidates/{candidate_id}/status")
async def update_faq_candidate_status(candidate_id: int, data: dict, request: Request):
    row = await request.app.state.review_persistence.acall(
        "faq_candidate_update",
        {
            "id": candidate_id,
            "status": data.get("status"),
            "faq_id": data.get("faq_id"),
        },
    )
    if row is None:
        raise HTTPException(status_code=404, detail="FAQ candidate not found")
    return row


@router.get("/faqs")
async def list_faqs(request: Request):
    return [item.model_dump(mode="json") for item in await request.app.state.faq_service.list_all(False)]


@router.post("/faqs")
async def create_faq(data: FaqItemCreate, request: Request):
    if not request.app.state.faq_service.configured:
        raise HTTPException(status_code=503, detail="FAQ persistence is not configured")
    return (await request.app.state.faq_service.create(data)).model_dump(mode="json")


@router.put("/faqs/{faq_id}")
async def update_faq(faq_id: int, data: FaqItemCreate, request: Request):
    result = await request.app.state.faq_service.update(faq_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="FAQ not found")
    return result.model_dump(mode="json")


@router.delete("/faqs/{faq_id}", status_code=204)
async def delete_faq(faq_id: int, request: Request):
    if not await request.app.state.faq_service.delete(faq_id):
        raise HTTPException(status_code=404, detail="FAQ not found")
    return Response(status_code=204)


@router.get("/hero-slides")
def list_heroes(request: Request):
    return [item.model_dump(mode="json") for item in request.app.state.hero_service.list_all()]


@router.post("/hero-slides")
def create_hero(data: HeroSlideCreate, request: Request):
    return request.app.state.hero_service.create(data).model_dump(mode="json")


@router.put("/hero-slides/{slide_id}")
def update_hero(slide_id: int, data: HeroSlideUpdate, request: Request):
    result = request.app.state.hero_service.update(slide_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="Hero slide not found")
    return result.model_dump(mode="json")


@router.delete("/hero-slides/{slide_id}", status_code=204)
def delete_hero(slide_id: int, request: Request):
    if not request.app.state.hero_service.delete(slide_id):
        raise HTTPException(status_code=404, detail="Hero slide not found")
    return Response(status_code=204)


@router.post("/hero-slides/reorder")
def reorder_heroes(items: list[HeroReorderItem], request: Request):
    return [item.model_dump(mode="json") for item in request.app.state.hero_service.reorder(items)]


@router.post("/hero-assets/upload")
async def upload_hero_asset(file: UploadFile = File(...)):
    allowed_types = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/svg+xml",
        "video/mp4",
    }
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=415, detail="Unsupported media type")
    data = await file.read()
    if len(data) > 4_500_000:
        raise HTTPException(status_code=413, detail="Server uploads are limited to 4.5 MB")

    try:
        from vercel.blob import AsyncBlobClient
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=501,
            detail="Connect a public Vercel Blob store or use an existing public media URL",
        ) from exc

    client = AsyncBlobClient()
    blob = await client.put(
        f"oppo-hero/{file.filename}",
        data,
        access="public",
        content_type=file.content_type,
        add_random_suffix=True,
    )
    return {"url": blob.url, "pathname": blob.pathname}


@router.get("/ai-health")
async def ai_health(request: Request):
    return await request.app.state.deepseek.health()


# Legacy engineering endpoints remain available but are intentionally not surfaced
# in the primary operations UI.
@router.get("/facts")
async def list_facts(request: Request):
    facts = await request.app.state.fact_service.list_active(launched_only=False)
    return [item.model_dump(mode="json") for item in facts]


@router.post("/facts")
async def upsert_fact(data: ProductFactSchema, request: Request):
    try:
        result = await request.app.state.fact_service.upsert(data)
        return result.model_dump(mode="json")
    except ValueError as exc:
        status_code = 410 if request.app.state.settings.source_b_provider == "google_sheets" else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.delete("/facts/{sku_id}", status_code=204)
async def delete_fact(sku_id: str, request: Request):
    try:
        if not await request.app.state.fact_service.delete(sku_id):
            raise HTTPException(status_code=404, detail="Product not found")
    except ValueError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    return Response(status_code=204)


@router.get("/source-b/status")
async def source_b_status(request: Request):
    return await request.app.state.fact_service.source_status()


@router.post("/source-b/refresh")
async def source_b_refresh(request: Request):
    try:
        return await request.app.state.fact_service.refresh_source()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Google Sheets sync failed: {exc}") from exc


@router.get("/leads")
def list_leads(request: Request):
    return [item.model_dump(mode="json") for item in request.app.state.lead_service.list()]

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile

from app.auth import require_admin
from app.schemas import (
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


@router.get("/hero-slides")
def list_heroes(request: Request):
    return [
        item.model_dump(mode="json")
        for item in request.app.state.hero_service.list_all()
    ]


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
    return [
        item.model_dump(mode="json")
        for item in request.app.state.hero_service.reorder(items)
    ]


@router.get("/ai-health")
async def ai_health(request: Request):
    return await request.app.state.deepseek.health()


@router.get("/analytics/summary")
def analytics_summary(request: Request):
    return request.app.state.analytics_service.summary()


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

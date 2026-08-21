from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile

from app.auth import require_admin
from app.schemas import (
    HeroReorderItem,
    HeroSlideCreate,
    HeroSlideUpdate,
    ProductFactSchema,
)
from app.services.hero_assets import (
    HeroAssetConfigurationError,
    HeroAssetUploadError,
    HeroAssetValidationError,
)

logger = logging.getLogger(__name__)

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
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/facts/{sku_id}", status_code=204)
async def delete_fact(sku_id: str, request: Request):
    if not await request.app.state.fact_service.delete(sku_id):
        raise HTTPException(status_code=404, detail="Product not found")
    return Response(status_code=204)


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
async def upload_hero_asset(request: Request, file: UploadFile = File(...)):
    try:
        data = await file.read()
        result = await request.app.state.hero_asset_storage.upload(
            data,
            file.content_type,
        )
        return {"url": result.url, "pathname": result.pathname}
    except HeroAssetConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail="Vercel Blob is not configured; use a managed media URL instead",
        ) from exc
    except HeroAssetValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HeroAssetUploadError as exc:
        logger.exception("hero_asset_upload_failed")
        raise HTTPException(status_code=502, detail="Hero image upload failed") from exc
    finally:
        await file.close()

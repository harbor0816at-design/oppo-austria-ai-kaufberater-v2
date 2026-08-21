from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/ui", tags=["ui"])


@router.get("/hero-slides")
def hero_slides(request: Request):
    slides = request.app.state.hero_service.list_active()
    return [
        slide.model_dump(mode="json") if hasattr(slide, "model_dump") else slide
        for slide in slides
    ]


@router.get("/products")
async def products(request: Request):
    facts = await request.app.state.fact_service.list_active(launched_only=True)
    return [
        {
            "sku_id": fact.sku_id,
            "product_name": fact.product_name,
            "price": (
                fact.pricing.official_price if fact.pricing.is_price_public else None
            ),
            "product_url": fact.product_url,
            "purchase_url": fact.purchase_url,
        }
        for fact in facts
    ]

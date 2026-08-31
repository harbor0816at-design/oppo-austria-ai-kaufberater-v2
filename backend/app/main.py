from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

try:
    from vercel.headers import set_headers
except Exception:  # pragma: no cover - local test environments may not install vercel
    def set_headers(headers):
        return None

from app.agent.graph import PresalesWorkflow
from app.api import admin, analytics, chat, leads, ui
from app.cache import HotCache
from app.config import get_settings
from app.db import Base, build_engine, build_session_factory
from app.services.analytics import AnalyticsService
from app.services.audits import AuditService
from app.services.conversations import ConversationService
from app.services.deepseek_gateway import ProductionDeepSeekClient
from app.services.fallback_facts import FallbackFactService
from app.services.faq_fallback import ProductionFAQService
from app.services.heroes import HeroService
from app.services.google_sheets import GoogleSheetsSource
from app.services.leads import LeadService
from app.services.public_search import PublicSearchService


EXPECTED_FAQ_SPREADSHEET_ID = "1MBk3s272IhbcJSXTIp16oPuKA2Su9dNbHeHEY_qmI38"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    cache = HotCache(settings.redis_url)
    await cache.ping()

    google_sheets_source = GoogleSheetsSource(
        settings.google_sheets_spreadsheet_id,
        settings.google_service_account_json,
        settings.google_service_account_json_b64,
        settings.google_sheets_products_range,
        settings.google_sheets_promotions_range,
        settings.google_sheets_services_range,
        settings.google_sheets_knowledge_range,
        settings.google_sheets_competitor_range,
        settings.google_sheets_competitor_facts_range,
    )
    fact_service = FallbackFactService(
        session_factory,
        cache,
        source_b_provider=settings.source_b_provider,
        google_source=google_sheets_source,
        sheet_cache_ttl_seconds=settings.google_sheets_cache_ttl_seconds,
        fail_open=settings.google_sheets_fail_open,
    )
    faq_service = ProductionFAQService(
        google_sheets_source,
        cache,
        settings.faq_spreadsheet_id,
        settings.faq_cache_ttl_seconds,
    )
    lead_service = LeadService(session_factory)
    hero_service = HeroService(session_factory)
    analytics_service = AnalyticsService(session_factory)
    audit_service = AuditService(session_factory)
    conversation_service = ConversationService(
        session_factory,
        cache,
        settings.session_ttl_seconds,
    )
    public_search = PublicSearchService(
        settings.brave_search_api_key,
        cache,
        official_timeout_seconds=settings.competitor_official_fetch_timeout_seconds,
        official_cache_ttl_seconds=settings.competitor_official_cache_ttl_seconds,
    )
    deepseek = ProductionDeepSeekClient(
        settings.deepseek_api_key,
        settings.deepseek_model,
        settings.deepseek_reasoning_model,
        settings.deepseek_base_url,
    )
    workflow = PresalesWorkflow(
        settings,
        fact_service,
        lead_service,
        conversation_service,
        public_search,
        deepseek,
        audit_service,
        faq_service=faq_service,
    )

    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.cache = cache
    app.state.fact_service = fact_service
    app.state.faq_service = faq_service
    app.state.google_sheets_source = google_sheets_source
    app.state.lead_service = lead_service
    app.state.hero_service = hero_service
    app.state.analytics_service = analytics_service
    app.state.audit_service = audit_service
    app.state.conversation_service = conversation_service
    app.state.public_search = public_search
    app.state.deepseek = deepseek
    app.state.workflow = workflow

    try:
        yield
    finally:
        await cache.close()
        engine.dispose()


app = FastAPI(
    title="OPPO Austria AI-Kaufberater API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def vercel_context_middleware(request: Request, call_next):
    set_headers(request.headers)
    return await call_next(request)


settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(ui.router)
app.include_router(leads.router)
app.include_router(analytics.router)
app.include_router(admin.router)


@app.get("/")
def root():
    return {
        "service": "OPPO Austria AI-Kaufberater API",
        "status": "ok",
        "ai_provider": "deepseek",
    }


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
async def readyz(response: Response):
    checks: dict[str, bool] = {}
    metrics: dict[str, int] = {}
    details: dict[str, object] = {}

    try:
        with app.state.session_factory() as session:
            session.execute(text("SELECT 1"))
        checks["database_connected"] = True
    except Exception as exc:
        checks["database_connected"] = False
        details["database_error"] = exc.__class__.__name__

    deepseek = app.state.deepseek
    checks["deepseek_configured"] = bool(deepseek and deepseek.configured)
    deepseek_health = await deepseek.health() if deepseek else {}
    checks["deepseek_reachable"] = bool(
        deepseek_health.get("api_reachable")
        and deepseek_health.get("response_received")
    )
    details["deepseek_health"] = deepseek_health

    source_status = await app.state.fact_service.source_status()
    checks["source_b_configured"] = bool(source_status.get("configured"))
    try:
        facts = await app.state.fact_service.list_active(launched_only=False)
    except Exception as exc:
        facts = []
        details["source_b_error"] = exc.__class__.__name__
    metrics["source_b_product_count"] = len(facts)
    checks["source_b_loadable"] = len(facts) > 0
    details["source_b"] = source_status

    faq_status = await app.state.faq_service.status()
    checks["faq_first_configured"] = bool(faq_status.get("configured"))
    checks["faq_spreadsheet_id_expected"] = (
        faq_status.get("spreadsheet_id") == EXPECTED_FAQ_SPREADSHEET_ID
    )
    faq_match = await app.state.faq_service.match("官网手机质保多久？", "zh")
    checks["faq_first_loadable"] = bool(faq_match and "3年保修" in faq_match.answer)
    details["faq"] = faq_status

    checks["vercel_runtime_detected"] = bool(
        os.getenv("VERCEL")
        or os.getenv("VERCEL_ENV")
        or os.getenv("VERCEL_OIDC_TOKEN")
    )

    required = [
        "database_connected",
        "deepseek_configured",
        "deepseek_reachable",
        "source_b_configured",
        "source_b_loadable",
        "faq_first_configured",
        "faq_spreadsheet_id_expected",
        "faq_first_loadable",
    ]
    ready = all(checks.get(key) for key in required)
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if ready else "degraded",
        "checks": checks,
        "metrics": metrics,
        "details": details,
    }

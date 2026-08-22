from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from vercel.headers import set_headers

from app.agent.graph import PresalesWorkflow
from app.api import admin, analytics, chat, leads, ui
from app.cache import HotCache
from app.config import get_settings
from app.db import Base, build_engine, build_session_factory
from app.persistence_auth import public_key_b64
from app.services.analytics import AnalyticsService
from app.services.audits import AuditService
from app.services.conversations import ConversationService
from app.services.deepseek import DeepSeekClient
from app.services.facts import FactService
from app.services.faqs import FaqService
from app.services.heroes import HeroService
from app.services.google_sheets import GoogleSheetsSource
from app.services.leads import LeadService
from app.services.persistence import RemotePersistenceClient
from app.services.public_search import PublicSearchService


def _admin_data_url(persistence_url: str | None) -> str | None:
    value = (persistence_url or "").strip().rstrip("/")
    if not value or "/" not in value:
        return None
    return value.rsplit("/", 1)[0] + "/kaufberater-admin-data"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    cache = HotCache(settings.redis_url)
    await cache.ping()

    persistence = RemotePersistenceClient(
        settings.persistence_url,
        settings.admin_api_key,
        settings.remote_persistence_enabled,
    )
    admin_persistence = RemotePersistenceClient(
        _admin_data_url(settings.persistence_url),
        settings.admin_api_key,
        settings.remote_persistence_enabled,
    )

    google_sheets_source = GoogleSheetsSource(
        settings.google_sheets_spreadsheet_id,
        settings.google_service_account_json,
        settings.google_service_account_json_b64,
        settings.google_sheets_products_range,
        settings.google_sheets_promotions_range,
        settings.google_sheets_services_range,
    )
    fact_service = FactService(
        session_factory,
        cache,
        source_b_provider=settings.source_b_provider,
        google_source=google_sheets_source,
        sheet_cache_ttl_seconds=settings.google_sheets_cache_ttl_seconds,
        fail_open=settings.google_sheets_fail_open,
        persistence=persistence,
    )
    lead_service = LeadService(session_factory, persistence=persistence)
    hero_service = HeroService(session_factory, persistence=persistence)
    faq_service = FaqService(admin_persistence)
    analytics_service = AnalyticsService(
        session_factory,
        persistence=persistence,
        admin_persistence=admin_persistence,
    )
    audit_service = AuditService(session_factory, persistence=persistence)
    conversation_service = ConversationService(
        session_factory,
        cache,
        settings.session_ttl_seconds,
        persistence=persistence,
    )
    conversation_service.purge_expired()
    public_search = PublicSearchService(settings.brave_search_api_key)
    deepseek = DeepSeekClient(
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
    )

    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.cache = cache
    app.state.persistence = persistence
    app.state.admin_persistence = admin_persistence
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
    version="1.1.0",
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
    allow_origin_regex=(
        r"https://oppo-austria-ai-kaufberater-web(?:-[a-z0-9-]+)?\.vercel\.app"
    ),
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


@app.get("/system/persistence-public-key")
def persistence_public_key(request: Request, response: Response):
    runtime_settings = request.app.state.settings
    if not runtime_settings.admin_key_secure:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_configured"}
    return {
        "status": "ok",
        "algorithm": "Ed25519",
        "key": public_key_b64(runtime_settings.admin_api_key),
    }


@app.get("/readyz")
async def readyz(request: Request, response: Response):
    runtime = request.app.state
    settings = runtime.settings

    database_connected = True
    try:
        with runtime.session_factory() as session:
            session.execute(text("SELECT 1"))
    except Exception:
        database_connected = False

    persistence_reachable = await runtime.persistence.ahealth()
    admin_data_reachable = await runtime.admin_persistence.ahealth()

    deepseek_configured = runtime.deepseek.configured
    deepseek_reachable = False
    ai_health = {
        "transport": "not_checked",
        "model": settings.deepseek_model,
        "authenticated": False,
        "api_reachable": False,
        "response_received": False,
        "status_code": None,
        "error": None,
        "error_code": None,
    }
    if deepseek_configured:
        try:
            ai_health = await runtime.deepseek.health()
            deepseek_reachable = bool(
                ai_health.get("api_reachable") and ai_health.get("response_received")
            )
        except Exception as exc:
            ai_health = {**ai_health, "error": exc.__class__.__name__}

    google_source_configured = bool(
        runtime.google_sheets_source and runtime.google_sheets_source.configured
    )
    source_b_loadable = False
    source_b_product_count = 0
    try:
        catalog = await runtime.fact_service.list_active(launched_only=False)
        source_b_product_count = len(catalog)
        source_b_loadable = source_b_product_count > 0
    except Exception:
        source_b_loadable = False

    source_b_configured = (
        settings.source_b_provider != "google_sheets"
        or google_source_configured
        or (persistence_reachable and source_b_loadable)
    )

    distributed_rate_limit = bool(settings.redis_url and runtime.cache.redis is not None)

    checks = {
        "deepseek_configured": deepseek_configured,
        "deepseek_reachable": deepseek_reachable,
        "source_b_configured": source_b_configured,
        "source_b_loadable": source_b_loadable,
        "database_connected": database_connected,
        "database_persistent": (
            persistence_reachable
            if settings.is_production
            else (settings.database_persistent or persistence_reachable)
        ),
        "admin_key_secure": settings.admin_key_secure if settings.is_production else True,
    }
    ready = all(checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    safe_ai_health = {
        key: ai_health.get(key)
        for key in (
            "transport",
            "model",
            "reasoning_model",
            "authenticated",
            "api_reachable",
            "response_received",
            "status_code",
            "error",
            "error_code",
        )
        if key in ai_health
    }

    return {
        "status": "ready" if ready else "not_ready",
        "checks": checks,
        "metrics": {"source_b_product_count": source_b_product_count},
        "optional": {
            "deepseek_health": safe_ai_health,
            "google_source_configured": google_source_configured,
            "distributed_rate_limit": distributed_rate_limit,
            "public_search_configured": bool(settings.brave_search_api_key),
            "remote_persistence_reachable": persistence_reachable,
            "admin_data_reachable": admin_data_reachable,
            "faq_configured": runtime.faq_service.configured,
        },
    }

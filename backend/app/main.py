from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.graph import PresalesWorkflow
from app.api import admin, analytics, chat, leads, ui
from app.cache import HotCache
from app.config import get_settings
from app.db import Base, build_engine, build_session_factory
from app.services.analytics import AnalyticsService
from app.services.audits import AuditService
from app.services.conversations import ConversationService
from app.services.deepseek import DeepSeekClient
from app.services.facts import FactService
from app.services.heroes import HeroService
from app.services.leads import LeadService
from app.services.public_search import PublicSearchService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    cache = HotCache(settings.redis_url)
    await cache.ping()

    fact_service = FactService(session_factory, cache)
    lead_service = LeadService(session_factory)
    hero_service = HeroService(session_factory)
    analytics_service = AnalyticsService(session_factory)
    audit_service = AuditService(session_factory)
    conversation_service = ConversationService(
        session_factory,
        cache,
        settings.session_ttl_seconds,
    )
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
    app.state.fact_service = fact_service
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

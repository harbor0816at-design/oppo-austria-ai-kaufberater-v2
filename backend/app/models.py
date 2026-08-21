from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProductFactORM(Base):
    __tablename__ = "product_facts"

    sku_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    product_name: Mapped[str] = mapped_column(String(300), nullable=False)
    official_status: Mapped[str] = mapped_column(String(32), nullable=False)
    pricing: Mapped[dict] = mapped_column(JSON, nullable=False)
    gifts: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    shipping_commitments: Mapped[dict] = mapped_column(JSON, nullable=False)
    key_features: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidential_fields: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    localized_content: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    product_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    purchase_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class LeadORM(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contact: Mapped[str] = mapped_column(String(320), nullable=False)
    target_sku: Mapped[str] = mapped_column(String(100), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    consent_marketing: Mapped[bool] = mapped_column(Boolean, nullable=False)
    consent_version: Mapped[str] = mapped_column(String(64), nullable=False, default="launch-v1")
    locale: Mapped[str] = mapped_column(String(32), nullable=False, default="de-AT")
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLogORM(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sku_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    request_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HeroSlideORM(Base):
    __tablename__ = "hero_slides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    subtitle: Mapped[str] = mapped_column(String(800), nullable=False, default="")
    title_en: Mapped[str | None] = mapped_column(String(300), nullable=True)
    subtitle_en: Mapped[str | None] = mapped_column(String(800), nullable=True)
    title_zh: Mapped[str | None] = mapped_column(String(300), nullable=True)
    subtitle_zh: Mapped[str | None] = mapped_column(String(800), nullable=True)
    eyebrow: Mapped[str | None] = mapped_column(String(120), nullable=True)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False, default="image")
    media_url: Mapped[str] = mapped_column(String(1200), nullable=False)
    mobile_media_url: Mapped[str | None] = mapped_column(String(1200), nullable=True)
    cta_label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    cta_label_en: Mapped[str | None] = mapped_column(String(160), nullable=True)
    cta_label_zh: Mapped[str | None] = mapped_column(String(160), nullable=True)
    cta_url: Mapped[str | None] = mapped_column(String(1200), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AnalyticsEventORM(Base):
    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_name: Mapped[str] = mapped_column(String(80), nullable=False)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConversationORM(Base):
    __tablename__ = "conversations"

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="de")
    profile: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    messages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

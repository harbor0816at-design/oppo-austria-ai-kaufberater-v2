from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OfficialStatus(str, Enum):
    unannounced = "unannounced"
    pre_order = "pre_order"
    launched = "launched"


class PricingSchema(BaseModel):
    is_price_public: bool
    official_price: float | None = Field(default=None, ge=0)
    early_bird_deposit: float | None = Field(default=None, ge=0)
    deposit_discount_value: float | None = Field(default=None, ge=0)
    refund_policy: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_pricing(self) -> "PricingSchema":
        if not self.is_price_public:
            self.official_price = None
        elif self.official_price is None:
            raise ValueError("official_price is required when is_price_public=true")

        deposit_only = (self.early_bird_deposit is None) != (
            self.deposit_discount_value is None
        )
        if deposit_only:
            raise ValueError(
                "early_bird_deposit and deposit_discount_value must both be set or both be null"
            )
        if (
            self.early_bird_deposit is not None
            and self.deposit_discount_value is not None
            and self.early_bird_deposit >= self.deposit_discount_value
        ):
            raise ValueError(
                "early_bird_deposit must be strictly less than deposit_discount_value"
            )
        return self


class GiftSchema(BaseModel):
    item_name: str = Field(min_length=1, max_length=200)
    stock_status: str = Field(min_length=1, max_length=100)
    value: float = Field(ge=0)


class ShippingSchema(BaseModel):
    timeline: str = Field(min_length=1, max_length=500)
    regions: list[str] = Field(min_length=1)

    @field_validator("regions")
    @classmethod
    def normalize_regions(cls, value: list[str]) -> list[str]:
        normalized = [item.strip().upper() for item in value if item.strip()]
        if not normalized:
            raise ValueError("regions cannot be empty")
        return list(dict.fromkeys(normalized))


class ProductFactSchema(BaseModel):
    sku_id: str = Field(min_length=1, max_length=100)
    product_name: str = Field(min_length=1, max_length=300)
    official_status: OfficialStatus
    pricing: PricingSchema
    gifts: list[GiftSchema] = Field(default_factory=list)
    shipping_commitments: ShippingSchema
    key_features: list[str] = Field(default_factory=list)
    confidential_fields: list[str] = Field(default_factory=list)
    localized_content: dict[str, Any] = Field(default_factory=dict)
    product_url: str | None = Field(default=None, max_length=1000)
    purchase_url: str | None = Field(default=None, max_length=1000)
    is_active: bool = True

    @field_validator("confidential_fields")
    @classmethod
    def normalize_confidential_fields(cls, value: list[str]) -> list[str]:
        return list(
            dict.fromkeys(
                item.strip().lower() for item in value if item.strip()
            )
        )

    @model_validator(mode="after")
    def validate_preorder(self) -> "ProductFactSchema":
        if self.official_status == OfficialStatus.pre_order and (
            self.pricing.early_bird_deposit is None
            or self.pricing.deposit_discount_value is None
        ):
            raise ValueError(
                "pre_order products require early_bird_deposit and deposit_discount_value"
            )
        return self


class ProductFactRead(ProductFactSchema):
    created_at: datetime | None = None
    updated_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class HeroSlideBase(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    subtitle: str = Field(default="", max_length=800)
    title_en: str | None = Field(default=None, max_length=300)
    subtitle_en: str | None = Field(default=None, max_length=800)
    title_zh: str | None = Field(default=None, max_length=300)
    subtitle_zh: str | None = Field(default=None, max_length=800)
    eyebrow: str | None = Field(default=None, max_length=120)
    media_type: Literal["image", "video"] = "image"
    media_url: str = Field(min_length=1, max_length=1200)
    mobile_media_url: str | None = Field(default=None, max_length=1200)
    cta_label: str | None = Field(default=None, max_length=160)
    cta_label_en: str | None = Field(default=None, max_length=160)
    cta_label_zh: str | None = Field(default=None, max_length=160)
    cta_url: str | None = Field(default=None, max_length=1200)
    sort_order: int = 0
    is_active: bool = True
    start_at: datetime | None = None
    end_at: datetime | None = None


class HeroSlideCreate(HeroSlideBase):
    pass


class HeroSlideUpdate(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    title_en: str | None = None
    subtitle_en: str | None = None
    title_zh: str | None = None
    subtitle_zh: str | None = None
    eyebrow: str | None = None
    media_type: Literal["image", "video"] | None = None
    media_url: str | None = None
    mobile_media_url: str | None = None
    cta_label: str | None = None
    cta_label_en: str | None = None
    cta_label_zh: str | None = None
    cta_url: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None


class HeroSlideRead(HeroSlideBase):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class HeroReorderItem(BaseModel):
    id: int
    sort_order: int


class ChatContext(BaseModel):
    sku: str | None = Field(default=None, max_length=100)


class ChatRequest(BaseModel):
    session_id: str | None = Field(default=None, max_length=128)
    channel: Literal["web"] = "web"
    source: str = "smartphone_finder"
    locale: str = Field(default="de-AT", max_length=32)
    message: str = Field(min_length=1, max_length=4000)
    context: ChatContext = Field(default_factory=ChatContext)


class LeadSubscribeRequest(BaseModel):
    contact: str = Field(min_length=3, max_length=320)
    target_sku: str = Field(min_length=1, max_length=100)
    channel: Literal["email", "whatsapp"]
    consent_marketing: bool
    consent_version: str = Field(default="launch-v1", max_length=64)
    locale: str = Field(default="de-AT", max_length=32)
    session_id: str | None = Field(default=None, max_length=128)


class LeadRead(BaseModel):
    id: int
    contact: str
    target_sku: str
    channel: str
    consent_marketing: bool
    consent_version: str
    locale: str
    session_id: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AnalyticsEventCreate(BaseModel):
    event_name: str = Field(min_length=1, max_length=80)
    session_id: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)


class PublicSearchResult(BaseModel):
    title: str
    url: str
    snippet: str


class AgentResult(BaseModel):
    response_markdown: str
    cards: list[dict[str, Any]] = Field(default_factory=list)
    route: str
    blocked: bool = False

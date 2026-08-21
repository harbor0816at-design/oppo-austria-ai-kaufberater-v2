import asyncio

import pytest

from app.config import Settings
from app.db import Base, build_engine, build_session_factory
from app.models import HeroSlideORM
from app.services.deepseek import DeepSeekClient
from app.services.hero_assets import (
    HeroAssetConfigurationError,
    HeroAssetStorage,
    HeroAssetValidationError,
)
from app.services.heroes import DEFAULT_SLIDES, HeroService


def make_hero(title: str, active: bool = True) -> HeroSlideORM:
    return HeroSlideORM(
        title=title,
        subtitle="Approved hero copy",
        media_type="image",
        media_url="https://example.com/hero.webp",
        sort_order=1,
        is_active=active,
    )


def build_hero_service():
    settings = Settings(database_url="sqlite:///:memory:")
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    return HeroService(build_session_factory(engine))


def test_hero_service_returns_backend_fallback_when_database_is_empty():
    slides = build_hero_service().list_active()

    assert len(slides) == 3
    assert [slide["id"] for slide in slides] == [-1, -2, -3]
    assert all(slide["is_active"] is True for slide in slides)


def test_hero_service_returns_only_active_database_slides():
    service = build_hero_service()
    with service.session_factory() as session:
        session.add(make_hero("Active", active=True))
        session.add(make_hero("Inactive", active=False))
        session.commit()

    slides = service.list_active()

    assert len(slides) == 1
    assert slides[0].title == "Active"


def test_hero_service_returns_fallback_when_database_read_fails():
    class BrokenSessionFactory:
        def __call__(self):
            raise RuntimeError("database unavailable")

    slides = HeroService(BrokenSessionFactory()).list_active()

    assert slides == DEFAULT_SLIDES


def test_deepseek_rejects_non_deepseek_endpoint_and_unsupported_models():
    with pytest.raises(ValueError):
        DeepSeekClient("key", "deepseek-v4-flash", "deepseek-v4-pro", "https://api.openai.com")
    with pytest.raises(ValueError):
        DeepSeekClient("key", "deepseek-chat", "deepseek-v4-pro", "https://api.deepseek.com")


def test_production_settings_require_deepseek_and_a_real_admin_secret():
    with pytest.raises(ValueError):
        Settings(
            app_env="production",
            deepseek_api_key=None,
            admin_api_key="change-me",
        )


def test_comparison_uses_the_deepseek_reasoning_model():
    client = DeepSeekClient(
        "key",
        "deepseek-v4-flash",
        "deepseek-v4-pro",
        "https://api.deepseek.com",
    )
    captured = []

    async def fake_request(payload, timeout=45):
        captured.append(payload)
        return {"choices": [{"message": {"content": "OK"}}]}

    client._request = fake_request

    result = asyncio.run(client.complete_with_tools([], [], lambda *_: None, reasoning=True))

    assert result == "OK"
    assert captured[0]["model"] == "deepseek-v4-pro"


def test_hero_asset_upload_validates_content_and_never_uses_local_storage():
    png = b"\x89PNG\r\n\x1a\n" + b"approved-image"
    extension, content_type = HeroAssetStorage._validate(png, "image/png")
    assert (extension, content_type) == ("png", "image/png")

    with pytest.raises(HeroAssetValidationError):
        HeroAssetStorage._validate(b"not an image", "image/png")
    with pytest.raises(HeroAssetConfigurationError):
        asyncio.run(HeroAssetStorage(None).upload(png, "image/png"))

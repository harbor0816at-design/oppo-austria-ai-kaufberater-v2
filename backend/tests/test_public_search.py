import asyncio

from app.schemas import PublicSearchResult
from app.services.public_search import PublicSearchService


class OfficialFirstSearch(PublicSearchService):
    def __init__(self):
        super().__init__("brave-key")
        self.brave_called = False

    async def _direct_official(self, query, refs, facts, count):
        return [PublicSearchResult(
            title="Samsung Austria official",
            url="https://www.samsung.com/at/smartphones/galaxy-s26-ultra/",
            snippet="5000 mAh",
            source_type="official_live",
            source_authority="official_manufacturer_at",
            market="AT",
        )]

    async def _brave_search(self, *args, **kwargs):
        self.brave_called = True
        raise AssertionError("Brave must not run when direct official fetch succeeds")


def test_direct_official_precedes_brave():
    service = OfficialFirstSearch()
    result = asyncio.run(service.search(
        "Samsung Galaxy S26 Ultra battery",
        set(),
        set(),
        official_references=[{
            "brand": "Samsung",
            "market": "AT",
            "source_type": "official_manufacturer",
            "source_url": "https://www.samsung.com/at/smartphones/",
            "is_active": True,
        }],
    ))
    assert result[0].source_type == "official_live"
    assert service.brave_called is False


class BraveFallbackSearch(PublicSearchService):
    def __init__(self):
        super().__init__("brave-key")
        self.calls = []

    async def _direct_official(self, query, refs, facts, count):
        return []

    async def _brave_search(self, query, *, count, allowed_domains=None, official_only=False):
        self.calls.append((query, official_only, allowed_domains))
        return [PublicSearchResult(
            title="Samsung official result",
            url="https://www.samsung.com/at/smartphones/galaxy-s26-ultra/",
            snippet="official result",
            source_type="brave_official",
            source_authority="official_manufacturer",
            market="AT",
        )]


def test_brave_official_domain_is_second_choice():
    service = BraveFallbackSearch()
    result = asyncio.run(service.search(
        "Samsung Galaxy S26 Ultra",
        set(),
        set(),
        official_references=[{
            "brand": "Samsung",
            "market": "AT",
            "source_type": "official_manufacturer",
            "source_url": "https://www.samsung.com/at/smartphones/",
            "is_active": True,
        }],
    ))
    assert result[0].source_type == "brave_official"
    assert service.calls[0][1] is True


class PublicReviewSearch(PublicSearchService):
    def __init__(self):
        super().__init__("brave-key")
        self.query = None

    async def _direct_official(self, query, refs, facts, count):
        raise AssertionError("Public reviews must bypass official competitor discovery")

    async def _brave_search(self, query, *, count, allowed_domains=None, official_only=False):
        self.query = query
        return [
            PublicSearchResult(
                title="Find X9 Pro review",
                url="https://www.youtube.com/watch?v=verified-review",
                snippet="Independent English review",
            ),
            PublicSearchResult(
                title="Unrelated product page",
                url="https://www.samsung.com/at/smartphones/",
                snippet="Not a video",
            ),
        ]


def test_youtube_review_search_returns_only_real_youtube_results():
    service = PublicReviewSearch()
    result = asyncio.run(
        service.search(
            "OPPO Find X9 Pro YouTube review",
            set(),
            set(),
            official_references=[{"source_url": "https://www.samsung.com/at/"}],
            public_review=True,
        )
    )
    assert service.query == "OPPO Find X9 Pro review site:youtube.com"
    assert [item.url for item in result] == [
        "https://www.youtube.com/watch?v=verified-review"
    ]


def test_youtube_html_parser_returns_real_watch_links_with_metadata():
    html = (
        '{"videoRenderer":{"videoId":"qXPVnv95sZM","title":{"runs":'
        '[{"text":"OPPO Find X9 Pro Review."}]},"longBylineText":{"runs":'
        '[{"text":"The Tech Chap"}]},"publishedTimeText":{"simpleText":'
        '"10 months ago"}}}'
    )
    results = PublicSearchService._youtube_results_from_html(
        html,
        "OPPO Find X9 Pro review",
        5,
    )
    assert len(results) == 1
    assert results[0].title == "OPPO Find X9 Pro Review."
    assert results[0].url == "https://www.youtube.com/watch?v=qXPVnv95sZM"
    assert "The Tech Chap" in results[0].snippet
    assert results[0].source_authority == "independent_review"


class YouTubeFallbackSearch(PublicSearchService):
    def __init__(self):
        super().__init__(None)
        self.youtube_query = None

    async def _brave_search(self, *args, **kwargs):
        return []

    async def _youtube_search(self, query, count):
        self.youtube_query = query
        return [
            PublicSearchResult(
                title="OPPO Find X9 Pro Review.",
                url="https://www.youtube.com/watch?v=qXPVnv95sZM",
                snippet="The Tech Chap",
                source_type="youtube_public",
                source_authority="independent_review",
            )
        ]


def test_youtube_public_page_is_used_when_brave_has_no_video():
    service = YouTubeFallbackSearch()
    result = asyncio.run(
        service.search(
            "给我 OPPO Find X9 Pro 的 YouTube 测评链接",
            set(),
            set(),
            public_review=True,
        )
    )
    assert service.youtube_query == "OPPO Find X9 Pro review"
    assert result[0].url == "https://www.youtube.com/watch?v=qXPVnv95sZM"


class SheetFallbackSearch(PublicSearchService):
    def __init__(self):
        super().__init__(None)

    async def _direct_official(self, query, refs, facts, count):
        return []


def test_sheet_b_verified_competitor_fact_is_last_known_good():
    service = SheetFallbackSearch()
    result = asyncio.run(service.search(
        "Samsung Galaxy S26 Ultra battery",
        set(),
        set(),
        competitor_facts=[{
            "competitor_id": "AT-SAMSUNG-GALAXY-S26-ULTRA",
            "brand": "Samsung",
            "product_name": "Samsung Galaxy S26 Ultra",
            "market": "AT",
            "is_active": True,
            "battery_mah": 5000,
            "official_specs_url": "https://www.samsung.com/at/smartphones/galaxy-s26-ultra/specs/",
            "verified_at": "2026-08-26",
            "source_authority": "official_manufacturer_at",
        }],
    ))
    assert result[0].source_type == "sheet_b_verified_cache"
    assert "5000" in result[0].snippet


def test_public_source_status_reports_evidence_chain():
    service = PublicSearchService("brave-key")
    refs = [
        {
            "brand": "Samsung",
            "market": "AT",
            "source_type": "official_manufacturer_at",
            "source_url": "https://www.samsung.com/at/smartphones/galaxy-s26-ultra/specs/",
            "is_active": True,
        }
    ]
    facts = [
        {
            "brand": "Samsung",
            "product_name": "Galaxy S26 Ultra",
            "market": "AT",
            "is_active": True,
            "verified_at": "2026-08-26",
            "fact_freshness_days": 30,
            "official_specs_url": "https://www.samsung.com/at/smartphones/galaxy-s26-ultra/specs/",
        }
    ]
    status = service.status(official_references=refs, competitor_facts=facts)
    assert status["official_direct_fetch_enabled"] is True
    assert status["brave_configured"] is True
    assert status["official_reference_count"] == 1
    assert status["competitor_fact_count"] == 1
    assert "samsung.com" in status["approved_official_domains"]
    assert status["ai_fact_source"] is False
    assert status["missing_fact_policy"] == "exact_or_unknown"

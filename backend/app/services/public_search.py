from __future__ import annotations

import re

import httpx

from app.schemas import PublicSearchResult


class PublicSearchRejected(ValueError):
    pass


class PublicSearchService:
    def __init__(self, api_key: str | None):
        self.api_key = api_key

    @staticmethod
    def validate(
        query: str,
        confidential_terms: set[str],
        unreleased_names: set[str],
    ) -> None:
        lower = query.lower()
        banned = (
            "leak",
            "leaked",
            "rumor",
            "rumour",
            "spy shot",
            "prototype",
            "gerücht",
            "geleakt",
            "爆料",
            "泄露",
            "谍照",
            "工程机",
        )
        if any(term in lower for term in banned):
            raise PublicSearchRejected("Leak or rumor searches are not allowed")
        if any(term.lower() in lower for term in confidential_terms if term):
            raise PublicSearchRejected(
                "Confidential Source_B fields cannot be searched"
            )
        if any(name.lower() in lower for name in unreleased_names if name):
            raise PublicSearchRejected(
                "Unreleased OPPO products cannot be searched on public sources"
            )

    async def search(
        self,
        query: str,
        confidential_terms: set[str],
        unreleased_names: set[str],
        count: int = 5,
    ) -> list[PublicSearchResult]:
        self.validate(query, confidential_terms, unreleased_names)
        if not self.api_key:
            return []

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": min(count, 10)},
                headers={
                    "X-Subscription-Token": self.api_key,
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

        results: list[PublicSearchResult] = []
        for item in data.get("web", {}).get("results", [])[:count]:
            url = item.get("url")
            title = item.get("title")
            if not url or not title:
                continue
            snippet = re.sub(r"<[^>]+>", "", item.get("description", ""))
            results.append(PublicSearchResult(title=title, url=url, snippet=snippet))
        return results

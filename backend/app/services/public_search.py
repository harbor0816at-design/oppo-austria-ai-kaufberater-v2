from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote_plus, urljoin, urlparse

import httpx

from app.schemas import PublicSearchResult


class PublicSearchRejected(ValueError):
    pass


_BRAND_ALIASES = {
    "apple": ("apple", "iphone"),
    "samsung": ("samsung", "galaxy"),
    "xiaomi": ("xiaomi", "redmi", "poco"),
    "google": ("google", "pixel"),
    "honor": ("honor",),
    "oneplus": ("oneplus", "1+"),
    "nothing": ("nothing", "nothing phone"),
    "motorola": ("motorola", "moto"),
    "huawei": ("huawei",),
    "sony": ("sony", "xperia"),
    "realme": ("realme",),
}

_STOPWORDS = {
    "a", "an", "and", "at", "be", "compare", "current", "der", "die", "das",
    "ein", "eine", "for", "gegen", "give", "ich", "in", "is", "latest", "link",
    "links", "mit", "of", "official", "oder", "page", "price", "spec", "specs",
    "the", "to", "und", "vs", "website", "with", "you", "your", "直接", "给我",
    "链接", "官网", "比较", "对比", "参数", "规格", "最新", "当前", "价格",
}


class _OfficialHTMLParser(HTMLParser):
    """Tiny dependency-free HTML extractor for manufacturer pages.

    We intentionally do not try to turn arbitrary HTML into structured product facts.
    The extractor only produces a bounded evidence text plus same-domain links; the
    authoritative competitor fields remain the verified rows in Sheet-B.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.description = ""
        self.text_parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._in_title = False
        self._skip_depth = 0
        self._current_href: str | None = None
        self._current_anchor: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        attrs_dict = {str(k).lower(): v for k, v in attrs}
        if name == "title":
            self._in_title = True
        if name in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if name == "meta":
            key = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
            if key in {"description", "og:description", "twitter:description"}:
                content = (attrs_dict.get("content") or "").strip()
                if content and not self.description:
                    self.description = content
        if name == "a":
            href = (attrs_dict.get("href") or "").strip()
            if href:
                self._current_href = href
                self._current_anchor = []

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name == "title":
            self._in_title = False
        if name in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if name == "a" and self._current_href:
            anchor = " ".join(self._current_anchor).strip()
            self.links.append((self._current_href, anchor))
            self._current_href = None
            self._current_anchor = []

    def handle_data(self, data: str) -> None:
        text = re.sub(r"\s+", " ", unescape(data)).strip()
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        if self._current_href:
            self._current_anchor.append(text)
        if not self._skip_depth:
            self.text_parts.append(text)

    @property
    def title(self) -> str:
        return " ".join(self.title_parts).strip()

    @property
    def text(self) -> str:
        # De-duplicate immediate repeated fragments common on highly dynamic pages.
        out: list[str] = []
        previous = None
        for item in self.text_parts:
            if item != previous:
                out.append(item)
            previous = item
        return " ".join(out)


class PublicSearchService:
    """Competitor/public evidence service.

    Source order for competitor/current facts:
      1. Direct fetch from manufacturer Austria/EU pages curated in Sheet-B.
      2. Brave Search fallback, first constrained to those manufacturer domains.
      3. Verified Sheet-B competitor facts as last-known-good evidence.

    DeepSeek never becomes a fact source in this service.
    """

    def __init__(
        self,
        api_key: str | None,
        cache=None,
        *,
        official_timeout_seconds: float = 12.0,
        official_cache_ttl_seconds: int = 21_600,
    ):
        self.api_key = api_key
        self.cache = cache
        self.official_timeout_seconds = official_timeout_seconds
        self.official_cache_ttl_seconds = official_cache_ttl_seconds

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

    @staticmethod
    def _brand_from_query(query: str) -> str | None:
        lower = query.lower()
        for brand, aliases in _BRAND_ALIASES.items():
            if any(alias in lower for alias in aliases):
                return brand
        return None

    @staticmethod
    def _tokens(text: str) -> list[str]:
        tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", text.lower())
        return [token for token in tokens if len(token) >= 2 and token not in _STOPWORDS]

    @classmethod
    def _score_text(cls, query: str, text: str) -> int:
        lower = text.lower()
        score = 0
        for token in cls._tokens(query):
            if token in lower:
                score += 3 if any(ch.isdigit() for ch in token) else 1
        return score

    @staticmethod
    def _market_matches(value: Any) -> bool:
        market = str(value or "").upper()
        return not market or "AT" in market or "EU" in market or "DE/AT" in market

    @staticmethod
    def _fact_freshness(row: dict[str, Any]) -> tuple[bool, int | None]:
        raw = str(row.get("verified_at") or "").strip()
        try:
            verified = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if verified.tzinfo is None:
                verified = verified.replace(tzinfo=timezone.utc)
            age_days = max(0, (datetime.now(timezone.utc) - verified).days)
        except Exception:
            return False, None
        try:
            freshness_days = int(float(row.get("fact_freshness_days") or 30))
        except (TypeError, ValueError):
            freshness_days = 30
        return age_days <= max(1, freshness_days), age_days

    @classmethod
    def _matching_competitor_facts(
        cls, query: str, competitor_facts: list[dict[str, Any]] | None
    ) -> list[dict[str, Any]]:
        rows = []
        brand = cls._brand_from_query(query)
        for row in competitor_facts or []:
            if str(row.get("is_active", "true")).strip().lower() not in {
                "1", "true", "yes", "y", "ja", "active", "on"
            }:
                continue
            if not cls._market_matches(row.get("market")):
                continue
            row_brand = str(row.get("brand", "")).lower()
            if brand and brand not in row_brand:
                continue
            haystack = " ".join(
                str(row.get(key, ""))
                for key in ("brand", "product_name", "competitor_id")
            )
            score = cls._score_text(query, haystack)
            if score or (brand and brand in row_brand):
                copy = dict(row)
                copy["_match_score"] = score
                fresh, age_days = cls._fact_freshness(copy)
                copy["_is_fresh"] = fresh
                copy["_age_days"] = age_days
                rows.append(copy)
        return sorted(rows, key=lambda item: int(item.get("_match_score", 0)), reverse=True)

    @classmethod
    def _matching_official_refs(
        cls, query: str, refs: list[dict[str, Any]] | None
    ) -> list[dict[str, Any]]:
        brand = cls._brand_from_query(query)
        rows = []
        for row in refs or []:
            if str(row.get("is_active", "true")).strip().lower() not in {
                "1", "true", "yes", "y", "ja", "active", "on"
            }:
                continue
            if str(row.get("source_type", "")).strip().lower() not in {
                "official_manufacturer",
                "official_manufacturer_at",
                "official",
            }:
                continue
            if not cls._market_matches(row.get("market")):
                continue
            row_brand = str(row.get("brand", "")).lower()
            if brand and brand not in row_brand:
                continue
            url = str(row.get("source_url", "")).strip()
            if not url:
                continue
            score = cls._score_text(
                query,
                " ".join(
                    str(row.get(key, ""))
                    for key in ("brand", "product_name", "source_title", "key_facts", "source_url")
                ),
            )
            if score == 0 and not brand:
                continue
            copy = dict(row)
            copy["_match_score"] = score
            rows.append(copy)
        return sorted(rows, key=lambda item: int(item.get("_match_score", 0)), reverse=True)

    @staticmethod
    def _safe_public_url(url: str, allowed_domains: set[str] | None = None) -> bool:
        try:
            parsed = urlparse(url)
        except ValueError:
            return False
        if parsed.scheme != "https" or not parsed.hostname:
            return False
        host = parsed.hostname.lower().rstrip(".")
        if host == "localhost" or host.endswith(".local"):
            return False
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        except ValueError:
            pass
        if allowed_domains:
            return any(host == domain or host.endswith("." + domain) for domain in allowed_domains)
        return True

    @staticmethod
    def _domain(url: str) -> str | None:
        try:
            return (urlparse(url).hostname or "").lower().removeprefix("www.") or None
        except ValueError:
            return None

    @staticmethod
    def _bounded_excerpt(text: str, query: str, limit: int = 6000) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= limit:
            return compact
        query_tokens = PublicSearchService._tokens(query)
        lower = compact.lower()
        positions = [lower.find(token) for token in query_tokens if lower.find(token) >= 0]
        if not positions:
            return compact[:limit]
        center = min(positions)
        start = max(0, center - 1000)
        return compact[start : start + limit]

    async def _cache_get(self, key: str) -> dict[str, Any] | None:
        if not self.cache:
            return None
        try:
            return await self.cache.get_json(key)
        except Exception:
            return None

    async def _cache_set(self, key: str, value: dict[str, Any]) -> None:
        if not self.cache:
            return
        try:
            await self.cache.set_json(key, value, ttl=self.official_cache_ttl_seconds)
        except Exception:
            return

    async def _fetch_official_page(
        self, url: str, *, allowed_domains: set[str]
    ) -> dict[str, Any] | None:
        if not self._safe_public_url(url, allowed_domains):
            return None
        key = "competitor:official:" + hashlib.sha256(url.encode("utf-8")).hexdigest()
        cached = await self._cache_get(key)
        if cached:
            return cached
        try:
            async with httpx.AsyncClient(
                timeout=self.official_timeout_seconds,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; OPPO-Austria-Kaufberater/1.0)",
                    "Accept-Language": "de-AT,de;q=0.9,en;q=0.8",
                },
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                final_url = str(response.url)
                if not self._safe_public_url(final_url, allowed_domains):
                    return None
                content_type = response.headers.get("content-type", "")
                if "html" not in content_type.lower() and "text" not in content_type.lower():
                    return None
                html = response.text[:2_000_000]
        except Exception:
            return None

        parser = _OfficialHTMLParser()
        try:
            parser.feed(html)
        except Exception:
            return None
        payload = {
            "title": parser.title or final_url,
            "url": final_url,
            "description": parser.description,
            "text": parser.text[:120_000],
            "links": parser.links[:3000],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._cache_set(key, payload)
        return payload

    @classmethod
    def _candidate_links(
        cls,
        query: str,
        base_url: str,
        links: list[list[str]] | list[tuple[str, str]],
        allowed_domains: set[str],
    ) -> list[str]:
        ranked: list[tuple[int, str]] = []
        seen: set[str] = set()
        for href, anchor in links:
            absolute = urljoin(base_url, href)
            if absolute in seen or not cls._safe_public_url(absolute, allowed_domains):
                continue
            seen.add(absolute)
            score = cls._score_text(query, f"{absolute} {anchor}")
            if score:
                if any(part in absolute.lower() for part in ("spec", "technical", "smartphone", "iphone", "galaxy", "product")):
                    score += 2
                ranked.append((score, absolute))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return [url for _, url in ranked[:3]]

    @classmethod
    def _sheet_fact_evidence(cls, row: dict[str, Any]) -> PublicSearchResult:
        excluded = {
            "_match_score", "_is_fresh", "_age_days", "is_active", "notes", "live_first", "ai_may_infer_missing_facts",
            "source_authority", "confidence", "fact_freshness_days",
        }
        labels = []
        for key, value in row.items():
            if key in excluded or value in (None, ""):
                continue
            labels.append(f"{key}: {value}")
        url = str(row.get("official_specs_url") or row.get("official_product_url") or "").strip()
        fresh = bool(row.get("_is_fresh"))
        age = row.get("_age_days")
        prefix = "" if fresh else f"LAST-KNOWN-GOOD; verified {age if age is not None else 'unknown'} days ago. "
        return PublicSearchResult(
            title=f"{row.get('product_name', 'Competitor')} — verified Austria facts",
            url=url,
            snippet=(prefix + " | ".join(labels))[:7000],
            source_type="sheet_b_verified_cache" if fresh else "sheet_b_verified_cache_stale",
            source_authority=str(row.get("source_authority") or "official_manufacturer_at"),
            market=str(row.get("market") or "AT"),
            brand=str(row.get("brand") or "") or None,
            product_name=str(row.get("product_name") or "") or None,
            verified_at=str(row.get("verified_at") or "") or None,
        )

    async def _direct_official(
        self,
        query: str,
        refs: list[dict[str, Any]],
        facts: list[dict[str, Any]],
        count: int,
    ) -> list[PublicSearchResult]:
        matching_facts = self._matching_competitor_facts(query, facts)
        matching_refs = self._matching_official_refs(query, refs)

        domains: set[str] = set()
        for row in [*matching_facts, *matching_refs]:
            for key in ("official_specs_url", "official_product_url", "source_url"):
                domain = self._domain(str(row.get(key, "")))
                if domain:
                    domains.add(domain)
        if not domains:
            return []

        # Known product URLs from verified Sheet-B facts are the strongest direct-fetch target.
        urls: list[tuple[str, dict[str, Any] | None]] = []
        for row in matching_facts[:3]:
            for key in ("official_specs_url", "official_product_url"):
                url = str(row.get(key, "")).strip()
                if url and all(existing[0] != url for existing in urls):
                    urls.append((url, row))
        for row in matching_refs[:3]:
            url = str(row.get("source_url", "")).strip()
            if url and all(existing[0] != url for existing in urls):
                urls.append((url, None))

        results: list[PublicSearchResult] = []
        for url, row in urls[:5]:
            page = await self._fetch_official_page(url, allowed_domains=domains)
            if not page:
                continue
            score = self._score_text(query, f"{page['title']} {page['description']} {page['text'][:30000]}")
            if score == 0 and row is None:
                # A category page that does not mention the requested product is useful only
                # to discover a product-specific official link.
                candidates = self._candidate_links(query, page["url"], page["links"], domains)
                for candidate in candidates[:2]:
                    child = await self._fetch_official_page(candidate, allowed_domains=domains)
                    if child and self._score_text(query, f"{child['title']} {child['text'][:30000]}") > 0:
                        page = child
                        score = 1
                        break
            if score == 0 and row is None:
                continue
            brand = str((row or {}).get("brand") or self._brand_from_query(query) or "") or None
            product_name = str((row or {}).get("product_name") or "") or None
            excerpt_source = " ".join(
                part for part in (page.get("description", ""), page.get("text", "")) if part
            )
            results.append(
                PublicSearchResult(
                    title=page["title"],
                    url=page["url"],
                    snippet=self._bounded_excerpt(excerpt_source, query),
                    source_type="official_live",
                    source_authority="official_manufacturer_at",
                    market="AT",
                    brand=brand,
                    product_name=product_name,
                    verified_at=page["fetched_at"],
                )
            )
            if len(results) >= count:
                break
        return results

    async def _brave_search(
        self,
        query: str,
        *,
        count: int,
        allowed_domains: set[str] | None = None,
        official_only: bool = False,
    ) -> list[PublicSearchResult]:
        if not self.api_key:
            return []
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": min(max(count, 1), 10)},
                headers={
                    "X-Subscription-Token": self.api_key,
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

        results: list[PublicSearchResult] = []
        for item in data.get("web", {}).get("results", []):
            url = str(item.get("url") or "").strip()
            title = str(item.get("title") or "").strip()
            if not url or not title or not self._safe_public_url(url):
                continue
            domain = self._domain(url)
            is_allowed = bool(
                domain
                and allowed_domains
                and any(domain == d or domain.endswith("." + d) for d in allowed_domains)
            )
            if official_only and not is_allowed:
                continue
            snippet = re.sub(r"<[^>]+>", "", item.get("description", ""))
            results.append(
                PublicSearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    source_type="brave_official" if is_allowed else "brave_public",
                    source_authority=("official_manufacturer" if is_allowed else "public_search"),
                    market="AT" if is_allowed else None,
                    verified_at=datetime.now(timezone.utc).isoformat(),
                )
            )
            if len(results) >= count:
                break
        return results

    @staticmethod
    def _youtube_results_from_html(
        html: str,
        query: str,
        count: int,
    ) -> list[PublicSearchResult]:
        starts = list(
            re.finditer(
                r'"videoRenderer":\{"videoId":"([A-Za-z0-9_-]{11})"',
                html,
            )
        )
        results: list[PublicSearchResult] = []
        seen: set[str] = set()
        for index, match in enumerate(starts):
            video_id = match.group(1)
            if video_id in seen:
                continue
            end = starts[index + 1].start() if index + 1 < len(starts) else match.start() + 20_000
            chunk = html[match.start() : min(end, match.start() + 20_000)]
            title_match = re.search(
                r'"title":\{"runs":\[\{"text":"((?:\\.|[^"\\])*)"',
                chunk,
            )
            if not title_match:
                continue
            try:
                title = json.loads(f'"{title_match.group(1)}"')
            except (json.JSONDecodeError, UnicodeDecodeError):
                title = title_match.group(1)
            if not title or PublicSearchService._score_text(query, title) == 0:
                continue
            channel_match = re.search(
                r'"longBylineText":\{"runs":\[\{"text":"((?:\\.|[^"\\])*)"',
                chunk,
            )
            published_match = re.search(
                r'"publishedTimeText":\{"simpleText":"((?:\\.|[^"\\])*)"',
                chunk,
            )
            details = []
            for value in (
                channel_match.group(1) if channel_match else "",
                published_match.group(1) if published_match else "",
            ):
                if value:
                    try:
                        details.append(json.loads(f'"{value}"'))
                    except json.JSONDecodeError:
                        details.append(value)
            results.append(
                PublicSearchResult(
                    title=title,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    snippet=" | ".join(details) or "Independent YouTube video review",
                    source_type="youtube_public",
                    source_authority="independent_review",
                    verified_at=datetime.now(timezone.utc).isoformat(),
                )
            )
            seen.add(video_id)
            if len(results) >= count:
                break
        return results

    async def _youtube_search(
        self,
        query: str,
        count: int,
    ) -> list[PublicSearchResult]:
        url = "https://www.youtube.com/results?search_query=" + quote_plus(query)
        try:
            async with httpx.AsyncClient(
                timeout=min(self.official_timeout_seconds, 15.0),
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; OPPO-Austria-Kaufberater/1.0)",
                    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
                },
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                html = response.text[:2_000_000]
        except Exception:
            return []
        return self._youtube_results_from_html(html, query, count)

    async def search(
        self,
        query: str,
        confidential_terms: set[str],
        unreleased_names: set[str],
        count: int = 5,
        *,
        official_references: list[dict[str, Any]] | None = None,
        competitor_facts: list[dict[str, Any]] | None = None,
        public_review: bool = False,
    ) -> list[PublicSearchResult]:
        self.validate(query, confidential_terms, unreleased_names)
        refs = official_references or []
        facts = competitor_facts or []

        # Independent reviews must not be displaced by unrelated manufacturer
        # references from the curated competitor evidence set.
        if public_review:
            youtube_requested = bool(re.search(r"\b(?:youtube|youtu\.be)\b", query, re.I))
            product_match = re.search(
                r"\bOPPO\s+(?:Find\s+X\d+(?:\s+(?:Pro|Ultra))?|"
                r"Reno\s*\d+(?:\s+(?:Pro|FS))?(?:\s+5G)?|Watch\s+X\d+)\b",
                query,
                re.I,
            )
            product = product_match.group(0) if product_match else query
            review_queries = [query]
            if youtube_requested:
                review_queries = [
                    f"{product} review site:youtube.com",
                    f"{product} review YouTube",
                ]

            for review_query in review_queries:
                results = await self._brave_search(review_query, count=count)
                if youtube_requested:
                    results = [
                        item
                        for item in results
                        if (
                            self._domain(item.url) == "youtu.be"
                            or (
                                self._domain(item.url) == "youtube.com"
                                and urlparse(item.url).path == "/watch"
                            )
                        )
                    ]
                if results:
                    return results[:count]
            if youtube_requested:
                return await self._youtube_search(f"{product} review", count)
            return []

        # 1) Direct official manufacturer fetch.
        official = await self._direct_official(query, refs, facts, count)
        if official:
            return official[:count]

        # Build the exact manufacturer-domain boundary from Sheet-B curated references.
        matching_refs = self._matching_official_refs(query, refs)
        domains = {
            domain
            for domain in (self._domain(str(row.get("source_url", ""))) for row in matching_refs)
            if domain
        }
        for row in self._matching_competitor_facts(query, facts):
            for key in ("official_product_url", "official_specs_url"):
                domain = self._domain(str(row.get(key, "")))
                if domain:
                    domains.add(domain)

        # 2) Brave fallback, constrained to official manufacturer domains first.
        if self.api_key and domains:
            site_query = query + " " + " OR ".join(f"site:{domain}" for domain in sorted(domains))
            brave_official = await self._brave_search(
                site_query,
                count=count,
                allowed_domains=domains,
                official_only=True,
            )
            if brave_official:
                return brave_official[:count]

        # 3) Last-known-good verified competitor facts from Sheet-B.
        sheet_matches = self._matching_competitor_facts(query, facts)
        if sheet_matches:
            return [self._sheet_fact_evidence(row) for row in sheet_matches[:count]]

        # 4) General Brave search is allowed for independent/current public evidence when
        # no official/verified competitor source exists. It never becomes OPPO authority.
        return await self._brave_search(query, count=count)

    def status(
        self,
        *,
        official_references: list[dict[str, Any]] | None = None,
        competitor_facts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        refs = official_references or []
        facts = competitor_facts or []
        official_refs = [
            row
            for row in refs
            if str(row.get("is_active", "true")).strip().lower()
            in {"1", "true", "yes", "y", "ja", "active", "on"}
            and str(row.get("source_type", "")).strip().lower()
            in {"official_manufacturer", "official_manufacturer_at", "official"}
            and self._market_matches(row.get("market"))
            and str(row.get("source_url", "")).strip()
        ]
        fact_rows = [
            row
            for row in facts
            if str(row.get("is_active", "true")).strip().lower()
            in {"1", "true", "yes", "y", "ja", "active", "on"}
            and self._market_matches(row.get("market"))
        ]
        fresh_count = 0
        stale_count = 0
        for row in fact_rows:
            fresh, _ = self._fact_freshness(row)
            if fresh:
                fresh_count += 1
            else:
                stale_count += 1
        domains = sorted(
            {
                domain
                for domain in (
                    self._domain(str(row.get("source_url", "")))
                    for row in official_refs
                )
                if domain
            }
            | {
                domain
                for row in fact_rows
                for domain in (
                    self._domain(str(row.get("official_specs_url", ""))),
                    self._domain(str(row.get("official_product_url", ""))),
                )
                if domain
            }
        )
        return {
            "official_direct_fetch_enabled": True,
            "official_fetch_timeout_seconds": self.official_timeout_seconds,
            "official_cache_ttl_seconds": self.official_cache_ttl_seconds,
            "brave_configured": self.brave_configured,
            "official_reference_count": len(official_refs),
            "competitor_fact_count": len(fact_rows),
            "fresh_competitor_fact_count": fresh_count,
            "stale_competitor_fact_count": stale_count,
            "approved_official_domains": domains,
            "source_order": [
                "official_manufacturer_live",
                "brave_official_domain_fallback",
                "sheet_b_verified_last_known_good",
                "brave_public_supporting_context",
            ],
            "ai_fact_source": False,
            "missing_fact_policy": "exact_or_unknown",
        }

    @property
    def brave_configured(self) -> bool:
        return bool(self.api_key)

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.faq import FAQ_CACHE_KEY, FAQService


FALLBACK_FAQ_DATA: dict[str, list[dict[str, Any]]] = {
    "Service_Policy": [
        {
            "Policy_ID": "S004",
            "主题_中文": "保修",
            "Thema_DE": "Garantie",
            "Topic_EN": "Warranty",
            "内容_中文": "oppo.com/at直接购买的手机享3年保修。",
            "Inhalt_DE": "Smartphones direkt von oppo.com/at: 3 Jahre Garantie.",
            "Content_EN": "Smartphones bought directly from oppo.com/at: 3-year warranty.",
            "Source": "https://www.oppo.com/at/",
        },
        {
            "Policy_ID": "S006",
            "主题_中文": "客服联系方式",
            "Thema_DE": "Kundenservice",
            "Topic_EN": "Customer service",
            "内容_中文": "如需人工协助，请通过 OPPO 奥地利官网客服入口、support.at@oppo.com 或 WhatsApp 联系客服。",
            "Inhalt_DE": "Für persönliche Unterstützung nutze bitte den OPPO Österreich Support, support.at@oppo.com oder WhatsApp.",
            "Content_EN": "For personal support, contact OPPO Austria support through the official site, support.at@oppo.com, or WhatsApp.",
            "Source": "https://www.oppo.com/at/contact/",
        },
    ],
    "Product_KB": [
        {
            "Product_ID": "P001",
            "Product_Name": "OPPO Find X9 Ultra",
            "Battery": "7050mAh",
            "Official_Source": "https://www.oppo.com/at/",
        },
        {
            "Product_ID": "P002",
            "Product_Name": "OPPO Find X9 Pro",
            "Battery": "7500mAh",
            "Charging": "80W SUPERVOOC; 50W AIRVOOC",
            "Official_Source": "https://www.oppo.com/at/",
        },
        {
            "Product_ID": "P003",
            "Product_Name": "OPPO Find X9",
            "Battery": "7025mAh",
            "Official_Source": "https://www.oppo.com/at/",
        },
    ],
    "Compatibility_Map": [
        {
            "Compatibility_ID": "CM001",
            "OPPO_Product": "OPPO Watch X3",
            "Target_Device_or_OS": "Android smartphones",
            "Compatibility_Type": "OS compatibility",
            "Status": "SUPPORTED",
            "Feature_or_Max_Level": "Full watch setup",
            "限制_中文": "仅支持Android；不支持iOS与Android Go",
            "Einschränkung_DE": "Nur Android; iOS und Android Go werden nicht unterstützt.",
            "Limitation_EN": "Android only; iOS and Android Go are not supported.",
            "最低系统/条件_中文": "Android 9+，且需要 Google Mobile Services。",
            "Mindestanforderung_DE": "Android 9+ mit Google Mobile Services.",
            "Minimum_Requirement_EN": "Android 9+ with Google Mobile Services.",
            "Official_Source": "https://www.oppo.com/at/",
        }
    ],
    "Consumer_Decision_Playbook": [
        {
            "Decision_ID": "D006",
            "Consumer_Question_CN": "哪台拍照最好？",
            "Verbraucherfrage_DE": "Welches Smartphone hat die beste Kamera?",
            "Consumer_Question_EN": "Which phone has the best camera?",
            "Decision_Logic_CN": "先追问场景，再结合官方硬件和中立实测。不存在无条件最好。",
            "Entscheidungslogik_DE": "Zuerst den Foto-Kontext klären und dann offizielle Hardwaredaten mit neutralen Tests verbinden. Es gibt kein pauschal bestes Modell.",
            "Decision_Logic_EN": "Ask the photography use case first, then combine official hardware data with neutral reviews. There is no unconditional best camera phone.",
        }
    ],
    "Competitor_KB": [],
    "OPPO_Competitor_Map": [],
}


class ProductionFAQService(FAQService):
    @property
    def live_configured(self) -> bool:
        return bool(self.google_source and self.google_source.configured)

    @property
    def fallback_available(self) -> bool:
        return any(FALLBACK_FAQ_DATA.values())

    @property
    def configured(self) -> bool:
        return bool(self.spreadsheet_id and (self.live_configured or self.fallback_available))

    @staticmethod
    def _fallback_data() -> dict[str, list[dict[str, Any]]]:
        return {
            sheet: [dict(row) for row in rows]
            for sheet, rows in FALLBACK_FAQ_DATA.items()
        }

    async def _index(self, force: bool = False) -> dict[str, list[dict[str, Any]]]:
        if not force:
            cached = await self.cache.get_json(FAQ_CACHE_KEY)
            if cached:
                return cached

        if self.live_configured:
            return await super()._index(force=force)

        data = self._fallback_data() if self.spreadsheet_id else {}
        self.last_counts = {key: len(value) for key, value in data.items()}
        self.last_sync_at = datetime.now(timezone.utc).isoformat() if data else None
        self.last_error = (
            "GOOGLE_SHEETS_NOT_CONFIGURED_USING_EMBEDDED_FALLBACK"
            if data
            else "FAQ_SPREADSHEET_ID_NOT_CONFIGURED"
        )
        if data:
            await self.cache.set_json(FAQ_CACHE_KEY, data, ttl=self.cache_ttl_seconds)
        return data

    async def refresh(self) -> dict[str, Any]:
        data = await self._index(force=True)
        return {
            "configured": self.configured,
            "spreadsheet_id": self.spreadsheet_id,
            "live_google_configured": self.live_configured,
            "fallback_active": bool(not self.live_configured and self.fallback_available),
            "sheet_counts": {key: len(value) for key, value in data.items()},
            "last_sync_at": self.last_sync_at,
            "last_error": self.last_error,
        }

    async def status(self) -> dict[str, Any]:
        cached = await self.cache.get_json(FAQ_CACHE_KEY)
        return {
            "configured": self.configured,
            "spreadsheet_id": self.spreadsheet_id,
            "live_google_configured": self.live_configured,
            "fallback_active": bool(not self.live_configured and self.fallback_available),
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "cached": bool(cached),
            "sheet_counts": self.last_counts or (
                {key: len(value) for key, value in (cached or {}).items()}
                if cached
                else {}
            ),
            "last_sync_at": self.last_sync_at,
            "last_error": self.last_error,
            "routing_policy": "FAQ hit -> exact database answer; FAQ miss -> normal DeepSeek workflow",
        }

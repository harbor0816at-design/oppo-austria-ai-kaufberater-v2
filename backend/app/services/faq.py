from __future__ import annotations

import asyncio
import re
import unicodedata
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from typing import Any

from app.cache import HotCache
from app.language import Language
from app.services.google_sheets import GoogleSheetsSource


FAQ_CACHE_KEY = "presales_faq:index:v1"


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower().strip()
    replacements = {
        "质保": "保修",
        "售后保修": "保修",
        "付款": "支付",
        "送货": "配送",
        "物流": "配送",
        "快递": "配送",
        "取货": "自提",
        "提货": "自提",
        "iphone": "ios",
        "apple phone": "ios",
        "garantiezeit": "garantie",
        "warranty period": "warranty",
        "delivery time": "shipping",
        "lieferdauer": "lieferzeit",
        "ladegeraet": "ladegerät",
        "e sim": "esim",
        "e-sim": "esim",
        "wi fi": "wifi",
        "wi-fi": "wifi",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = re.sub(r"[\s\-_/.]+", " ", text)
    text = re.sub(r"[^0-9a-zäöüß\u3400-\u9fff+ ]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _compact(value: Any) -> str:
    return _norm(value).replace(" ", "")


def _tokens(value: Any) -> set[str]:
    text = _norm(value)
    latin = {
        token
        for token in re.findall(r"[0-9a-zäöüß+]{2,}", text)
        if token not in {"the", "and", "with", "for", "oder", "und", "mit", "ein", "eine"}
    }
    cjk_runs = re.findall(r"[\u3400-\u9fff]{2,}", text)
    cjk: set[str] = set()
    for run in cjk_runs:
        if len(run) <= 4:
            cjk.add(run)
        else:
            cjk.update(run[i : i + 2] for i in range(len(run) - 1))
    return latin | cjk


COMPARISON_CUE_RE = re.compile(
    r"\b(?:vs\.?|versus|compare|comparison|vergleich|gegen|oder|or|"
    r"which(?:\s+\w+){0,5}\s+(?:better|choose|buy)|better\s+choice)\b|"
    r"对比|比较|相比|哪个好|哪个更|怎么选|如何选|选哪个|该选|区别|差异|和|与|跟",
    re.I,
)

OPPO_MENTION_RE = re.compile(
    r"(?<![0-9a-z])(?:oppo|find\s*x\d|reno\s*\d|coloros|supervooc|airvooc)"
    r"(?![0-9a-z])",
    re.I,
)

PUBLIC_REVIEW_RE = re.compile(
    r"\b(?:youtube|youtu\.be|video\s+review|review\s+video|reviews?|hands[- ]on|"
    r"unboxing|testbericht|erfahrungsbericht|praxistest)\b|"
    r"测评|评测|开箱|体验视频|实测视频|测评视频|评测视频",
    re.I,
)

DETAILED_SPECS_RE = re.compile(
    r"\b(?:spec|specs|specification|specifications|technical\s+data|full\s+details|"
    r"datenblatt|technische\s+daten|vollständige\s+daten)\b|"
    r"参数|规格|配置|详细参数|完整参数|参数表|配置表",
    re.I,
)

COMPETITOR_MENTION_RE = re.compile(
    r"\b(?:apple|iphone|samsung|galaxy|xiaomi|redmi|poco|honor|google\s*pixel|pixel|"
    r"oneplus|nothing\s*phone|motorola|huawei|sony\s*xperia|realme)\b|"
    r"苹果|三星|小米|红米|荣耀|谷歌(?:\s*Pixel)?|一加|摩托罗拉|华为|索尼|真我",
    re.I,
)


def _alias_hit(alias: str, normalized: str, compact: str) -> bool:
    """Match short Latin fact aliases as tokens, not arbitrary substrings."""
    term = _norm(alias)
    if not term:
        return False
    if re.fullmatch(r"[0-9a-z+]{1,3}", term):
        return bool(
            re.search(
                rf"(?<![0-9a-z]){re.escape(term)}(?![0-9a-z])",
                normalized,
                re.I,
            )
        )
    return term in normalized or _compact(term) in compact


def _competitor_model_variants(model: str, brand: str = "") -> set[str]:
    """Return common consumer names for a maintained competitor model."""
    variants = {model}
    if brand and model.lower().startswith(brand.lower() + " "):
        variants.add(model[len(brand) + 1 :])

    lower = model.lower()
    families = {
        "galaxy ": ("Samsung", "三星"),
        "iphone ": ("Apple", "苹果"),
        "pixel ": ("Google", "谷歌"),
    }
    for prefix, aliases in families.items():
        if not lower.startswith(prefix):
            continue
        suffix = model[len(prefix) :].strip()
        for alias in aliases:
            variants.add(f"{alias} {suffix}")
            variants.add(f"{alias} {model}")
    return variants


SERVICE_ALIASES = {
    "S001": ["版本", "欧洲版", "欧版", "发货地", "哪里发货", "德国地址", "versand", "version", "shipping", "germany"],
    "S002": ["退货", "退换", "return", "rückgabe"],
    "S003": ["换机", "换新", "质量问题", "defect exchange", "austausch", "defekt"],
    "S004": ["保修", "warranty", "garantie"],
    "S005": ["线下体验", "展厅", "showroom", "dc tower", "自提", "pickup", "abholung", "wien", "vienna"],
    "S006": ["客服", "联系", "whatsapp", "邮箱", "email", "customer service", "kundenservice", "support"],
    "S007": ["支付", "付款", "payment", "zahlung", "visa", "mastercard", "paypal", "klarna", "apple pay", "amex"],
    "S008": ["配送时效", "多久到", "几天到", "shipping", "delivery", "lieferzeit", "versanddauer"],
    "S009": ["发票", "企业发票", "公司购买", "business deal", "invoice", "rechnung", "uid", "vat"],
    "S010": ["以旧换新", "trade in", "trade-in", "数据迁移", "换机迁移", "data migration", "datenübertragung", "clone phone", "whatsapp迁移"],
}

PRODUCT_FIELD_ALIASES: list[tuple[str, list[str]]] = [
    ("specs", ["参数", "配置", "spec", "specs", "specification", "technische daten", "datenblatt"]),
    ("Memory", ["内存", "存储", "ram", "rom", "memory", "storage", "speicher"]),
    ("Chipset", ["芯片", "处理器", "chip", "chipset", "processor", "prozessor"]),
    ("Display", ["屏幕", "显示", "display", "screen", "bildschirm", "刷新率", "hz", "亮度", "nits"]),
    ("Camera_or_Core_Features", ["相机", "摄像头", "拍照", "camera", "kamera", "长焦", "telephoto", "zoom", "自拍", "selfie", "video", "视频"]),
    ("Battery", ["电池", "续航", "mah", "battery", "akku", "laufzeit"]),
    ("Charging", ["充电", "快充", "charging", "charge", "laden", "ladeleistung", "watt", "supervooc", "airvooc"]),
    ("in_box", ["包装", "包装清单", "盒子", "盒内", "充电器", "保护壳", "贴膜", "in the box", "box contents", "included", "lieferumfang", "ladegerät", "hülle", "folie"]),
    ("sim", ["esim", "sim", "5g", "频段", "网络", "volte", "vowifi", "micro sd", "microsd", "speicherkarte", "netz", "konnektivität", "connectivity"]),
    ("why", ["为什么推荐", "推荐理由", "适合谁", "why recommend", "who is it for", "empfehlung", "zielgruppe", "geeignet"]),
    ("caveat", ["缺点", "不足", "注意", "限制", "weakness", "downside", "caveat", "nachteil", "einschränkung"]),
]


def _lang_field(language: Language, zh: str, de: str, en: str) -> str:
    return {"zh": zh, "de": de, "en": en}[language]


@dataclass
class FAQMatch:
    answer: str
    source_sheet: str
    source_id: str
    source_url: str | None
    score: float
    match_type: str
    matched_terms: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FAQService:
    """Read-only FAQ/knowledge router backed by the OPPO Austria Smart Advisor workbook.

    A hit is returned verbatim from the database. DeepSeek is deliberately not involved
    in FAQ-hit responses. If no conservative match is found, the normal DeepSeek +
    Source_B/public-source workflow continues.
    """

    def __init__(
        self,
        google_source: GoogleSheetsSource,
        cache: HotCache,
        spreadsheet_id: str,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self.google_source = google_source
        self.cache = cache
        self.spreadsheet_id = spreadsheet_id.strip()
        self.cache_ttl_seconds = cache_ttl_seconds
        self.last_sync_at: str | None = None
        self.last_counts: dict[str, int] = {}
        self.last_error: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.spreadsheet_id and self.google_source and self.google_source.configured)

    def _read_rows(self, range_name: str) -> list[dict[str, Any]]:
        values = self.google_source.values_from(self.spreadsheet_id, range_name)
        return self.google_source._dict_rows(values)

    def _load_sync(self) -> dict[str, list[dict[str, Any]]]:
        ranges = {
            "Service_Policy": "Service_Policy!A1:H1000",
            "Product_KB": "Product_KB!A1:AF1000",
            "Compatibility_Map": "Compatibility_Map!A1:R1000",
            "Consumer_Decision_Playbook": "Consumer_Decision_Playbook!A1:L1000",
            "Competitor_KB": "Competitor_KB!A1:Z1000",
            "OPPO_Competitor_Map": "OPPO_Competitor_Map!A1:X1000",
        }
        return {name: self._read_rows(a1) for name, a1 in ranges.items()}

    async def _index(self, force: bool = False) -> dict[str, list[dict[str, Any]]]:
        if not force:
            cached = await self.cache.get_json(FAQ_CACHE_KEY)
            if cached:
                return cached
        if not self.configured:
            return {}
        try:
            data = await asyncio.to_thread(self._load_sync)
            self.last_counts = {key: len(value) for key, value in data.items()}
            from datetime import datetime, timezone
            self.last_sync_at = datetime.now(timezone.utc).isoformat()
            self.last_error = None
            await self.cache.set_json(FAQ_CACHE_KEY, data, ttl=self.cache_ttl_seconds)
            return data
        except Exception as exc:
            self.last_error = f"{exc.__class__.__name__}: {exc}"
            cached = await self.cache.get_json(FAQ_CACHE_KEY)
            return cached or {}

    @staticmethod
    def _service_match(message: str, language: Language, rows: list[dict[str, Any]]) -> FAQMatch | None:
        q = _norm(message)
        q_compact = _compact(message)
        best: FAQMatch | None = None
        for row in rows:
            policy_id = str(row.get("Policy_ID", "")).strip()
            aliases = SERVICE_ALIASES.get(policy_id, [])
            topics = [row.get("主题_中文"), row.get("Thema_DE"), row.get("Topic_EN")]
            matched = []
            for term in [*aliases, *topics]:
                n = _norm(term)
                if not n:
                    continue
                if n in q or _compact(n) in q_compact:
                    matched.append(str(term))
            if not matched:
                continue
            answer_field = _lang_field(language, "内容_中文", "Inhalt_DE", "Content_EN")
            answer = str(row.get(answer_field, "")).strip()
            if not answer:
                continue
            score = 100.0 + min(10.0, len(matched))
            match = FAQMatch(
                answer=answer,
                source_sheet="Service_Policy",
                source_id=policy_id,
                source_url=str(row.get("Source", "")).strip() or None,
                score=score,
                match_type="service_policy",
                matched_terms=matched[:6],
            )
            if best is None or match.score > best.score:
                best = match
        return best

    @staticmethod
    def _find_product(message: str, context_text: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        combined = f"{message} {context_text}"
        n = _norm(combined)
        c = _compact(combined)
        matches: list[tuple[int, dict[str, Any]]] = []
        for row in rows:
            name = str(row.get("Product_Name", "")).strip()
            if not name:
                continue
            variants = {name, name.removeprefix("OPPO ")}
            for variant in list(variants):
                variants.add(variant.replace("Find ", ""))
            hit = any(_norm(v) in n or _compact(v) in c for v in variants if _norm(v))
            if hit:
                matches.append((len(_compact(name)), row))
        return max(matches, key=lambda x: x[0])[1] if matches else None

    @staticmethod
    def _product_match(
        message: str,
        context_text: str,
        language: Language,
        rows: list[dict[str, Any]],
    ) -> FAQMatch | None:
        row = FAQService._find_product(message, context_text, rows)
        if row is None:
            return None
        q = _norm(message)
        field_matches: list[tuple[str, list[str]]] = []
        matched_terms: list[str] = []
        for candidate, aliases in PRODUCT_FIELD_ALIASES:
            hits = [term for term in aliases if _norm(term) in q or _compact(term) in _compact(q)]
            if hits:
                field_matches.append((candidate, hits))
                matched_terms.extend(hits)
        # Merely mentioning a product is not enough to suppress DeepSeek. A factual
        # attribute/FAQ keyword is required for a direct database response.
        if not field_matches:
            return None

        requested_fields = [item[0] for item in field_matches]
        field = "specs" if "specs" in requested_fields else requested_fields[0]

        product = str(row.get("Product_Name", "")).strip()
        source = str(row.get("Official_Source", "")).strip() or None
        if field == "specs":
            fields = ["Memory", "Chipset", "Display", "Camera_or_Core_Features", "Battery", "Charging"]
            labels = {
                "zh": ["内存/存储", "芯片", "屏幕", "影像", "电池", "充电"],
                "de": ["Speicher", "Chip", "Display", "Kamera", "Akku", "Laden"],
                "en": ["Memory/storage", "Chipset", "Display", "Camera", "Battery", "Charging"],
            }[language]
            lines = [f"**{product}**"]
            for label, key in zip(labels, fields):
                value = str(row.get(key, "")).strip()
                if value:
                    lines.append(f"- **{label}:** {value}")
            answer = "\n".join(lines)
        elif len(requested_fields) > 1 and all(
            item
            in {
                "Memory",
                "Chipset",
                "Display",
                "Camera_or_Core_Features",
                "Battery",
                "Charging",
            }
            for item in requested_fields
        ):
            label_map = dict(
                zip(
                    ["Memory", "Chipset", "Display", "Camera_or_Core_Features", "Battery", "Charging"],
                    {
                        "zh": ["内存/存储", "芯片", "屏幕", "影像", "电池", "充电"],
                        "de": ["Speicher", "Chip", "Display", "Kamera", "Akku", "Laden"],
                        "en": ["Memory/storage", "Chipset", "Display", "Camera", "Battery", "Charging"],
                    }[language],
                )
            )
            lines = [f"**{product}**"]
            for key in requested_fields:
                value = str(row.get(key, "")).strip()
                if value:
                    lines.append(f"- **{label_map[key]}:** {value}")
            answer = "\n".join(lines)
        elif field == "in_box":
            key = _lang_field(language, "In_The_Box_CN", "Lieferumfang_DE", "In_The_Box_EN")
            answer = f"**{product}:** {str(row.get(key, '')).strip()}"
        elif field == "sim":
            key = _lang_field(language, "SIM_Connectivity_CN", "SIM_Konnektivitaet_DE", "SIM_Connectivity_EN")
            answer = f"**{product}:** {str(row.get(key, '')).strip()}"
        elif field == "why":
            key = _lang_field(language, "推荐理由_中文", "Empfehlungsgrund_DE", "Why_Recommend_EN")
            target_key = _lang_field(language, "适合人群_中文", "Zielgruppe_DE", "Target_User_EN")
            answer = f"**{product}:** {str(row.get(key, '')).strip()}\n\n{str(row.get(target_key, '')).strip()}"
        elif field == "caveat":
            key = _lang_field(language, "注意事项_中文", "Hinweise_DE", "Caveats_EN")
            answer = f"**{product}:** {str(row.get(key, '')).strip()}"
        else:
            value = str(row.get(field, "")).strip()
            answer = f"**{product}:** {value}"

        if not answer.split(":", 1)[-1].strip():
            return None
        return FAQMatch(
            answer=answer,
            source_sheet="Product_KB",
            source_id=str(row.get("Product_ID", "")).strip(),
            source_url=source,
            score=96.0,
            match_type="product_fact",
            matched_terms=list(dict.fromkeys(matched_terms))[:6],
        )

    @staticmethod
    def _compatibility_match(
        message: str,
        context_text: str,
        language: Language,
        rows: list[dict[str, Any]],
    ) -> FAQMatch | None:
        combined = _norm(f"{message} {context_text}")
        compact = _compact(combined)
        q_tokens = _tokens(message)
        best: FAQMatch | None = None
        for row in rows:
            product = str(row.get("OPPO_Product", "")).strip()
            if not product:
                continue
            variants = {product, product.removeprefix("OPPO ")}
            if not any(_norm(v) in combined or _compact(v) in compact for v in variants):
                continue
            searchable = " ".join(
                str(row.get(key, ""))
                for key in (
                    "Target_Device_or_OS",
                    "Compatibility_Type",
                    "Feature_or_Max_Level",
                    "限制_中文",
                    "Einschränkung_DE",
                    "Limitation_EN",
                )
            )
            row_tokens = _tokens(searchable)
            overlap = q_tokens & row_tokens
            # product mention alone is not enough; require at least one compatibility cue.
            compat_cues = {
                "ios", "android", "bluetooth", "camera", "kamera", "遥控", "翻译", "translation",
                "lhdc", "hires", "连接", "connection", "兼容", "support", "支持", "iphone",
                "youtube", "tiktok", "windows", "wearos", "wear", "remote",
            }
            cue_hit = any(_norm(cue) in _norm(message) for cue in compat_cues)
            if not overlap and not cue_hit:
                continue
            # Make sure a cue refers to this row, not merely another feature on the product.
            if overlap:
                score = 92.0 + min(5.0, len(overlap))
            else:
                ratio = SequenceMatcher(None, _norm(message), _norm(searchable)).ratio()
                if ratio < 0.18:
                    continue
                score = 90.0 + ratio

            limitation_key = _lang_field(language, "限制_中文", "Einschränkung_DE", "Limitation_EN")
            min_key = _lang_field(language, "最低系统/条件_中文", "Mindestanforderung_DE", "Minimum_Requirement_EN")
            status = str(row.get("Status", "")).strip()
            feature = str(row.get("Feature_or_Max_Level", "")).strip()
            limitation = str(row.get(limitation_key, "")).strip()
            minimum = str(row.get(min_key, "")).strip()
            if language == "zh":
                answer = f"**{product} — {feature}:** {limitation}"
                if minimum:
                    answer += f"\n\n最低条件：{minimum}"
            elif language == "de":
                answer = f"**{product} — {feature}:** {limitation}"
                if minimum:
                    answer += f"\n\nMindestanforderung: {minimum}"
            else:
                answer = f"**{product} — {feature}:** {limitation}"
                if minimum:
                    answer += f"\n\nMinimum requirement: {minimum}"
            match = FAQMatch(
                answer=answer,
                source_sheet="Compatibility_Map",
                source_id=str(row.get("Compatibility_ID", "")).strip(),
                source_url=str(row.get("Official_Source", "")).strip() or None,
                score=score,
                match_type=f"compatibility:{status.lower()}",
                matched_terms=sorted(overlap)[:6],
            )
            if best is None or match.score > best.score:
                best = match
        return best

    @staticmethod
    def _competitor_fact_match(
        message: str,
        language: Language,
        rows: list[dict[str, Any]],
    ) -> FAQMatch | None:
        # Prices, stock and other time-sensitive trading facts must continue through
        # live official/public search rather than a cached FAQ row.
        if re.search(r"\b(price|cost|today|current|latest|stock|availability|deal|promo|discount|preis|aktuell|heute|angebot)\b|价格|多少钱|当前|现在|今天|库存|促销|优惠", message, re.I):
            return None
        # A product-vs-product buying question must use the maintained comparison
        # map (or the grounded comparison workflow), never a single competitor field.
        if COMPARISON_CUE_RE.search(message) and OPPO_MENTION_RE.search(message):
            return None
        model_row = FAQService._find_competitor(message, rows)
        if model_row is None:
            return None
        q = _norm(message)
        q_compact = _compact(message)

        field_map = [
            ("OS", ["系统", "os", "android", "ios", "one ui", "hyperos", "oxygenos"]),
            ("Chipset", ["芯片", "处理器", "chip", "chipset", "processor", "prozessor"]),
            ("Display", ["屏幕", "display", "screen", "bildschirm", "刷新率", "hz", "ltpo"]),
            ("Rear_Camera", ["相机", "摄像头", "拍照", "camera", "kamera", "长焦", "telephoto", "zoom", "video", "视频"]),
            ("Battery", ["电池", "续航", "battery", "akku", "mah", "laufzeit"]),
            ("Wired_Charging", ["有线充电", "快充", "wired charging", "charging", "laden", "watt"]),
            ("Wireless_Charging", ["无线充电", "wireless charging", "kabellos", "qi", "magsafe"]),
            ("Weight", ["重量", "weight", "gewicht"]),
            ("Update_Durability", ["更新", "软件支持", "安全更新", "update", "updates", "software support", "aktualisierung"]),
            ("strength", ["优势", "优点", "强项", "strength", "advantage", "stärke", "vorteil"]),
            ("weakness", ["缺点", "不足", "弱点", "weakness", "downside", "schwäche", "nachteil"]),
            ("specs", ["参数", "配置", "spec", "specs", "specification", "technische daten"]),
        ]
        selected = None
        terms: list[str] = []
        for field, aliases in field_map:
            hits = [a for a in aliases if _alias_hit(a, q, q_compact)]
            if hits:
                selected = field
                terms = hits
                break
        if selected is None:
            return None

        model = str(model_row.get("Model", "")).strip()
        if selected == "strength":
            key = _lang_field(language, "Strength_CN", "Stärke_DE", "Strength_EN")
            value = str(model_row.get(key, "")).strip()
            answer = f"**{model}:** {value}"
        elif selected == "weakness":
            key = _lang_field(language, "Weakness_CN", "Schwäche_DE", "Weakness_EN")
            value = str(model_row.get(key, "")).strip()
            answer = f"**{model}:** {value}"
        elif selected == "specs":
            fields = ["OS", "Chipset", "Display", "Rear_Camera", "Battery", "Wired_Charging", "Wireless_Charging", "Weight", "Update_Durability"]
            labels = {
                "zh": ["系统", "芯片", "屏幕", "相机", "电池", "有线充电", "无线充电", "重量", "更新/耐用"],
                "de": ["OS", "Chip", "Display", "Kamera", "Akku", "Kabel-Laden", "Wireless Charging", "Gewicht", "Updates/Robustheit"],
                "en": ["OS", "Chipset", "Display", "Camera", "Battery", "Wired charging", "Wireless charging", "Weight", "Updates/durability"],
            }[language]
            lines = [f"**{model}**"]
            for label, key in zip(labels, fields):
                value = str(model_row.get(key, "")).strip()
                if value:
                    lines.append(f"- **{label}:** {value}")
            answer = "\n".join(lines)
        else:
            value = str(model_row.get(selected, "")).strip()
            if not value:
                return None
            answer = f"**{model}:** {value}"

        return FAQMatch(
            answer=answer,
            source_sheet="Competitor_KB",
            source_id=str(model_row.get("Competitor_ID", "")).strip(),
            source_url=str(model_row.get("Official_Source", "")).strip() or None,
            score=95.0,
            match_type="competitor_fact",
            matched_terms=terms[:6],
        )

    @staticmethod
    def _find_competitor(
        message: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        q = _norm(message)
        q_compact = _compact(message)
        matches: list[tuple[int, dict[str, Any]]] = []
        for row in rows:
            model = str(row.get("Model", "")).strip()
            if not model:
                continue
            brand = str(row.get("Brand", "")).strip()
            variants = _competitor_model_variants(model, brand)
            if any(
                _norm(variant) in q or _compact(variant) in q_compact
                for variant in variants
                if _norm(variant)
            ):
                matches.append((len(_compact(model)), row))
        return max(matches, key=lambda item: item[0])[1] if matches else None

    @staticmethod
    def _detailed_comparison_match(
        message: str,
        context_text: str,
        language: Language,
        product_rows: list[dict[str, Any]],
        competitor_rows: list[dict[str, Any]],
    ) -> FAQMatch | None:
        if not (
            DETAILED_SPECS_RE.search(message)
            and OPPO_MENTION_RE.search(message)
            and COMPETITOR_MENTION_RE.search(message)
        ):
            return None

        product_row = FAQService._find_product(message, context_text, product_rows)
        competitor_row = FAQService._find_competitor(message, competitor_rows)
        if product_row is None or competitor_row is None:
            return None

        product_name = str(product_row.get("Product_Name", "")).strip()
        competitor_name = str(competitor_row.get("Model", "")).strip()
        product_match = FAQService._product_match(
            f"{product_name} specs",
            "",
            language,
            [product_row],
        )
        competitor_match = FAQService._competitor_fact_match(
            f"{competitor_name} specs",
            language,
            [competitor_row],
        )
        if product_match is None or competitor_match is None:
            return None

        heading = {
            "zh": "**详细参数对比（奥地利版本）**",
            "de": "**Detaillierter Datenvergleich (Österreich-Versionen)**",
            "en": "**Detailed specification comparison (Austria variants)**",
        }[language]
        source_heading = {"zh": "**官方来源**", "de": "**Offizielle Quellen**", "en": "**Official sources**"}[language]
        source_lines = []
        if product_match.source_url:
            source_lines.append(f"- [{product_name}]({product_match.source_url})")
        if competitor_match.source_url:
            source_lines.append(f"- [{competitor_name}]({competitor_match.source_url})")
        source_block = f"\n\n{source_heading}\n" + "\n".join(source_lines) if source_lines else ""

        return FAQMatch(
            answer=(
                f"{heading}\n\n{product_match.answer}\n\n"
                f"{competitor_match.answer}{source_block}"
            ),
            source_sheet="Product_KB + Competitor_KB",
            source_id=f"{product_match.source_id}+{competitor_match.source_id}",
            source_url=None,
            score=110.0,
            match_type="detailed_comparison",
            matched_terms=[product_name, competitor_name, "specs"],
        )

    @staticmethod
    def _comparison_map_match(
        message: str,
        context_text: str,
        language: Language,
        rows: list[dict[str, Any]],
    ) -> FAQMatch | None:
        if re.search(r"\b(price|cost|today|current|latest|stock|availability|deal|promo|discount|preis|aktuell|heute|angebot)\b|价格|多少钱|当前|现在|今天|库存|促销|优惠", message, re.I):
            return None
        combined = _norm(f"{message} {context_text}")
        compact = _compact(combined)
        compare_cue = bool(COMPARISON_CUE_RE.search(message))
        if not compare_cue:
            return None
        best = None
        for row in rows:
            oppo = str(row.get("OPPO_Model", "")).strip()
            comp = str(row.get("Competitor_Model", "")).strip()
            if not oppo or not comp:
                continue
            oppo_variants = {oppo, oppo.removeprefix("OPPO "), oppo.removeprefix("OPPO ").replace("Find ", "")}
            comp_variants = _competitor_model_variants(comp)
            oppo_hit = any(_norm(v) in combined or _compact(v) in compact for v in oppo_variants if _norm(v))
            comp_hit = any(_norm(v) in combined or _compact(v) in compact for v in comp_variants if _norm(v))
            if not (oppo_hit and comp_hit):
                continue

            oppo_key = _lang_field(language, "OPPO_Wins_CN", "OPPO_Wins_DE", "OPPO_Wins_EN")
            comp_key = _lang_field(language, "Competitor_Wins_CN", "Competitor_Wins_DE", "Competitor_Wins_EN")
            migration_key = _lang_field(language, "Migration_Risk_CN", "Migration_Risk_DE", "Migration_Risk_EN")
            oppo_wins = str(row.get(oppo_key, "")).strip()
            comp_wins = str(row.get(comp_key, "")).strip()
            migration = str(row.get(migration_key, "")).strip()
            if language == "zh":
                answer = f"**{oppo} 的优势：** {oppo_wins}\n\n**{comp} 的优势：** {comp_wins}"
                if migration:
                    answer += f"\n\n**迁移/取舍：** {migration}"
            elif language == "de":
                answer = f"**Vorteile {oppo}:** {oppo_wins}\n\n**Vorteile {comp}:** {comp_wins}"
                if migration:
                    answer += f"\n\n**Wechsel/Trade-off:** {migration}"
            else:
                answer = f"**{oppo} advantages:** {oppo_wins}\n\n**{comp} advantages:** {comp_wins}"
                if migration:
                    answer += f"\n\n**Migration/trade-off:** {migration}"
            match = FAQMatch(
                answer=answer,
                source_sheet="OPPO_Competitor_Map",
                source_id=str(row.get("Map_ID", "")).strip(),
                source_url=None,
                score=98.0,
                match_type="comparison_map",
                matched_terms=[oppo, comp],
            )
            if best is None or match.score > best.score:
                best = match
        return best

    @staticmethod
    def _decision_match(message: str, language: Language, rows: list[dict[str, Any]]) -> FAQMatch | None:
        q = _norm(message)
        if len(q) < 5:
            return None
        q_tokens = _tokens(q)
        best: FAQMatch | None = None
        for row in rows:
            questions = [
                str(row.get("Consumer_Question_CN", "")),
                str(row.get("Verbraucherfrage_DE", "")),
                str(row.get("Consumer_Question_EN", "")),
            ]
            normalized = [_norm(item) for item in questions if item]
            if not normalized:
                continue
            ratios = [SequenceMatcher(None, q, item).ratio() for item in normalized]
            substring = any(q in item or item in q for item in normalized)
            row_tokens = set().union(*(_tokens(item) for item in normalized))
            overlap = q_tokens & row_tokens
            coverage = len(overlap) / max(1, len(q_tokens))
            score = max(ratios) * 100.0
            if substring:
                score = max(score, 94.0)
            elif score < 64.0 and coverage < 0.62:
                continue
            answer_key = _lang_field(language, "Decision_Logic_CN", "Entscheidungslogik_DE", "Decision_Logic_EN")
            answer = str(row.get(answer_key, "")).strip()
            if not answer:
                continue
            match = FAQMatch(
                answer=answer,
                source_sheet="Consumer_Decision_Playbook",
                source_id=str(row.get("Decision_ID", "")).strip(),
                source_url=None,
                score=score,
                match_type="decision_playbook",
                matched_terms=sorted(overlap)[:8],
            )
            if best is None or match.score > best.score:
                best = match
        return best

    async def match(
        self,
        message: str,
        language: Language,
        context_text: str = "",
    ) -> FAQMatch | None:
        if PUBLIC_REVIEW_RE.search(message):
            return None
        data = await self._index()
        if not data:
            return None

        detailed_comparison = self._detailed_comparison_match(
            message,
            context_text,
            language,
            data.get("Product_KB", []),
            data.get("Competitor_KB", []),
        )
        if detailed_comparison is not None:
            return detailed_comparison

        candidates = [
            self._service_match(message, language, data.get("Service_Policy", [])),
            self._product_match(message, context_text, language, data.get("Product_KB", [])),
            self._compatibility_match(message, context_text, language, data.get("Compatibility_Map", [])),
            self._competitor_fact_match(message, language, data.get("Competitor_KB", [])),
            self._comparison_map_match(message, context_text, language, data.get("OPPO_Competitor_Map", [])),
            self._decision_match(message, language, data.get("Consumer_Decision_Playbook", [])),
        ]
        matches = [item for item in candidates if item is not None]
        if not matches:
            return None
        return max(matches, key=lambda item: item.score)

    async def refresh(self) -> dict[str, Any]:
        data = await self._index(force=True)
        return {
            "configured": self.configured,
            "spreadsheet_id": self.spreadsheet_id,
            "sheet_counts": {key: len(value) for key, value in data.items()},
            "last_sync_at": self.last_sync_at,
            "last_error": self.last_error,
        }

    async def status(self) -> dict[str, Any]:
        cached = await self.cache.get_json(FAQ_CACHE_KEY)
        return {
            "configured": self.configured,
            "spreadsheet_id": self.spreadsheet_id,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "cached": bool(cached),
            "sheet_counts": self.last_counts or ({key: len(value) for key, value in (cached or {}).items()} if cached else {}),
            "last_sync_at": self.last_sync_at,
            "last_error": self.last_error,
            "routing_policy": "FAQ hit -> exact database answer; FAQ miss -> normal DeepSeek workflow",
        }

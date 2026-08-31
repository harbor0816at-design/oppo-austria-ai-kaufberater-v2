from __future__ import annotations

import base64
import binascii
import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from app.schemas import GiftSchema, ProductFactSchema


SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _split(value: Any, *separators: str) -> list[str]:
    if value in (None, ""):
        return []
    text = str(value).strip()
    for sep in separators or ("|", ",", "\n"):
        text = text.replace(sep, "|")
    return [item.strip() for item in text.split("|") if item.strip()]


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "ja", "active", "on"}


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("€", "").replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def _date_is_active(start: Any, end: Any) -> bool:
    today = date.today()
    def parse(v: Any) -> date | None:
        if v in (None, ""):
            return None
        text = str(v).strip()
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            for fmt in ("%d.%m.%Y", "%m/%d/%Y", "%d/%m/%Y"):
                try:
                    return datetime.strptime(text, fmt).date()
                except ValueError:
                    pass
        return None
    start_d, end_d = parse(start), parse(end)
    return (start_d is None or start_d <= today) and (end_d is None or today <= end_d)


@dataclass
class GoogleSheetLoadResult:
    products: list[ProductFactSchema]
    errors: list[str]
    fetched_at: str
    services: list[dict[str, Any]] = field(default_factory=list)
    knowledge: list[dict[str, Any]] = field(default_factory=list)
    promotions: list[dict[str, Any]] = field(default_factory=list)
    competitor_references: list[dict[str, Any]] = field(default_factory=list)
    competitor_facts: list[dict[str, Any]] = field(default_factory=list)


class GoogleSheetsSource:
    """Read-only Source_B adapter for a private Google Sheet.

    Authentication uses a Google Cloud service-account JSON stored only in Vercel
    environment variables. The Sheet itself remains private and only needs to be
    shared with the service account's client_email as Viewer.
    """

    def __init__(
        self,
        spreadsheet_id: str,
        service_account_json: str | None,
        service_account_json_b64: str | None,
        products_range: str,
        promotions_range: str,
        services_range: str,
        knowledge_range: str = "Knowledge_FAQ!A1:P1000",
        competitor_range: str = "Competitor_References!A1:N1000",
        competitor_facts_range: str = "Competitor_Facts!A1:AB1000",
    ) -> None:
        self.spreadsheet_id = spreadsheet_id.strip()
        self.products_range = products_range
        self.promotions_range = promotions_range
        self.services_range = services_range
        self.knowledge_range = knowledge_range
        self.competitor_range = competitor_range
        self.competitor_facts_range = competitor_facts_range
        self._raw_json_present = bool(service_account_json and service_account_json.strip())
        self._base64_present = bool(
            service_account_json_b64 and service_account_json_b64.strip()
        )
        (
            self._info,
            self.credential_source,
            self.credential_error,
        ) = self._parse_info(service_account_json, service_account_json_b64)
        self._token: str | None = None
        self._token_expires_at = 0.0
        self.last_result: GoogleSheetLoadResult | None = None

    @staticmethod
    def _parse_info(
        raw: str | None,
        raw_b64: str | None,
    ) -> tuple[dict[str, Any] | None, str | None, str | None]:
        payload = raw.strip() if raw and raw.strip() else None
        source = "json" if payload else None
        if payload is None and raw_b64 and raw_b64.strip():
            source = "base64"
            try:
                compact = "".join(raw_b64.split())
                payload = base64.b64decode(compact, validate=True).decode("utf-8")
            except (binascii.Error, ValueError):
                return None, source, "invalid_base64"
            except UnicodeDecodeError:
                return None, source, "base64_not_utf8"
        if not payload:
            return None, None, "credentials_missing"
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return None, source, "invalid_json"
        if not isinstance(data, dict):
            return None, source, "json_not_object"
        required = {"client_email", "private_key"}
        if not required.issubset(data):
            return None, source, "required_fields_missing"
        return data, source, None

    @property
    def configured(self) -> bool:
        return bool(self.spreadsheet_id and self._info)

    @property
    def client_email(self) -> str | None:
        return str(self._info.get("client_email")) if self._info else None

    @property
    def credential_status(self) -> dict[str, Any]:
        return {
            "json_present": self._raw_json_present,
            "base64_present": self._base64_present,
            "selected_source": self.credential_source,
            "parsed": bool(self._info),
            "error": self.credential_error,
        }

    def _access_token(self) -> str:
        if self._token and self._token_expires_at > time.time() + 60:
            return self._token
        if not self._info:
            raise RuntimeError("Google Sheets service account is not configured")

        token_uri = self._info.get("token_uri") or "https://oauth2.googleapis.com/token"
        now = int(time.time())
        header = {"alg": "RS256", "typ": "JWT"}
        claims = {
            "iss": self._info["client_email"],
            "scope": SHEETS_SCOPE,
            "aud": token_uri,
            "iat": now,
            "exp": now + 3600,
        }
        signing_input = (
            _b64url(json.dumps(header, separators=(",", ":")).encode())
            + "."
            + _b64url(json.dumps(claims, separators=(",", ":")).encode())
        )
        key = serialization.load_pem_private_key(
            self._info["private_key"].encode("utf-8"), password=None
        )
        signature = key.sign(
            signing_input.encode("ascii"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        assertion = signing_input + "." + _b64url(signature)
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                token_uri,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
            )
            response.raise_for_status()
            data = response.json()
        self._token = data["access_token"]
        self._token_expires_at = time.time() + int(data.get("expires_in", 3600))
        return self._token

    def values_from(self, spreadsheet_id: str, range_name: str) -> list[list[Any]]:
        """Read one range from any spreadsheet shared with the configured service account."""
        token = self._access_token()
        encoded_range = quote(range_name, safe="!:'")
        url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id.strip()}"
            f"/values/{encoded_range}"
        )
        with httpx.Client(timeout=20.0) as client:
            response = client.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "majorDimension": "ROWS",
                    "valueRenderOption": "UNFORMATTED_VALUE",
                },
            )
            response.raise_for_status()
            return response.json().get("values", [])

    def _values(self, range_name: str) -> list[list[Any]]:
        return self.values_from(self.spreadsheet_id, range_name)

    @staticmethod
    def _dict_rows(values: list[list[Any]]) -> list[dict[str, Any]]:
        if not values:
            return []
        headers = [str(item).strip() for item in values[0]]
        rows: list[dict[str, Any]] = []
        for raw in values[1:]:
            row = {headers[i]: raw[i] if i < len(raw) else "" for i in range(len(headers))}
            if any(value not in (None, "") for value in row.values()):
                rows.append(row)
        return rows

    def load(self) -> GoogleSheetLoadResult:
        if not self.configured:
            raise RuntimeError("Google Sheets Source_B is not configured")
        product_rows = self._dict_rows(self._values(self.products_range))
        promo_rows = self._dict_rows(self._values(self.promotions_range))
        service_rows = self._dict_rows(self._values(self.services_range))
        knowledge_rows = self._dict_rows(self._values(self.knowledge_range)) if self.knowledge_range else []
        competitor_rows = self._dict_rows(self._values(self.competitor_range)) if self.competitor_range else []
        competitor_fact_rows = self._dict_rows(self._values(self.competitor_facts_range)) if self.competitor_facts_range else []
        result = self.parse_catalog(
            product_rows, promo_rows, service_rows, knowledge_rows, competitor_rows, competitor_fact_rows
        )
        self.last_result = result
        return result

    @staticmethod
    def parse_catalog(
        product_rows: list[dict[str, Any]],
        promo_rows: list[dict[str, Any]],
        service_rows: list[dict[str, Any]],
        knowledge_rows: list[dict[str, Any]] | None = None,
        competitor_rows: list[dict[str, Any]] | None = None,
        competitor_fact_rows: list[dict[str, Any]] | None = None,
    ) -> GoogleSheetLoadResult:
        errors: list[str] = []
        services = {
            str(row.get("service_key", "")).strip(): row
            for row in service_rows
            if _as_bool(row.get("active"), True)
        }
        promotions: dict[str, list[dict[str, Any]]] = {}
        for row in promo_rows:
            if not _as_bool(row.get("active"), False) or not _date_is_active(
                row.get("valid_from"), row.get("valid_to")
            ):
                continue
            sku = str(row.get("sku_id", "")).strip()
            if sku:
                promotions.setdefault(sku, []).append(row)

        products: list[ProductFactSchema] = []
        for idx, row in enumerate(product_rows, start=2):
            sku = str(row.get("sku_id", "")).strip()
            if not sku or not _as_bool(row.get("is_active"), True):
                continue
            try:
                status = str(row.get("official_status", "launched")).strip() or "launched"
                price_public = _as_bool(row.get("price_public"), False)
                official_price = _as_float(row.get("official_price_eur")) if price_public else None
                early_deposit = _as_float(row.get("early_bird_deposit_eur"))
                discount_value = _as_float(row.get("deposit_discount_value_eur"))

                gifts: list[GiftSchema] = []
                for promo in promotions.get(sku, []):
                    for gift_key in ("gift_1", "gift_2"):
                        gift = str(promo.get(gift_key, "")).strip()
                        if gift:
                            gifts.append(
                                GiftSchema(item_name=gift, stock_status="active", value=0.0)
                            )

                regions = _split(row.get("regions"), ",", "|", ";") or ["AT"]
                service_shipping = services.get("shipping", {})
                shipping_de = str(row.get("shipping_timeline_de", "")).strip() or str(
                    service_shipping.get("body_de", "Versand gemäß Checkout")
                ).strip()
                shipping_en = str(row.get("shipping_timeline_en", "")).strip() or str(
                    service_shipping.get("body_en", shipping_de)
                ).strip()
                shipping_zh = str(row.get("shipping_timeline_zh", "")).strip() or str(
                    service_shipping.get("body_zh", shipping_de)
                ).strip()

                warranty_de = str(row.get("warranty_de", "")).strip() or str(
                    services.get("warranty", {}).get("body_de", "")
                ).strip()
                return_de = str(row.get("return_policy_de", "")).strip() or str(
                    services.get("return", {}).get("body_de", "")
                ).strip()
                replacement_de = str(row.get("replacement_policy_de", "")).strip() or str(
                    services.get("replacement", {}).get("body_de", "")
                ).strip()
                refund_policy = " ".join(
                    part for part in (return_de, replacement_de, warranty_de) if part
                ) or "Es gelten die offiziellen OPPO Österreich Shop-Bedingungen."

                de_features = _split(row.get("key_features_de"), "|", "\n")
                en_features = _split(row.get("key_features_en"), "|", "\n")
                zh_features = _split(row.get("key_features_zh"), "|", "\n")

                # Keep structured numeric facts in the authoritative feature payload too,
                # so ranking and model synthesis can use them without guessing.
                battery = _as_float(row.get("battery_mah"))
                wired = _as_float(row.get("wired_charging_w"))
                wireless = _as_float(row.get("wireless_charging_w"))
                structured = []
                if battery is not None:
                    structured.append(f"Battery: {battery:g} mAh")
                if wired is not None:
                    structured.append(f"Wired charging: {wired:g} W")
                if wireless is not None:
                    structured.append(f"Wireless charging: {wireless:g} W")
                for field, label in (
                    ("camera_summary", "Camera"),
                    ("chipset", "Chipset"),
                    ("display_summary", "Display"),
                    ("storage_summary", "Storage"),
                ):
                    value = str(row.get(field, "")).strip()
                    if value:
                        structured.append(f"{label}: {value}")

                official_fact_keys = (
                    "official_model_code", "market_scope", "dimensions_mm", "weight_g",
                    "display_size_in", "display_resolution", "refresh_rate_exact", "hbm_nits",
                    "panel_type", "ltpo_status", "storage_card_support", "esim_support",
                    "nfc_support", "wifi_standard", "os_version", "ip_rating_eu",
                    "battery_cycle_min", "box_contents_de", "charger_in_box_status",
                    "network_5g_at_summary", "official_specs_url", "fact_authority",
                    "source_priority", "answer_market_default", "user_need_tags",
                    "comparison_notes", "software_support_status", "last_verified_at",
                    "confidence", "direct_link_policy", "exact_fact_policy",
                )
                official_facts = {
                    key: row.get(key)
                    for key in official_fact_keys
                    if row.get(key) not in (None, "")
                }
                official_facts["ai_may_infer_missing_facts"] = _as_bool(
                    row.get("ai_may_infer_missing_facts"), False
                )
                source_meta = {
                    "official_facts": official_facts,
                    "verified_source_url": str(row.get("verified_source_url", "")).strip() or None,
                    "official_specs_url": str(row.get("official_specs_url", "")).strip() or None,
                    "verified_at": str(row.get("verified_at", "")).strip() or None,
                    "market": str(row.get("market", "")).strip() or "AT",
                    "exact_fact_policy": str(row.get("exact_fact_policy", "")).strip() or "exact_or_unknown",
                    "direct_link_policy": str(row.get("direct_link_policy", "")).strip() or None,
                }

                products.append(
                    ProductFactSchema(
                        sku_id=sku,
                        product_name=str(row.get("product_name", sku)).strip(),
                        official_status=status,
                        pricing={
                            "is_price_public": price_public,
                            "official_price": official_price,
                            "early_bird_deposit": early_deposit,
                            "deposit_discount_value": discount_value,
                            "refund_policy": refund_policy,
                        },
                        gifts=gifts,
                        shipping_commitments={
                            "timeline": shipping_de,
                            "regions": regions,
                        },
                        key_features=structured + de_features,
                        confidential_fields=_split(
                            row.get("confidential_fields"), ",", "|", ";"
                        ),
                        localized_content={
                            "de": {"shipping_timeline": shipping_de, "key_features": de_features or structured},
                            "en": {"shipping_timeline": shipping_en, "key_features": en_features or structured},
                            "zh": {"shipping_timeline": shipping_zh, "key_features": zh_features or structured},
                            "_source_b": source_meta,
                        },
                        product_url=str(row.get("product_url", "")).strip() or None,
                        purchase_url=str(row.get("purchase_url", "")).strip() or None,
                        is_active=True,
                    )
                )
            except Exception as exc:
                errors.append(f"Products row {idx} ({sku or 'no sku'}): {exc}")

        active_services = [
            row for row in service_rows if _as_bool(row.get("active"), True)
        ]
        active_knowledge = [
            row for row in (knowledge_rows or []) if _as_bool(row.get("active"), True)
        ]
        active_promotions = [
            row for row in promo_rows
            if _as_bool(row.get("active"), False)
            and _date_is_active(row.get("valid_from"), row.get("valid_to"))
        ]
        active_competitor_refs = [
            row for row in (competitor_rows or []) if _as_bool(row.get("is_active"), True)
        ]
        active_competitor_facts = [
            row for row in (competitor_fact_rows or [])
            if _as_bool(row.get("is_active"), True)
            and str(row.get("market", "AT")).strip().upper() in {"AT", "AT/EU", "EU", "DE/AT"}
        ]
        return GoogleSheetLoadResult(
            products=products,
            errors=errors,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            services=active_services,
            knowledge=active_knowledge,
            promotions=active_promotions,
            competitor_references=active_competitor_refs,
            competitor_facts=active_competitor_facts,
        )

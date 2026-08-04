from __future__ import annotations

from typing import Any
import logging
import re

from .base import StoreAdapter, money_to_minor, parse_datetime
from ..classify import classify_offer, looks_like_bundle, looks_like_dlc, looks_like_demo
from ..models import Offer, Store


LOGGER = logging.getLogger(__name__)


class GogAdapter(StoreAdapter):
    CATALOG_URL = "https://catalog.gog.com/v1/catalog"

    def fetch_offers(self) -> list[Offer]:
        offers: list[Offer] = []
        for page in range(1, max(1, self.config.stores.gog_pages) + 1):
            response = self.http.get(
                self.CATALOG_URL,
                params={
                    "limit": 48,
                    "order": "desc:trending",
                    "discounted": "eq:true",
                    "productType": "in:game,pack",
                    "page": page,
                    "countryCode": self.config.region,
                    "locale": "en-US",
                    "currencyCode": self.config.currency,
                },
                headers={"Referer": "https://www.gog.com/"},
            )
            body = response.json()
            products = body.get("products") or body.get("items") or []
            if not products:
                break
            for product in products:
                parsed = self._parse_product(product)
                if parsed:
                    offers.append(parsed)
            pages = _safe_int(body.get("pages")) or _safe_int(body.get("totalPages"))
            if pages and page >= pages:
                break
        LOGGER.info("GOG produced %d candidate offers", len(offers))
        return offers

    def _parse_product(self, item: dict[str, Any]) -> Offer | None:
        title = str(item.get("title") or item.get("name") or "").strip()
        external_id = str(
            item.get("id") or item.get("productId") or item.get("externalProductId") or ""
        ).strip()
        if not title or not external_id:
            return None
        product_type = str(item.get("productType") or item.get("type") or "game")
        categories = tuple(_string_list(item.get("categories")))
        if looks_like_dlc(title, product_type, categories) or looks_like_demo(title, product_type):
            return None

        price = item.get("price") or item.get("prices") or {}
        current = _gog_money(
            price.get("finalMoney")
            or price.get("final")
            or price.get("discountedPrice")
            or price.get("current")
        )
        normal = _gog_money(
            price.get("baseMoney")
            or price.get("base")
            or price.get("fullPrice")
            or price.get("regular")
        )
        currency = _gog_currency(price) or self.config.currency
        discount = _parse_discount(price.get("discount") or item.get("discount"))
        if discount is None and normal and current is not None:
            discount = max(0, min(100, round((normal - current) / normal * 100)))

        is_bundle = looks_like_bundle(title, product_type)
        offer_type = classify_offer(
            title=title,
            product_type="bundle" if is_bundle else product_type,
            categories=categories,
            current_price_minor=current,
            normal_price_minor=normal,
            is_free_product=normal in (None, 0) and current == 0,
            descriptive_text=str(item.get("description") or ""),
            promotion_active=(discount or 0) > 0,
        )
        if offer_type.value in {"DLC / add-on", "Demo", "Free-to-play", "Other"}:
            return None

        rating = item.get("reviewsRating") or item.get("rating") or item.get("reviewScore")
        review_percent = _rating_to_percent(rating)
        review_count = _safe_int(
            item.get("reviewsCount") or item.get("reviewCount") or item.get("ratingsCount")
        )
        slug = str(item.get("slug") or item.get("urlSlug") or "").strip("/")
        url = item.get("storeLink") or item.get("url")
        if not url:
            url = f"https://www.gog.com/en/game/{slug}" if slug else "https://www.gog.com/en/games"
        image_url = _gog_image(item)
        genres = tuple(_string_list(item.get("genres") or item.get("tags")))
        developer = _party_name(item.get("developers") or item.get("developer"))
        publisher = _party_name(item.get("publishers") or item.get("publisher"))
        return Offer(
            external_id=external_id,
            title=title,
            store=Store.GOG,
            url=str(url),
            current_price_minor=current,
            normal_price_minor=normal,
            currency=currency,
            discount_percent=discount,
            offer_type=offer_type,
            end_at=parse_datetime(
                item.get("discountEndDate")
                or item.get("saleEndDate")
                or item.get("promoEndDate")
            ),
            review_percent=review_percent,
            review_count=review_count,
            review_label=_review_label(review_percent),
            genres=genres,
            developer=developer,
            publisher=publisher,
            image_url=image_url,
            description=_text_or_none(item.get("description")),
            is_bundle=is_bundle,
            rarity_hint=offer_type.value.startswith("Free to keep"),
            metadata={"source": "gog_catalog", "product_type": product_type},
        )


def _gog_money(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, dict):
        amount = value.get("amount")
        if amount is None:
            amount = value.get("value")
        if amount is None:
            amount = value.get("raw")
        return money_to_minor(amount)
    return money_to_minor(value)


def _gog_currency(price: dict[str, Any]) -> str | None:
    for key in ("finalMoney", "baseMoney"):
        value = price.get(key)
        if isinstance(value, dict) and value.get("currency"):
            return str(value["currency"])
    if price.get("currency"):
        return str(price["currency"])
    return None


def _parse_discount(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("percentage") or value.get("value")
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else None


def _rating_to_percent(value: Any) -> int | None:
    if value is None:
        return None
    try:
        rating = float(value)
    except (TypeError, ValueError):
        return None
    if rating <= 5:
        rating *= 20
    elif rating <= 10:
        rating *= 10
    return max(0, min(100, round(rating)))


def _review_label(percent: int | None) -> str | None:
    if percent is None:
        return None
    if percent >= 90:
        return "Excellent"
    if percent >= 80:
        return "Very Good"
    if percent >= 70:
        return "Good"
    return "Mixed"


def _gog_image(item: dict[str, Any]) -> str | None:
    candidates = (
        item.get("coverHorizontal"),
        item.get("coverVertical"),
        item.get("image"),
        item.get("images", {}).get("background") if isinstance(item.get("images"), dict) else None,
    )
    for candidate in candidates:
        if isinstance(candidate, dict):
            candidate = candidate.get("url")
        if candidate:
            value = str(candidate)
            if value.startswith("//"):
                value = "https:" + value
            return value
    return None


def _string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    result: list[str] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                text = item.get("name") or item.get("title") or item.get("slug")
            else:
                text = item
            if text:
                result.append(str(text))
    return result


def _party_name(value: Any) -> str | None:
    if isinstance(value, list) and value:
        value = value[0]
    if isinstance(value, dict):
        value = value.get("name") or value.get("title")
    return _text_or_none(value)


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

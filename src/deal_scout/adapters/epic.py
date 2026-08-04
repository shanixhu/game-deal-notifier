from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import logging

from .base import StoreAdapter, parse_datetime
from ..classify import classify_offer, looks_like_bundle, looks_like_dlc, looks_like_demo
from ..models import Offer, Store


LOGGER = logging.getLogger(__name__)


class EpicAdapter(StoreAdapter):
    FREE_URL = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
    GRAPHQL_URL = "https://graphql.epicgames.com/graphql"

    STORE_QUERY = """
    query searchStoreQuery(
      $allowCountries: String
      $category: String
      $count: Int
      $country: String!
      $locale: String
      $sortBy: String
      $sortDir: String
      $start: Int
      $withPrice: Boolean = true
      $withPromotions: Boolean = true
    ) {
      Catalog {
        searchStore(
          allowCountries: $allowCountries
          category: $category
          count: $count
          country: $country
          locale: $locale
          sortBy: $sortBy
          sortDir: $sortDir
          start: $start
          onSale: true
        ) {
          elements {
            id
            namespace
            title
            description
            productSlug
            urlSlug
            developerDisplayName
            publisherDisplayName
            seller { name }
            keyImages { type url }
            categories { path }
            offerMappings { pageSlug pageType }
            catalogNs { mappings { pageSlug pageType } }
            price(country: $country) @include(if: $withPrice) {
              totalPrice {
                discountPrice
                originalPrice
                discount
                currencyCode
                currencyInfo { decimals }
                fmtPrice(locale: $locale) { originalPrice discountPrice intermediatePrice }
              }
            }
            promotions(category: $category) @include(if: $withPromotions) {
              promotionalOffers {
                promotionalOffers {
                  startDate
                  endDate
                  discountSetting { discountType discountPercentage }
                }
              }
              upcomingPromotionalOffers {
                promotionalOffers {
                  startDate
                  endDate
                  discountSetting { discountType discountPercentage }
                }
              }
            }
          }
          paging { count total }
        }
      }
    }
    """

    def fetch_offers(self) -> list[Offer]:
        offers: dict[str, Offer] = {}
        try:
            for offer in self._fetch_giveaways():
                offers[offer.external_id] = offer
        except Exception as exc:
            LOGGER.warning("Epic giveaway feed failed: %s", exc)

        try:
            for offer in self._fetch_paid_sales():
                existing = offers.get(offer.external_id)
                if existing is None or _offer_priority(offer) > _offer_priority(existing):
                    offers[offer.external_id] = offer
        except Exception as exc:
            # The GraphQL storefront schema is not a documented public contract.
            # Giveaways still work through the separate public promotions feed.
            LOGGER.warning("Epic paid-sale query failed; giveaways remain available: %s", exc)

        result = list(offers.values())
        LOGGER.info("Epic produced %d candidate offers", len(result))
        return result

    def _fetch_giveaways(self) -> list[Offer]:
        response = self.http.get(
            self.FREE_URL,
            params={
                "locale": "en-US",
                "country": self.config.region,
                "allowCountries": self.config.region,
            },
            headers={"Referer": "https://store.epicgames.com/"},
        )
        elements = (
            response.json()
            .get("data", {})
            .get("Catalog", {})
            .get("searchStore", {})
            .get("elements", [])
        )
        now = datetime.now(timezone.utc)
        offers: list[Offer] = []
        for item in elements:
            promo = _active_promotion(item.get("promotions"), now)
            if promo is None:
                continue
            parsed = self._parse_item(item, promo=promo, source="epic_free_promotions")
            if parsed and parsed.offer_type.value.startswith("Free to keep"):
                offers.append(parsed)
        return offers

    def _fetch_paid_sales(self) -> list[Offer]:
        offers: list[Offer] = []
        count = 50
        for page in range(max(0, self.config.stores.epic_paid_pages)):
            start = page * count
            variables = {
                "allowCountries": self.config.region,
                "category": "games/edition/base|bundles/games|editors",
                "count": count,
                "country": self.config.region,
                "locale": "en-US",
                "sortBy": "currentPrice",
                "sortDir": "ASC",
                "start": start,
                "withPrice": True,
                "withPromotions": True,
            }
            response = self.http.post(
                self.GRAPHQL_URL,
                json_body={"query": self.STORE_QUERY, "variables": variables},
                headers={
                    "Content-Type": "application/json",
                    "Referer": "https://store.epicgames.com/",
                    "Origin": "https://store.epicgames.com",
                },
            )
            body = response.json()
            if body.get("errors") and not body.get("data"):
                raise RuntimeError(f"Epic GraphQL errors: {body['errors'][:1]}")
            search = body.get("data", {}).get("Catalog", {}).get("searchStore", {})
            elements = search.get("elements", [])
            now = datetime.now(timezone.utc)
            for item in elements:
                promo = _active_promotion(item.get("promotions"), now)
                parsed = self._parse_item(item, promo=promo, source="epic_graphql")
                if parsed:
                    offers.append(parsed)
            total = int(search.get("paging", {}).get("total", 0) or 0)
            if not elements or start + count >= total:
                break
        return offers

    def _parse_item(
        self, item: dict[str, Any], *, promo: dict[str, Any] | None, source: str
    ) -> Offer | None:
        title = str(item.get("title") or "").strip()
        external_id = str(item.get("id") or item.get("namespace") or "").strip()
        if not title or not external_id:
            return None
        categories = tuple(
            str(category.get("path") or "")
            for category in item.get("categories", [])
            if category.get("path")
        )
        if looks_like_dlc(title, None, categories) or looks_like_demo(title):
            return None

        price_root = item.get("price", {}).get("totalPrice", {})
        if not price_root:
            price_root = item.get("price", {}).get("totalPrice", {})
        decimals = int(price_root.get("currencyInfo", {}).get("decimals", 2) or 2)
        original = _minor_from_epic(price_root.get("originalPrice"), decimals)
        current = _minor_from_epic(price_root.get("discountPrice"), decimals)
        currency = str(price_root.get("currencyCode") or self.config.currency)

        # The promotions feed sometimes stores price under price.totalPrice while
        # older variants expose totalPrice directly.
        if original is None:
            fallback_total = item.get("price", {}).get("totalPrice", {})
            original = _minor_from_epic(fallback_total.get("originalPrice"), decimals)
            current = _minor_from_epic(fallback_total.get("discountPrice"), decimals)
            currency = str(fallback_total.get("currencyCode") or currency)

        promotion_active = promo is not None
        promo_discount_setting = (promo or {}).get("discountSetting", {})
        promo_final_percentage = promo_discount_setting.get("discountPercentage")
        if promotion_active and original and current is None and promo_final_percentage == 0:
            current = 0
        if promotion_active and original and promo_final_percentage == 0:
            current = 0

        discount = _discount_percent(original, current)
        if discount is None:
            raw_discount = price_root.get("discount")
            try:
                discount = int(raw_discount)
            except (TypeError, ValueError):
                pass

        product_type = "bundle" if looks_like_bundle(title) else "game"
        offer_type = classify_offer(
            title=title,
            product_type=product_type,
            categories=categories,
            current_price_minor=current,
            normal_price_minor=original,
            is_free_product=original in (None, 0) and current == 0,
            descriptive_text=str(item.get("description") or ""),
            promotion_active=promotion_active,
        )
        if offer_type.value in {"Free-to-play", "DLC / add-on", "Demo"}:
            return None
        if offer_type.value == "Other":
            return None

        slug = _epic_slug(item)
        url = f"https://store.epicgames.com/en-US/p/{slug}" if slug else "https://store.epicgames.com/free-games"
        image_url = _epic_image(item.get("keyImages", []))
        developer = _string_or_none(item.get("developerDisplayName"))
        publisher = _string_or_none(item.get("publisherDisplayName"))
        if not publisher:
            publisher = _string_or_none(item.get("seller", {}).get("name"))
        return Offer(
            external_id=external_id,
            title=title,
            store=Store.EPIC,
            url=url,
            current_price_minor=current,
            normal_price_minor=original,
            currency=currency,
            discount_percent=discount,
            offer_type=offer_type,
            start_at=parse_datetime((promo or {}).get("startDate")),
            end_at=parse_datetime((promo or {}).get("endDate")),
            genres=(),
            developer=developer,
            publisher=publisher,
            image_url=image_url,
            description=_string_or_none(item.get("description")),
            is_bundle=product_type == "bundle",
            rarity_hint=offer_type.value.startswith("Free to keep"),
            metadata={"source": source, "categories": categories},
        )


def _active_promotion(promotions: Any, now: datetime) -> dict[str, Any] | None:
    if not isinstance(promotions, dict):
        return None
    groups = promotions.get("promotionalOffers") or []
    for group in groups:
        for promo in group.get("promotionalOffers", []):
            start = parse_datetime(promo.get("startDate"))
            end = parse_datetime(promo.get("endDate"))
            if (start is None or start <= now) and (end is None or now < end):
                return promo
    return None


def _minor_from_epic(value: Any, decimals: int) -> int | None:
    if value is None:
        return None
    try:
        # Epic numeric price fields are already in minor units.
        return int(value)
    except (TypeError, ValueError):
        return None


def _discount_percent(original: int | None, current: int | None) -> int | None:
    if original is None or current is None or original <= 0:
        return None
    return max(0, min(100, round((original - current) / original * 100)))


def _epic_slug(item: dict[str, Any]) -> str | None:
    for mapping in item.get("offerMappings", []) or []:
        slug = mapping.get("pageSlug")
        if slug:
            return str(slug).strip("/").split("/")[0]
    for mapping in item.get("catalogNs", {}).get("mappings", []) or []:
        slug = mapping.get("pageSlug")
        if slug:
            return str(slug).strip("/").split("/")[0]
    slug = item.get("productSlug") or item.get("urlSlug")
    if slug:
        return str(slug).strip("/").split("/")[0]
    return None


def _epic_image(images: Any) -> str | None:
    preferred = ("OfferImageWide", "DieselStoreFrontWide", "Thumbnail", "OfferImageTall")
    if not isinstance(images, list):
        return None
    for image_type in preferred:
        for image in images:
            if image.get("type") == image_type and image.get("url"):
                return str(image["url"])
    for image in images:
        if image.get("url"):
            return str(image["url"])
    return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _offer_priority(offer: Offer) -> tuple[int, int, int]:
    return (
        int(offer.current_price_minor == 0),
        offer.price_drop_percent or 0,
        -(offer.current_price_minor or 0),
    )

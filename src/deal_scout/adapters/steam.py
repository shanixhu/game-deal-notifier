from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
from typing import Any
import json
import logging
import re

from bs4 import BeautifulSoup

from .base import StoreAdapter, parse_date_only
from ..classify import classify_offer, clean_html_text, looks_like_dlc, looks_like_demo
from ..models import Offer, Store


LOGGER = logging.getLogger(__name__)


class SteamAdapter(StoreAdapter):
    SEARCH_URL = "https://store.steampowered.com/search/results/"
    DETAILS_URL = "https://store.steampowered.com/api/appdetails"
    REVIEWS_URL = "https://store.steampowered.com/appreviews/{app_id}"
    FEATURED_URL = "https://store.steampowered.com/api/featuredcategories"

    def fetch_offers(self) -> list[Offer]:
        featured_deadlines = self._fetch_featured_deadlines()
        raw_rows: dict[str, dict[str, Any]] = {}
        max_results = max(1, self.config.stores.steam_search_results)
        queries = (
            {"sort_by": "Reviews_DESC", "maxprice": None},
            {"sort_by": "Price_ASC", "maxprice": "free"},
        )
        for query in queries:
            start = 0
            while start < max_results:
                count = min(50, max_results - start)
                rows, total = self._fetch_search_page(
                    start=start,
                    count=count,
                    sort_by=query["sort_by"],
                    maxprice=query["maxprice"],
                )
                for row in rows:
                    raw_rows.setdefault(row["app_id"], row)
                start += count
                if not rows or start >= total:
                    break
                if query["maxprice"] == "free":
                    break

        candidates = sorted(
            raw_rows.values(),
            key=lambda row: (
                row.get("current_price_minor") != 0,
                -(row.get("review_count") or 0),
                -(row.get("discount_percent") or 0),
            ),
        )[: self.config.stores.steam_enrich_limit]

        offers: list[Offer] = []
        for row in candidates:
            try:
                offers.append(self._enrich(row, featured_deadlines.get(row["app_id"])))
            except Exception as exc:  # isolate one malformed app
                LOGGER.warning("Steam app %s enrichment failed: %s", row.get("app_id"), exc)
        LOGGER.info("Steam produced %d candidate offers", len(offers))
        return offers

    def _fetch_search_page(
        self, *, start: int, count: int, sort_by: str, maxprice: str | None
    ) -> tuple[list[dict[str, Any]], int]:
        params: dict[str, Any] = {
            "query": "",
            "start": start,
            "count": count,
            "dynamic_data": "",
            "sort_by": sort_by,
            "specials": 1,
            "category1": 998,
            "infinite": 1,
            "ndl": 1,
            "cc": self.config.region,
            "l": "english",
        }
        if maxprice:
            params["maxprice"] = maxprice
        response = self.http.get(self.SEARCH_URL, params=params)
        try:
            body = response.json()
            html = body.get("results_html", "")
            total = int(body.get("total_count", 0) or 0)
        except ValueError:
            html = response.text
            total = start + count
        return self._parse_search_html(html), total

    def _parse_search_html(self, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        rows: list[dict[str, Any]] = []
        for node in soup.select("a.search_result_row"):
            app_id = node.get("data-ds-appid") or ""
            app_id = str(app_id).split(",")[0].strip()
            if not app_id.isdigit():
                continue
            title_node = node.select_one("span.title")
            title = title_node.get_text(" ", strip=True) if title_node else ""
            if not title:
                continue
            discount_text = _text(node.select_one(".search_discount span"))
            discount_match = re.search(r"(\d+)", discount_text)
            original = _parse_steam_price(_text(node.select_one(".discount_original_price")))
            final = _parse_steam_price(_text(node.select_one(".discount_final_price")))
            review_node = node.select_one(".search_review_summary")
            tooltip = unescape(review_node.get("data-tooltip-html", "")) if review_node else ""
            review_label, review_percent, review_count = _parse_review_tooltip(tooltip)
            image = node.select_one("img")
            release = _text(node.select_one(".search_released"))
            tag_ids: tuple[int, ...] = ()
            try:
                parsed_tags = json.loads(node.get("data-ds-tagids", "[]"))
                tag_ids = tuple(int(tag) for tag in parsed_tags)
            except (ValueError, TypeError, json.JSONDecodeError):
                pass
            rows.append(
                {
                    "app_id": app_id,
                    "title": title,
                    "url": str(node.get("href") or f"https://store.steampowered.com/app/{app_id}/"),
                    "discount_percent": int(discount_match.group(1)) if discount_match else None,
                    "normal_price_minor": original,
                    "current_price_minor": final,
                    "review_label": review_label,
                    "review_percent": review_percent,
                    "review_count": review_count,
                    "image_url": str(image.get("src")) if image and image.get("src") else None,
                    "release_date": parse_date_only(release),
                    "tag_ids": tag_ids,
                }
            )
        return rows

    def _enrich(self, row: dict[str, Any], deadline: datetime | None) -> Offer:
        app_id = row["app_id"]
        details_response = self.http.get(
            self.DETAILS_URL,
            params={"appids": app_id, "cc": self.config.region, "l": "english"},
        )
        details_root = details_response.json().get(str(app_id), {})
        data = details_root.get("data", {}) if details_root.get("success") else {}

        review_label = row.get("review_label")
        review_percent = row.get("review_percent")
        review_count = row.get("review_count")
        try:
            reviews_response = self.http.get(
                self.REVIEWS_URL.format(app_id=app_id),
                params={
                    "json": 1,
                    "language": "all",
                    "purchase_type": "all",
                    "filter": "summary",
                    "num_per_page": 0,
                },
            )
            summary = reviews_response.json().get("query_summary", {})
            total_positive = int(summary.get("total_positive", 0) or 0)
            total_reviews = int(summary.get("total_reviews", 0) or 0)
            if total_reviews > 0:
                review_percent = round(total_positive / total_reviews * 100)
                review_count = total_reviews
            review_label = summary.get("review_score_desc") or review_label
        except Exception as exc:
            LOGGER.info("Steam review summary unavailable for %s: %s", app_id, exc)

        price = data.get("price_overview") or {}
        normal = _safe_int(price.get("initial"), row.get("normal_price_minor"))
        current = _safe_int(price.get("final"), row.get("current_price_minor"))
        discount = _safe_int(price.get("discount_percent"), row.get("discount_percent"))
        product_type = str(data.get("type") or "game")
        title = str(data.get("name") or row["title"])
        description = clean_html_text(data.get("short_description"))
        categories = tuple(
            str(item.get("description"))
            for item in data.get("categories", [])
            if item.get("description")
        )
        package_text = " ".join(
            str(sub.get("option_text") or "")
            for group in data.get("package_groups", [])
            for sub in group.get("subs", [])
        )
        promotion_active = (
            current == 0
            and (normal or 0) > 0
            and (deadline is not None or (discount or 0) == 100)
        )
        offer_type = classify_offer(
            title=title,
            product_type=product_type,
            categories=categories,
            current_price_minor=current,
            normal_price_minor=normal,
            is_free_product=bool(data.get("is_free")),
            descriptive_text=f"{description} {package_text}",
            promotion_active=promotion_active,
        )
        genres = tuple(
            str(item.get("description"))
            for item in data.get("genres", [])
            if item.get("description")
        )
        release_date = row.get("release_date")
        release_info = data.get("release_date") or {}
        release_date = parse_date_only(release_info.get("date")) or release_date
        return Offer(
            external_id=app_id,
            title=title,
            store=Store.STEAM,
            url=f"https://store.steampowered.com/app/{app_id}/",
            current_price_minor=current,
            normal_price_minor=normal,
            currency=str(price.get("currency") or self.config.currency),
            discount_percent=discount,
            offer_type=offer_type,
            end_at=deadline,
            review_percent=review_percent,
            review_count=review_count,
            review_label=review_label,
            genres=genres,
            developer=_first(data.get("developers")),
            publisher=_first(data.get("publishers")),
            release_date=release_date,
            image_url=data.get("header_image") or row.get("image_url"),
            description=description,
            is_dlc=looks_like_dlc(title, product_type, categories),
            is_demo=looks_like_demo(title, product_type),
            is_free_to_play=bool(data.get("is_free")) and (normal in (None, 0)),
            rarity_hint=offer_type.value.startswith("Free to keep"),
            metadata={"source": "steam_storefront", "tag_ids": row.get("tag_ids", ())},
        )

    def _fetch_featured_deadlines(self) -> dict[str, datetime]:
        deadlines: dict[str, datetime] = {}
        try:
            response = self.http.get(
                self.FEATURED_URL,
                params={"cc": self.config.region, "l": "english"},
                cache=True,
            )
            body = response.json()
            for category in body.values():
                if not isinstance(category, dict):
                    continue
                for item in category.get("items", []):
                    app_id = str(item.get("id") or "")
                    expiration = item.get("discount_expiration")
                    if app_id.isdigit() and isinstance(expiration, (int, float)) and expiration > 0:
                        deadlines[app_id] = datetime.fromtimestamp(expiration, tz=timezone.utc)
        except Exception as exc:
            LOGGER.info("Steam featured deadlines unavailable: %s", exc)
        return deadlines


def _text(node: Any) -> str:
    return node.get_text(" ", strip=True) if node is not None else ""


def _parse_steam_price(text: str) -> int | None:
    if not text:
        return None
    if "free" in text.casefold():
        return 0
    cleaned = re.sub(r"[^0-9.]", "", text.replace(",", ""))
    if not cleaned:
        return None
    try:
        return round(float(cleaned) * 100)
    except ValueError:
        return None


def _parse_review_tooltip(value: str) -> tuple[str | None, int | None, int | None]:
    text = clean_html_text(value)
    label_match = re.match(r"([^0-9]+?)(?=\d|$)", text)
    percent_match = re.search(r"(\d{1,3})%", text)
    count_match = re.search(r"([\d,]+)\s+(?:user\s+)?reviews", text, flags=re.I)
    label = label_match.group(1).strip(" -") if label_match else None
    percent = int(percent_match.group(1)) if percent_match else None
    count = int(count_match.group(1).replace(",", "")) if count_match else None
    return label, percent, count


def _safe_int(primary: Any, fallback: Any) -> int | None:
    try:
        return int(primary)
    except (TypeError, ValueError):
        try:
            return int(fallback)
        except (TypeError, ValueError):
            return None


def _first(value: Any) -> str | None:
    if isinstance(value, list) and value:
        return str(value[0])
    return None

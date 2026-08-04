from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json


DEFAULT_PREFERRED_GENRES = (
    "atmospheric",
    "story rich",
    "horror",
    "survival",
    "racing",
    "automobile sim",
    "action",
    "rpg",
    "role-playing",
    "experimental",
    "indie",
    "psychological horror",
    "adventure",
)


@dataclass(frozen=True, slots=True)
class FilterConfig:
    preferred_genres: tuple[str, ...] = DEFAULT_PREFERRED_GENRES
    max_price_inr: int = 1500
    min_paid_discount_percent: int = 50
    min_review_percent: int = 75
    min_review_count: int = 200
    min_quality_score: float = 52.0
    min_deal_score: float = 62.0
    send_wait_verdicts: bool = True
    max_wait_alerts_per_run: int = 1
    max_alerts_per_run: int = 8
    blocked_title_terms: tuple[str, ...] = (
        "soundtrack",
        "artbook",
        "wallpaper",
        "currency pack",
        "starter pack",
        "skin pack",
        "cosmetic pack",
        "points pack",
        "dedicated server",
        "benchmark",
    )


@dataclass(frozen=True, slots=True)
class StoreConfig:
    steam: bool = True
    epic: bool = True
    gog: bool = True
    steam_search_results: int = 120
    steam_enrich_limit: int = 36
    gog_pages: int = 3
    epic_paid_pages: int = 2


@dataclass(frozen=True, slots=True)
class AlertConfig:
    include_cover_images: bool = True
    username: str = "PC Game Deal Scout"


@dataclass(frozen=True, slots=True)
class AppConfig:
    region: str = "IN"
    currency: str = "INR"
    timezone: str = "Asia/Kolkata"
    filters: FilterConfig = field(default_factory=FilterConfig)
    stores: StoreConfig = field(default_factory=StoreConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)


def _tuple(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if not isinstance(value, list):
        raise ValueError("Expected a JSON array")
    return tuple(str(item).strip() for item in value if str(item).strip())


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        return AppConfig()
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    filters_raw = raw.get("filters", {})
    stores_raw = raw.get("stores", {})
    alerts_raw = raw.get("alerts", {})

    default_filters = FilterConfig()
    filters = FilterConfig(
        preferred_genres=_tuple(
            filters_raw.get("preferred_genres"), default_filters.preferred_genres
        ),
        max_price_inr=int(filters_raw.get("max_price_inr", default_filters.max_price_inr)),
        min_paid_discount_percent=int(
            filters_raw.get(
                "min_paid_discount_percent", default_filters.min_paid_discount_percent
            )
        ),
        min_review_percent=int(
            filters_raw.get("min_review_percent", default_filters.min_review_percent)
        ),
        min_review_count=int(
            filters_raw.get("min_review_count", default_filters.min_review_count)
        ),
        min_quality_score=float(
            filters_raw.get("min_quality_score", default_filters.min_quality_score)
        ),
        min_deal_score=float(
            filters_raw.get("min_deal_score", default_filters.min_deal_score)
        ),
        send_wait_verdicts=bool(
            filters_raw.get("send_wait_verdicts", default_filters.send_wait_verdicts)
        ),
        max_wait_alerts_per_run=int(
            filters_raw.get(
                "max_wait_alerts_per_run", default_filters.max_wait_alerts_per_run
            )
        ),
        max_alerts_per_run=int(
            filters_raw.get("max_alerts_per_run", default_filters.max_alerts_per_run)
        ),
        blocked_title_terms=_tuple(
            filters_raw.get("blocked_title_terms"), default_filters.blocked_title_terms
        ),
    )

    default_stores = StoreConfig()
    stores = StoreConfig(
        steam=bool(stores_raw.get("steam", default_stores.steam)),
        epic=bool(stores_raw.get("epic", default_stores.epic)),
        gog=bool(stores_raw.get("gog", default_stores.gog)),
        steam_search_results=int(
            stores_raw.get("steam_search_results", default_stores.steam_search_results)
        ),
        steam_enrich_limit=int(
            stores_raw.get("steam_enrich_limit", default_stores.steam_enrich_limit)
        ),
        gog_pages=int(stores_raw.get("gog_pages", default_stores.gog_pages)),
        epic_paid_pages=int(
            stores_raw.get("epic_paid_pages", default_stores.epic_paid_pages)
        ),
    )

    default_alerts = AlertConfig()
    alerts = AlertConfig(
        include_cover_images=bool(
            alerts_raw.get("include_cover_images", default_alerts.include_cover_images)
        ),
        username=str(alerts_raw.get("username", default_alerts.username)),
    )

    return AppConfig(
        region=str(raw.get("region", "IN")).upper(),
        currency=str(raw.get("currency", "INR")).upper(),
        timezone=str(raw.get("timezone", "Asia/Kolkata")),
        filters=filters,
        stores=stores,
        alerts=alerts,
    )

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
    "psychological horror",
    "adventure",
)

DEFAULT_PUBLISHER_WATCHLIST = (
    "Electronic Arts",
    "Capcom",
    "SEGA",
    "Ubisoft",
    "2K",
    "Rockstar Games",
    "Bandai Namco Entertainment",
    "Square Enix",
    "Bethesda Softworks",
    "Xbox Game Studios",
    "PlayStation Publishing LLC",
    "Warner Bros. Games",
    "THQ Nordic",
    "Focus Entertainment",
    "Devolver Digital",
    "Annapurna Interactive",
    "Paradox Interactive",
)


@dataclass(frozen=True, slots=True)
class FilterConfig:
    preferred_genres: tuple[str, ...] = DEFAULT_PREFERRED_GENRES
    max_price_inr: int = 1500
    min_paid_discount_percent: int = 50
    min_review_percent: int = 72
    min_review_count: int = 500
    reliable_review_count: int = 1000
    min_paid_quality_score: float = 58.0
    min_giveaway_quality_score: float = 62.0
    min_deal_score: float = 64.0
    send_wait_verdicts: bool = False
    max_wait_alerts_per_run: int = 0
    max_alerts_per_run: int = 6
    publisher_event_min_offers: int = 3
    publisher_event_min_discount: int = 65
    absence_grace_hours: int = 168
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

    @property
    def min_quality_score(self) -> float:
        """Compatibility alias for older callers and config files."""
        return self.min_paid_quality_score


@dataclass(frozen=True, slots=True)
class StoreConfig:
    steam: bool = True
    epic: bool = True
    gog: bool = True
    steam_search_results: int = 140
    steam_top_seller_results: int = 80
    steam_cheap_special_results: int = 100
    steam_publisher_results: int = 30
    steam_enrich_limit: int = 64
    publisher_watchlist: tuple[str, ...] = DEFAULT_PUBLISHER_WATCHLIST
    gog_pages: int = 4
    epic_paid_pages: int = 3


@dataclass(frozen=True, slots=True)
class AlertConfig:
    include_cover_images: bool = True
    username: str = "Game Deal Notifier"
    batch_alerts: bool = True
    max_embeds_per_message: int = 6


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
    legacy_quality = filters_raw.get("min_quality_score")
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
        reliable_review_count=int(
            filters_raw.get("reliable_review_count", default_filters.reliable_review_count)
        ),
        min_paid_quality_score=float(
            filters_raw.get(
                "min_paid_quality_score",
                legacy_quality if legacy_quality is not None else default_filters.min_paid_quality_score,
            )
        ),
        min_giveaway_quality_score=float(
            filters_raw.get(
                "min_giveaway_quality_score", default_filters.min_giveaway_quality_score
            )
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
        publisher_event_min_offers=int(
            filters_raw.get(
                "publisher_event_min_offers", default_filters.publisher_event_min_offers
            )
        ),
        publisher_event_min_discount=int(
            filters_raw.get(
                "publisher_event_min_discount", default_filters.publisher_event_min_discount
            )
        ),
        absence_grace_hours=int(
            filters_raw.get("absence_grace_hours", default_filters.absence_grace_hours)
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
        steam_top_seller_results=int(
            stores_raw.get(
                "steam_top_seller_results", default_stores.steam_top_seller_results
            )
        ),
        steam_cheap_special_results=int(
            stores_raw.get(
                "steam_cheap_special_results", default_stores.steam_cheap_special_results
            )
        ),
        steam_publisher_results=int(
            stores_raw.get(
                "steam_publisher_results", default_stores.steam_publisher_results
            )
        ),
        steam_enrich_limit=int(
            stores_raw.get("steam_enrich_limit", default_stores.steam_enrich_limit)
        ),
        publisher_watchlist=_tuple(
            stores_raw.get("publisher_watchlist"), default_stores.publisher_watchlist
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
        batch_alerts=bool(alerts_raw.get("batch_alerts", default_alerts.batch_alerts)),
        max_embeds_per_message=max(
            1,
            min(
                10,
                int(
                    alerts_raw.get(
                        "max_embeds_per_message", default_alerts.max_embeds_per_message
                    )
                ),
            ),
        ),
    )

    return AppConfig(
        region=str(raw.get("region", "IN")).upper(),
        currency=str(raw.get("currency", "INR")).upper(),
        timezone=str(raw.get("timezone", "Asia/Kolkata")),
        filters=filters,
        stores=stores,
        alerts=alerts,
    )

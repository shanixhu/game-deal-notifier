from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import hashlib
import json
import re


class Store(str, Enum):
    STEAM = "Steam"
    EPIC = "Epic Games Store"
    GOG = "GOG"


class OfferType(str, Enum):
    FREE_TO_KEEP = "Free to keep permanently"
    FREE_TO_PLAY = "Free-to-play"
    FREE_WEEKEND = "Free weekend / temporary trial"
    DEMO = "Demo"
    PAID_DISCOUNT = "Paid discount"
    BUNDLE = "Bundle"
    DLC = "DLC / add-on"
    OTHER = "Other"


class Verdict(str, Enum):
    CLAIM_NOW = "CLAIM NOW"
    BUY_NOW = "BUY NOW"
    EXCELLENT_PRICE = "EXCELLENT PRICE"
    WAIT = "WAIT FOR A BETTER PRICE"
    SKIP = "SKIP"


VERDICT_RANK: dict[Verdict, int] = {
    Verdict.SKIP: 0,
    Verdict.WAIT: 1,
    Verdict.EXCELLENT_PRICE: 2,
    Verdict.BUY_NOW: 3,
    Verdict.CLAIM_NOW: 4,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def canonical_title(title: str) -> str:
    value = title.casefold().replace("™", "").replace("®", "")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


@dataclass(slots=True)
class Offer:
    external_id: str
    title: str
    store: Store
    url: str
    current_price_minor: int | None
    normal_price_minor: int | None
    currency: str = "INR"
    discount_percent: int | None = None
    offer_type: OfferType = OfferType.OTHER
    start_at: datetime | None = None
    end_at: datetime | None = None
    review_percent: int | None = None
    review_count: int | None = None
    review_label: str | None = None
    genres: tuple[str, ...] = ()
    developer: str | None = None
    publisher: str | None = None
    release_date: datetime | None = None
    image_url: str | None = None
    description: str | None = None
    is_dlc: bool = False
    is_bundle: bool = False
    is_demo: bool = False
    is_free_to_play: bool = False
    historical_low: bool | None = None
    near_historical_low: bool | None = None
    history_source: str | None = None
    rarity_hint: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    quality_score: float = 0.0
    deal_score: float = 0.0
    verdict: Verdict = Verdict.SKIP
    reputation_reason: str = ""
    deal_reason: str = ""

    def __post_init__(self) -> None:
        self.start_at = ensure_utc(self.start_at)
        self.end_at = ensure_utc(self.end_at)
        self.release_date = ensure_utc(self.release_date)
        self.genres = tuple(self.genres)

    @property
    def key(self) -> str:
        return canonical_title(self.title)

    @property
    def is_free(self) -> bool:
        return self.current_price_minor == 0

    @property
    def price_drop_percent(self) -> int | None:
        if self.discount_percent is not None:
            return max(0, min(100, int(self.discount_percent)))
        if (
            self.normal_price_minor is None
            or self.current_price_minor is None
            or self.normal_price_minor <= 0
        ):
            return None
        return max(
            0,
            min(
                100,
                round(
                    (self.normal_price_minor - self.current_price_minor)
                    / self.normal_price_minor
                    * 100
                ),
            ),
        )

    def with_scores(
        self,
        *,
        quality_score: float,
        deal_score: float,
        verdict: Verdict,
        reputation_reason: str,
        deal_reason: str,
    ) -> "Offer":
        return replace(
            self,
            quality_score=quality_score,
            deal_score=deal_score,
            verdict=verdict,
            reputation_reason=reputation_reason,
            deal_reason=deal_reason,
        )

    def state_snapshot(self, now: datetime | None = None) -> dict[str, Any]:
        now = ensure_utc(now or utc_now())
        payload: dict[str, Any] = {
            "title": self.title,
            "store": self.store.value,
            "external_id": self.external_id,
            "current_price_minor": self.current_price_minor,
            "normal_price_minor": self.normal_price_minor,
            "currency": self.currency,
            "discount_percent": self.price_drop_percent,
            "offer_type": self.offer_type.value,
            "end_at": self.end_at.isoformat() if self.end_at else None,
            "historical_low": self.historical_low,
            "near_historical_low": self.near_historical_low,
            "verdict": self.verdict.value,
            "last_seen_at": now.isoformat(),
            "active": True,
        }
        fingerprint_fields = {
            key: payload[key]
            for key in (
                "store",
                "current_price_minor",
                "normal_price_minor",
                "discount_percent",
                "offer_type",
                "end_at",
                "historical_low",
                "near_historical_low",
                "verdict",
            )
        }
        payload["fingerprint"] = hashlib.sha256(
            json.dumps(fingerprint_fields, sort_keys=True).encode("utf-8")
        ).hexdigest()[:20]
        return payload

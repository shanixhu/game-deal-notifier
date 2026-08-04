from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import Offer, OfferType, Store


def sample_offers(now: datetime | None = None) -> list[Offer]:
    now = now or datetime.now(timezone.utc)
    return [
        Offer(
            external_id="sample-control",
            title="Control Ultimate Edition",
            store=Store.EPIC,
            url="https://store.epicgames.com/",
            current_price_minor=0,
            normal_price_minor=249900,
            currency="INR",
            discount_percent=100,
            offer_type=OfferType.FREE_TO_KEEP,
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(days=4),
            genres=("Action", "Atmospheric", "Story Rich"),
            developer="Remedy Entertainment",
            publisher="505 Games",
            image_url="https://cdn1.epicgames.com/offer/sample/control.jpg",
            description="Sample data used only for a local dry run.",
            rarity_hint=True,
            metadata={"source": "sample"},
        ),
        Offer(
            external_id="sample-signalis",
            title="SIGNALIS",
            store=Store.STEAM,
            url="https://store.steampowered.com/",
            current_price_minor=27400,
            normal_price_minor=109900,
            currency="INR",
            discount_percent=75,
            offer_type=OfferType.PAID_DISCOUNT,
            end_at=now + timedelta(days=2),
            review_percent=96,
            review_count=22000,
            review_label="Overwhelmingly Positive",
            genres=("Psychological Horror", "Survival Horror", "Story Rich"),
            developer="rose-engine",
            publisher="Humble Games",
            metadata={"source": "sample"},
        ),
        Offer(
            external_id="sample-soundtrack",
            title="SIGNALIS Soundtrack",
            store=Store.STEAM,
            url="https://store.steampowered.com/",
            current_price_minor=9900,
            normal_price_minor=29900,
            currency="INR",
            discount_percent=67,
            offer_type=OfferType.DLC,
            metadata={"source": "sample"},
        ),
    ]

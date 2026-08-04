from datetime import datetime, timezone

from deal_scout.discord import build_webhook_payload, format_money
from deal_scout.models import Offer, OfferType, Store, Verdict


def test_embed_contains_required_deal_fields(config) -> None:
    deal = Offer(
        external_id="1",
        title="Control Ultimate Edition",
        store=Store.EPIC,
        url="https://store.epicgames.com/",
        current_price_minor=0,
        normal_price_minor=249900,
        currency="INR",
        discount_percent=100,
        offer_type=OfferType.FREE_TO_KEEP,
        end_at=datetime(2026, 8, 6, 15, tzinfo=timezone.utc),
        review_label="Highly regarded",
        image_url="https://example.com/cover.jpg",
        quality_score=90,
        deal_score=100,
        verdict=Verdict.CLAIM_NOW,
        reputation_reason="Excellent atmosphere and world design.",
        deal_reason="Paid game temporarily free to keep.",
    )
    payload = build_webhook_payload(deal, config)
    assert payload["allowed_mentions"] == {"parse": []}
    embed = payload["embeds"][0]
    assert embed["title"].startswith("CLAIM NOW")
    names = {field["name"] for field in embed["fields"]}
    assert {
        "Store",
        "Current price",
        "Normal price",
        "Discount",
        "Offer type",
        "Offer ends",
        "Reputation",
        "Why it matters",
        "Deal analysis",
        "Verdict",
    } <= names
    assert embed["thumbnail"]["url"] == "https://example.com/cover.jpg"


def test_indian_money_formatting() -> None:
    assert format_money(0, "INR") == "Free"
    assert format_money(249900, "INR") == "₹2,499"

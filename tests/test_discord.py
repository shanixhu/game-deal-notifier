from datetime import datetime, timezone

from deal_scout.discord import (
    MAX_EMBED_TEXT_PER_MESSAGE,
    build_digest_payload,
    build_embed,
    build_webhook_payload,
    discord_offer_batches,
    embed_text_length,
    format_money,
)
from deal_scout.models import Offer, OfferType, Store, Verdict


def deal(**overrides) -> Offer:
    values = dict(
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
        deal_reason="A paid, respected game is temporarily free to keep.",
    )
    values.update(overrides)
    return Offer(**values)


def test_embed_contains_compact_required_fields(config) -> None:
    payload = build_webhook_payload(deal(), config)
    assert payload["allowed_mentions"] == {"parse": []}
    embed = payload["embeds"][0]
    assert embed["title"].startswith("CLAIM NOW")
    names = {field["name"] for field in embed["fields"]}
    assert {"Price", "Store", "Offer", "Claim by", "Reputation", "Why it matters", "Why now"} <= names
    deadline = next(field["value"] for field in embed["fields"] if field["name"] == "Claim by")
    assert "IST" in deadline
    assert embed["thumbnail"]["url"] == "https://example.com/cover.jpg"


def test_digest_groups_publisher_sale(config) -> None:
    offers = [
        deal(
            external_id=str(i),
            title=f"EA Game {i}",
            store=Store.STEAM,
            current_price_minor=19900,
            normal_price_minor=199900,
            discount_percent=90,
            offer_type=OfferType.PAID_DISCOUNT,
            verdict=Verdict.BUY_NOW,
            metadata={"sale_event_name": "Electronic Arts sale", "sale_event_size": 3},
        )
        for i in range(3)
    ]
    payload = build_digest_payload(offers, config)
    assert "Electronic Arts sale" in payload["content"]
    assert len(payload["embeds"]) == 3


def test_indian_money_formatting() -> None:
    assert format_money(0, "INR") == "Free"
    assert format_money(249900, "INR") == "₹2,499"


def test_batches_respect_discord_shared_embed_text_limit(config) -> None:
    offers = [
        deal(
            external_id=str(index),
            title=f"Long Deal {index}",
            reputation_reason="R" * 900,
            deal_reason="D" * 900,
        )
        for index in range(6)
    ]
    batches = discord_offer_batches(offers, config)
    assert len(batches) > 1
    for batch in batches:
        total = sum(embed_text_length(build_embed(offer, config)) for offer in batch)
        assert total <= MAX_EMBED_TEXT_PER_MESSAGE
        assert len(batch) <= config.alerts.max_embeds_per_message

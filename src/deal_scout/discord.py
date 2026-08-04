from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Iterable
from zoneinfo import ZoneInfo
import logging

from .config import AppConfig
from .http import HttpClient
from .models import Offer, Verdict


LOGGER = logging.getLogger(__name__)


MAX_EMBEDS_PER_MESSAGE = 10
MAX_EMBED_TEXT_PER_MESSAGE = 5800


VERDICT_COLORS: dict[Verdict, int] = {
    Verdict.CLAIM_NOW: 0x2ECC71,
    Verdict.BUY_NOW: 0x3498DB,
    Verdict.EXCELLENT_PRICE: 0x9B59B6,
    Verdict.WAIT: 0xF1C40F,
    Verdict.SKIP: 0x95A5A6,
}


def format_money(minor: int | None, currency: str) -> str:
    if minor is None:
        return "Not listed"
    if minor == 0:
        return "Free"
    amount = minor / 100
    if currency.upper() == "INR":
        return f"₹{amount:,.0f}" if amount.is_integer() else f"₹{amount:,.2f}"
    return f"{currency.upper()} {amount:,.2f}"


def format_deadline(value: datetime | None, timezone_name: str) -> str:
    if value is None:
        return "Not published by the store"
    local = value.astimezone(ZoneInfo(timezone_name))
    unix = int(value.timestamp())
    return f"{local.strftime('%a, %d %b at %I:%M %p IST')} · <t:{unix}:R>"


def build_embed(offer: Offer, config: AppConfig) -> dict[str, Any]:
    discount = offer.price_drop_percent
    discount_text = f"{discount}% off" if discount is not None else offer.offer_type.value
    price_line = format_money(offer.current_price_minor, offer.currency)
    normal_line = format_money(offer.normal_price_minor, offer.currency)
    if offer.normal_price_minor not in (None, 0):
        price_line += f" · normally {normal_line}"

    review_text = offer.review_label or "Independent store review data unavailable"
    if offer.review_percent is not None:
        review_text = f"{offer.review_percent}% positive"
        if offer.review_count is not None:
            review_text += f" from {offer.review_count:,} reviews"
    elif offer.quality_score >= config.filters.min_giveaway_quality_score:
        review_text = "Known, well-regarded release"

    fields = [
        {"name": "Price", "value": price_line[:1024], "inline": True},
        {"name": "Store", "value": offer.store.value, "inline": True},
        {
            "name": "Offer",
            "value": offer.offer_type.value if offer.current_price_minor == 0 else discount_text,
            "inline": True,
        },
        {
            "name": "Claim by" if offer.offer_type.value.startswith("Free to keep") else "Offer ends",
            "value": format_deadline(offer.end_at, config.timezone),
            "inline": False,
        },
        {"name": "Reputation", "value": review_text[:1024], "inline": False},
        {"name": "Why it matters", "value": offer.reputation_reason[:1024], "inline": False},
        {"name": "Why now", "value": offer.deal_reason[:1024], "inline": False},
    ]

    title = f"{offer.verdict.value} · {offer.title}"
    if offer.current_price_minor == 0 and offer.offer_type.value.startswith("Free to keep"):
        title += " — FREE TO KEEP"
    elif discount is not None:
        title += f" — {discount}% off"
    embed: dict[str, Any] = {
        "title": title[:256],
        "url": offer.url,
        "color": VERDICT_COLORS[offer.verdict],
        "fields": fields,
        "footer": {
            "text": "India pricing when available · no repeat alerts for unchanged sales"
        },
    }
    if config.alerts.include_cover_images and offer.image_url:
        embed["thumbnail"] = {"url": offer.image_url}
    return embed


def embed_text_length(embed: dict[str, Any]) -> int:
    total = len(str(embed.get("title") or "")) + len(str(embed.get("description") or ""))
    footer = embed.get("footer") or {}
    total += len(str(footer.get("text") or ""))
    author = embed.get("author") or {}
    total += len(str(author.get("name") or ""))
    for field in embed.get("fields") or []:
        total += len(str(field.get("name") or ""))
        total += len(str(field.get("value") or ""))
    return total


def discord_offer_batches(
    offers: Iterable[Offer], config: AppConfig
) -> list[list[Offer]]:
    """Split embeds by both Discord's count limit and its shared text budget."""
    count_limit = max(1, min(MAX_EMBEDS_PER_MESSAGE, config.alerts.max_embeds_per_message))
    batches: list[list[Offer]] = []
    current: list[Offer] = []
    current_chars = 0
    for offer in offers:
        chars = embed_text_length(build_embed(offer, config))
        if current and (
            len(current) >= count_limit
            or current_chars + chars > MAX_EMBED_TEXT_PER_MESSAGE
        ):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(offer)
        current_chars += chars
    if current:
        batches.append(current)
    return batches


def build_webhook_payload(offer: Offer, config: AppConfig) -> dict[str, Any]:
    return {
        "username": config.alerts.username[:80],
        "allowed_mentions": {"parse": []},
        "embeds": [build_embed(offer, config)],
    }


def build_digest_payload(offers: Iterable[Offer], config: AppConfig) -> dict[str, Any]:
    selected = list(offers)
    if not selected:
        raise ValueError("Cannot build an empty deal digest")
    event_names = [offer.sale_event_name for offer in selected if offer.sale_event_name]
    dominant = Counter(event_names).most_common(1)
    if dominant and dominant[0][1] >= config.filters.publisher_event_min_offers:
        heading = f"**{dominant[0][0]} — {len(selected)} picks worth checking**"
    elif len(selected) == 1:
        heading = "**One worthwhile PC deal found**"
    else:
        heading = f"**{len(selected)} worthwhile PC deals found**"
    return {
        "username": config.alerts.username[:80],
        "content": heading,
        "allowed_mentions": {"parse": []},
        "embeds": [build_embed(offer, config) for offer in selected],
    }


def build_test_payload(config: AppConfig) -> dict[str, Any]:
    return {
        "username": config.alerts.username[:80],
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "title": "TEST OK · Game Deal Notifier",
                "description": "Discord is connected. This is sample data; no store offer was claimed or purchased.",
                "color": 0x2ECC71,
                "fields": [
                    {"name": "Mode", "value": "GitHub Actions manual test", "inline": True},
                    {"name": "Region", "value": "India (INR)", "inline": True},
                    {
                        "name": "Next step",
                        "value": "Run `dry-run` to inspect live store results, then use `live` for real alerts.",
                        "inline": False,
                    },
                ],
                "footer": {"text": "No state was changed by this test"},
            }
        ],
    }


class DiscordWebhookSender:
    def __init__(self, webhook_url: str, http: HttpClient) -> None:
        if not webhook_url.startswith(("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/")):
            raise ValueError("DISCORD_WEBHOOK_URL does not look like a Discord webhook URL")
        self.webhook_url = webhook_url
        self.http = http

    def send_payload(self, payload: dict[str, Any]) -> None:
        response = self.http.post(
            self.webhook_url,
            params={"wait": "true"},
            json_body=payload,
            headers={"Content-Type": "application/json"},
        )
        LOGGER.info("Discord accepted webhook message with HTTP %s", response.status_code)

    def send_offer(self, offer: Offer, config: AppConfig) -> None:
        self.send_payload(build_webhook_payload(offer, config))

    def send_offers(self, offers: Iterable[Offer], config: AppConfig) -> None:
        selected = list(offers)
        if not selected:
            return
        for chunk in discord_offer_batches(selected, config):
            if config.alerts.batch_alerts:
                self.send_payload(build_digest_payload(chunk, config))
            else:
                for offer in chunk:
                    self.send_offer(offer, config)

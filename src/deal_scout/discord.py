from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo
import logging

from .config import AppConfig
from .http import HttpClient
from .models import Offer, OfferType, Verdict


LOGGER = logging.getLogger(__name__)


VERDICT_COLORS: dict[Verdict, int] = {
    Verdict.CLAIM_NOW: 0x2ECC71,
    Verdict.BUY_NOW: 0x3498DB,
    Verdict.EXCELLENT_PRICE: 0x9B59B6,
    Verdict.WAIT: 0xF1C40F,
    Verdict.SKIP: 0x95A5A6,
}


def format_money(minor: int | None, currency: str) -> str:
    if minor is None:
        return "Not supplied"
    if minor == 0:
        return "Free"
    amount = minor / 100
    if currency.upper() == "INR":
        return f"₹{amount:,.0f}" if amount.is_integer() else f"₹{amount:,.2f}"
    return f"{currency.upper()} {amount:,.2f}"


def format_deadline(value: datetime | None, timezone_name: str) -> str:
    if value is None:
        return "Not listed by the store feed"
    local = value.astimezone(ZoneInfo(timezone_name))
    unix = int(value.timestamp())
    return f"{local.strftime('%a, %d %b %Y, %I:%M %p IST')} • <t:{unix}:R>"


def build_embed(offer: Offer, config: AppConfig) -> dict[str, Any]:
    discount = offer.price_drop_percent
    review_text = offer.review_label or "Reputation data limited"
    if offer.review_percent is not None:
        review_text = f"{review_text} — {offer.review_percent}% positive"
        if offer.review_count is not None:
            review_text += f" ({offer.review_count:,} reviews)"

    fields = [
        {"name": "Store", "value": offer.store.value, "inline": True},
        {
            "name": "Current price",
            "value": format_money(offer.current_price_minor, offer.currency),
            "inline": True,
        },
        {
            "name": "Normal price",
            "value": format_money(offer.normal_price_minor, offer.currency),
            "inline": True,
        },
        {
            "name": "Discount",
            "value": f"{discount}%" if discount is not None else "Not supplied",
            "inline": True,
        },
        {"name": "Offer type", "value": offer.offer_type.value, "inline": True},
        {
            "name": "Offer ends",
            "value": format_deadline(offer.end_at, config.timezone),
            "inline": False,
        },
        {"name": "Reputation", "value": review_text[:1024], "inline": False},
        {
            "name": "Why it matters",
            "value": offer.reputation_reason[:1024],
            "inline": False,
        },
        {
            "name": "Deal analysis",
            "value": offer.deal_reason[:1024],
            "inline": False,
        },
        {
            "name": "Verdict",
            "value": _verdict_copy(offer),
            "inline": False,
        },
    ]

    embed: dict[str, Any] = {
        "title": f"{offer.verdict.value} — {offer.title}"[:256],
        "url": offer.url,
        "description": "Direct link to the legitimate store listing.",
        "color": VERDICT_COLORS[offer.verdict],
        "fields": fields,
        "footer": {
            "text": "PC Game Deal Scout • Indian pricing when supplied by the store • No unverified historical-low claims"
        },
    }
    if config.alerts.include_cover_images and offer.image_url:
        embed["thumbnail"] = {"url": offer.image_url}
    return embed


def build_webhook_payload(offer: Offer, config: AppConfig) -> dict[str, Any]:
    return {
        "username": config.alerts.username[:80],
        "allowed_mentions": {"parse": []},
        "embeds": [build_embed(offer, config)],
    }


def build_test_payload(config: AppConfig) -> dict[str, Any]:
    return {
        "username": config.alerts.username[:80],
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "title": "TEST OK — PC Game Deal Scout",
                "description": (
                    "The Discord webhook is configured correctly. This is sample data only; "
                    "no real deal was claimed or purchased."
                ),
                "color": VERDICT_COLORS[Verdict.CLAIM_NOW],
                "fields": [
                    {"name": "Mode", "value": "GitHub Actions manual test", "inline": True},
                    {"name": "Region", "value": "India (INR)", "inline": True},
                    {
                        "name": "Next step",
                        "value": "Run the workflow in `live` mode, or let the schedule handle it automatically.",
                        "inline": False,
                    },
                ],
                "footer": {"text": "No state was changed by this test"},
            }
        ],
    }


class DiscordWebhookSender:
    def __init__(self, webhook_url: str, http: HttpClient) -> None:
        if not webhook_url.startswith("https://discord.com/api/webhooks/") and not webhook_url.startswith(
            "https://discordapp.com/api/webhooks/"
        ):
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


def _verdict_copy(offer: Offer) -> str:
    if offer.verdict == Verdict.CLAIM_NOW:
        return "Claim it during the promotion. It should remain permanently in your library after claiming."
    if offer.verdict == Verdict.BUY_NOW:
        return "Buy now if the game interests you; the current combination of quality and price is unusually strong."
    if offer.verdict == Verdict.EXCELLENT_PRICE:
        return "An excellent current price. It is a strong buy, though not labelled a historical low without verified history."
    if offer.verdict == Verdict.WAIT:
        return "Keep it wishlisted and wait for a deeper discount."
    return "Skip."

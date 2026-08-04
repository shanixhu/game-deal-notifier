from __future__ import annotations

import re
from typing import Iterable

from .models import Offer, OfferType


DLC_TERMS = (
    " dlc",
    "add-on",
    "addon",
    "expansion pass",
    "season pass",
    "content pack",
    "skin pack",
    "cosmetic",
    "soundtrack",
    "artbook",
    "currency pack",
    "starter pack",
)
DEMO_TERMS = (" demo", "prologue", "playtest", "benchmark")
TRIAL_TERMS = (
    "free weekend",
    "free trial",
    "trial version",
    "free access",
    "play for free until",
    "friend's pass",
    "friend’s pass",
)
BUNDLE_TERMS = ("bundle", "collection", "anthology", "complete pack")


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    lowered = f" {text.casefold()} "
    return any(term in lowered for term in terms)


def looks_like_dlc(title: str, product_type: str | None = None, categories: Iterable[str] = ()) -> bool:
    category_text = " ".join(categories).casefold()
    product = (product_type or "").casefold()
    return (
        product in {"dlc", "addon", "add-on", "extras"}
        or "addons" in category_text
        or "dlc" in category_text
        or _contains_any(title, DLC_TERMS)
    )


def looks_like_demo(title: str, product_type: str | None = None) -> bool:
    return (product_type or "").casefold() in {"demo", "playtest"} or _contains_any(
        title, DEMO_TERMS
    )


def looks_like_trial(text: str) -> bool:
    return _contains_any(text, TRIAL_TERMS)


def looks_like_bundle(title: str, product_type: str | None = None) -> bool:
    product = (product_type or "").casefold()
    return product in {"bundle", "pack"} or _contains_any(title, BUNDLE_TERMS)


def classify_offer(
    *,
    title: str,
    product_type: str | None,
    categories: Iterable[str],
    current_price_minor: int | None,
    normal_price_minor: int | None,
    is_free_product: bool = False,
    descriptive_text: str = "",
    promotion_active: bool = False,
) -> OfferType:
    combined = f"{title} {descriptive_text}"
    if looks_like_dlc(title, product_type, categories):
        return OfferType.DLC
    if looks_like_demo(title, product_type):
        return OfferType.DEMO
    if looks_like_trial(combined):
        return OfferType.FREE_WEEKEND
    if looks_like_bundle(title, product_type):
        if current_price_minor == 0 and (normal_price_minor or 0) > 0 and promotion_active:
            return OfferType.FREE_TO_KEEP
        return OfferType.BUNDLE
    if is_free_product and (normal_price_minor in (None, 0)):
        return OfferType.FREE_TO_PLAY
    if current_price_minor == 0 and (normal_price_minor or 0) > 0 and promotion_active:
        return OfferType.FREE_TO_KEEP
    if current_price_minor == 0 and is_free_product:
        return OfferType.FREE_TO_PLAY
    if (
        current_price_minor is not None
        and normal_price_minor is not None
        and current_price_minor < normal_price_minor
    ):
        return OfferType.PAID_DISCOUNT
    return OfferType.OTHER


def is_blocked_offer(offer: Offer, blocked_terms: Iterable[str]) -> bool:
    title = offer.title.casefold()
    if offer.offer_type in {OfferType.DLC, OfferType.DEMO, OfferType.FREE_TO_PLAY}:
        return True
    if offer.is_dlc or offer.is_demo:
        return True
    return any(term.casefold() in title for term in blocked_terms)


def clean_html_text(value: str | None) -> str:
    if not value:
        return ""
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return " ".join(without_tags.replace("&amp;", "&").split())

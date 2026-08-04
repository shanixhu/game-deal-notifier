from __future__ import annotations

from datetime import datetime, timezone
import math

from .classify import is_blocked_offer
from .config import AppConfig
from .curation import ReputationCatalog
from .models import Offer, OfferType, Verdict


def _review_quality(offer: Offer) -> float:
    if offer.review_percent is None:
        return 18.0 if offer.store.value == "Epic Games Store" else 12.0
    percent_component = max(0.0, min(32.0, (offer.review_percent - 50) * 0.64))
    count = max(0, offer.review_count or 0)
    count_component = min(21.0, math.log10(count + 1) / 5.0 * 21.0)
    return percent_component + count_component


def _genre_bonus(offer: Offer, config: AppConfig) -> float:
    genres = " ".join(offer.genres).casefold()
    matches = sum(1 for preferred in config.filters.preferred_genres if preferred in genres)
    return min(9.0, matches * 2.25)


def _age_bonus(offer: Offer, now: datetime) -> float:
    if not offer.release_date:
        return 1.0
    age_days = (now - offer.release_date).days
    if age_days >= 365:
        return 4.0
    if age_days >= 90:
        return 2.0
    return 0.0


def score_quality(
    offer: Offer, config: AppConfig, catalog: ReputationCatalog, now: datetime | None = None
) -> tuple[float, str]:
    now = now or datetime.now(timezone.utc)
    entry = catalog.match(offer.title)
    trusted = catalog.is_trusted(offer.developer, offer.publisher)

    score = 20.0 + _review_quality(offer) + _genre_bonus(offer, config) + _age_bonus(offer, now)
    if entry:
        score += entry.boost
    if trusted:
        score += 6.0
    if offer.offer_type == OfferType.FREE_TO_KEEP and offer.store.value == "Epic Games Store":
        score += 5.0  # Epic's weekly giveaway slot is itself curated.
    if offer.review_percent is not None:
        if offer.review_percent < 65:
            score -= 25.0
        elif offer.review_percent < config.filters.min_review_percent and not entry:
            score -= 8.0
    if offer.review_count is not None and not entry:
        if offer.review_count < 50:
            score -= 12.0
        elif offer.review_count < config.filters.min_review_count:
            score -= 5.0
    if offer.is_dlc or offer.is_demo:
        score -= 60.0
    score = max(0.0, min(100.0, score))

    if entry:
        reason = entry.reason
    elif offer.review_percent is not None and offer.review_count is not None:
        genre_text = ", ".join(offer.genres[:2]) or "its genre"
        reason = (
            f"Strong player reception at {offer.review_percent}% positive across "
            f"{offer.review_count:,} reviews, with appeal for fans of {genre_text}."
        )
    elif trusted:
        maker = offer.developer or offer.publisher or "an established studio"
        reason = f"From {maker}, an established name with a stronger-than-average track record."
    else:
        genre_text = ", ".join(offer.genres[:2]) or "PC games"
        reason = f"A store-featured {genre_text} release; reputation data is limited, so the filter stays conservative."
    return score, reason


def score_deal(offer: Offer, quality_score: float, config: AppConfig) -> float:
    discount = offer.price_drop_percent or 0
    score = quality_score * 0.45
    if offer.offer_type == OfferType.FREE_TO_KEEP:
        score += 48.0
    else:
        if discount >= 90:
            score += 35.0
        elif discount >= 80:
            score += 29.0
        elif discount >= 70:
            score += 23.0
        elif discount >= 60:
            score += 17.0
        elif discount >= 50:
            score += 12.0
        elif discount >= 35:
            score += 5.0

        price = offer.current_price_minor
        if price is not None:
            rupees = price / 100
            if rupees <= 200:
                score += 12.0
            elif rupees <= 500:
                score += 8.0
            elif rupees <= 1000:
                score += 4.0
            elif rupees > config.filters.max_price_inr:
                score -= 5.0

    if offer.historical_low is True:
        score += 14.0
    elif offer.near_historical_low is True:
        score += 7.0
    if offer.rarity_hint:
        score += 5.0
    return max(0.0, min(100.0, score))


def select_verdict(
    offer: Offer, quality_score: float, deal_score: float, config: AppConfig
) -> tuple[Verdict, str]:
    discount = offer.price_drop_percent or 0
    current_rupees = (
        offer.current_price_minor / 100 if offer.current_price_minor is not None else None
    )

    if offer.offer_type == OfferType.FREE_TO_KEEP:
        if quality_score >= 42.0:
            return (
                Verdict.CLAIM_NOW,
                "This is a paid game temporarily reduced to zero. Claiming during the window keeps it permanently in your library.",
            )
        return Verdict.SKIP, "The giveaway does not clear the quality threshold."

    if offer.offer_type not in {OfferType.PAID_DISCOUNT, OfferType.BUNDLE}:
        return Verdict.SKIP, "This offer type is not eligible for deal alerts."

    if offer.historical_low is True and quality_score >= config.filters.min_quality_score:
        return Verdict.BUY_NOW, "A verified historical low on a well-regarded game makes this an unusually strong buying point."

    if (
        quality_score >= 66
        and deal_score >= 72
        and discount >= 70
        and (current_rupees is None or current_rupees <= config.filters.max_price_inr)
    ):
        return Verdict.BUY_NOW, "The quality, discount, and final price align well enough to recommend buying now."

    if (
        quality_score >= config.filters.min_quality_score
        and deal_score >= config.filters.min_deal_score
        and discount >= config.filters.min_paid_discount_percent
    ):
        history_note = (
            " No reliable lifetime price-history source was available, so this is labelled a strong discount rather than a historical low."
            if offer.historical_low is None
            else ""
        )
        return Verdict.EXCELLENT_PRICE, f"This is a strong discount for the game's reputation and current price.{history_note}"

    if (
        config.filters.send_wait_verdicts
        and quality_score >= 70
        and 25 <= discount < config.filters.min_paid_discount_percent
        and current_rupees is not None
        and current_rupees >= 700
    ):
        return Verdict.WAIT, "The game is worth watching, but this discount is ordinary enough that a better sale is plausible."

    return Verdict.SKIP, "The offer is not strong enough to justify a notification."


def evaluate_offer(
    offer: Offer, config: AppConfig, catalog: ReputationCatalog, now: datetime | None = None
) -> Offer:
    if is_blocked_offer(offer, config.filters.blocked_title_terms):
        return offer.with_scores(
            quality_score=0,
            deal_score=0,
            verdict=Verdict.SKIP,
            reputation_reason="Excluded non-base-game content or low-signal product type.",
            deal_reason="DLC, demos, free-to-play listings, cosmetics, and soundtracks are not deal alerts.",
        )
    quality, reputation_reason = score_quality(offer, config, catalog, now)
    deal = score_deal(offer, quality, config)
    verdict, deal_reason = select_verdict(offer, quality, deal, config)
    return offer.with_scores(
        quality_score=quality,
        deal_score=deal,
        verdict=verdict,
        reputation_reason=reputation_reason,
        deal_reason=deal_reason,
    )

from __future__ import annotations

from datetime import datetime, timezone
import math

from .classify import is_blocked_offer
from .config import AppConfig
from .curation import ReputationCatalog
from .models import Offer, OfferType, Verdict


_REVIEW_PRIOR_PERCENT = 72.0
_REVIEW_PRIOR_WEIGHT = 600


def adjusted_review_percent(offer: Offer) -> float | None:
    if offer.review_percent is None or offer.review_count is None:
        return None
    count = max(0, offer.review_count)
    return (
        offer.review_percent * count + _REVIEW_PRIOR_PERCENT * _REVIEW_PRIOR_WEIGHT
    ) / (count + _REVIEW_PRIOR_WEIGHT)


def _review_quality(offer: Offer) -> float:
    adjusted = adjusted_review_percent(offer)
    if adjusted is None:
        return 0.0
    rating_component = max(0.0, min(36.0, (adjusted - 52.0) * 1.05))
    count = max(0, offer.review_count or 0)
    volume_component = min(22.0, math.log10(count + 1) * 4.8)
    return rating_component + volume_component


def _genre_bonus(offer: Offer, config: AppConfig) -> float:
    genres = " ".join(offer.genres).casefold()
    matches = sum(1 for preferred in config.filters.preferred_genres if preferred in genres)
    return min(7.0, matches * 1.75)


def _age_bonus(offer: Offer, now: datetime) -> float:
    if not offer.release_date:
        return 1.0
    age_days = (now - offer.release_date).days
    if age_days >= 730:
        return 5.0
    if age_days >= 365:
        return 3.0
    if age_days >= 120:
        return 1.0
    return 0.0


def has_reliable_reputation(
    offer: Offer, config: AppConfig, catalog: ReputationCatalog
) -> bool:
    entry = catalog.match(offer.title)
    if entry:
        return True
    adjusted = adjusted_review_percent(offer)
    count = offer.review_count or 0
    if adjusted is not None:
        if count >= config.filters.reliable_review_count and adjusted >= config.filters.min_review_percent:
            return True
        if (
            catalog.is_trusted(offer.developer, offer.publisher)
            and count >= config.filters.min_review_count
            and adjusted >= 68
        ):
            return True
    return False


def score_quality(
    offer: Offer, config: AppConfig, catalog: ReputationCatalog, now: datetime | None = None
) -> tuple[float, str]:
    now = now or datetime.now(timezone.utc)
    entry = catalog.match(offer.title)
    trusted = catalog.is_trusted(offer.developer, offer.publisher)
    adjusted = adjusted_review_percent(offer)
    count = offer.review_count or 0

    score = 18.0 + _review_quality(offer) + _genre_bonus(offer, config) + _age_bonus(offer, now)
    if entry:
        score += 24.0 + entry.boost
    if trusted:
        score += 5.0
    if offer.sale_event_name:
        score += 2.0

    if offer.review_percent is not None:
        if offer.review_percent < 60:
            score -= 32.0
        elif offer.review_percent < 67:
            score -= 16.0
    if not entry:
        if count and count < 50:
            score -= 24.0
        elif count and count < 200:
            score -= 15.0
        elif count and count < config.filters.min_review_count:
            score -= 8.0
        elif count == 0 and not trusted:
            score -= 30.0
        elif count == 0:
            score -= 12.0

    # Free is a price, not a quality signal. Unknown giveaways are intentionally
    # held back unless the title has independent reputation evidence.
    if offer.offer_type == OfferType.FREE_TO_KEEP and not entry and adjusted is None:
        score -= 12.0
    if offer.is_dlc or offer.is_demo:
        score -= 70.0
    score = max(0.0, min(100.0, score))

    if entry:
        reason = entry.reason
    elif adjusted is not None and offer.review_count is not None:
        genre_text = ", ".join(offer.genres[:2]) or "its genre"
        reason = (
            f"{offer.review_percent}% positive from {offer.review_count:,} Steam reviews "
            f"(confidence-adjusted to {adjusted:.0f}%), with appeal for fans of {genre_text}."
        )
    elif trusted:
        maker = offer.developer or offer.publisher or "an established studio"
        reason = (
            f"From {maker}, but the store feed does not provide enough independent review "
            "evidence for a confident recommendation."
        )
    else:
        reason = "The listing does not have enough review volume or established reputation to recommend confidently."
    return score, reason


def score_deal(offer: Offer, quality_score: float, config: AppConfig) -> float:
    discount = offer.price_drop_percent or 0
    score = quality_score * 0.50
    if offer.offer_type == OfferType.FREE_TO_KEEP:
        score += 38.0
    else:
        if discount >= 90:
            score += 34.0
        elif discount >= 85:
            score += 31.0
        elif discount >= 80:
            score += 28.0
        elif discount >= 75:
            score += 25.0
        elif discount >= 70:
            score += 21.0
        elif discount >= 60:
            score += 15.0
        elif discount >= 50:
            score += 10.0
        elif discount >= 35:
            score += 4.0

        price = offer.current_price_minor
        if price is not None:
            rupees = price / 100
            if rupees <= 200:
                score += 12.0
            elif rupees <= 500:
                score += 9.0
            elif rupees <= 1000:
                score += 5.0
            elif rupees > config.filters.max_price_inr * 1.5:
                score -= 7.0

    if offer.sale_event_name:
        score += 8.0
    if offer.historical_low is True:
        score += 14.0
    elif offer.near_historical_low is True:
        score += 7.0
    if offer.rarity_hint:
        score += 3.0
    return max(0.0, min(100.0, score))


def select_verdict(
    offer: Offer,
    quality_score: float,
    deal_score: float,
    config: AppConfig,
    catalog: ReputationCatalog,
) -> tuple[Verdict, str]:
    discount = offer.price_drop_percent or 0
    current_rupees = (
        offer.current_price_minor / 100 if offer.current_price_minor is not None else None
    )
    reliable = has_reliable_reputation(offer, config, catalog)

    if offer.offer_type == OfferType.FREE_TO_KEEP:
        if reliable and quality_score >= config.filters.min_giveaway_quality_score:
            return (
                Verdict.CLAIM_NOW,
                "A paid, well-established game is temporarily free to keep. Claim it before the promotion closes.",
            )
        return Verdict.SKIP, "Free alone is not enough; this giveaway lacks reliable quality evidence."

    if offer.offer_type not in {OfferType.PAID_DISCOUNT, OfferType.BUNDLE}:
        return Verdict.SKIP, "This offer type is not eligible for deal alerts."
    if not reliable:
        return Verdict.SKIP, "The discount is visible, but the game lacks enough reliable reputation evidence."

    event_note = f" It is also part of a broader {offer.sale_event_name}." if offer.sale_event_name else ""
    if offer.historical_low is True and quality_score >= config.filters.min_paid_quality_score:
        return Verdict.BUY_NOW, f"A verified historical low on a respected game is a rare buying point.{event_note}"

    affordable = current_rupees is None or current_rupees <= config.filters.max_price_inr * 1.25
    if quality_score >= 68 and deal_score >= 74 and discount >= 70 and affordable:
        return (
            Verdict.BUY_NOW,
            f"The game has strong reputation evidence and the {discount}% cut puts it at a genuinely compelling price.{event_note}",
        )

    if (
        quality_score >= config.filters.min_paid_quality_score
        and deal_score >= config.filters.min_deal_score
        and discount >= config.filters.min_paid_discount_percent
    ):
        history_note = (
            " Price history is not independently verified, so this is called a strong price rather than a historical low."
            if offer.historical_low is None
            else ""
        )
        return (
            Verdict.EXCELLENT_PRICE,
            f"This is a strong discount relative to the game's reputation and final price.{event_note}{history_note}",
        )

    if (
        config.filters.send_wait_verdicts
        and quality_score >= 78
        and 30 <= discount < config.filters.min_paid_discount_percent
        and current_rupees is not None
        and current_rupees >= 700
    ):
        return Verdict.WAIT, "The game is worth tracking, but this is still a routine discount rather than a standout buy."

    return Verdict.SKIP, "The price or discount is not strong enough to justify an alert."


def evaluate_offer(
    offer: Offer, config: AppConfig, catalog: ReputationCatalog, now: datetime | None = None
) -> Offer:
    now = now or datetime.now(timezone.utc)
    if offer.start_at and offer.start_at > now:
        return offer.with_scores(
            quality_score=0,
            deal_score=0,
            verdict=Verdict.SKIP,
            reputation_reason="The promotion has not started yet.",
            deal_reason="Upcoming offers are not sent as active deals.",
        )
    if offer.end_at and offer.end_at <= now:
        return offer.with_scores(
            quality_score=0,
            deal_score=0,
            verdict=Verdict.SKIP,
            reputation_reason="The promotion deadline has passed.",
            deal_reason="Expired offers are not sent.",
        )
    if is_blocked_offer(offer, config.filters.blocked_title_terms):
        return offer.with_scores(
            quality_score=0,
            deal_score=0,
            verdict=Verdict.SKIP,
            reputation_reason="Excluded non-base-game content or unsupported offer type.",
            deal_reason="DLC, demos, free-to-play listings, cosmetics and soundtracks are not deal alerts.",
        )
    quality, reputation_reason = score_quality(offer, config, catalog, now)
    deal = score_deal(offer, quality, config)
    verdict, deal_reason = select_verdict(offer, quality, deal, config, catalog)
    return offer.with_scores(
        quality_score=quality,
        deal_score=deal,
        verdict=verdict,
        reputation_reason=reputation_reason,
        deal_reason=deal_reason,
    )

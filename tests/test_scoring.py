from datetime import datetime, timezone

from deal_scout.models import Offer, OfferType, Store, Verdict
from deal_scout.scoring import evaluate_offer, score_quality


def make_offer(**overrides):
    values = dict(
        external_id="1",
        title="SIGNALIS",
        store=Store.STEAM,
        url="https://store.steampowered.com/app/1/",
        current_price_minor=27400,
        normal_price_minor=109900,
        currency="INR",
        discount_percent=75,
        offer_type=OfferType.PAID_DISCOUNT,
        review_percent=96,
        review_count=22000,
        review_label="Overwhelmingly Positive",
        genres=("Psychological Horror", "Survival Horror"),
    )
    values.update(overrides)
    return Offer(**values)


def test_high_quality_game_scores_above_weak_game(config, catalog) -> None:
    strong = make_offer()
    weak = make_offer(
        external_id="2",
        title="Unknown Low Quality Game",
        review_percent=55,
        review_count=20,
        genres=("Casual",),
    )
    now = datetime(2026, 8, 2, tzinfo=timezone.utc)
    strong_score, _ = score_quality(strong, config, catalog, now)
    weak_score, _ = score_quality(weak, config, catalog, now)
    assert strong_score > weak_score + 25


def test_strong_discount_gets_buy_now(config, catalog) -> None:
    evaluated = evaluate_offer(make_offer(), config, catalog)
    assert evaluated.verdict == Verdict.BUY_NOW
    assert evaluated.quality_score >= 66


def test_soundtrack_is_skipped(config, catalog) -> None:
    soundtrack = make_offer(
        title="SIGNALIS Soundtrack",
        offer_type=OfferType.DLC,
        is_dlc=True,
    )
    evaluated = evaluate_offer(soundtrack, config, catalog)
    assert evaluated.verdict == Verdict.SKIP


def test_useful_wait_verdict(config, catalog) -> None:
    ordinary_sale = make_offer(
        title="Disco Elysium - The Final Cut",
        current_price_minor=99900,
        normal_price_minor=149900,
        discount_percent=33,
        review_percent=92,
        review_count=80000,
    )
    evaluated = evaluate_offer(ordinary_sale, config, catalog)
    assert evaluated.verdict == Verdict.WAIT

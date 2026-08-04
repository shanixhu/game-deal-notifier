from dataclasses import replace
from datetime import datetime, timedelta, timezone

from deal_scout.models import Offer, OfferType, Store, Verdict
from deal_scout.scoring import adjusted_review_percent, evaluate_offer, score_quality


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
    assert strong_score > weak_score + 35


def test_review_label_with_tiny_sample_is_not_enough(config, catalog) -> None:
    tiny = make_offer(
        title="Unknown Tiny Indie",
        review_percent=100,
        review_count=12,
        current_price_minor=4900,
        normal_price_minor=49900,
        discount_percent=90,
    )
    assert adjusted_review_percent(tiny) < 75
    assert evaluate_offer(tiny, config, catalog).verdict == Verdict.SKIP


def test_unknown_epic_giveaway_is_not_auto_recommended(config, catalog) -> None:
    giveaway = make_offer(
        title="Unknown Weekly Giveaway",
        store=Store.EPIC,
        current_price_minor=0,
        normal_price_minor=149900,
        discount_percent=100,
        offer_type=OfferType.FREE_TO_KEEP,
        review_percent=None,
        review_count=None,
        developer="Unknown Studio",
        publisher="Unknown Publisher",
    )
    assert evaluate_offer(giveaway, config, catalog).verdict == Verdict.SKIP


def test_respected_giveaway_is_claim_now(config, catalog) -> None:
    control = make_offer(
        title="Control Ultimate Edition",
        store=Store.EPIC,
        current_price_minor=0,
        normal_price_minor=249900,
        discount_percent=100,
        offer_type=OfferType.FREE_TO_KEEP,
        review_percent=None,
        review_count=None,
        developer="Remedy Entertainment",
        publisher="505 Games",
    )
    assert evaluate_offer(control, config, catalog).verdict == Verdict.CLAIM_NOW


def test_ea_deep_discount_is_not_missed(config, catalog) -> None:
    ea_deal = make_offer(
        title="Need for Speed Heat",
        current_price_minor=17900,
        normal_price_minor=179900,
        discount_percent=90,
        review_percent=84,
        review_count=110000,
        publisher="Electronic Arts",
        developer="Ghost Games",
        genres=("Racing", "Open World"),
        metadata={"sale_event_name": "Electronic Arts sale", "sale_event_size": 5},
    )
    evaluated = evaluate_offer(ea_deal, config, catalog)
    assert evaluated.verdict == Verdict.BUY_NOW
    assert "Electronic Arts sale" in evaluated.deal_reason


def test_soundtrack_is_skipped(config, catalog) -> None:
    soundtrack = make_offer(title="SIGNALIS Soundtrack", offer_type=OfferType.DLC, is_dlc=True)
    assert evaluate_offer(soundtrack, config, catalog).verdict == Verdict.SKIP


def test_wait_alerts_are_off_by_default(config, catalog) -> None:
    ordinary_sale = make_offer(
        title="Disco Elysium - The Final Cut",
        current_price_minor=99900,
        normal_price_minor=149900,
        discount_percent=33,
        review_percent=92,
        review_count=80000,
    )
    assert evaluate_offer(ordinary_sale, config, catalog).verdict == Verdict.SKIP


def test_wait_can_be_enabled_explicitly(config, catalog) -> None:
    enabled = replace(config, filters=replace(config.filters, send_wait_verdicts=True, max_wait_alerts_per_run=1))
    ordinary_sale = make_offer(
        title="Disco Elysium - The Final Cut",
        current_price_minor=99900,
        normal_price_minor=149900,
        discount_percent=33,
        review_percent=92,
        review_count=80000,
    )
    assert evaluate_offer(ordinary_sale, enabled, catalog).verdict == Verdict.WAIT


def test_expired_offer_is_never_alerted(config, catalog) -> None:
    now = datetime(2026, 8, 5, tzinfo=timezone.utc)
    expired = make_offer(end_at=now - timedelta(minutes=1))
    evaluated = evaluate_offer(expired, config, catalog, now)
    assert evaluated.verdict == Verdict.SKIP
    assert "Expired" in evaluated.deal_reason


def test_upcoming_offer_is_not_sent_early(config, catalog) -> None:
    now = datetime(2026, 8, 5, tzinfo=timezone.utc)
    upcoming = make_offer(start_at=now + timedelta(hours=2), end_at=now + timedelta(days=3))
    evaluated = evaluate_offer(upcoming, config, catalog, now)
    assert evaluated.verdict == Verdict.SKIP

from datetime import datetime, timedelta, timezone

from deal_scout.models import Offer, OfferType, Store, Verdict
from deal_scout.state import StateStore


NOW = datetime(2026, 8, 2, 12, tzinfo=timezone.utc)


def offer(**overrides) -> Offer:
    values = dict(
        external_id="x",
        title="Control Ultimate Edition",
        store=Store.EPIC,
        url="https://store.epicgames.com/",
        current_price_minor=49900,
        normal_price_minor=249900,
        discount_percent=80,
        offer_type=OfferType.PAID_DISCOUNT,
        end_at=NOW + timedelta(days=3),
        verdict=Verdict.BUY_NOW,
    )
    values.update(overrides)
    return Offer(**values)


def test_first_offer_sends_and_unchanged_duplicate_does_not(tmp_path) -> None:
    state = StateStore(tmp_path / "state.json")
    current = offer()
    assert state.should_send(current, NOW)[0]
    state.record_sent(current, NOW)
    assert not state.should_send(current, NOW + timedelta(hours=2))[0]


def test_price_drop_sends_again(tmp_path) -> None:
    state = StateStore(tmp_path / "state.json")
    state.record_sent(offer(), NOW)
    lower = offer(current_price_minor=29900, discount_percent=88)
    should, reason = state.should_send(lower, NOW + timedelta(hours=1))
    assert should
    assert "price" in reason


def test_becoming_free_sends_again(tmp_path) -> None:
    state = StateStore(tmp_path / "state.json")
    state.record_sent(offer(), NOW)
    free = offer(
        current_price_minor=0,
        discount_percent=100,
        offer_type=OfferType.FREE_TO_KEEP,
        verdict=Verdict.CLAIM_NOW,
    )
    should, reason = state.should_send(free, NOW + timedelta(hours=1))
    assert should
    assert "free" in reason


def test_better_store_offer_sends(tmp_path) -> None:
    state = StateStore(tmp_path / "state.json")
    state.record_sent(offer(store=Store.STEAM), NOW)
    better = offer(store=Store.GOG, current_price_minor=39900)
    should, reason = state.should_send(better, NOW + timedelta(hours=1))
    assert should
    assert "price" in reason or "store" in reason


def test_return_after_inactive_sends(tmp_path) -> None:
    state = StateStore(tmp_path / "state.json")
    state.record_sent(offer(), NOW)
    state.mark_inactive(set(), NOW + timedelta(days=4))
    should, reason = state.should_send(offer(), NOW + timedelta(days=30))
    assert should
    assert "returned" in reason

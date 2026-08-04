from datetime import datetime, timedelta, timezone
import json

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


def test_deadline_extension_updates_silently(tmp_path) -> None:
    state = StateStore(tmp_path / "state.json")
    state.record_sent(offer(), NOW)
    extended = offer(end_at=NOW + timedelta(days=5))
    should, reason = state.should_send(extended, NOW + timedelta(hours=2))
    assert not should
    assert "ongoing" in reason


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
    free = offer(current_price_minor=0, discount_percent=100, offer_type=OfferType.FREE_TO_KEEP, verdict=Verdict.CLAIM_NOW)
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


def test_missing_offer_uses_grace_period_before_inactive(tmp_path) -> None:
    state = StateStore(tmp_path / "state.json")
    state.record_sent(offer(end_at=None), NOW)
    state.finish_scan(seen_keys=set(), successful_stores={Store.EPIC.value}, now=NOW + timedelta(days=1), absence_grace_hours=168)
    assert state.offers[offer().key]["active"] is True
    state.finish_scan(seen_keys=set(), successful_stores={Store.EPIC.value}, now=NOW + timedelta(days=9), absence_grace_hours=168)
    assert state.offers[offer().key]["active"] is False


def test_return_after_inactive_sends(tmp_path) -> None:
    state = StateStore(tmp_path / "state.json")
    state.record_sent(offer(), NOW)
    state.mark_inactive(set(), NOW + timedelta(days=4))
    should, reason = state.should_send(offer(), NOW + timedelta(days=30))
    assert should
    assert "sale again" in reason


def test_schema_one_state_is_migrated(tmp_path) -> None:
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"schema_version": 1, "offers": {"control": {"active": True}}}), encoding="utf-8")
    state = StateStore(path)
    state.load()
    assert state.data["schema_version"] == 2
    assert state.offers["control"]["missing_since"] is None


def test_stale_feed_after_deadline_does_not_create_duplicate(tmp_path) -> None:
    state = StateStore(tmp_path / "state.json")
    original = offer(end_at=NOW + timedelta(hours=1))
    state.record_sent(original, NOW)
    should, reason = state.should_send(original, NOW + timedelta(hours=4))
    assert not should
    assert "same ongoing" in reason


def test_explicit_new_start_after_old_end_is_new_sale(tmp_path) -> None:
    state = StateStore(tmp_path / "state.json")
    original = offer(start_at=NOW - timedelta(days=1), end_at=NOW + timedelta(hours=1))
    state.record_sent(original, NOW)
    later = offer(
        start_at=NOW + timedelta(days=8),
        end_at=NOW + timedelta(days=12),
    )
    should, reason = state.should_send(later, NOW + timedelta(days=8, hours=1))
    assert should
    assert "new sale episode" in reason

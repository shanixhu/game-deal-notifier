from __future__ import annotations

from dataclasses import replace
import json

from deal_scout.http import HttpClient
from deal_scout.pipeline import DealPipeline
from deal_scout.sample_data import sample_offers
from deal_scout.state import StateStore


class FakeSender:
    def __init__(self) -> None:
        self.sent = []
        self.messages = 0

    def send_offers(self, offers, config) -> None:
        self.messages += 1
        self.sent.extend(offers)


def test_live_pipeline_batches_and_suppresses_unchanged_duplicates(tmp_path, config, catalog) -> None:
    pipeline = DealPipeline(config=config, http=HttpClient(), catalog=catalog)
    state_path = tmp_path / "state.json"
    sender = FakeSender()

    first = pipeline.run_live(sample_offers(), state=StateStore(state_path), sender=sender)
    assert first.sent == 5
    assert len(sender.sent) == 5
    assert sender.messages == 2

    second_sender = FakeSender()
    second = pipeline.run_live(sample_offers(), state=StateStore(state_path), sender=second_sender)
    assert second.sent == 0
    assert second.unchanged == 5
    assert second_sender.sent == []


def test_one_missing_scan_does_not_create_fake_new_sale(tmp_path, config, catalog) -> None:
    pipeline = DealPipeline(config=config, http=HttpClient(), catalog=catalog)
    state_path = tmp_path / "state.json"
    pipeline.run_live(sample_offers(), state=StateStore(state_path), sender=FakeSender())

    pipeline.run_live(
        [],
        state=StateStore(state_path),
        sender=FakeSender(),
        successful_stores={"Steam", "Epic Games Store", "GOG"},
    )

    returning_sender = FakeSender()
    result = pipeline.run_live(sample_offers(), state=StateStore(state_path), sender=returning_sender)
    assert result.sent == 0
    assert result.unchanged == 5


def test_inactive_offer_can_alert_in_a_future_sale(tmp_path, config, catalog) -> None:
    pipeline = DealPipeline(config=config, http=HttpClient(), catalog=catalog)
    state_path = tmp_path / "state.json"
    pipeline.run_live(sample_offers(), state=StateStore(state_path), sender=FakeSender())

    state = StateStore(state_path)
    state.load()
    state.mark_inactive(set())
    state.save()

    returning_sender = FakeSender()
    result = pipeline.run_live(sample_offers(), state=StateStore(state_path), sender=returning_sender)
    assert result.sent == 5
    assert len(returning_sender.sent) == 5


def test_dry_run_separates_publisher_event_from_general_deals(tmp_path, config, catalog) -> None:
    pipeline = DealPipeline(config=config, http=HttpClient(), catalog=catalog)
    report_path = tmp_path / "scan.json"
    result = pipeline.dry_run(sample_offers(), payload_output=report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert result.qualifying == 5
    assert len(report["selected"]) == 2
    headings = [payload.get("content", "") for payload in report["selected"]]
    assert any("Electronic Arts sale" in heading for heading in headings)
    assert any("2 worthwhile PC deals" in heading for heading in headings)


def test_unchanged_top_deal_does_not_hide_a_new_lower_ranked_deal(tmp_path, config, catalog) -> None:
    one_alert_config = replace(
        config, filters=replace(config.filters, max_alerts_per_run=1)
    )
    pipeline = DealPipeline(config=one_alert_config, http=HttpClient(), catalog=catalog)
    state_path = tmp_path / "state.json"
    top = sample_offers()[0]
    pipeline.run_live([top], state=StateStore(state_path), sender=FakeSender())

    new_deal = sample_offers()[1]
    sender = FakeSender()
    result = pipeline.run_live(
        [top, new_deal], state=StateStore(state_path), sender=sender
    )
    assert result.sent == 1
    assert [offer.title for offer in sender.sent] == ["SIGNALIS"]


def test_alert_overflow_is_not_dripped_into_later_runs(tmp_path, config, catalog) -> None:
    two_alert_config = replace(
        config, filters=replace(config.filters, max_alerts_per_run=2)
    )
    pipeline = DealPipeline(config=two_alert_config, http=HttpClient(), catalog=catalog)
    state_path = tmp_path / "state.json"

    first_sender = FakeSender()
    first = pipeline.run_live(
        sample_offers(), state=StateStore(state_path), sender=first_sender
    )
    assert first.sent == 2

    second_sender = FakeSender()
    second = pipeline.run_live(
        sample_offers(), state=StateStore(state_path), sender=second_sender
    )
    assert second.sent == 0
    assert second_sender.sent == []

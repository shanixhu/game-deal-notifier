from __future__ import annotations

from deal_scout.http import HttpClient
from deal_scout.pipeline import DealPipeline
from deal_scout.sample_data import sample_offers
from deal_scout.state import StateStore


class FakeSender:
    def __init__(self) -> None:
        self.sent = []

    def send_offer(self, offer, config) -> None:
        self.sent.append(offer)


def test_live_pipeline_suppresses_unchanged_duplicates(tmp_path, config, catalog) -> None:
    pipeline = DealPipeline(config=config, http=HttpClient(), catalog=catalog)
    state_path = tmp_path / "state.json"
    sender = FakeSender()

    first = pipeline.run_live(
        sample_offers(), state=StateStore(state_path), sender=sender
    )
    assert first.sent == 2
    assert len(sender.sent) == 2

    second_sender = FakeSender()
    second = pipeline.run_live(
        sample_offers(), state=StateStore(state_path), sender=second_sender
    )
    assert second.sent == 0
    assert second.unchanged == 2
    assert second_sender.sent == []


def test_pipeline_realerts_when_offer_returns_after_inactive(tmp_path, config, catalog) -> None:
    pipeline = DealPipeline(config=config, http=HttpClient(), catalog=catalog)
    state_path = tmp_path / "state.json"
    first_sender = FakeSender()
    pipeline.run_live(sample_offers(), state=StateStore(state_path), sender=first_sender)

    empty_sender = FakeSender()
    pipeline.run_live([], state=StateStore(state_path), sender=empty_sender)

    returning_sender = FakeSender()
    result = pipeline.run_live(
        sample_offers(), state=StateStore(state_path), sender=returning_sender
    )
    assert result.sent == 2
    assert len(returning_sender.sent) == 2

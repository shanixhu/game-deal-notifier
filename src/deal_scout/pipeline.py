from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
import json
import logging

from .adapters import EpicAdapter, GogAdapter, SteamAdapter
from .config import AppConfig
from .curation import ReputationCatalog
from .discord import DiscordWebhookSender, build_webhook_payload
from .http import HttpClient
from .models import Offer, VERDICT_RANK, Verdict
from .scoring import evaluate_offer
from .state import StateStore


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class PipelineResult:
    fetched: int = 0
    qualifying: int = 0
    sent: int = 0
    unchanged: int = 0
    adapter_failures: int = 0
    delivery_failures: int = 0


class DealPipeline:
    def __init__(
        self,
        *,
        config: AppConfig,
        http: HttpClient,
        catalog: ReputationCatalog,
    ) -> None:
        self.config = config
        self.http = http
        self.catalog = catalog

    def fetch_live_offers(self) -> tuple[list[Offer], int, int]:
        adapters = []
        if self.config.stores.steam:
            adapters.append(SteamAdapter(self.http, self.config))
        if self.config.stores.epic:
            adapters.append(EpicAdapter(self.http, self.config))
        if self.config.stores.gog:
            adapters.append(GogAdapter(self.http, self.config))

        offers: list[Offer] = []
        successes = 0
        failures = 0
        for adapter in adapters:
            adapter_name = adapter.__class__.__name__
            try:
                store_offers = adapter.fetch_offers()
                offers.extend(store_offers)
                successes += 1
                LOGGER.info("%s completed with %d offers", adapter_name, len(store_offers))
            except Exception:
                failures += 1
                LOGGER.exception("%s failed; continuing with other stores", adapter_name)
        return offers, successes, failures

    def evaluate(self, offers: Iterable[Offer], now: datetime | None = None) -> list[Offer]:
        now = now or datetime.now(timezone.utc)
        evaluated = [evaluate_offer(offer, self.config, self.catalog, now) for offer in offers]
        best_by_title: dict[str, Offer] = {}
        for offer in evaluated:
            existing = best_by_title.get(offer.key)
            if existing is None or _offer_sort_key(offer) > _offer_sort_key(existing):
                best_by_title[offer.key] = offer
        return list(best_by_title.values())

    def select_alerts(self, evaluated: Iterable[Offer]) -> list[Offer]:
        candidates = [offer for offer in evaluated if offer.verdict != Verdict.SKIP]
        candidates.sort(key=_offer_sort_key, reverse=True)
        selected: list[Offer] = []
        wait_count = 0
        for offer in candidates:
            if offer.verdict == Verdict.WAIT:
                if wait_count >= self.config.filters.max_wait_alerts_per_run:
                    continue
                wait_count += 1
            selected.append(offer)
            if len(selected) >= self.config.filters.max_alerts_per_run:
                break
        return selected

    def dry_run(
        self,
        offers: Iterable[Offer],
        *,
        payload_output: str | Path | None = None,
    ) -> PipelineResult:
        offers_list = list(offers)
        evaluated = self.evaluate(offers_list)
        selected = self.select_alerts(evaluated)
        payloads = [build_webhook_payload(offer, self.config) for offer in selected]
        rendered = json.dumps(payloads, indent=2, ensure_ascii=False)
        print(rendered)
        if payload_output:
            path = Path(payload_output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered + "\n", encoding="utf-8")
            LOGGER.info("Wrote %d inspected payloads to %s", len(payloads), path)
        return PipelineResult(
            fetched=len(offers_list),
            qualifying=len(selected),
        )

    def run_live(
        self,
        offers: Iterable[Offer],
        *,
        state: StateStore,
        sender: DiscordWebhookSender,
        adapter_failures: int = 0,
    ) -> PipelineResult:
        now = datetime.now(timezone.utc)
        offers_list = list(offers)
        evaluated = self.evaluate(offers_list, now)
        qualifying_all = [offer for offer in evaluated if offer.verdict != Verdict.SKIP]
        selected = self.select_alerts(evaluated)
        result = PipelineResult(
            fetched=len(offers_list),
            qualifying=len(selected),
            adapter_failures=adapter_failures,
        )
        state.load()
        seen_keys = {offer.key for offer in qualifying_all}
        selected_keys = {offer.key for offer in selected}

        # Check alert eligibility before marking an old inactive offer as seen;
        # otherwise a returning promotion with the same price would be suppressed.
        for offer in selected:
            should_send, reason = state.should_send(offer, now)
            if not should_send:
                result.unchanged += 1
                state.mark_seen_without_alert(offer, now)
                LOGGER.info("Suppressing %s: %s", offer.title, reason)
                continue
            LOGGER.info("Sending %s because %s", offer.title, reason)
            try:
                sender.send_offer(offer, self.config)
            except Exception:
                result.delivery_failures += 1
                LOGGER.exception("Discord delivery failed for %s; continuing", offer.title)
                continue
            state.record_sent(offer, now)
            result.sent += 1

        for offer in qualifying_all:
            if offer.key not in selected_keys:
                state.mark_seen_without_alert(offer, now)

        state.mark_inactive(seen_keys, now)
        state.prune(now)
        state.save()
        return result


def _offer_sort_key(offer: Offer) -> tuple[int, float, float, int, int]:
    price = offer.current_price_minor
    return (
        VERDICT_RANK[offer.verdict],
        offer.deal_score,
        offer.quality_score,
        offer.price_drop_percent or 0,
        -(price if price is not None else 10**12),
    )

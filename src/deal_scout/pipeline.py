from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
import json
import logging

from .adapters import EpicAdapter, GogAdapter, SteamAdapter
from .config import AppConfig
from .curation import ReputationCatalog
from .discord import (
    DiscordWebhookSender,
    build_digest_payload,
    build_webhook_payload,
    discord_offer_batches,
)
from .http import HttpClient
from .models import Offer, OfferType, Store, VERDICT_RANK, Verdict, canonical_title
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

    def fetch_live_offers(self) -> tuple[list[Offer], set[str], int]:
        adapters = []
        if self.config.stores.steam:
            adapters.append((Store.STEAM.value, SteamAdapter(self.http, self.config)))
        if self.config.stores.epic:
            adapters.append((Store.EPIC.value, EpicAdapter(self.http, self.config)))
        if self.config.stores.gog:
            adapters.append((Store.GOG.value, GogAdapter(self.http, self.config)))

        offers: list[Offer] = []
        successful_stores: set[str] = set()
        failures = 0
        for store_name, adapter in adapters:
            adapter_name = adapter.__class__.__name__
            try:
                store_offers = adapter.fetch_offers()
                offers.extend(store_offers)
                successful_stores.add(store_name)
                LOGGER.info("%s completed with %d offers", adapter_name, len(store_offers))
            except Exception:
                failures += 1
                LOGGER.exception("%s failed; continuing with other stores", adapter_name)
        return offers, successful_stores, failures

    def evaluate(self, offers: Iterable[Offer], now: datetime | None = None) -> list[Offer]:
        now = now or datetime.now(timezone.utc)
        offers_list = list(offers)
        self._annotate_sale_events(offers_list)
        evaluated = [evaluate_offer(offer, self.config, self.catalog, now) for offer in offers_list]
        best_by_title: dict[str, Offer] = {}
        for offer in evaluated:
            existing = best_by_title.get(offer.key)
            if existing is None or _offer_sort_key(offer) > _offer_sort_key(existing):
                best_by_title[offer.key] = offer
        return list(best_by_title.values())

    def ranked_alert_candidates(self, evaluated: Iterable[Offer]) -> list[Offer]:
        candidates = [offer for offer in evaluated if offer.verdict != Verdict.SKIP]
        candidates.sort(key=_offer_sort_key, reverse=True)
        ranked: list[Offer] = []
        wait_count = 0
        for offer in candidates:
            if offer.verdict == Verdict.WAIT:
                if wait_count >= self.config.filters.max_wait_alerts_per_run:
                    continue
                wait_count += 1
            ranked.append(offer)
        return ranked

    def select_alerts(self, evaluated: Iterable[Offer]) -> list[Offer]:
        limit = max(0, self.config.filters.max_alerts_per_run)
        return self.ranked_alert_candidates(evaluated)[:limit]

    def dry_run(
        self,
        offers: Iterable[Offer],
        *,
        payload_output: str | Path | None = None,
    ) -> PipelineResult:
        offers_list = list(offers)
        evaluated = self.evaluate(offers_list)
        selected = self.select_alerts(evaluated)
        if self.config.alerts.batch_alerts and selected:
            payloads = [
                build_digest_payload(batch, self.config)
                for group in self._notification_groups(selected)
                for batch in discord_offer_batches(group, self.config)
            ]
        else:
            payloads = [build_webhook_payload(offer, self.config) for offer in selected]
        rejected = sorted(
            (offer for offer in evaluated if offer.verdict == Verdict.SKIP),
            key=lambda offer: (offer.deal_score, offer.quality_score),
            reverse=True,
        )[:12]
        report = {
            "selected": payloads,
            "top_rejected": [
                {
                    "title": offer.title,
                    "store": offer.store.value,
                    "discount_percent": offer.price_drop_percent,
                    "quality_score": round(offer.quality_score, 1),
                    "deal_score": round(offer.deal_score, 1),
                    "reason": offer.deal_reason,
                }
                for offer in rejected
            ],
        }
        rendered = json.dumps(report, indent=2, ensure_ascii=False)
        print(rendered)
        if payload_output:
            path = Path(payload_output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered + "\n", encoding="utf-8")
            LOGGER.info("Wrote scan report to %s", path)
        self._log_decisions(evaluated)
        return PipelineResult(fetched=len(offers_list), qualifying=len(selected))

    def run_live(
        self,
        offers: Iterable[Offer],
        *,
        state: StateStore,
        sender: DiscordWebhookSender,
        successful_stores: Iterable[str] | None = None,
        adapter_failures: int = 0,
    ) -> PipelineResult:
        now = datetime.now(timezone.utc)
        offers_list = list(offers)
        evaluated = self.evaluate(offers_list, now)
        candidates = self.ranked_alert_candidates(evaluated)
        result = PipelineResult(
            fetched=len(offers_list),
            qualifying=len(candidates),
            adapter_failures=adapter_failures,
        )
        state.load()
        seen_keys = {offer.key for offer in evaluated}
        candidate_keys = {offer.key for offer in candidates}
        pending: list[Offer] = []
        alert_cap = max(0, self.config.filters.max_alerts_per_run)

        # Check duplicate state before applying the per-run cap. Otherwise unchanged
        # top-ranked games could hide a genuinely new offer ranked just below them.
        # Qualifying overflow is remembered silently so a large publisher sale does not
        # drip another batch of old deals into Discord on every scheduled run.
        for offer in candidates:
            should_send, reason = state.should_send(offer, now)
            if not should_send:
                result.unchanged += 1
                state.refresh_seen(offer, now)
                LOGGER.info("Muted %s: %s", offer.title, reason)
                continue
            if len(pending) < alert_cap:
                pending.append(offer)
                LOGGER.info("Queued %s because %s", offer.title, reason)
            else:
                state.record_suppressed(offer, now)
                LOGGER.info(
                    "Held back %s for this sale episode because the %d-alert cap was reached",
                    offer.title,
                    alert_cap,
                )

        # Refresh already-known games even if their current score falls below the alert
        # threshold. Their sale is still present, so absence must not create a fake new episode.
        for offer in evaluated:
            if offer.key not in candidate_keys:
                state.refresh_seen(offer, now)

        for message_group in self._notification_groups(pending):
            for chunk in discord_offer_batches(message_group, self.config):
                try:
                    if hasattr(sender, "send_offers"):
                        sender.send_offers(chunk, self.config)
                    else:
                        for offer in chunk:
                            sender.send_offer(offer, self.config)
                except Exception:
                    result.delivery_failures += len(chunk)
                    LOGGER.exception("Discord delivery failed for a %d-offer digest", len(chunk))
                    continue
                for offer in chunk:
                    state.record_sent(offer, now)
                    result.sent += 1

        successful = set(successful_stores or {offer.store.value for offer in offers_list})
        state.finish_scan(
            seen_keys=seen_keys,
            successful_stores=successful,
            now=now,
            absence_grace_hours=self.config.filters.absence_grace_hours,
        )
        state.prune(now)
        state.save()
        self._log_decisions(evaluated)
        return result


    def _notification_groups(self, offers: list[Offer]) -> list[list[Offer]]:
        if not offers:
            return []
        event_groups: dict[str, list[Offer]] = defaultdict(list)
        remainder: list[Offer] = []
        for offer in offers:
            if offer.sale_event_name:
                event_groups[offer.sale_event_name].append(offer)
            else:
                remainder.append(offer)

        groups: list[list[Offer]] = []
        for _, group in sorted(
            event_groups.items(),
            key=lambda item: max((_offer_sort_key(offer) for offer in item[1])),
            reverse=True,
        ):
            if len(group) >= self.config.filters.publisher_event_min_offers:
                group.sort(key=_offer_sort_key, reverse=True)
                groups.append(group)
            else:
                remainder.extend(group)
        if remainder:
            remainder.sort(key=_offer_sort_key, reverse=True)
            groups.append(remainder)
        return groups

    def _annotate_sale_events(self, offers: list[Offer]) -> None:
        groups: dict[tuple[str, str], list[Offer]] = defaultdict(list)
        for offer in offers:
            if offer.is_dlc or offer.is_demo or offer.is_free_to_play:
                continue
            if offer.offer_type not in {OfferType.PAID_DISCOUNT, OfferType.BUNDLE}:
                continue
            if (offer.price_drop_percent or 0) < self.config.filters.publisher_event_min_discount:
                continue
            watched = offer.metadata.get("watched_publishers") or []
            publisher = str(watched[0]).strip() if watched else (offer.publisher or "").strip()
            if publisher:
                groups[(offer.store.value, canonical_title(publisher))].append(offer)

        for group in groups.values():
            if len(group) < self.config.filters.publisher_event_min_offers:
                continue
            watched = group[0].metadata.get("watched_publishers") or []
            publisher = str(watched[0]) if watched else (group[0].publisher or "Publisher")
            event_name = f"{publisher} sale"
            for offer in group:
                offer.metadata["sale_event_name"] = event_name
                offer.metadata["sale_event_size"] = len(group)

    @staticmethod
    def _log_decisions(evaluated: Iterable[Offer]) -> None:
        ordered = sorted(
            evaluated,
            key=lambda offer: (VERDICT_RANK[offer.verdict], offer.deal_score, offer.quality_score),
            reverse=True,
        )
        for offer in ordered[:20]:
            LOGGER.info(
                "Decision %-22s q=%5.1f d=%5.1f discount=%s title=%s reason=%s",
                offer.verdict.value,
                offer.quality_score,
                offer.deal_score,
                offer.price_drop_percent,
                offer.title,
                offer.deal_reason,
            )


def _offer_sort_key(offer: Offer) -> tuple[int, float, float, int, int, int]:
    price = offer.current_price_minor
    return (
        VERDICT_RANK[offer.verdict],
        offer.deal_score,
        offer.quality_score,
        offer.sale_event_size,
        offer.price_drop_percent or 0,
        -(price if price is not None else 10**12),
    )

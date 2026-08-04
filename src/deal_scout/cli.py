from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import logging
import os
import sys

from .config import load_config
from .curation import ReputationCatalog
from .discord import DiscordWebhookSender, build_test_payload
from .http import HttpClient
from .pipeline import DealPipeline
from .sample_data import sample_offers
from .state import StateStore


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Find worthwhile PC game deals and alert Discord.")
    parser.add_argument("--mode", choices=("live", "dry-run", "test"), default="dry-run")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--state", default="state/deals.json")
    parser.add_argument("--sample-data", action="store_true")
    parser.add_argument("--payload-output")
    parser.add_argument("--log-level", default="INFO")
    return parser


def _write_github_summary(title: str, lines: list[str]) -> None:
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if not target:
        return
    path = Path(target)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"## {title}\n\n")
        for line in lines:
            handle.write(f"- {line}\n")
        handle.write("\n")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("deal_scout")
    config = load_config(args.config)
    http = HttpClient()
    catalog = ReputationCatalog.load_default()
    pipeline = DealPipeline(config=config, http=http, catalog=catalog)

    if args.mode == "test":
        webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
        if not webhook:
            logger.error("DISCORD_WEBHOOK_URL is required for test mode")
            return 2
        sender = DiscordWebhookSender(webhook, http)
        sender.send_payload(build_test_payload(config))
        logger.info("Test notification sent successfully; no state was changed")
        _write_github_summary("Game Deal Notifier test", ["Discord webhook accepted the test message", "No store data or state file was changed"])
        return 0

    if args.sample_data:
        offers = sample_offers()
        successful_stores, failures = {offer.store.value for offer in offers}, 0
        logger.info("Using deterministic sample data; no store network calls will run")
    else:
        offers, successful_stores, failures = pipeline.fetch_live_offers()
        if not successful_stores:
            logger.error("All enabled store adapters failed; refusing to change state")
            return 3

    if args.mode == "dry-run":
        result = pipeline.dry_run(offers, payload_output=args.payload_output)
        logger.info(
            "Dry run complete: fetched=%d qualifying=%d adapter_failures=%d",
            result.fetched,
            result.qualifying,
            failures,
        )
        _write_github_summary(
            "Game Deal Notifier dry run",
            [
                f"Offers inspected: {result.fetched}",
                f"Deals selected: {result.qualifying}",
                f"Store adapters failed: {failures}",
                "No Discord alerts were sent and no state was changed",
            ],
        )
        return 0

    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook:
        logger.error("DISCORD_WEBHOOK_URL is required for live mode")
        return 2
    sender = DiscordWebhookSender(webhook, http)
    result = pipeline.run_live(
        offers,
        state=StateStore(args.state),
        sender=sender,
        successful_stores=successful_stores,
        adapter_failures=failures,
    )
    logger.info(
        "Live run complete: fetched=%d qualifying=%d sent=%d unchanged=%d "
        "adapter_failures=%d delivery_failures=%d",
        result.fetched,
        result.qualifying,
        result.sent,
        result.unchanged,
        result.adapter_failures,
        result.delivery_failures,
    )
    _write_github_summary(
        "Game Deal Notifier live scan",
        [
            f"Offers inspected: {result.fetched}",
            f"Qualifying deals: {result.qualifying}",
            f"New alerts sent: {result.sent}",
            f"Ongoing offers muted: {result.unchanged}",
            f"Store adapter failures: {result.adapter_failures}",
            f"Discord delivery failures: {result.delivery_failures}",
        ],
    )
    return 1 if result.delivery_failures else 0


if __name__ == "__main__":
    sys.exit(main())

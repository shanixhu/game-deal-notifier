from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
import json
import logging
import os
import tempfile

from .models import Offer, VERDICT_RANK, Verdict, ensure_utc


LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 2


class StateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.data: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "offers": {}}

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(loaded.get("offers"), dict):
                raise ValueError("State file has no offers object")
            version = int(loaded.get("schema_version", 1))
            if version == 1:
                loaded = self._migrate_v1(loaded)
            elif version != SCHEMA_VERSION:
                raise ValueError(f"Unsupported state schema {version}")
            self.data = loaded
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Could not load state file {self.path}: {exc}") from exc

    @property
    def offers(self) -> dict[str, dict[str, Any]]:
        return self.data.setdefault("offers", {})

    def should_send(self, offer: Offer, now: datetime | None = None) -> tuple[bool, str]:
        now = ensure_utc(now or datetime.now(timezone.utc))
        previous = self.offers.get(offer.key)
        current = offer.state_snapshot(now)
        if previous is None:
            return True, "first qualifying alert"
        if not previous.get("active", True):
            return True, "the game is on sale again after the previous offer ended"

        old_end = _parse_datetime(previous.get("end_at"))
        current_start = _parse_datetime(current.get("start_at"))
        if old_end and current_start and current_start >= old_end:
            return True, "a new sale episode started after the previous offer ended"

        if previous.get("fingerprint") == current.get("fingerprint"):
            return False, "same ongoing offer"

        old_price = previous.get("current_price_minor")
        new_price = current.get("current_price_minor")
        if new_price == 0 and old_price != 0:
            return True, "the game became free"
        if isinstance(old_price, int) and isinstance(new_price, int) and new_price < old_price:
            return True, "the price dropped further"
        if current.get("offer_type") != previous.get("offer_type"):
            return True, "the offer type changed"

        old_discount = previous.get("discount_percent")
        new_discount = current.get("discount_percent")
        if (
            isinstance(old_discount, int)
            and isinstance(new_discount, int)
            and new_discount >= old_discount + 10
        ):
            return True, "the discount improved materially"

        if (
            current.get("store") != previous.get("store")
            and isinstance(new_price, int)
            and (not isinstance(old_price, int) or new_price < old_price)
        ):
            return True, "a better store offer appeared"

        if current.get("historical_low") is True and previous.get("historical_low") is not True:
            return True, "a verified historical low was reached"
        if (
            current.get("near_historical_low") is True
            and previous.get("near_historical_low") is not True
        ):
            return True, "a verified near-historical low was reached"

        old_verdict = _parse_verdict(previous.get("verdict"))
        if VERDICT_RANK[offer.verdict] > VERDICT_RANK[old_verdict]:
            return True, "the recommendation became stronger"

        # Deadline corrections and extensions are useful in the message/state but are
        # not worth another Discord alert during the same sale episode.
        return False, "the ongoing offer changed only in a non-alert-worthy way"

    def record_sent(self, offer: Offer, now: datetime | None = None) -> None:
        now = ensure_utc(now or datetime.now(timezone.utc))
        previous = self.offers.get(offer.key, {})
        snapshot = offer.state_snapshot(now)
        snapshot["first_seen_at"] = previous.get("first_seen_at") or now.isoformat()
        snapshot["first_sent_at"] = previous.get("first_sent_at") or now.isoformat()
        snapshot["last_sent_at"] = now.isoformat()
        snapshot["suppressed"] = False
        snapshot["missing_since"] = None
        self.offers[offer.key] = snapshot

    def record_suppressed(self, offer: Offer, now: datetime | None = None) -> None:
        """Remember qualifying overflow without dripping it into later scheduled runs."""
        now = ensure_utc(now or datetime.now(timezone.utc))
        previous = self.offers.get(offer.key, {})
        snapshot = offer.state_snapshot(now)
        snapshot["first_seen_at"] = previous.get("first_seen_at") or now.isoformat()
        if previous.get("first_sent_at"):
            snapshot["first_sent_at"] = previous["first_sent_at"]
        if previous.get("last_sent_at"):
            snapshot["last_sent_at"] = previous["last_sent_at"]
        snapshot["suppressed"] = True
        snapshot["missing_since"] = None
        self.offers[offer.key] = snapshot

    def refresh_seen(self, offer: Offer, now: datetime | None = None) -> None:
        now = ensure_utc(now or datetime.now(timezone.utc))
        previous = self.offers.get(offer.key)
        if not previous:
            return
        snapshot = offer.state_snapshot(now)
        for field in ("first_seen_at", "first_sent_at", "last_sent_at", "suppressed"):
            if field in previous:
                snapshot[field] = previous[field]
        # Avoid a state-file commit on every scheduled run. last_seen_at only moves
        # when an offer returns after being missing or its meaningful snapshot changes.
        unchanged = (
            previous.get("fingerprint") == snapshot.get("fingerprint")
            and previous.get("end_at") == snapshot.get("end_at")
            and previous.get("missing_since") in (None, "")
            and previous.get("active", True)
        )
        if unchanged:
            return
        snapshot["last_seen_at"] = now.isoformat()
        snapshot["missing_since"] = None
        self.offers[offer.key] = snapshot

    def finish_scan(
        self,
        *,
        seen_keys: set[str],
        successful_stores: Iterable[str],
        now: datetime | None = None,
        absence_grace_hours: int = 168,
    ) -> None:
        now = ensure_utc(now or datetime.now(timezone.utc))
        successful = {str(store) for store in successful_stores}
        grace = timedelta(hours=max(1, absence_grace_hours))
        for key, entry in self.offers.items():
            if key in seen_keys:
                if not entry.get("active", True) or entry.get("missing_since"):
                    entry["active"] = True
                    entry["last_seen_at"] = now.isoformat()
                    entry["missing_since"] = None
                    entry.pop("inactive_since", None)
                continue
            if entry.get("store") not in successful:
                continue

            end_at = _parse_datetime(entry.get("end_at"))
            if end_at and end_at <= now:
                entry["active"] = False
                entry["inactive_since"] = now.isoformat()
                continue

            missing_since = _parse_datetime(entry.get("missing_since"))
            if missing_since is None:
                entry["missing_since"] = now.isoformat()
                continue
            if now - missing_since >= grace:
                entry["active"] = False
                entry["inactive_since"] = now.isoformat()

    def mark_seen_without_alert(self, offer: Offer, now: datetime | None = None) -> None:
        self.refresh_seen(offer, now)

    def mark_inactive(self, seen_keys: set[str], now: datetime | None = None) -> None:
        """Compatibility helper used by older tests and callers."""
        now = ensure_utc(now or datetime.now(timezone.utc))
        for key, entry in self.offers.items():
            if key not in seen_keys and entry.get("active", True):
                entry["active"] = False
                entry["inactive_since"] = now.isoformat()

    def prune(self, now: datetime | None = None, days: int = 365) -> None:
        now = ensure_utc(now or datetime.now(timezone.utc))
        cutoff = now.timestamp() - days * 86400
        remove: list[str] = []
        for key, entry in self.offers.items():
            if entry.get("active", True):
                continue
            timestamp = _parse_datetime(entry.get("inactive_since"))
            if timestamp and timestamp.timestamp() < cutoff:
                remove.append(key)
        for key in remove:
            self.offers.pop(key, None)

    def save(self) -> None:
        self.data["schema_version"] = SCHEMA_VERSION
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.data, indent=2, sort_keys=True) + "\n"
        fd, temp_path = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=str(self.path.parent), text=True
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @staticmethod
    def _migrate_v1(loaded: dict[str, Any]) -> dict[str, Any]:
        migrated = {"schema_version": SCHEMA_VERSION, "offers": loaded.get("offers", {})}
        for entry in migrated["offers"].values():
            entry.setdefault("missing_since", None)
            entry.setdefault("suppressed", False)
        LOGGER.info("Migrated duplicate-prevention state from schema 1 to schema 2")
        return migrated


def _parse_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return ensure_utc(parsed)
    except ValueError:
        return None


def _parse_verdict(value: Any) -> Verdict:
    try:
        return Verdict(value)
    except (ValueError, TypeError):
        return Verdict.SKIP

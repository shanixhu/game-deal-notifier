from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import logging
import os
import tempfile

from .models import Offer, VERDICT_RANK, Verdict, ensure_utc


LOGGER = logging.getLogger(__name__)


class StateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.data: dict[str, Any] = {"schema_version": 1, "offers": {}}

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if loaded.get("schema_version") != 1 or not isinstance(
                loaded.get("offers"), dict
            ):
                raise ValueError("Unsupported state schema")
            self.data = loaded
        except (OSError, ValueError, json.JSONDecodeError) as exc:
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
            return True, "offer returned after being inactive"
        if previous.get("fingerprint") == current.get("fingerprint"):
            return False, "unchanged offer"

        old_price = previous.get("current_price_minor")
        new_price = current.get("current_price_minor")
        if new_price == 0 and old_price != 0:
            return True, "game became free"
        if isinstance(old_price, int) and isinstance(new_price, int) and new_price < old_price:
            return True, "price decreased"
        if current.get("offer_type") != previous.get("offer_type"):
            return True, "offer type changed"

        old_discount = previous.get("discount_percent")
        new_discount = current.get("discount_percent")
        if (
            isinstance(old_discount, int)
            and isinstance(new_discount, int)
            and new_discount >= old_discount + 5
        ):
            return True, "discount improved"

        if (
            current.get("store") != previous.get("store")
            and isinstance(new_price, int)
            and (not isinstance(old_price, int) or new_price < old_price)
        ):
            return True, "a better store offer appeared"

        if current.get("historical_low") is True and previous.get("historical_low") is not True:
            return True, "verified historical low reached"
        if (
            current.get("near_historical_low") is True
            and previous.get("near_historical_low") is not True
        ):
            return True, "verified near-historical-low reached"

        old_verdict = _parse_verdict(previous.get("verdict"))
        if VERDICT_RANK[offer.verdict] > VERDICT_RANK[old_verdict]:
            return True, "verdict improved"

        old_end = _parse_datetime(previous.get("end_at"))
        new_end = offer.end_at
        if old_end and new_end and abs((new_end - old_end).total_seconds()) >= 6 * 3600:
            return True, "deadline changed materially"

        return False, "change was not notification-worthy"

    def record_sent(self, offer: Offer, now: datetime | None = None) -> None:
        now = ensure_utc(now or datetime.now(timezone.utc))
        snapshot = offer.state_snapshot(now)
        snapshot["last_sent_at"] = now.isoformat()
        self.offers[offer.key] = snapshot

    def mark_seen_without_alert(self, offer: Offer, now: datetime | None = None) -> None:
        now = ensure_utc(now or datetime.now(timezone.utc))
        previous = self.offers.get(offer.key)
        if not previous:
            return
        previous["last_seen_at"] = now.isoformat()
        previous["active"] = True

    def mark_inactive(self, seen_keys: set[str], now: datetime | None = None) -> None:
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

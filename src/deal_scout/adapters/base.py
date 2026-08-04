from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
import re

from ..config import AppConfig
from ..http import HttpClient
from ..models import Offer


class StoreAdapter(ABC):
    def __init__(self, http: HttpClient, config: AppConfig) -> None:
        self.http = http
        self.config = config

    @abstractmethod
    def fetch_offers(self) -> list[Offer]:
        raise NotImplementedError


def parse_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def parse_date_only(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    for fmt in ("%d %b, %Y", "%b %d, %Y", "%Y-%m-%d", "%d %B %Y"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def money_to_minor(value: Any, decimals: int = 2) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value * (10**decimals))
    text = str(value).strip()
    if not text:
        return None
    cleaned = re.sub(r"[^0-9.,-]", "", text).replace(",", "")
    if cleaned in {"", "-"}:
        return None
    try:
        return int((Decimal(cleaned) * (10**decimals)).quantize(Decimal("1")))
    except (InvalidOperation, ValueError):
        return None


def first_nonempty(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None

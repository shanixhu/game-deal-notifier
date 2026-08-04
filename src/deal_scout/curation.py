from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json

from .models import canonical_title


@dataclass(frozen=True, slots=True)
class ReputationEntry:
    title: str
    aliases: tuple[str, ...]
    reason: str
    boost: float


class ReputationCatalog:
    def __init__(self, entries: list[ReputationEntry], trusted_names: tuple[str, ...]) -> None:
        self.entries = entries
        self.trusted_names = tuple(name.casefold() for name in trusted_names)
        self._lookup: dict[str, ReputationEntry] = {}
        for entry in entries:
            self._lookup[canonical_title(entry.title)] = entry
            for alias in entry.aliases:
                self._lookup[canonical_title(alias)] = entry

    @classmethod
    def load_default(cls) -> "ReputationCatalog":
        path = Path(__file__).with_name("data") / "reputation_catalog.json"
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        entries = [
            ReputationEntry(
                title=item["title"],
                aliases=tuple(item.get("aliases", [])),
                reason=item["reason"],
                boost=float(item.get("boost", 12)),
            )
            for item in raw.get("games", [])
        ]
        return cls(entries, tuple(raw.get("trusted_publishers_and_developers", [])))

    def match(self, title: str) -> ReputationEntry | None:
        key = canonical_title(title)
        if key in self._lookup:
            return self._lookup[key]
        # Edition suffixes commonly prevent an exact match. Prefer a conservative
        # whole-title prefix match and require at least three words or 10 characters.
        for known, entry in self._lookup.items():
            if len(known) >= 10 and (key.startswith(known + " ") or known.startswith(key + " ")):
                return entry
        return None

    def is_trusted(self, developer: str | None, publisher: str | None) -> bool:
        combined = f"{developer or ''} {publisher or ''}".casefold()
        return any(name in combined for name in self.trusted_names)

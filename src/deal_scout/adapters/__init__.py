"""Store adapters."""

from .epic import EpicAdapter
from .gog import GogAdapter
from .steam import SteamAdapter

__all__ = ["SteamAdapter", "EpicAdapter", "GogAdapter"]

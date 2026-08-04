from __future__ import annotations

import pytest

from deal_scout.config import AppConfig, StoreConfig
from deal_scout.curation import ReputationCatalog


@pytest.fixture
def config() -> AppConfig:
    return AppConfig(
        stores=StoreConfig(
            steam=True,
            epic=True,
            gog=True,
            steam_search_results=1,
            steam_top_seller_results=1,
            steam_cheap_special_results=1,
            steam_publisher_results=1,
            steam_enrich_limit=2,
            publisher_watchlist=("Electronic Arts",),
            gog_pages=1,
            epic_paid_pages=0,
        )
    )


@pytest.fixture
def catalog() -> ReputationCatalog:
    return ReputationCatalog.load_default()

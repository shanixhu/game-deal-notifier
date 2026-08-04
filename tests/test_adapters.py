from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from deal_scout.adapters.epic import EpicAdapter
from deal_scout.adapters.gog import GogAdapter
from deal_scout.adapters.steam import SteamAdapter, _select_enrichment_candidates
from deal_scout.models import OfferType


class FakeResponse:
    def __init__(self, data: Any, text: str = "") -> None:
        self._data = data
        self.text = text
        self.status_code = 200

    def json(self) -> Any:
        return self._data


class SteamHttp:
    def __init__(self) -> None:
        self.search_params = []

    def get(self, url, *, params=None, headers=None, cache=False):
        if "featuredcategories" in url:
            return FakeResponse(
                {
                    "specials": {
                        "items": [
                            {
                                "id": 123,
                                "discount_expiration": int(
                                    (datetime.now(timezone.utc) + timedelta(days=2)).timestamp()
                                ),
                            }
                        ]
                    }
                }
            )
        if "search/results" in url:
            self.search_params.append(dict(params or {}))
            html = """
            <a class="search_result_row" data-ds-appid="123" href="https://store.steampowered.com/app/123/">
              <img src="https://example.com/steam.jpg">
              <span class="title">Test Horror</span>
              <div class="search_discount"><span>-100%</span></div>
              <div class="discount_original_price">₹999</div>
              <div class="discount_final_price">Free</div>
              <span class="search_review_summary" data-tooltip-html="Very Positive&lt;br&gt;90% of the 1,000 user reviews"></span>
              <div class="search_released">1 Jan, 2020</div>
            </a>
            """
            return FakeResponse({"results_html": html, "total_count": 1})
        if "appdetails" in url:
            return FakeResponse(
                {
                    "123": {
                        "success": True,
                        "data": {
                            "type": "game",
                            "name": "Test Horror",
                            "is_free": False,
                            "short_description": "An atmospheric survival horror game.",
                            "price_overview": {
                                "currency": "INR",
                                "initial": 99900,
                                "final": 0,
                                "discount_percent": 100,
                            },
                            "genres": [{"description": "Horror"}],
                            "categories": [{"description": "Single-player"}],
                            "developers": ["Trusted Studio"],
                            "publishers": ["Trusted Publisher"],
                            "header_image": "https://example.com/header.jpg",
                            "release_date": {"date": "1 Jan, 2020"},
                            "package_groups": [
                                {"subs": [{"option_text": "Test Horror - Free"}]}
                            ],
                        },
                    }
                }
            )
        if "appreviews" in url:
            return FakeResponse(
                {
                    "query_summary": {
                        "review_score_desc": "Very Positive",
                        "total_positive": 900,
                        "total_reviews": 1000,
                    }
                }
            )
        raise AssertionError(url)


class EpicHttp:
    def get(self, url, *, params=None, headers=None, cache=False):
        now = datetime.now(timezone.utc)
        return FakeResponse(
            {
                "data": {
                    "Catalog": {
                        "searchStore": {
                            "elements": [
                                {
                                    "id": "epic-1",
                                    "namespace": "ns",
                                    "title": "Control Ultimate Edition",
                                    "description": "Supernatural action adventure.",
                                    "productSlug": "control",
                                    "developerDisplayName": "Remedy Entertainment",
                                    "publisherDisplayName": "505 Games",
                                    "keyImages": [
                                        {
                                            "type": "OfferImageWide",
                                            "url": "https://example.com/epic.jpg",
                                        }
                                    ],
                                    "categories": [{"path": "games/edition/base"}],
                                    "price": {
                                        "totalPrice": {
                                            "originalPrice": 249900,
                                            "discountPrice": 0,
                                            "currencyCode": "INR",
                                            "currencyInfo": {"decimals": 2},
                                        }
                                    },
                                    "promotions": {
                                        "promotionalOffers": [
                                            {
                                                "promotionalOffers": [
                                                    {
                                                        "startDate": (now - timedelta(hours=1)).isoformat(),
                                                        "endDate": (now + timedelta(days=5)).isoformat(),
                                                        "discountSetting": {
                                                            "discountType": "PERCENTAGE",
                                                            "discountPercentage": 0,
                                                        },
                                                    }
                                                ]
                                            }
                                        ],
                                        "upcomingPromotionalOffers": [],
                                    },
                                }
                            ]
                        }
                    }
                }
            }
        )

    def post(self, *args, **kwargs):
        raise AssertionError("Paid GraphQL should be disabled in this test")


class GogHttp:
    def get(self, url, *, params=None, headers=None, cache=False):
        return FakeResponse(
            {
                "products": [
                    {
                        "id": "gog-1",
                        "title": "SOMA",
                        "slug": "soma",
                        "productType": "game",
                        "price": {
                            "finalMoney": {"amount": "299", "currency": "INR"},
                            "baseMoney": {"amount": "1499", "currency": "INR"},
                            "discount": "-80%",
                        },
                        "reviewsRating": 4.6,
                        "reviewsCount": 5000,
                        "genres": [{"name": "Horror"}],
                        "developers": [{"name": "Frictional Games"}],
                        "publishers": [{"name": "Frictional Games"}],
                        "coverHorizontal": "https://example.com/gog.jpg",
                    }
                ],
                "pages": 1,
            }
        )


def test_steam_adapter_with_mocked_network(config) -> None:
    http = SteamHttp()
    offers = SteamAdapter(http, config).fetch_offers()
    assert len(offers) == 1
    assert offers[0].offer_type == OfferType.FREE_TO_KEEP
    assert offers[0].review_percent == 90
    assert offers[0].current_price_minor == 0
    assert any(call.get("publisher") == "Electronic Arts" for call in http.search_params)
    assert any(call.get("filter") == "topsellers" for call in http.search_params)


def test_epic_adapter_with_mocked_network(config) -> None:
    offers = EpicAdapter(EpicHttp(), config).fetch_offers()
    assert len(offers) == 1
    assert offers[0].offer_type == OfferType.FREE_TO_KEEP
    assert offers[0].normal_price_minor == 249900


def test_gog_adapter_with_mocked_network(config) -> None:
    offers = GogAdapter(GogHttp(), config).fetch_offers()
    assert len(offers) == 1
    assert offers[0].discount_percent == 80
    assert offers[0].review_percent == 92


def test_steam_candidate_selection_reserves_publisher_sale_rows() -> None:
    rows = []
    for index in range(8):
        rows.append(
            {
                "app_id": f"global-{index}",
                "title": f"Global {index}",
                "discount_percent": 95 - index,
                "review_count": 500000 - index,
                "review_percent": 95,
                "current_price_minor": 10000,
                "discovery_lanes": {"reviewed_specials", "top_selling_specials"},
            }
        )
    for index in range(3):
        rows.append(
            {
                "app_id": f"ea-{index}",
                "title": f"EA Deal {index}",
                "discount_percent": 80,
                "review_count": 5000,
                "review_percent": 82,
                "current_price_minor": 20000,
                "discovery_lanes": {"publisher:Electronic Arts"},
            }
        )

    selected = _select_enrichment_candidates(rows, limit=5, publisher_reserve=3)
    selected_ids = {row["app_id"] for row in selected}
    assert {"ea-0", "ea-1", "ea-2"} <= selected_ids

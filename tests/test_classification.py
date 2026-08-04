from deal_scout.classify import classify_offer, looks_like_dlc
from deal_scout.models import OfferType


def test_paid_game_temporarily_free_is_free_to_keep() -> None:
    result = classify_offer(
        title="A Good Game",
        product_type="game",
        categories=(),
        current_price_minor=0,
        normal_price_minor=199900,
        promotion_active=True,
    )
    assert result == OfferType.FREE_TO_KEEP


def test_free_to_play_is_not_giveaway() -> None:
    result = classify_offer(
        title="Always Free Arena",
        product_type="game",
        categories=(),
        current_price_minor=0,
        normal_price_minor=0,
        is_free_product=True,
        promotion_active=False,
    )
    assert result == OfferType.FREE_TO_PLAY


def test_free_weekend_is_temporary_trial() -> None:
    result = classify_offer(
        title="Great Game Free Weekend",
        product_type="game",
        categories=(),
        current_price_minor=0,
        normal_price_minor=299900,
        descriptive_text="Play for free until Monday",
        promotion_active=True,
    )
    assert result == OfferType.FREE_WEEKEND


def test_demo_and_dlc_are_classified() -> None:
    demo = classify_offer(
        title="Great Game Demo",
        product_type="demo",
        categories=(),
        current_price_minor=0,
        normal_price_minor=0,
    )
    dlc = classify_offer(
        title="Great Game Soundtrack",
        product_type="dlc",
        categories=("addons",),
        current_price_minor=9900,
        normal_price_minor=19900,
    )
    assert demo == OfferType.DEMO
    assert dlc == OfferType.DLC
    assert looks_like_dlc("Game Season Pass", "game", ())

# Game Deal Notifier

[![Tests](https://github.com/shanixhu/game-deal-notifier/actions/workflows/ci.yml/badge.svg)](https://github.com/shanixhu/game-deal-notifier/actions/workflows/ci.yml)
[![Deal checks](https://github.com/shanixhu/game-deal-notifier/actions/workflows/deal-scout.yml/badge.svg)](https://github.com/shanixhu/game-deal-notifier/actions/workflows/deal-scout.yml)

A selective PC game deal watcher for Steam, Epic Games Store and GOG. It runs on GitHub Actions and sends the deals that are actually worth looking at to Discord.

The aim is not to post every discount. A cheap unknown game, a tiny sample of positive reviews or a weekly giveaway is not automatically a recommendation.

## What makes the cut

The ranking combines:

- review percentage **and** review volume
- a confidence-adjusted review score, so 12 positive reviews do not beat 50,000 strong reviews
- a curated catalog of respected AAA, AA, indie and cult games
- developer and publisher reputation
- discount depth and final Indian price
- preferred genres such as atmospheric, horror, survival, racing, action and RPGs
- publisher-wide sale signals
- DLC, demo, soundtrack, cosmetic and free-to-play filtering

Steam is checked through several discovery lanes: top sellers, highly reviewed specials, cheap specials, temporary giveaways and a configurable publisher watchlist. A small candidate quota is reserved for every active publisher lane before the remaining spots are filled by overall rank. That prevents a large sale such as an EA promotion from being buried by Steam's global search order.

## Discord behaviour

Qualifying offers are bundled into compact digests rather than posted as a wall of separate notifications. Publisher events get their own digest, while unrelated deals are kept separate. Each deal includes:

- current and normal price
- discount
- store
- review evidence
- why the game is respected
- the deal verdict
- a clear `Offer ends` or `Claim by` deadline when the store exposes one
- a direct store link

The default verdicts are `CLAIM NOW`, `BUY NOW` and `EXCELLENT PRICE`. Routine `WAIT` alerts are disabled by default.

## Repeat-alert rules

`state/deals.json` remembers active offers.

An unchanged sale stays silent until it ends. The duplicate check happens before the per-run alert cap, so an old top-ranked deal cannot hide a genuinely new one. If a huge sale has more qualifying games than the cap, only the best picks are posted and the overflow is remembered silently instead of being dripped into Discord over the next several runs.

A new alert is allowed when something meaningful happens, such as:

- the price drops further
- the game becomes free to keep
- a better store offer appears
- the previous sale ends and the game goes on sale again later

A temporary store-feed miss does not immediately mark an offer as ended. The default grace period is seven days, which prevents sampling changes from creating fake “new sale” alerts.

Existing schema-1 state files are upgraded automatically, so old alert history can be kept when updating the project.

## Setup

1. Create a Discord webhook for the target channel.
2. Add it to the GitHub repository as the Actions secret `DISCORD_WEBHOOK_URL`.
3. Set repository Actions permissions to **Read and write** so the workflow can update `state/deals.json`.
4. Run the **Game Deal Notifier** workflow in `test` mode.
5. Run `dry-run` to inspect live decisions without sending real alerts.
6. Use `live` or leave the twice-daily schedule enabled.

Your PC does not need to stay on.

## Configuration

The useful controls are in `config.json`:

- `publisher_watchlist`: publishers that receive a dedicated Steam sale scan
- `max_price_inr`: comfortable buying-price reference
- `min_paid_discount_percent`: normal paid-deal floor
- `min_giveaway_quality_score`: stops unknown giveaways being recommended just because they are free
- `max_alerts_per_run`: maximum deals in a digest
- `absence_grace_hours`: time before a missing offer is treated as ended
- `preferred_genres`: personal taste bonus, not a hard restriction

## Limits

Storefront website feeds can change without notice. Each adapter fails independently, so one broken store does not stop the others. Steam does not expose an end time for every sale, and the project does not claim a historical low unless a reliable source explicitly verifies it.

## Project layout

```text
.github/workflows/   scheduled scan and tests
src/deal_scout/      adapters, scoring, state and Discord code
tests/               mocked-network and decision tests
state/deals.json     duplicate and sale-episode history
config.json          user settings
```

Built and maintained by [Shanu](https://github.com/shanixhu).

Copyright © 2026 Shanu. All rights reserved.

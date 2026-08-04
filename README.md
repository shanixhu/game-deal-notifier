# Game Deal Notifier

[![Tests](https://github.com/shanixhu/game-deal-notifier/actions/workflows/ci.yml/badge.svg)](https://github.com/shanixhu/game-deal-notifier/actions/workflows/ci.yml)
[![Deal checks](https://github.com/shanixhu/game-deal-notifier/actions/workflows/deal-scout.yml/badge.svg)](https://github.com/shanixhu/game-deal-notifier/actions/workflows/deal-scout.yml)

A Python project that watches Steam, Epic Games Store and GOG for PC game deals worth sharing, then sends the best ones to Discord.

It is deliberately selective. Permanent giveaways, respected games at strong discounts and unusually good promotions are prioritised; weak sales, demos, trials, DLC and repeat alerts are filtered out.

## Highlights

- Steam, Epic Games Store and GOG
- Indian pricing when INR is available
- Free-to-keep detection
- Review and reputation-aware scoring
- Clear `CLAIM NOW`, `BUY NOW` and `WAIT` verdicts
- Duplicate prevention
- Twice-daily GitHub Actions checks
- No paid API, server or always-on PC

## How it works

The notifier gathers current offers, classifies their promotion type, scores game quality and deal value, removes low-signal listings, and posts qualifying results as Discord embeds.

`state/deals.json` stores the last alert for each offer so unchanged deals are not posted again.

## Running your own copy

1. Fork the repository.
2. Create a Discord webhook.
3. Save it as the repository secret `DISCORD_WEBHOOK_URL`.
4. Give GitHub Actions read/write permission so it can update `state/deals.json`.
5. Run the **Game Deal Notifier** workflow in `test` mode.

The workflow also supports `dry-run` and `live` modes.

## Configuration

Edit `config.json` to change preferred genres, price limits, score thresholds, enabled stores and alert caps.

## Project layout

```text
.github/workflows/   automation and tests
src/deal_scout/      application code
tests/               automated tests
state/deals.json     duplicate history
config.json          user settings
```

## Author

Built and maintained by [Shanu](https://github.com/shanixhu).

Copyright © 2026 Shanu. All rights reserved.

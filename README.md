# Game Deal Notifier

[![Tests](https://github.com/shanixhu/game-deal-notifier/actions/workflows/ci.yml/badge.svg)](https://github.com/shanixhu/game-deal-notifier/actions/workflows/ci.yml)
[![Deal checks](https://github.com/shanixhu/game-deal-notifier/actions/workflows/deal-scout.yml/badge.svg)](https://github.com/shanixhu/game-deal-notifier/actions/workflows/deal-scout.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: GPL v3](https://img.shields.io/badge/license-GPLv3-blue)](LICENSE)

A small Python project that checks Steam, Epic Games Store and GOG for deals that are actually worth seeing, then posts the useful ones to Discord.

I made this because most deal feeds are noisy. A 10% discount on a random game is not an alert. A respected game at a genuinely strong price, or a paid game that is free to keep, is.

## What it does

- runs twice a day on GitHub Actions, even when my PC is off;
- checks Steam, Epic and GOG independently;
- prefers Indian prices when a store returns INR;
- separates permanent giveaways from free weekends, trials, demos and free-to-play games;
- filters DLC, soundtracks, cosmetics and low-signal listings;
- scores deals using reviews, reputation, price, discount and genre fit;
- avoids reposting the same unchanged offer;
- sends readable Discord embeds with a verdict such as `CLAIM NOW`, `BUY NOW` or `WAIT FOR A BETTER PRICE`.

## Example

```text
CLAIM NOW — Control Ultimate Edition

Store: Epic Games Store
Price: Free
Normal price: ₹2,499
Offer type: Free to keep
Verdict: Claim it before the deadline. It stays in your library.
```

## Quick setup

### 1. Create a Discord webhook

In your Discord server, open **Server Settings → Integrations → Webhooks**, create a webhook for the channel you want, and copy its URL.

Treat the webhook like a password. Never commit it to this repository.

### 2. Add the GitHub secret

Open the repository and go to:

**Settings → Secrets and variables → Actions → New repository secret**

Use this exact name:

```text
DISCORD_WEBHOOK_URL
```

Paste the webhook URL as the secret value.

### 3. Allow state updates

Go to:

**Settings → Actions → General → Workflow permissions**

Select **Read and write permissions**. The workflow needs this only to update `state/deals.json`, which remembers already-sent alerts.

Leave **Allow GitHub Actions to create and approve pull requests** unchecked.

### 4. Test it

Open **Actions → Game Deal Notifier → Run workflow** and choose `test`.

A successful setup sends this message to Discord:

```text
TEST OK — Game Deal Notifier
```

Available manual modes:

- `test` — sends one sample Discord message;
- `dry-run` — checks live store data but sends nothing;
- `live` — checks stores, sends qualifying alerts and updates state.

Scheduled runs use `live` automatically.

## Schedule

The workflow currently runs at:

| UTC | India time |
|---|---:|
| `03:37` | `09:07 IST` |
| `16:17` | `21:47 IST` |

The evening run is placed after Epic's usual weekly giveaway refresh.

## Configuration

Most people can use the included `config.json` unchanged.

Useful settings:

```json
{
  "filters": {
    "max_price_inr": 1500,
    "min_paid_discount_percent": 50,
    "min_quality_score": 52,
    "min_deal_score": 62,
    "send_wait_verdicts": true,
    "max_alerts_per_run": 8
  }
}
```

`preferred_genres` adds a score bonus but does not block excellent games from other genres.

## How duplicate prevention works

`state/deals.json` stores a compact record of sent offers. A new alert is allowed when something meaningful changes, such as:

- the price drops;
- a paid game becomes free;
- the discount improves;
- a better store offer appears;
- the deadline changes materially;
- an expired promotion returns.

Routine state-only commits are excluded from the test workflow.

## Local development

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

Mocked dry run:

```bash
PYTHONPATH=src python -m deal_scout.cli --mode dry-run --sample-data
```

Live-data dry run without Discord:

```bash
PYTHONPATH=src python -m deal_scout.cli --mode dry-run
```

## Project layout

```text
.github/workflows/   scheduled checks and tests
src/deal_scout/      application code
src/deal_scout/adapters/  Steam, Epic and GOG integrations
tests/               automated tests
state/deals.json     duplicate-prevention state
config.json          user settings
```

## Accuracy and limitations

The project does not invent historical-low claims. It uses phrases such as **strong discount** unless a trustworthy source explicitly verifies a historical low.

Storefront endpoints can change. Each store adapter is isolated, so one broken source should not stop the others. Steam also does not provide a sale deadline for every listing.

## Contributing

Bug reports and focused pull requests are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening one.

For security issues, use the instructions in [SECURITY.md](SECURITY.md) instead of posting the details publicly.

## Author

Built and maintained by [Shanu](https://github.com/shanixhu).

## License

Licensed under the GNU General Public License v3.0. You may use and modify the code, but distributed versions based on it must remain under the same license and include the corresponding source. See [LICENSE](LICENSE).

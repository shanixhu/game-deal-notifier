# PC Game Deal Scout

A personal, cloud-run PC game deal filter that checks **Steam**, **Epic Games Store**, and **GOG**, then sends only worthwhile alerts to a private Discord channel.

It runs in **GitHub Actions**, so your PC can be switched off. It does not use ChatGPT scheduled tasks, a paid AI API, a database server, Windows Task Scheduler, or paid hosting.

## What it does

- Checks stores twice daily.
- Uses Indian region/currency parameters and shows **₹ prices when the store supplies INR**.
- Detects paid games temporarily free to keep.
- Separates permanent giveaways from free-to-play games, free weekends, trials, demos, DLC, soundtracks, cosmetics, and bundles.
- Scores offers using review quality, review volume, reputation, developer/publisher reputation, genre fit, price, discount, game age, and promotion rarity.
- Gives one of these useful verdicts:
  - `CLAIM NOW`
  - `BUY NOW`
  - `EXCELLENT PRICE`
  - `WAIT FOR A BETTER PRICE`
- Suppresses weak discounts, low-quality products, shovelware-like low-signal listings, DLC, demos, soundtracks, cosmetics, and unchanged repeat alerts.
- Remembers sent offers in `state/deals.json`, which the workflow commits back to the repository.
- Retries temporary failures with exponential backoff and respects Discord's `Retry-After` rate-limit response.
- Isolates store failures: one broken source does not stop the other stores.

## Schedule

The main workflow uses UTC cron, as GitHub Actions expects:

| UTC | India time |
|---|---:|
| `03:37 UTC` | `09:07 IST` |
| `16:17 UTC` | `21:47 IST` |

The evening check runs after Epic's usual Thursday giveaway refresh in both US daylight-saving and standard time. GitHub may occasionally delay scheduled jobs during periods of high load.

## Fast setup

You only need to create the repository, create a Discord webhook, add one GitHub secret, and upload this project.

### 1. Create the Discord webhook

You need the **Manage Webhooks** permission in your Discord server.

1. Open your Discord server.
2. Open **Server Settings**.
3. Select **Integrations**.
4. Open **Webhooks**.
5. Select **New Webhook** or **Create Webhook**.
6. Choose your existing private text channel.
7. Give it a name such as `PC Game Deal Scout`.
8. Select **Copy Webhook URL**.

Treat the copied URL like a password. Do not paste it into chat, source code, `config.json`, an issue, or a commit.

### 2. Create the GitHub repository

1. On GitHub, create a new repository.
2. Public or private both work.
3. For the easiest upload, create it empty: do not pre-add another README, `.gitignore`, or license.
4. The workflow must be present on the repository's default branch, normally `main`.

### 3. Upload the project

1. Extract the downloaded ZIP on your computer.
2. Open the new GitHub repository.
3. Select **Add file → Upload files**.
4. Drag the **contents inside** the extracted `pc-game-deal-scout` folder into GitHub. Make sure `.github`, `src`, `tests`, `state`, `config.json`, and the other root files are included.
5. Commit the upload to the default branch.

GitHub Desktop or normal Git commands also work, but they are not required.

### 4. Add the webhook as a GitHub Actions secret

1. Open the repository on GitHub.
2. Select **Settings**.
3. Select **Secrets and variables → Actions**.
4. Select **New repository secret**.
5. Enter this exact name:

   `DISCORD_WEBHOOK_URL`

6. Paste the Discord webhook URL into the secret value.
7. Save it.

The workflow reads the secret only at runtime. The project contains no webhook token.

### 5. Allow the workflow to update its state file

The workflow requests only `contents: write`, which it needs to commit `state/deals.json`.

1. In the repository, open **Settings**.
2. Select **Actions → General**.
3. Scroll to **Workflow permissions**.
4. Select **Read and write permissions**.
5. Save.

If the default branch is protected against bot pushes, allow GitHub Actions to push to that branch or use a repository without that restriction. Otherwise alerts can still send, but duplicate-prevention state cannot be persisted.

### 6. Run the safe manual test

1. Open the repository's **Actions** tab.
2. Select **PC Game Deal Scout** in the left sidebar.
3. Select **Run workflow**.
4. Choose `test`.
5. Select **Run workflow** again.

`test` mode sends one clearly labelled sample message. It does not contact the game stores and does not change `state/deals.json`.

### 7. Confirm Discord worked

Within the chosen Discord channel, you should see an embed titled:

`TEST OK — PC Game Deal Scout`

If the workflow is green but no message appears, confirm that the webhook points to the correct channel. If the workflow is red, open the failed step's log; the project reports missing or invalid webhook configuration without printing the secret itself.

### 8. Run real checks

From the same **Run workflow** menu:

- `dry-run`: fetches live store data, applies all filters, and prints the Discord payloads to the GitHub Actions log without sending or changing state.
- `live`: fetches live store data, sends new qualifying alerts, and updates `state/deals.json`.
- Scheduled runs automatically use `live` mode.

## Configuration

The included `config.json` is ready to use. No editing is required.

To customize it later, edit only the values in `config.json` through GitHub's file editor or locally. `config.example.json` is a clean reference copy.

### Preferred genres

Edit:

```json
"preferred_genres": [
  "atmospheric",
  "story rich",
  "horror",
  "survival",
  "racing"
]
```

Preferred genres add a score bonus; they are not a hard restriction. Excellent games in other genres can still alert.

### Maximum comfortable price

Edit:

```json
"max_price_inr": 1500
```

This affects scoring and `BUY NOW` decisions. It is not an absolute block on every offer.

### Minimum paid discount

Edit:

```json
"min_paid_discount_percent": 50
```

Raising it makes alerts rarer. Lowering it allows more ordinary sales to qualify.

### Make filtering stricter or looser

Important controls:

- `min_quality_score`: minimum game-quality score.
- `min_deal_score`: minimum combined price/deal score.
- `min_review_percent`: reference threshold for positive reception.
- `min_review_count`: reference threshold for review confidence.
- `max_alerts_per_run`: hard cap on Discord alerts in one run.
- `max_wait_alerts_per_run`: cap on useful `WAIT` alerts.
- `send_wait_verdicts`: set to `false` to disable all `WAIT` alerts.

### Store request limits

- `steam_search_results`: discounted Steam search rows examined.
- `steam_enrich_limit`: Steam candidates enriched with details and review summaries.
- `gog_pages`: GOG catalog pages checked.
- `epic_paid_pages`: best-effort Epic paid-sale pages checked.

The defaults are intentionally modest and respectful for a twice-daily personal checker.

### Disable a store

Set its value to `false`:

```json
"stores": {
  "steam": true,
  "epic": true,
  "gog": false
}
```

## Duplicate prevention

The repository includes:

`state/deals.json`

For each alerted title, it stores the last sent store, price, discount, offer type, deadline, verdict, and a compact fingerprint. A new alert is sent when a meaningful change occurs, including:

- a lower price;
- a paid game becoming free;
- a stronger discount;
- a better store offer;
- a material deadline change;
- an improved verdict;
- a verified historical-low flag becoming available;
- an expired/inactive offer returning later.

An unchanged promotion is suppressed. Old inactive entries are pruned after one year.

## How deal quality is judged

The filter combines:

- player review percentage;
- review count using a logarithmic confidence bonus;
- a curated reputation catalog for acclaimed and cult games;
- respected developer/publisher signals;
- preferred genre fit;
- age/established reputation;
- discount percentage;
- final price;
- permanent-free status;
- promotion rarity;
- content type and title-pattern exclusions.

The curated catalog lives at:

`src/deal_scout/data/reputation_catalog.json`

It improves explanations for known respected games but does not limit the system to those titles.

## Offer-type accuracy

The classifier distinguishes:

- paid game temporarily free to keep;
- always-free/free-to-play product;
- free weekend or trial;
- demo or playtest;
- base game discount;
- bundle;
- DLC/add-on/cosmetic/soundtrack.

Store data is not perfectly uniform. The system is deliberately conservative: known trial language such as “free weekend,” “free trial,” or “play for free until” prevents a promotion from being called permanent.

## Historical-low policy

This project does **not** invent historical-low claims.

No paid, keyless, lifetime price-history API is required by this project. Unless a store response supplies a reliable and explicitly understood history flag, the alert says **strong discount** or **excellent price**, not historical low. The data model supports verified historical/near-historical flags for a future trusted source, but the included adapters leave them unknown.

## Data sources and resilience

The project uses store-owned storefront endpoints and pages:

- Steam storefront search, app details, review summaries, and featured-category data.
- Epic's public free-games promotions feed, plus a separate best-effort storefront GraphQL sale query.
- GOG's storefront catalog feed.

Some storefront endpoints are used by the stores' own websites but are not documented as permanent public API contracts. Their parsers are therefore isolated. If one changes:

- the exception is logged;
- other stores continue;
- Epic giveaways can continue even if Epic's paid-sale GraphQL query breaks;
- if every enabled adapter fails, the program refuses to mark existing deals inactive.

## Discord behavior

Each real alert includes:

- title and verdict;
- store;
- current price;
- normal price;
- discount;
- offer type;
- deadline in IST plus Discord relative time;
- review/reputation information;
- why the game matters;
- why the price is or is not strong enough;
- direct legitimate store link;
- optional cover thumbnail.

Discord mentions are disabled in generated payloads to prevent accidental `@everyone` or role pings from store-supplied text.

## Reliability and security

- HTTP request timeout: 20 seconds.
- Retry attempts: 4.
- Exponential backoff with jitter for temporary connection and server failures.
- Discord `429` handling uses `Retry-After`/`retry_after` rather than a hard-coded rate limit.
- GitHub job timeout: 15 minutes.
- Store failures and individual malformed products are isolated.
- State writes are atomic locally before Git commits them.
- Workflow concurrency prevents two scheduled scans from modifying state simultaneously.
- Only `contents: write` is granted to the deal workflow; the test workflow is `contents: read`.
- The webhook secret is never stored in a file or printed intentionally.

## Local commands for advanced users

Local execution is optional; GitHub Actions is the intended runtime.

```bash
python -m pip install -r requirements-dev.txt
```

```bash
PYTHONPATH=src pytest
```

Deterministic mocked-data dry run:

```bash
PYTHONPATH=src python -m deal_scout.cli \
  --mode dry-run \
  --sample-data \
  --payload-output reports/sample-payload.json
```

Live-data dry run without Discord:

```bash
PYTHONPATH=src python -m deal_scout.cli --mode dry-run
```

Do not place a real webhook URL in a command, file, or shell history. For an intentional local webhook test, set it through an environment variable appropriate for your operating system.

## Project structure

```text
.github/workflows/
  ci.yml                 Automated tests on code changes
  deal-scout.yml         Scheduled/manual cloud workflow
src/deal_scout/
  adapters/              Steam, Epic, and GOG adapters
  data/                  Curated reputation catalog
  classify.py            Offer-type and DLC/demo filtering
  scoring.py             Quality, deal score, and verdicts
  discord.py             Discord embeds and webhook sender
  http.py                Timeouts, retry, backoff, rate limits
  state.py               Duplicate-prevention persistence
  pipeline.py            Failure-isolated orchestration
  cli.py                 live, dry-run, and test modes
tests/                    Mocked network and logic tests
state/deals.json          GitHub-native persistent state
config.json               Ready-to-use configuration
VERIFICATION.md            Final build/test record
```

## Tests included

The test suite covers:

- offer classification;
- free-to-keep detection;
- free-to-play and free-weekend separation;
- DLC/demo filtering;
- quality scoring;
- verdict selection;
- duplicate detection;
- returning expired promotions;
- Discord embed generation;
- mocked Steam, Epic, and GOG requests;
- Discord rate-limit retry behavior;
- GitHub Actions schedules and permissions;
- hard-coded webhook-token scanning.

The packaged verification record is in `VERIFICATION.md`.

## Unavoidable limitations

- Storefront schemas can change without notice, especially undocumented website endpoints.
- Steam does not expose a deadline for every sale through the used feeds; those alerts say the deadline was not listed.
- Epic does not provide the same player-review depth as Steam through the used public storefront data, so curated reputation and publisher/developer signals matter more there.
- GOG fields can vary by catalog item and region.
- Currency availability is controlled by the store. The system requests India/INR but displays the currency actually returned.
- A lifetime historical-low claim requires a reliable history provider; this project intentionally avoids false claims.
- GitHub scheduled workflows can be delayed, and public-repository schedules may be disabled by GitHub after long repository inactivity.

## License

MIT. See `LICENSE`.

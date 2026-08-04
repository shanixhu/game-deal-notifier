# Verified implementation references

These references were checked before the project was built.

## Discord

- Webhook resource and execute-webhook fields: https://docs.discord.com/developers/resources/webhook
- HTTP API user-agent/content-type rules: https://docs.discord.com/developers/reference
- Rate-limit headers and `Retry-After`: https://docs.discord.com/developers/topics/rate-limits
- Creating and managing webhooks: https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks

## GitHub Actions

- Workflow syntax, cron, schedule timezone/UTC behavior, and permissions: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- Scheduled workflow behavior: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- Manual `workflow_dispatch` runs: https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow
- Repository Actions secrets: https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions
- Official checkout action: https://github.com/actions/checkout
- Official setup-python action: https://github.com/actions/setup-python

## Stores

- Epic's official free-games page and permanent weekly giveaway description: https://store.epicgames.com/free-games
- Steam Web API overview: https://partner.steamgames.com/doc/webapi_overview
- Steam store-owned endpoints used by its storefront: `store.steampowered.com`
- Epic store-owned promotions/GraphQL endpoints: `store-site-backend-static.ak.epicgames.com` and `graphql.epicgames.com`
- GOG store-owned catalog endpoint: `catalog.gog.com`

The Steam storefront, Epic GraphQL, and GOG catalog schemas used here are not all documented as stable public contracts. The project treats them as best-effort store-owned feeds and isolates failures accordingly.

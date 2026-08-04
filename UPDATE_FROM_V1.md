# Updating an existing repository from 1.0.0

This package is intended to replace the project files in the existing `game-deal-notifier` repository.

Do not delete or replace these GitHub-side settings:

- the `DISCORD_WEBHOOK_URL` repository secret;
- Actions workflow permission set to read and write;
- the existing repository visibility and URL.

Preserve the current `state/deals.json` from the repository if it already contains sent-deal history. Replacing it with the empty packaged copy resets duplicate prevention.

The update changes documentation, public naming, repository health files, metadata and licensing. The working Python module remains named `deal_scout` internally to avoid an unnecessary risky refactor.

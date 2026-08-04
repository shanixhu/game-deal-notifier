# Security policy

## Reporting a vulnerability

Please do not open a public issue containing a webhook URL, token, exploit details or other sensitive information.

Use GitHub's private vulnerability reporting feature for this repository when available. Otherwise, open a minimal issue asking the maintainer for a private contact method without including the sensitive details.

## Secret handling

The only required secret is `DISCORD_WEBHOOK_URL`. It belongs in GitHub Actions repository secrets, never in `config.json`, workflow files, screenshots, logs or commits.

If a webhook is exposed, delete or regenerate it in Discord immediately and update the GitHub secret.

## Supported version

Security fixes are applied to the latest version on the `main` branch.

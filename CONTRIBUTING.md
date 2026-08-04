# Contributing

Thanks for taking an interest in the project.

## Before opening an issue

- Check existing issues first.
- Include the affected store, workflow run and relevant log lines.
- Remove webhook URLs, tokens and personal information from screenshots or logs.
- For a store parser problem, include the product URL and the result you expected.

## Pull requests

Keep pull requests focused. A bug fix and an unrelated refactor should usually be separate changes.

Before submitting:

```bash
python -m pip install -r requirements-dev.txt
python -m compileall -q src tests
python -m pytest
```

Please explain what changed, why it changed and how you tested it. New behavior should include tests when practical.

## Project preferences

- Keep dependencies minimal.
- Do not add paid APIs or AI services.
- Do not log secrets.
- Do not label an offer as a historical low without a reliable source.
- Preserve failure isolation between store adapters.

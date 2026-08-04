# Final verification

Verified on **2026-08-02** before packaging.

## Completed checks

- `python -m compileall -q src tests` — passed.
- `PYTHONPATH=src pytest` — **24 tests passed**.
- Deterministic local dry run with mocked/sample data — passed.
- Generated Discord payload inspection — passed.
- Expected sample verdicts: `CLAIM NOW — Control Ultimate Edition` and `BUY NOW — SIGNALIS`.
- Soundtrack sample suppression — passed.
- GitHub Actions YAML parsed successfully for both workflows.
- Python package wheel build — passed.
- Hard-coded Discord webhook-token scan — passed.
- Project contains no `.env`, webhook URL, token, or secret value.
- Scheduled workflow requires no local PC process and runs on GitHub-hosted runners.

## Scope note

The deterministic build verification intentionally used mocked store responses, as required by the project specification. Live storefront behavior should be checked after upload with the included manual `dry-run` workflow. Store-owned website feeds can change without notice; each adapter is isolated so one failed store does not stop the others.

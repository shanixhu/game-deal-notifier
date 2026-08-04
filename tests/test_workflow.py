from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path):
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_deal_workflow_has_schedule_dispatch_and_minimal_write_permission() -> None:
    workflow = load_yaml(ROOT / ".github" / "workflows" / "deal-scout.yml")
    assert "schedule" in workflow["on"]
    assert "workflow_dispatch" in workflow["on"]
    crons = [entry["cron"] for entry in workflow["on"]["schedule"]]
    assert crons == ["37 3 * * *", "17 16 * * *"]
    assert workflow["jobs"]["scan"]["steps"][0]["uses"] == "actions/checkout@v6"
    assert workflow["permissions"] == {"contents": "write"}
    assert workflow["jobs"]["scan"]["timeout-minutes"] == "20"


def test_ci_workflow_is_read_only() -> None:
    workflow = load_yaml(ROOT / ".github" / "workflows" / "ci.yml")
    assert workflow["permissions"] == {"contents": "read"}


def test_no_hardcoded_discord_webhook_secret() -> None:
    token_pattern = re.compile(
        r"https://(?:discord(?:app)?\.com)/api/webhooks/\d+/[A-Za-z0-9._-]{20,}"
    )
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.suffix in {".py", ".yml", ".yaml", ".json", ".md", ".toml", ".txt"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            assert not token_pattern.search(text), f"Possible webhook secret in {path}"

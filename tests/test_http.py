from __future__ import annotations

import requests

from deal_scout.http import HttpClient, RetryPolicy


class SequenceSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def request(self, *args, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


def response(status: int, *, retry_after: str | None = None) -> requests.Response:
    item = requests.Response()
    item.status_code = status
    item.url = "https://discord.com/api/webhooks/example"
    item._content = b'{"retry_after": 2.5}' if status == 429 else b"{}"
    if retry_after is not None:
        item.headers["Retry-After"] = retry_after
    return item


def test_rate_limit_retry_honors_retry_after(monkeypatch) -> None:
    sleeps = []
    session = SequenceSession([response(429, retry_after="2.5"), response(204)])
    monkeypatch.setattr("deal_scout.http.time.sleep", sleeps.append)
    client = HttpClient(
        session=session,
        retry_policy=RetryPolicy(attempts=2, base_delay_seconds=0.1, max_delay_seconds=5),
    )
    result = client.post("https://discord.com/api/webhooks/example", json_body={})
    assert result.status_code == 204
    assert session.calls == 2
    assert sleeps == [2.5]

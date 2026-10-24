import io
import json
import urllib.error
from email.message import Message

from scripts import persons_ai_runner


def _response() -> io.BytesIO:
    data = {"candidates": [{"content": {"parts": [{"text": "[]"}]}}]}
    return io.BytesIO(json.dumps(data).encode("utf-8"))


def test_call_retries_429_after_retry_after(monkeypatch) -> None:
    headers = Message()
    headers["Retry-After"] = "7"
    rate_limit = urllib.error.HTTPError(
        "https://example.invalid", 429, "Too Many Requests", headers, io.BytesIO(b'{"error": {}}')
    )
    responses = iter([rate_limit, _response()])
    sleeps: list[float] = []

    def fake_urlopen(*args, **kwargs):
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(persons_ai_runner.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(persons_ai_runner.time, "sleep", sleeps.append)

    assert persons_ai_runner._call({}, ["test-key"]) == []
    assert sleeps == [7.0]


def test_retry_delay_reads_gemini_retry_info() -> None:
    error = {"details": [{"retryDelay": "12.5s"}]}

    assert persons_ai_runner._retry_delay(0, None, error) == 12.5

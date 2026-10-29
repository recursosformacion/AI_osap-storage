import io
import json
import sys
import urllib.error
from email.message import Message
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from scripts import works_ai_runner


def _response() -> io.BytesIO:
    data = {"candidates": [{"content": {"parts": [{"text": "[]"}]}}]}
    return io.BytesIO(json.dumps(data).encode("utf-8"))


def test_keys_reads_multiple_environment_keys(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY2", raising=False)
    monkeypatch.setenv("GEMINI_API_KEYS", "first-key;second-key,first-key")

    assert works_ai_runner._keys() == ["first-key", "second-key"]


def test_call_uses_next_key_immediately_after_429(monkeypatch) -> None:
    headers = Message()
    rate_limit = urllib.error.HTTPError(
        "https://example.invalid", 429, "Too Many Requests", headers, io.BytesIO(b'{"error": {}}')
    )
    responses = iter([rate_limit, _response()])
    urls: list[str] = []
    sleeps: list[float] = []

    def fake_urlopen(request, **kwargs):
        urls.append(request.full_url)
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(works_ai_runner.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(works_ai_runner.time, "sleep", sleeps.append)

    assert works_ai_runner._call({}, ["first-key", "second-key"]) == []
    assert [parse_qs(urlsplit(url).query)["key"][0] for url in urls] == ["first-key", "second-key"]
    assert sleeps == []

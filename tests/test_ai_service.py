"""The Groq wrapper copes with rejected JSON mode and messy replies (no network: the client is faked)."""
from types import SimpleNamespace

import pytest

from backend import ai_service as A


def _reply(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


@pytest.fixture
def fake(monkeypatch):
    calls = []
    monkeypatch.setattr(A, "_client", lambda: object())
    monkeypatch.setattr(A, "_cache_get", lambda k: None)
    monkeypatch.setattr(A, "_cache_set", lambda k, v: None)

    def install(*results):
        it = iter(results)

        def create(client, **kw):
            calls.append(kw)
            r = next(it)
            if isinstance(r, Exception):
                raise r
            return _reply(r)
        monkeypatch.setattr(A, "_create", create)
        return calls
    return install


def test_json_mode_rejected_retries_without_it(fake):
    calls = fake(A.AIJsonRejected("bad"), 'Here you go:\n```json\n{"sql": "SELECT 1"}\n```')
    assert A.chat_json([{"role": "user", "content": "q"}]) == {"sql": "SELECT 1"}
    assert "response_format" in calls[0] and "response_format" not in calls[1]


def test_unparseable_reply_is_a_clean_error(fake):
    fake("no json here")
    with pytest.raises(A.AIBadOutput):
        A.chat_json([{"role": "user", "content": "q"}])


def test_chart_blurb_is_plain_text_and_tidied(fake, monkeypatch):
    monkeypatch.setattr(A, "available", lambda: True)
    calls = fake('"**Intercity** fell — the biggest drop.\nRead small groups with care."')
    out = A.chart_blurb("t", [{"a": 1}])
    assert out == "Intercity fell, the biggest drop. Read small groups with care."
    assert "response_format" not in calls[0]

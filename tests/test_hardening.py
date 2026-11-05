"""Hardening: headers, gzip, request-size cap, AI rate limit, SPA routes, no CORS by default."""
import pytest

from backend import main


@pytest.fixture(autouse=True)
def _fresh_limiter():
    main._hits.clear()
    yield
    main._hits.clear()


def test_security_and_cache_headers(api):
    r = api.get("/api/health")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


def test_gzip_on_large_responses(api):
    r = api.post("/api/enps/segment?dim=function", json={}, headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200 and r.headers.get("content-encoding") == "gzip"


def test_body_size_cap(api):
    big = {"title": "x", "rows": [{"v": "y" * 1000}] * 400}
    r = api.post("/api/chart-insight", json=big)
    assert r.status_code == 413


def test_ai_rate_limit(api, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)      # no Groq calls: the no-key path answers instantly
    monkeypatch.setattr(main, "AI_RATE_PER_MIN", 3)
    codes = [api.post("/api/ask", json={"question": "eNPS by thread", "dataset": "enps"}).status_code
             for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3:] == [429, 429]
    assert "wait a minute" in api.post("/api/ask", json={"question": "x", "dataset": "enps"}).json()["detail"]
    # dashboards are never rate limited
    assert all(api.post("/api/enps/kpis", json={}).status_code == 200 for _ in range(5))


def test_rate_limit_is_per_client(api, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(main, "AI_RATE_PER_MIN", 1)
    a = api.post("/api/ask", json={"question": "q", "dataset": "enps"}, headers={"X-Forwarded-For": "1.1.1.1"})
    b = api.post("/api/ask", json={"question": "q", "dataset": "enps"}, headers={"X-Forwarded-For": "2.2.2.2"})
    c = api.post("/api/ask", json={"question": "q", "dataset": "enps"}, headers={"X-Forwarded-For": "1.1.1.1"})
    assert (a.status_code, b.status_code, c.status_code) == (200, 200, 429)


def test_no_cors_by_default(api):
    r = api.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


@pytest.mark.parametrize("path", ["/sentiment", "/hiring", "/data-quality", "/"])
def test_spa_routes_served(api, path):
    r = api.get(path)
    if not (main.DIST / "index.html").exists():
        pytest.skip("frontend not built")
    assert r.status_code == 200 and "<div id=\"root\">" in r.text
    assert r.headers["cache-control"] == "no-cache"

"""
Covers the shared-session-cache integration added 2026-10-28 (see
jainam/broker/xts_client.py's SessionInvalidatedError docstring and
/root/shared_jainam/session_cache.py) -- from_env() must adopt an
already-cached token instead of logging in, and must correctly adopt-
or-login when a token is later rejected mid-run. Mocks _login itself
(not the raw HTTP layer), since from_env's own retry/network logic is
already covered elsewhere; this only tests the cache-vs-login branching.
"""

import sys

import jainam.broker.xts_client as xts

sys.path.insert(0, "/root/shared_jainam")
import session_cache as sc  # noqa: E402

ENV = {
    "JAINAM_BASE_URL": "https://x",
    "JAINAM_MARKET_API_KEY": "mkey",
    "JAINAM_MARKET_API_SECRET": "msecret",
    "JAINAM_INTERACTIVE_API_KEY": "ikey",
    "JAINAM_INTERACTIVE_API_SECRET": "isecret",
}


def _set_env(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(xts, "load_dotenv", lambda *a, **k: None)


def test_from_env_logs_in_when_cache_is_empty(monkeypatch):
    _set_env(monkeypatch)
    calls = []

    def fake_login(session, base_url, path, app_key, secret_key, source):
        calls.append(path)
        return f"TOKEN_FOR_{path}"

    monkeypatch.setattr(xts, "_login", fake_login)
    client = xts.XTSDataClient.from_env()
    assert client.market_token == "TOKEN_FOR_/apibinarymarketdata/auth/login"
    assert client.interactive_token == "TOKEN_FOR_/interactive/user/session"
    assert len(calls) == 2  # both logins actually happened
    cached = sc.read_cache("https://x")
    assert cached == {
        "base_url": "https://x",
        "market_token": "TOKEN_FOR_/apibinarymarketdata/auth/login",
        "interactive_token": "TOKEN_FOR_/interactive/user/session",
    }


def test_from_env_adopts_cached_tokens_without_logging_in(monkeypatch):
    _set_env(monkeypatch)
    sc.write_cache("https://x", "CACHED_MARKET", "CACHED_INTERACTIVE")

    def fake_login(*a, **k):
        raise AssertionError("should not log in -- a valid cache entry exists")

    monkeypatch.setattr(xts, "_login", fake_login)
    client = xts.XTSDataClient.from_env()
    assert client.market_token == "CACHED_MARKET"
    assert client.interactive_token == "CACHED_INTERACTIVE"


def test_relogin_market_adopts_a_token_another_process_already_refreshed(monkeypatch):
    _set_env(monkeypatch)

    def fake_login(session, base_url, path, app_key, secret_key, source):
        return "FIRST_LOGIN_TOKEN"

    monkeypatch.setattr(xts, "_login", fake_login)
    client = xts.XTSDataClient.from_env()
    assert client.market_token == "FIRST_LOGIN_TOKEN"

    # Another process refreshed the market token while ours went stale.
    sc.write_cache("https://x", "SOMEONE_ELSES_FRESH_TOKEN", client.interactive_token)

    def fail_if_called(*a, **k):
        raise AssertionError("should not log in -- should adopt the cached token instead")

    monkeypatch.setattr(xts, "_login", fail_if_called)
    new_token = client._relogin_market()
    assert new_token == "SOMEONE_ELSES_FRESH_TOKEN"
    assert client.market_token == "FIRST_LOGIN_TOKEN"  # relogin() returns it; caller assigns it


def test_relogin_market_logs_in_when_cache_is_also_stale(monkeypatch):
    _set_env(monkeypatch)
    monkeypatch.setattr(xts, "_login", lambda *a, **k: "FIRST_LOGIN_TOKEN")
    client = xts.XTSDataClient.from_env()

    relogin_calls = []

    def fake_relogin(session, base_url, path, app_key, secret_key, source):
        relogin_calls.append(path)
        return "FRESH_TOKEN_FROM_US"

    monkeypatch.setattr(xts, "_login", fake_relogin)
    new_token = client._relogin_market()
    assert new_token == "FRESH_TOKEN_FROM_US"
    assert relogin_calls == ["/apibinarymarketdata/auth/login"]
    assert sc.read_cache("https://x")["market_token"] == "FRESH_TOKEN_FROM_US"


def test_relogin_interactive_preserves_the_other_tokens_cache_entry(monkeypatch):
    _set_env(monkeypatch)
    monkeypatch.setattr(xts, "_login", lambda *a, **k: "FIRST_LOGIN_TOKEN")
    client = xts.XTSDataClient.from_env()

    monkeypatch.setattr(xts, "_login", lambda *a, **k: "NEW_INTERACTIVE_TOKEN")
    client._relogin_interactive()
    cached = sc.read_cache("https://x")
    assert cached["interactive_token"] == "NEW_INTERACTIVE_TOKEN"
    assert cached["market_token"] == "FIRST_LOGIN_TOKEN"  # untouched

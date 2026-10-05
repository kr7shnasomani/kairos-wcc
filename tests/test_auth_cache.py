"""Verified-token cache (auth hot path) — pure logic, no network."""

from api import dependencies as deps


def _clear():
    deps._auth_cache.clear()


def test_cache_put_and_get():
    _clear()
    user = {"user_id": "u1", "role": "engineer"}
    deps._auth_cache_put("tok-abc", user, ttl=60)
    assert deps._auth_cache_get("tok-abc") == user


def test_cache_disabled_when_ttl_zero():
    _clear()
    deps._auth_cache_put("tok-x", {"user_id": "u"}, ttl=0)
    assert deps._auth_cache_get("tok-x") is None  # ttl<=0 → not cached (strict mode)


def test_cache_miss_for_unknown_token():
    _clear()
    assert deps._auth_cache_get("never-seen") is None


def test_cache_expiry_bounds_revocation_staleness(monkeypatch):
    _clear()
    clock = [1000.0]
    monkeypatch.setattr(deps.time, "monotonic", lambda: clock[0])
    deps._auth_cache_put("tok-exp", {"user_id": "u"}, ttl=60)
    assert deps._auth_cache_get("tok-exp") is not None   # within TTL → served from cache
    clock[0] += 61                                        # past TTL
    assert deps._auth_cache_get("tok-exp") is None        # re-verify (revocation catches up)

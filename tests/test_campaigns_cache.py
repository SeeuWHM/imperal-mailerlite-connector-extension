"""Unit tests for the campaigns-list/detail ctx.cache wiring added to
panels.py and panels_workspace.py (sidebar "Recent campaigns", workspace
overview list, workspace single-campaign detail) — no network.

Mirrors bing-webmaster-connector/gsc-connector's cache_helpers test pattern:
a fake CacheClient standing in for imperal_sdk's real ctx.cache contract
(get_or_fetch: miss -> fetch + store; hit -> never re-fetch).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from cache_models import CampaignsPayload, campaigns_cache_key
from panels import _fetch_campaigns_payload
from panels_workspace import _fetch_campaigns


class _FakeCacheClient:
    def __init__(self):
        self.store: dict[str, object] = {}
        self.fetch_calls = 0

    async def get_or_fetch(self, key, model, fetcher, ttl_seconds=60):
        if key in self.store:
            return self.store[key]
        self.fetch_calls += 1
        value = await fetcher()
        self.store[key] = value
        return value


def test_campaigns_cache_key_differs_per_scope_account_and_extra():
    a = campaigns_cache_key("sidebar_recent", "key-1")
    b = campaigns_cache_key("workspace_overview", "key-1")
    c = campaigns_cache_key("sidebar_recent", "key-2")
    d = campaigns_cache_key("workspace_detail", "key-1", "campaign-42")
    assert len({a, b, c, d}) == 4
    for k in (a, b, c, d):
        assert k.startswith("mailerlite-camp-")
        assert len(k) <= 128


@pytest.mark.asyncio
async def test_fetch_campaigns_payload_wraps_ml_get(monkeypatch):
    calls = []

    async def fake_ml_get(ctx, api_key, path, params=None):
        calls.append((api_key, path, params))
        return {"data": [{"id": "1", "name": "Hello"}]}

    monkeypatch.setattr("panels.ml_get", fake_ml_get)

    payload = await _fetch_campaigns_payload(None, "key-abc", "campaigns", {"limit": 8})
    assert isinstance(payload, CampaignsPayload)
    assert payload.data == {"data": [{"id": "1", "name": "Hello"}]}
    assert calls == [("key-abc", "campaigns", {"limit": 8})]


@pytest.mark.asyncio
async def test_fetch_campaigns_wraps_ml_get_for_workspace(monkeypatch):
    async def fake_ml_get(ctx, api_key, path, params=None):
        return {"data": {"id": "42", "name": "Detail"}}

    monkeypatch.setattr("panels_workspace.ml_get", fake_ml_get)

    payload = await _fetch_campaigns(None, "key-abc", "campaigns/42")
    assert isinstance(payload, CampaignsPayload)
    assert payload.data == {"data": {"id": "42", "name": "Detail"}}


@pytest.mark.asyncio
async def test_cache_serves_repeat_calls_without_refetching():
    cache = _FakeCacheClient()
    calls = []

    async def fetcher():
        calls.append(1)
        return CampaignsPayload(data={"data": []})

    key = campaigns_cache_key("workspace_overview", "key-1")
    first = await cache.get_or_fetch(key, CampaignsPayload, fetcher, ttl_seconds=180)
    second = await cache.get_or_fetch(key, CampaignsPayload, fetcher, ttl_seconds=180)

    assert first is second
    assert len(calls) == 1
    assert cache.fetch_calls == 1

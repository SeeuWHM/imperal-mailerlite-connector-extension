"""Unit tests for handlers_webhooks_reference.py — no network."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from imperal_sdk.testing import MockContext
from imperal_sdk.testing.mock_secrets import MockSecretStore

import handlers_webhooks_reference as hw
from params import CreateWebhookParams, EmptyParams, WebhookIdParams


def _ctx() -> MockContext:
    ctx = MockContext(user_id="tenant-abc-123")
    ctx.secrets = MockSecretStore({"mailerlite_accounts": '[{"label":"Main","api_key":"key-1","is_active":true}]'})
    return ctx


WEBHOOK_ROW = {"id": "w1", "name": "My hook", "url": "https://example.com/hook", "events": ["subscriber.created"], "enabled": True}


@pytest.mark.asyncio
async def test_list_webhooks_success(monkeypatch):
    ctx = _ctx()

    async def fake_get(ctx, key, path):
        assert path == "webhooks"
        return {"data": [WEBHOOK_ROW]}

    monkeypatch.setattr(hw, "ml_get", fake_get)
    result = await hw.fn_list_webhooks(ctx, EmptyParams())
    assert result.status == "success"
    assert result.data.webhooks[0].event == "subscriber.created"


@pytest.mark.asyncio
async def test_create_webhook_sends_events_list_not_singular(monkeypatch):
    """Confirmed live: MailerLite requires `events` (a list), not `event`."""
    ctx = _ctx()
    seen = {}

    async def fake_post(ctx, key, path, body):
        seen["body"] = body
        return {"data": WEBHOOK_ROW}

    monkeypatch.setattr(hw, "ml_post", fake_post)
    result = await hw.fn_create_webhook(
        ctx, CreateWebhookParams(name="My hook", events=["subscriber.created"], url="https://example.com/hook")
    )
    assert result.status == "success"
    assert seen["body"]["events"] == ["subscriber.created"]
    assert "event" not in seen["body"] or "events" in seen["body"]


@pytest.mark.asyncio
async def test_create_webhook_batchable_flag_passed(monkeypatch):
    ctx = _ctx()
    seen = {}

    async def fake_post(ctx, key, path, body):
        seen["body"] = body
        return {"data": WEBHOOK_ROW}

    monkeypatch.setattr(hw, "ml_post", fake_post)
    await hw.fn_create_webhook(
        ctx, CreateWebhookParams(name="My hook", events=["campaign.click"], url="https://example.com/hook", batchable=True)
    )
    assert seen["body"]["batchable"] is True


@pytest.mark.asyncio
async def test_delete_webhook_success(monkeypatch):
    ctx = _ctx()

    async def fake_delete(ctx, key, path):
        assert path == "webhooks/w1"
        return {}

    monkeypatch.setattr(hw, "ml_delete", fake_delete)
    result = await hw.fn_delete_webhook(ctx, WebhookIdParams(webhook_id="w1"))
    assert result.status == "success"


@pytest.mark.asyncio
async def test_list_campaign_languages_success(monkeypatch):
    ctx = _ctx()

    async def fake_get(ctx, key, path):
        assert path == "campaigns/languages"
        return {"data": [{"id": "1", "shortcode": "en", "name": "English"}]}

    monkeypatch.setattr(hw, "ml_get", fake_get)
    result = await hw.fn_list_campaign_languages(ctx, EmptyParams())
    assert result.status == "success"
    assert result.data.languages[0].shortcode == "en"


@pytest.mark.asyncio
async def test_list_timezones_success(monkeypatch):
    ctx = _ctx()

    async def fake_get(ctx, key, path):
        assert path == "timezones"
        return {"data": [{"id": "1", "name": "UTC"}]}

    monkeypatch.setattr(hw, "ml_get", fake_get)
    result = await hw.fn_list_timezones(ctx, EmptyParams())
    assert result.status == "success"
    assert result.data.timezones[0].name == "UTC"


@pytest.mark.asyncio
async def test_no_account_returns_error():
    ctx = MockContext(user_id="empty-tenant")
    ctx.secrets = MockSecretStore({})
    result = await hw.fn_list_webhooks(ctx, EmptyParams())
    assert result.status == "error"

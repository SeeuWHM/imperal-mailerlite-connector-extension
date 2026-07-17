"""Unit tests for handlers_subscribers.py — no network."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from imperal_sdk.testing import MockContext
from imperal_sdk.testing.mock_secrets import MockSecretStore

import handlers_subscribers as hs
from ml_api import MailerLiteError
from params import GroupSubscriberParams, ListSubscribersParams, SubscriberIdParams, UpsertSubscriberParams


def _ctx() -> MockContext:
    ctx = MockContext(user_id="tenant-abc-123")
    ctx.secrets = MockSecretStore({"mailerlite_accounts": '[{"label":"Main","api_key":"key-1","is_active":true}]'})
    return ctx


SAMPLE_ROW = {
    "id": "123", "email": "a@b.com", "status": "active", "source": "api",
    "sent": 5, "opens_count": 3, "clicks_count": 1, "open_rate": 60.0, "click_rate": 20.0,
    "subscribed_at": "2026-01-01 00:00:00", "unsubscribed_at": None,
    "fields": {"name": "Alice"}, "groups": [{"id": "g1"}, "g2"],
}


@pytest.mark.asyncio
async def test_list_subscribers_no_account_errors():
    ctx = MockContext(user_id="empty-tenant")
    ctx.secrets = MockSecretStore({})
    result = await hs.fn_list_subscribers(ctx, ListSubscribersParams())
    assert result.status == "error"


@pytest.mark.asyncio
async def test_list_subscribers_success(monkeypatch):
    ctx = _ctx()

    async def fake_get(ctx, key, path, params=None):
        assert path == "subscribers"
        assert params["limit"] == 25
        return {"data": [SAMPLE_ROW], "meta": {"next_cursor": "abc"}}

    monkeypatch.setattr(hs, "ml_get", fake_get)
    result = await hs.fn_list_subscribers(ctx, ListSubscribersParams())
    assert result.status == "success"
    assert result.data.count == 1
    assert result.data.subscribers[0].email == "a@b.com"
    assert result.data.subscribers[0].groups == ["g1", "g2"]
    assert result.data.next_cursor == "abc"


@pytest.mark.asyncio
async def test_list_subscribers_with_status_filter(monkeypatch):
    ctx = _ctx()
    seen = {}

    async def fake_get(ctx, key, path, params=None):
        seen.update(params)
        return {"data": []}

    monkeypatch.setattr(hs, "ml_get", fake_get)
    await hs.fn_list_subscribers(ctx, ListSubscribersParams(status="active", cursor="xyz"))
    assert seen["filter[status]"] == "active"
    assert seen["cursor"] == "xyz"


@pytest.mark.asyncio
async def test_upsert_subscriber_success(monkeypatch):
    ctx = _ctx()

    async def fake_post(ctx, key, path, json=None):
        assert path == "subscribers"
        assert json["email"] == "new@x.com"
        return {"data": SAMPLE_ROW}

    monkeypatch.setattr(hs, "ml_post", fake_post)
    result = await hs.fn_upsert_subscriber(ctx, UpsertSubscriberParams(email="new@x.com"))
    assert result.status == "success"
    assert result.data.email == "a@b.com"


@pytest.mark.asyncio
async def test_upsert_subscriber_plan_restricted_error(monkeypatch):
    ctx = _ctx()

    async def fake_post(ctx, key, path, json=None):
        raise MailerLiteError("Content submission is only available on Premium plan.", 422, plan_restricted=True)

    monkeypatch.setattr(hs, "ml_post", fake_post)
    result = await hs.fn_upsert_subscriber(ctx, UpsertSubscriberParams(email="new@x.com"))
    assert result.status == "error"
    assert "Premium plan" in result.error


@pytest.mark.asyncio
async def test_get_subscriber_success(monkeypatch):
    ctx = _ctx()

    async def fake_get(ctx, key, path):
        assert path == "subscribers/123"
        return {"data": SAMPLE_ROW}

    monkeypatch.setattr(hs, "ml_get", fake_get)
    result = await hs.fn_get_subscriber(ctx, SubscriberIdParams(subscriber_id="123"))
    assert result.status == "success"
    assert result.data.id == "123"


@pytest.mark.asyncio
async def test_subscriber_activity_404_means_no_activity_yet(monkeypatch):
    ctx = _ctx()

    async def fake_get(ctx, key, path):
        raise MailerLiteError("Resource does not exist.", 404)

    monkeypatch.setattr(hs, "ml_get", fake_get)
    result = await hs.fn_subscriber_activity(ctx, SubscriberIdParams(subscriber_id="999"))
    assert result.status == "success"
    assert result.data.has_no_activity_yet is True
    assert result.data.count == 0


@pytest.mark.asyncio
async def test_subscriber_activity_with_rows(monkeypatch):
    ctx = _ctx()

    async def fake_get(ctx, key, path):
        return {"data": [{"type": "open", "date": "2026-01-01"}]}

    monkeypatch.setattr(hs, "ml_get", fake_get)
    result = await hs.fn_subscriber_activity(ctx, SubscriberIdParams(subscriber_id="123"))
    assert result.status == "success"
    assert result.data.count == 1
    assert result.data.rows[0].activity_type == "open"


@pytest.mark.asyncio
async def test_subscriber_activity_other_error_propagates(monkeypatch):
    ctx = _ctx()

    async def fake_get(ctx, key, path):
        raise MailerLiteError("Server error", 500)

    monkeypatch.setattr(hs, "ml_get", fake_get)
    result = await hs.fn_subscriber_activity(ctx, SubscriberIdParams(subscriber_id="123"))
    assert result.status == "error"


@pytest.mark.asyncio
async def test_add_and_remove_subscriber_group(monkeypatch):
    ctx = _ctx()
    calls = []

    async def fake_post(ctx, key, path):
        calls.append(("post", path))
        return {}

    async def fake_delete(ctx, key, path):
        calls.append(("delete", path))
        return {}

    monkeypatch.setattr(hs, "ml_post", fake_post)
    monkeypatch.setattr(hs, "ml_delete", fake_delete)

    added = await hs.fn_add_subscriber_to_group(ctx, GroupSubscriberParams(subscriber_id="123", group_id="g1"))
    assert added.status == "success"
    removed = await hs.fn_remove_subscriber_from_group(ctx, GroupSubscriberParams(subscriber_id="123", group_id="g1"))
    assert removed.status == "success"
    assert calls == [("post", "subscribers/123/groups/g1"), ("delete", "subscribers/123/groups/g1")]


@pytest.mark.asyncio
async def test_delete_subscriber(monkeypatch):
    ctx = _ctx()

    async def fake_delete(ctx, key, path):
        assert path == "subscribers/123"
        return {}

    monkeypatch.setattr(hs, "ml_delete", fake_delete)
    result = await hs.fn_delete_subscriber(ctx, SubscriberIdParams(subscriber_id="123"))
    assert result.status == "success"
    assert result.data.deleted is True


@pytest.mark.asyncio
async def test_forget_subscriber(monkeypatch):
    ctx = _ctx()

    async def fake_post(ctx, key, path):
        assert path == "subscribers/123/forget"
        return {}

    monkeypatch.setattr(hs, "ml_post", fake_post)
    result = await hs.fn_forget_subscriber(ctx, SubscriberIdParams(subscriber_id="123"))
    assert result.status == "success"
    assert result.data.deleted is True

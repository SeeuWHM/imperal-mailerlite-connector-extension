"""Unit tests for handlers_groups_segments.py — no network."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from imperal_sdk.testing import MockContext
from imperal_sdk.testing.mock_secrets import MockSecretStore

import handlers_groups_segments as hg
from params import (
    CreateGroupParams, GroupIdParams, GroupSubscribersParams, ListGroupsParams,
    ListSegmentsParams, RenameGroupParams, RenameSegmentParams, SegmentIdParams, SegmentSubscribersParams,
)


def _ctx() -> MockContext:
    ctx = MockContext(user_id="tenant-abc-123")
    ctx.secrets = MockSecretStore({"mailerlite_accounts": '[{"label":"Main","api_key":"key-1","is_active":true}]'})
    return ctx


GROUP_ROW = {
    "id": "g1", "name": "Newsletter", "active_count": 100, "sent_count": 50,
    "open_rate": {"float": 42.5}, "click_rate": {"float": 10.0},
    "unsubscribed_count": 2, "created_at": "2026-01-01",
}

SEGMENT_ROW = {
    "id": "s1", "name": "Engaged", "total": 30,
    "open_rate": {"float": 80.0}, "click_rate": {"float": 30.0},
    "created_at": "2026-01-01", "automations_using_segment_count": 1,
}


@pytest.mark.asyncio
async def test_list_groups_success(monkeypatch):
    ctx = _ctx()

    async def fake_get(ctx, key, path, params=None):
        assert path == "groups"
        return {"data": [GROUP_ROW]}

    monkeypatch.setattr(hg, "ml_get", fake_get)
    result = await hg.fn_list_groups(ctx, ListGroupsParams())
    assert result.status == "success"
    assert result.data.count == 1
    assert result.data.groups[0].open_rate == 42.5


@pytest.mark.asyncio
async def test_list_groups_with_name_filter(monkeypatch):
    ctx = _ctx()
    seen = {}

    async def fake_get(ctx, key, path, params=None):
        seen.update(params)
        return {"data": []}

    monkeypatch.setattr(hg, "ml_get", fake_get)
    await hg.fn_list_groups(ctx, ListGroupsParams(name_contains="News"))
    assert seen["filter[name]"] == "News"


@pytest.mark.asyncio
async def test_create_rename_delete_group(monkeypatch):
    ctx = _ctx()

    async def fake_post(ctx, key, path, json=None):
        assert json == {"name": "New Group"}
        return {"data": GROUP_ROW}

    async def fake_put(ctx, key, path, json=None):
        assert path == "groups/g1"
        return {"data": {**GROUP_ROW, "name": "Renamed"}}

    async def fake_delete(ctx, key, path):
        assert path == "groups/g1"
        return {}

    monkeypatch.setattr(hg, "ml_post", fake_post)
    monkeypatch.setattr(hg, "ml_put", fake_put)
    monkeypatch.setattr(hg, "ml_delete", fake_delete)

    created = await hg.fn_create_group(ctx, CreateGroupParams(name="New Group"))
    assert created.status == "success"

    renamed = await hg.fn_rename_group(ctx, RenameGroupParams(group_id="g1", name="Renamed"))
    assert renamed.status == "success"
    assert renamed.data.name == "Renamed"

    deleted = await hg.fn_delete_group(ctx, GroupIdParams(group_id="g1"))
    assert deleted.status == "success"
    assert deleted.data.deleted is True


@pytest.mark.asyncio
async def test_group_subscribers(monkeypatch):
    ctx = _ctx()

    async def fake_get(ctx, key, path, params=None):
        assert path == "groups/g1/subscribers"
        return {"data": [], "meta": {}}

    monkeypatch.setattr(hg, "ml_get", fake_get)
    result = await hg.fn_group_subscribers(ctx, GroupSubscribersParams(group_id="g1"))
    assert result.status == "success"
    assert result.data.count == 0


@pytest.mark.asyncio
async def test_list_segments_success(monkeypatch):
    ctx = _ctx()

    async def fake_get(ctx, key, path, params=None):
        assert path == "segments"
        return {"data": [SEGMENT_ROW]}

    monkeypatch.setattr(hg, "ml_get", fake_get)
    result = await hg.fn_list_segments(ctx, ListSegmentsParams())
    assert result.status == "success"
    assert result.data.segments[0].automations_using_segment_count == 1


@pytest.mark.asyncio
async def test_rename_and_delete_segment(monkeypatch):
    ctx = _ctx()

    async def fake_put(ctx, key, path, json=None):
        assert path == "segments/s1"
        return {"data": {**SEGMENT_ROW, "name": "Renamed"}}

    async def fake_delete(ctx, key, path):
        assert path == "segments/s1"
        return {}

    monkeypatch.setattr(hg, "ml_put", fake_put)
    monkeypatch.setattr(hg, "ml_delete", fake_delete)

    renamed = await hg.fn_rename_segment(ctx, RenameSegmentParams(segment_id="s1", name="Renamed"))
    assert renamed.status == "success"
    assert renamed.data.name == "Renamed"

    deleted = await hg.fn_delete_segment(ctx, SegmentIdParams(segment_id="s1"))
    assert deleted.status == "success"


@pytest.mark.asyncio
async def test_segment_subscribers(monkeypatch):
    ctx = _ctx()

    async def fake_get(ctx, key, path, params=None):
        assert path == "segments/s1/subscribers"
        return {"data": []}

    monkeypatch.setattr(hg, "ml_get", fake_get)
    result = await hg.fn_segment_subscribers(ctx, SegmentSubscribersParams(segment_id="s1"))
    assert result.status == "success"


@pytest.mark.asyncio
async def test_no_account_errors():
    ctx = MockContext(user_id="empty")
    ctx.secrets = MockSecretStore({})
    result = await hg.fn_list_groups(ctx, ListGroupsParams())
    assert result.status == "error"

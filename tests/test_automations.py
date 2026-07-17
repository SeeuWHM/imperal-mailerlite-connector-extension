"""Unit tests for handlers_automations.py — no network."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from imperal_sdk.testing import MockContext
from imperal_sdk.testing.mock_secrets import MockSecretStore

import handlers_automations as ha
from ml_api import MailerLiteError
from params import AutomationActivityParams, AutomationIdParams, CreateAutomationDraftParams, ListAutomationsParams


def _ctx() -> MockContext:
    ctx = MockContext(user_id="tenant-abc-123")
    ctx.secrets = MockSecretStore({"mailerlite_accounts": '[{"label":"Main","api_key":"key-1","is_active":true}]'})
    return ctx


AUTOMATION_ROW = {"id": "a1", "name": "Welcome series", "enabled": True, "created_at": "2026-01-01"}


@pytest.mark.asyncio
async def test_list_automations_success(monkeypatch):
    ctx = _ctx()

    async def fake_get(ctx, key, path, query=None):
        assert path == "automations"
        return {"data": [AUTOMATION_ROW]}

    monkeypatch.setattr(ha, "ml_get", fake_get)
    result = await ha.fn_list_automations(ctx, ListAutomationsParams())
    assert result.status == "success"
    assert result.data.count == 1
    assert result.data.automations[0].name == "Welcome series"


@pytest.mark.asyncio
async def test_get_automation_success(monkeypatch):
    ctx = _ctx()

    async def fake_get(ctx, key, path):
        assert path == "automations/a1"
        return {"data": AUTOMATION_ROW}

    monkeypatch.setattr(ha, "ml_get", fake_get)
    result = await ha.fn_get_automation(ctx, AutomationIdParams(automation_id="a1"))
    assert result.status == "success"
    assert result.data.id == "a1"


@pytest.mark.asyncio
async def test_automation_activity_success(monkeypatch):
    ctx = _ctx()

    async def fake_get(ctx, key, path, query=None):
        assert path == "automations/a1/activity"
        assert query["filter[status]"] == "completed"
        return {"data": [{"status": "completed", "date": "2026-01-01", "reason": None}]}

    monkeypatch.setattr(ha, "ml_get", fake_get)
    result = await ha.fn_automation_activity(
        ctx, AutomationActivityParams(automation_id="a1", status="completed")
    )
    assert result.status == "success"
    assert result.data.count == 1


@pytest.mark.asyncio
async def test_automation_activity_404_returns_empty_not_error(monkeypatch):
    ctx = _ctx()

    async def fake_get(ctx, key, path, query=None):
        raise MailerLiteError("Resource does not exist.", status_code=404)

    monkeypatch.setattr(ha, "ml_get", fake_get)
    result = await ha.fn_automation_activity(
        ctx, AutomationActivityParams(automation_id="a1", status="active")
    )
    assert result.status == "success"
    assert result.data.count == 0


@pytest.mark.asyncio
async def test_create_automation_draft_success(monkeypatch):
    ctx = _ctx()

    async def fake_post(ctx, key, path, body):
        assert path == "automations"
        assert body == {"name": "My draft"}
        return {"data": {**AUTOMATION_ROW, "name": "My draft"}}

    monkeypatch.setattr(ha, "ml_post", fake_post)
    result = await ha.fn_create_automation_draft(ctx, CreateAutomationDraftParams(name="My draft"))
    assert result.status == "success"
    assert "My draft" in result.summary
    assert "MailerLite's UI" in result.summary


@pytest.mark.asyncio
async def test_delete_automation_success(monkeypatch):
    ctx = _ctx()
    seen = {}

    async def fake_delete(ctx, key, path):
        seen["path"] = path
        return {}

    monkeypatch.setattr(ha, "ml_delete", fake_delete)
    result = await ha.fn_delete_automation(ctx, AutomationIdParams(automation_id="a1"))
    assert result.status == "success"
    assert seen["path"] == "automations/a1"


@pytest.mark.asyncio
async def test_no_account_returns_error():
    ctx = MockContext(user_id="empty-tenant")
    ctx.secrets = MockSecretStore({})
    result = await ha.fn_list_automations(ctx, ListAutomationsParams())
    assert result.status == "error"

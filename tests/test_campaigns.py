"""Unit tests for handlers_campaigns.py — no network."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from imperal_sdk.testing import MockContext
from imperal_sdk.testing.mock_secrets import MockSecretStore

import handlers_campaigns as hc
from ml_api import MailerLiteError
from params import CampaignIdParams, CreateCampaignParams, ListCampaignsParams, ScheduleCampaignParams


def _ctx() -> MockContext:
    ctx = MockContext(user_id="tenant-abc-123")
    ctx.secrets = MockSecretStore({"mailerlite_accounts": '[{"label":"Main","api_key":"key-1","is_active":true}]'})
    return ctx


CAMPAIGN_ROW = {
    "id": "c1", "name": "Spring Sale", "type": "regular", "status": "draft",
    "emails": [{"subject": "Save big!"}], "missing_data": [], "created_at": "2026-01-01",
    "scheduled_for": None,
}


@pytest.mark.asyncio
async def test_list_campaigns_success(monkeypatch):
    ctx = _ctx()
    seen = {}

    async def fake_get(ctx, key, path, params=None):
        seen["path"] = path
        seen["params"] = params
        return {"data": [CAMPAIGN_ROW]}

    monkeypatch.setattr(hc, "ml_get", fake_get)
    result = await hc.fn_list_campaigns(ctx, ListCampaignsParams())
    assert result.status == "success"
    assert seen["path"] == "campaigns"
    assert result.data.campaigns[0].subject == "Save big!"


@pytest.mark.asyncio
async def test_list_campaigns_snaps_invalid_limit(monkeypatch):
    ctx = _ctx()
    seen = {}

    async def fake_get(ctx, key, path, params=None):
        seen.update(params)
        return {"data": []}

    monkeypatch.setattr(hc, "ml_get", fake_get)
    await hc.fn_list_campaigns(ctx, ListCampaignsParams(limit=7))
    # 7 isn't in the whitelist {1,10,25,50,100} — validate_campaigns_limit
    # must snap it to the nearest valid value, never pass 7 through raw.
    assert seen["limit"] in (1, 10, 25, 50, 100)


@pytest.mark.asyncio
async def test_get_campaign_success(monkeypatch):
    ctx = _ctx()

    async def fake_get(ctx, key, path):
        assert path == "campaigns/c1"
        return {"data": CAMPAIGN_ROW}

    monkeypatch.setattr(hc, "ml_get", fake_get)
    result = await hc.fn_get_campaign(ctx, CampaignIdParams(campaign_id="c1"))
    assert result.status == "success"
    assert result.data.id == "c1"


@pytest.mark.asyncio
async def test_create_campaign_success(monkeypatch):
    ctx = _ctx()

    async def fake_post(ctx, key, path, body=None):
        assert path == "campaigns"
        assert body["type"] == "regular"
        assert body["emails"][0]["subject"] == "Hello"
        return {"data": CAMPAIGN_ROW}

    monkeypatch.setattr(hc, "ml_post", fake_post)
    result = await hc.fn_create_campaign(ctx, CreateCampaignParams(
        name="Spring Sale", type="regular", subject="Hello", from_name="Me", from_email="me@x.com",
    ))
    assert result.status == "success"


@pytest.mark.asyncio
async def test_create_campaign_plan_restricted_records_verdict(monkeypatch):
    ctx = _ctx()
    recorded = {}

    async def fake_post(ctx, key, path, body=None):
        raise MailerLiteError(
            "Campaign types 'resend' and 'multivariate' are only available for accounts on growing or advanced plans.",
            422, plan_restricted=True,
        )

    async def fake_record_verdict(ctx, label, capability_key, restricted, message):
        recorded["capability_key"] = capability_key
        recorded["restricted"] = restricted

    monkeypatch.setattr(hc, "ml_post", fake_post)
    monkeypatch.setattr(hc, "record_verdict", fake_record_verdict)

    result = await hc.fn_create_campaign(ctx, CreateCampaignParams(
        name="X", type="resend", subject="Hi", from_name="Me", from_email="me@x.com",
    ))
    assert result.status == "error"
    assert "growing or advanced plans" in result.error
    assert recorded["capability_key"] == "campaign_type_resend_multivariate"
    assert recorded["restricted"] is True


@pytest.mark.asyncio
async def test_schedule_campaign_instant(monkeypatch):
    ctx = _ctx()
    seen = {}

    async def fake_post(ctx, key, path, body=None):
        seen["path"] = path
        seen["body"] = body
        return {"data": {**CAMPAIGN_ROW, "status": "ready"}}

    monkeypatch.setattr(hc, "ml_post", fake_post)
    result = await hc.fn_schedule_campaign(ctx, ScheduleCampaignParams(campaign_id="c1", delivery="instant"))
    assert result.status == "success"
    assert seen["path"] == "campaigns/c1/schedule"
    assert seen["body"] == {"delivery": "instant"}


@pytest.mark.asyncio
async def test_schedule_campaign_scheduled_builds_schedule_body(monkeypatch):
    ctx = _ctx()
    seen = {}

    async def fake_post(ctx, key, path, body=None):
        seen["body"] = body
        return {"data": CAMPAIGN_ROW}

    monkeypatch.setattr(hc, "ml_post", fake_post)
    await hc.fn_schedule_campaign(ctx, ScheduleCampaignParams(
        campaign_id="c1", delivery="scheduled", date="2026-08-01", hours="14", minutes="30", timezone_id="1",
    ))
    assert seen["body"]["schedule"] == {"date": "2026-08-01", "hours": "14", "minutes": "30", "timezone_id": "1"}


@pytest.mark.asyncio
async def test_cancel_campaign(monkeypatch):
    ctx = _ctx()

    async def fake_post(ctx, key, path):
        assert path == "campaigns/c1/cancel"
        return {"data": {**CAMPAIGN_ROW, "status": "canceled"}}

    monkeypatch.setattr(hc, "ml_post", fake_post)
    result = await hc.fn_cancel_campaign(ctx, CampaignIdParams(campaign_id="c1"))
    assert result.status == "success"


@pytest.mark.asyncio
async def test_delete_campaign(monkeypatch):
    ctx = _ctx()

    async def fake_delete(ctx, key, path):
        assert path == "campaigns/c1"
        return {}

    monkeypatch.setattr(hc, "ml_delete", fake_delete)
    result = await hc.fn_delete_campaign(ctx, CampaignIdParams(campaign_id="c1"))
    assert result.status == "success"
    assert result.data.deleted is True


@pytest.mark.asyncio
async def test_no_account_errors():
    ctx = MockContext(user_id="empty")
    ctx.secrets = MockSecretStore({})
    result = await hc.fn_list_campaigns(ctx, ListCampaignsParams())
    assert result.status == "error"

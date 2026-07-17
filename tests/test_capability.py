"""Unit tests for handlers_capability.py — no network."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from imperal_sdk.testing import MockContext
from imperal_sdk.testing.mock_secrets import MockSecretStore

import handlers_capability as hcap
from capability import GATED_HINTS, record_verdict
from params import EmptyParams


def _ctx() -> MockContext:
    ctx = MockContext(user_id="tenant-abc-123")
    ctx.secrets = MockSecretStore({"mailerlite_accounts": '[{"label":"Main","api_key":"key-1","is_active":true}]'})
    return ctx


@pytest.mark.asyncio
async def test_capability_status_no_account_errors():
    ctx = MockContext(user_id="empty-tenant")
    ctx.secrets = MockSecretStore({})
    result = await hcap.fn_mailerlite_capability_status(ctx, EmptyParams())
    assert result.status == "error"


@pytest.mark.asyncio
async def test_capability_status_returns_documented_hints_when_nothing_observed():
    ctx = _ctx()
    result = await hcap.fn_mailerlite_capability_status(ctx, EmptyParams())
    assert result.status == "success"
    assert result.data.count == len(GATED_HINTS)
    assert all(h.confirmed_restricted is None for h in result.data.hints)


@pytest.mark.asyncio
async def test_capability_status_surfaces_recorded_live_verdict():
    ctx = _ctx()
    await record_verdict(ctx, "Main", "campaign_rich_content", restricted=True, message="Content submission is only available on Premium plan.")

    result = await hcap.fn_mailerlite_capability_status(ctx, EmptyParams())
    assert result.status == "success"
    live = [h for h in result.data.hints if h.confirmed_restricted is not None]
    assert len(live) == 1
    assert live[0].capability_key == "campaign_rich_content"
    assert live[0].confirmed_restricted is True

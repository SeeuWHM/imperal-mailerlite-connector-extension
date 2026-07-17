"""Unit tests for handlers_accounts.py — no network. Mirrors
bing-webmaster-connector's test pattern: monkeypatch ml_get on the HANDLER
module (where it's imported and called), never on ml_api (where it's merely
defined) — patching the wrong one lets the real function run and hit the
network during tests.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from imperal_sdk.testing import MockContext
from imperal_sdk.testing.mock_secrets import MockSecretStore

import handlers_accounts
from params import AccountLabelParams, EmptyParams, SaveKeyParams


def _ctx(initial: dict | None = None) -> MockContext:
    ctx = MockContext(user_id="tenant-abc-123")
    ctx.secrets = MockSecretStore(initial or {})
    return ctx


async def _fake_ml_get_ok(ctx, key, path, params=None):
    return {"data": []}


# ─── connection_status ──────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_connection_status_not_connected():
    ctx = _ctx()
    result = await handlers_accounts.fn_connection_status(ctx, EmptyParams())
    assert result.status == "success"
    assert result.data.connected is False


@pytest.mark.asyncio
async def test_connection_status_connected(monkeypatch):
    ctx = _ctx()
    monkeypatch.setattr(handlers_accounts, "ml_get", _fake_ml_get_ok)
    await handlers_accounts.fn_save_mailerlite_key(ctx, SaveKeyParams(mailerlite_api_key="key-1", label=""))

    result = await handlers_accounts.fn_connection_status(ctx, EmptyParams())
    assert result.status == "success"
    assert result.data.connected is True
    assert result.data.masked_key == "••••ey-1"


# ─── save_mailerlite_key ─────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_save_mailerlite_key_success_adds_account(monkeypatch):
    ctx = _ctx()
    monkeypatch.setattr(handlers_accounts, "ml_get", _fake_ml_get_ok)
    result = await handlers_accounts.fn_save_mailerlite_key(
        ctx, SaveKeyParams(mailerlite_api_key="key-1", label="Agency"),
    )
    assert result.status == "success"
    assert result.data.label == "Agency"
    assert result.data.is_active is True


@pytest.mark.asyncio
async def test_save_mailerlite_key_rejects_invalid_key(monkeypatch):
    ctx = _ctx()
    from ml_api import MailerLiteError

    async def fake_ml_get_fail(ctx, key, path, params=None):
        raise MailerLiteError("Unauthenticated.", status_code=401)

    monkeypatch.setattr(handlers_accounts, "ml_get", fake_ml_get_fail)
    result = await handlers_accounts.fn_save_mailerlite_key(
        ctx, SaveKeyParams(mailerlite_api_key="bad-key", label=""),
    )
    assert result.status == "error"


# ─── list / switch / disconnect ─────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_list_mailerlite_accounts_empty():
    ctx = _ctx()
    result = await handlers_accounts.fn_list_mailerlite_accounts(ctx, EmptyParams())
    assert result.status == "success"
    assert result.data.count == 0


@pytest.mark.asyncio
async def test_switch_and_disconnect_account(monkeypatch):
    ctx = _ctx()
    monkeypatch.setattr(handlers_accounts, "ml_get", _fake_ml_get_ok)
    await handlers_accounts.fn_save_mailerlite_key(ctx, SaveKeyParams(mailerlite_api_key="key-1", label="First"))
    await handlers_accounts.fn_save_mailerlite_key(ctx, SaveKeyParams(mailerlite_api_key="key-2", label="Second"))

    switched = await handlers_accounts.fn_switch_mailerlite_account(ctx, AccountLabelParams(label="Second"))
    assert switched.status == "success"
    assert switched.data.active == "Second"

    disconnected = await handlers_accounts.fn_disconnect_mailerlite_account(ctx, AccountLabelParams(label="Second"))
    assert disconnected.status == "success"
    assert disconnected.data.remaining == 1


@pytest.mark.asyncio
async def test_switch_unknown_account_returns_error():
    ctx = _ctx()
    result = await handlers_accounts.fn_switch_mailerlite_account(ctx, AccountLabelParams(label="Ghost"))
    assert result.status == "error"

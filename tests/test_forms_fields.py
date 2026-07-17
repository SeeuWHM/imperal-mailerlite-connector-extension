"""Unit tests for handlers_forms_fields.py — no network."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from imperal_sdk.testing import MockContext
from imperal_sdk.testing.mock_secrets import MockSecretStore

import handlers_forms_fields as hf
from params import (
    CreateFieldParams, FieldIdParams, FormIdParams, FormSubscribersParams,
    ListFieldsParams, ListFormsParams, RenameFieldParams, RenameFormParams,
)


def _ctx() -> MockContext:
    ctx = MockContext(user_id="tenant-abc-123")
    ctx.secrets = MockSecretStore({"mailerlite_accounts": '[{"label":"Main","api_key":"key-1","is_active":true}]'})
    return ctx


FORM_ROW = {"id": "f1", "name": "Signup popup", "conversions_count": 10, "visitors": 100, "created_at": "2026-01-01"}
FIELD_ROW = {"id": "fd1", "name": "Birthday", "type": "date"}


@pytest.mark.asyncio
async def test_list_forms_uses_type_as_path_segment(monkeypatch):
    ctx = _ctx()
    seen = {}

    async def fake_get(ctx, key, path, query=None):
        seen["path"] = path
        return {"data": [FORM_ROW]}

    monkeypatch.setattr(hf, "ml_get", fake_get)
    result = await hf.fn_list_forms(ctx, ListFormsParams(form_type="popup"))
    assert result.status == "success"
    assert seen["path"] == "forms/popup"
    assert result.data.form_type == "popup"


@pytest.mark.asyncio
async def test_rename_form_success(monkeypatch):
    ctx = _ctx()

    async def fake_put(ctx, key, path, body):
        assert path == "forms/f1"
        assert body == {"name": "New name"}
        return {"data": {**FORM_ROW, "name": "New name"}}

    monkeypatch.setattr(hf, "ml_put", fake_put)
    result = await hf.fn_rename_form(ctx, RenameFormParams(form_id="f1", name="New name"))
    assert result.status == "success"
    assert result.data.name == "New name"


@pytest.mark.asyncio
async def test_delete_form_success(monkeypatch):
    ctx = _ctx()

    async def fake_delete(ctx, key, path):
        assert path == "forms/f1"
        return {}

    monkeypatch.setattr(hf, "ml_delete", fake_delete)
    result = await hf.fn_delete_form(ctx, FormIdParams(form_id="f1"))
    assert result.status == "success"


@pytest.mark.asyncio
async def test_form_subscribers_success(monkeypatch):
    ctx = _ctx()

    row = {
        "id": "s1", "email": "x@y.com", "status": "active", "source": "form",
        "sent": 0, "opens_count": 0, "clicks_count": 0, "open_rate": 0, "click_rate": 0,
        "subscribed_at": None, "unsubscribed_at": None, "fields": {}, "groups": [],
    }

    async def fake_get(ctx, key, path, query=None):
        assert path == "forms/f1/subscribers"
        return {"data": [row], "meta": {}}

    monkeypatch.setattr(hf, "ml_get", fake_get)
    result = await hf.fn_form_subscribers(ctx, FormSubscribersParams(form_id="f1"))
    assert result.status == "success"
    assert result.data.count == 1


@pytest.mark.asyncio
async def test_list_fields_success(monkeypatch):
    ctx = _ctx()

    async def fake_get(ctx, key, path, query=None):
        assert path == "fields"
        return {"data": [FIELD_ROW]}

    monkeypatch.setattr(hf, "ml_get", fake_get)
    result = await hf.fn_list_fields(ctx, ListFieldsParams())
    assert result.status == "success"
    assert result.data.fields[0].type == "date"


@pytest.mark.asyncio
async def test_create_field_success(monkeypatch):
    ctx = _ctx()

    async def fake_post(ctx, key, path, body):
        assert path == "fields"
        assert body == {"name": "Birthday", "type": "date"}
        return {"data": FIELD_ROW}

    monkeypatch.setattr(hf, "ml_post", fake_post)
    result = await hf.fn_create_field(ctx, CreateFieldParams(name="Birthday", field_type="date"))
    assert result.status == "success"
    assert result.data.name == "Birthday"


@pytest.mark.asyncio
async def test_rename_field_success(monkeypatch):
    ctx = _ctx()

    async def fake_put(ctx, key, path, body):
        assert path == "fields/fd1"
        return {"data": {**FIELD_ROW, "name": "DOB"}}

    monkeypatch.setattr(hf, "ml_put", fake_put)
    result = await hf.fn_rename_field(ctx, RenameFieldParams(field_id="fd1", name="DOB"))
    assert result.status == "success"
    assert result.data.name == "DOB"


@pytest.mark.asyncio
async def test_delete_field_success(monkeypatch):
    ctx = _ctx()

    async def fake_delete(ctx, key, path):
        assert path == "fields/fd1"
        return {}

    monkeypatch.setattr(hf, "ml_delete", fake_delete)
    result = await hf.fn_delete_field(ctx, FieldIdParams(field_id="fd1"))
    assert result.status == "success"


@pytest.mark.asyncio
async def test_no_account_returns_error():
    ctx = MockContext(user_id="empty-tenant")
    ctx.secrets = MockSecretStore({})
    result = await hf.fn_list_forms(ctx, ListFormsParams(form_type="popup"))
    assert result.status == "error"

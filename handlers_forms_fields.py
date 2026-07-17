"""Chat-function handlers: forms (list/get/rename/delete/subscribers — path
is /forms/{type}, type in popup/embedded/promotion, confirmed live — NOT a
query param as the prose docs implied) and fields (full CRUD — text/number/
date custom fields attachable to subscribers).
"""
from imperal_sdk.types import ActionResult

from app import chat
from accounts import _active_api_key
from ml_api import ml_get, ml_post, ml_put, ml_delete, ml_str, MailerLiteError
from params import (
    ListFormsParams, FormIdParams, RenameFormParams, FormSubscribersParams,
    ListFieldsParams, CreateFieldParams, FieldIdParams, RenameFieldParams,
)
from response_models import FormRecord, FormList, FieldRecord, FieldList, SubscriberList, DeletedResponse
from handlers_subscribers import _to_subscriber


async def _require_key(ctx) -> str:
    key = await _active_api_key(ctx)
    if not key:
        raise RuntimeError("No MailerLite account connected. Call save_mailerlite_key first.")
    return key


def _to_form(row: dict) -> FormRecord:
    return FormRecord(
        id=str(row.get("id", "")), name=ml_str(row, "name"),
        conversions_count=row.get("conversions_count", 0), visitors=row.get("visitors", 0),
        created_at=ml_str(row, "created_at"),
    )


def _to_field(row: dict) -> FieldRecord:
    return FieldRecord(id=str(row.get("id", "")), name=ml_str(row, "name"), type=ml_str(row, "type"))


@chat.function(
    "list_forms", action_type="read", chain_callable=True, data_model=FormList,
    description=(
        "List forms of one type: popup, embedded, or promotion (required — MailerLite has no combined "
        "'all forms' endpoint). Use for: list my popup/embedded forms."
    ),
)
async def fn_list_forms(ctx, params: ListFormsParams) -> ActionResult:
    """List forms of one type: popup, embedded, or promotion (required — MailerLite has no combined 'all forms' endpoint)."""
    try:
        key = await _require_key(ctx)
        query = {"limit": params.limit, "page": params.page}
        if params.name:
            query["filter[name]"] = params.name
        data = await ml_get(ctx, key, f"forms/{params.form_type}", query)
    except (MailerLiteError, RuntimeError) as e:
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    rows = data.get("data") or []
    result = FormList(forms=[_to_form(r) for r in rows], count=len(rows), form_type=params.form_type)
    return ActionResult.success(data=result, summary=f"{result.count} {params.form_type} form(s)")


@chat.function(
    "rename_form", action_type="write", event="mailerlite.form.updated", effects=["update:form"],
    data_model=FormRecord, description="Rename a form. Use for: rename this form.",
)
async def fn_rename_form(ctx, params: RenameFormParams) -> ActionResult:
    """Rename a form."""
    try:
        key = await _require_key(ctx)
        data = await ml_put(ctx, key, f"forms/{params.form_id}", {"name": params.name})
    except (MailerLiteError, RuntimeError) as e:
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    result = _to_form(data.get("data") or {})
    return ActionResult.success(data=result, summary=f"Renamed to '{result.name}'.", refresh_panels=["workspace"])


@chat.function(
    "delete_form", action_type="destructive", event="mailerlite.form.deleted", effects=["delete:form"],
    data_model=DeletedResponse, description="Permanently delete a form. Use for: delete this form.",
)
async def fn_delete_form(ctx, params: FormIdParams) -> ActionResult:
    """Permanently delete a form."""
    try:
        key = await _require_key(ctx)
        await ml_delete(ctx, key, f"forms/{params.form_id}")
    except (MailerLiteError, RuntimeError) as e:
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    return ActionResult.success(data=DeletedResponse(deleted=True), summary="Form deleted.", refresh_panels=["workspace"])


@chat.function(
    "form_subscribers", action_type="read", chain_callable=True, data_model=SubscriberList,
    description="List subscribers who signed up via a specific form. Use for: subscribers from this form.",
)
async def fn_form_subscribers(ctx, params: FormSubscribersParams) -> ActionResult:
    """List subscribers who signed up via a specific form."""
    try:
        key = await _require_key(ctx)
        query = {"limit": params.limit}
        if params.status:
            query["filter[status]"] = params.status
        if params.cursor:
            query["cursor"] = params.cursor
        data = await ml_get(ctx, key, f"forms/{params.form_id}/subscribers", query)
    except (MailerLiteError, RuntimeError) as e:
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    rows = data.get("data") or []
    meta = data.get("meta") or {}
    result = SubscriberList(subscribers=[_to_subscriber(r) for r in rows], count=len(rows), next_cursor=meta.get("next_cursor"))
    return ActionResult.success(data=result, summary=f"{result.count} subscriber(s) from this form")


# ── Fields ───────────────────────────────────────────────────────────────

@chat.function(
    "list_fields", action_type="read", chain_callable=True, data_model=FieldList,
    description="List custom subscriber fields (text/number/date). Use for: list custom fields.",
)
async def fn_list_fields(ctx, params: ListFieldsParams) -> ActionResult:
    """List custom subscriber fields (text/number/date)."""
    try:
        key = await _require_key(ctx)
        query = {"limit": params.limit, "page": params.page}
        if params.field_type:
            query["filter[type]"] = params.field_type
        data = await ml_get(ctx, key, "fields", query)
    except (MailerLiteError, RuntimeError) as e:
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    rows = data.get("data") or []
    result = FieldList(fields=[_to_field(r) for r in rows], count=len(rows))
    return ActionResult.success(data=result, summary=f"{result.count} custom field(s)")


@chat.function(
    "create_field", action_type="write", event="mailerlite.field.created", effects=["create:field"],
    data_model=FieldRecord,
    description="Create a custom subscriber field (type: text, number, or date). Use for: add a custom field.",
)
async def fn_create_field(ctx, params: CreateFieldParams) -> ActionResult:
    """Create a custom subscriber field (type: text, number, or date)."""
    try:
        key = await _require_key(ctx)
        data = await ml_post(ctx, key, "fields", {"name": params.name, "type": params.field_type})
    except (MailerLiteError, RuntimeError) as e:
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    result = _to_field(data.get("data") or {})
    return ActionResult.success(data=result, summary=f"Field '{result.name}' created.", refresh_panels=["workspace"])


@chat.function(
    "rename_field", action_type="write", event="mailerlite.field.updated", effects=["update:field"],
    data_model=FieldRecord, description="Rename a custom field. Use for: rename this field.",
)
async def fn_rename_field(ctx, params: RenameFieldParams) -> ActionResult:
    """Rename a custom field."""
    try:
        key = await _require_key(ctx)
        data = await ml_put(ctx, key, f"fields/{params.field_id}", {"name": params.name})
    except (MailerLiteError, RuntimeError) as e:
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    result = _to_field(data.get("data") or {})
    return ActionResult.success(data=result, summary=f"Renamed to '{result.name}'.", refresh_panels=["workspace"])


@chat.function(
    "delete_field", action_type="destructive", event="mailerlite.field.deleted", effects=["delete:field"],
    data_model=DeletedResponse, description="Permanently delete a custom field. Use for: delete this field.",
)
async def fn_delete_field(ctx, params: FieldIdParams) -> ActionResult:
    """Permanently delete a custom field."""
    try:
        key = await _require_key(ctx)
        await ml_delete(ctx, key, f"fields/{params.field_id}")
    except (MailerLiteError, RuntimeError) as e:
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    return ActionResult.success(data=DeletedResponse(deleted=True), summary="Field deleted.", refresh_panels=["workspace"])

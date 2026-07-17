"""Chat-function handlers: webhooks (full CRUD) and small read-only
reference lookups (campaign languages, timezones) used when creating/
scheduling campaigns.
"""
from imperal_sdk.types import ActionResult

from app import chat
from accounts import _active_api_key
from ml_api import ml_get, ml_post, ml_put, ml_delete, ml_str, MailerLiteError
from params import ListWebhooksParams, CreateWebhookParams, WebhookIdParams, EmptyParams
from response_models import WebhookRecord, WebhookList, DeletedResponse, LanguageRecord, LanguageList, TimezoneRecord, TimezoneList


async def _require_key(ctx) -> str:
    key = await _active_api_key(ctx)
    if not key:
        raise RuntimeError("No MailerLite account connected. Call save_mailerlite_key first.")
    return key


def _to_webhook(row: dict) -> WebhookRecord:
    # Confirmed live: MailerLite's real payload has `events` (a LIST), not a
    # singular `event` string, despite how some third-party mirrors describe
    # it. We surface it as a comma-joined string here for a simple display
    # field; nothing downstream needs the raw list.
    events = row.get("events") or []
    return WebhookRecord(
        id=str(row.get("id", "")), name=ml_str(row, "name"), event=", ".join(events),
        url=ml_str(row, "url"), enabled=bool(row.get("enabled", True)),
    )


@chat.function(
    "list_webhooks", action_type="read", chain_callable=True, data_model=WebhookList,
    description="List configured webhooks. Use for: покажи вебхуки, list my webhooks.",
)
async def fn_list_webhooks(ctx, params: EmptyParams) -> ActionResult:
    """List configured webhooks."""
    try:
        key = await _require_key(ctx)
        data = await ml_get(ctx, key, "webhooks")
    except (MailerLiteError, RuntimeError) as e:
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    rows = data.get("data") or []
    result = WebhookList(webhooks=[_to_webhook(r) for r in rows], count=len(rows))
    return ActionResult.success(data=result, summary=f"{result.count} webhook(s)")


@chat.function(
    "create_webhook", action_type="write", event="mailerlite.webhook.created", effects=["create:webhook"],
    data_model=WebhookRecord,
    description=(
        "Create a webhook for a MailerLite event (e.g. subscriber.created, campaign.sent — see MailerLite "
        "docs for the full event list). campaign.click/campaign.open/subscriber.deleted REQUIRE batchable=true "
        "(MailerLite's own requirement). Use for: создай вебхук, add a webhook for this event."
    ),
)
async def fn_create_webhook(ctx, params: CreateWebhookParams) -> ActionResult:
    """Create a webhook for a MailerLite event (e.g."""
    try:
        key = await _require_key(ctx)
        body = {"name": params.name, "events": params.events, "url": params.url}
        if params.batchable:
            body["batchable"] = True
        data = await ml_post(ctx, key, "webhooks", body)
    except (MailerLiteError, RuntimeError) as e:
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    result = _to_webhook(data.get("data") or {})
    return ActionResult.success(data=result, summary=f"Webhook '{result.name}' created.", refresh_panels=["workspace"])


@chat.function(
    "delete_webhook", action_type="destructive", event="mailerlite.webhook.deleted", effects=["delete:webhook"],
    data_model=DeletedResponse, description="Permanently delete a webhook. Use for: удали вебхук, delete this webhook.",
)
async def fn_delete_webhook(ctx, params: WebhookIdParams) -> ActionResult:
    """Permanently delete a webhook."""
    try:
        key = await _require_key(ctx)
        await ml_delete(ctx, key, f"webhooks/{params.webhook_id}")
    except (MailerLiteError, RuntimeError) as e:
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    return ActionResult.success(data=DeletedResponse(deleted=True), summary="Webhook deleted.", refresh_panels=["workspace"])


# ── Reference lookups ────────────────────────────────────────────────────

@chat.function(
    "list_campaign_languages", action_type="read", chain_callable=True, data_model=LanguageList,
    description="List valid language_id values for campaign unsubscribe-page language. Use for: какие языки доступны для кампании.",
)
async def fn_list_campaign_languages(ctx, params: EmptyParams) -> ActionResult:
    """List valid language_id values for campaign unsubscribe-page language."""
    try:
        key = await _require_key(ctx)
        data = await ml_get(ctx, key, "campaigns/languages")
    except (MailerLiteError, RuntimeError) as e:
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    rows = data.get("data") or []
    result = LanguageList(
        languages=[LanguageRecord(id=str(r.get("id", "")), shortcode=r.get("shortcode", ""), name=r.get("name", "")) for r in rows],
        count=len(rows),
    )
    return ActionResult.success(data=result, summary=f"{result.count} language(s)")


@chat.function(
    "list_timezones", action_type="read", chain_callable=True, data_model=TimezoneList,
    description="List valid timezone_id values for scheduling campaigns. Use for: какие таймзоны доступны.",
)
async def fn_list_timezones(ctx, params: EmptyParams) -> ActionResult:
    """List valid timezone_id values for scheduling campaigns."""
    try:
        key = await _require_key(ctx)
        data = await ml_get(ctx, key, "timezones")
    except (MailerLiteError, RuntimeError) as e:
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    rows = data.get("data") or []
    result = TimezoneList(
        timezones=[TimezoneRecord(id=str(r.get("id", "")), name=r.get("name", "")) for r in rows],
        count=len(rows),
    )
    return ActionResult.success(data=result, summary=f"{result.count} timezone(s)")

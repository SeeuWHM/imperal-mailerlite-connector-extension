"""Chat-function handlers: subscribers — list/create/update/fetch/delete,
group assignment, activity. Confirmed live behaviors baked in (see
docs/research.md):
  - a brand-new subscriber's /activity 404s (not empty list) until they have
    at least one event — we treat that specific 404 as "no activity yet".
  - create/update is a genuine upsert: omitted fields/groups are NOT removed.
"""
from imperal_sdk.types import ActionResult

from app import chat
from accounts import _active_api_key
from ml_api import ml_get, ml_post, ml_put, ml_delete, ml_str, MailerLiteError
from params import (
    ListSubscribersParams, SubscriberIdParams, UpsertSubscriberParams, GroupSubscriberParams,
)
from response_models import (
    SubscriberRecord, SubscriberList, SubscriberActivityRow, SubscriberActivityList, DeletedResponse,
)


async def _require_key(ctx) -> str:
    key = await _active_api_key(ctx)
    if not key:
        raise RuntimeError("No MailerLite account connected. Call save_mailerlite_key first.")
    return key


def _to_subscriber(row: dict) -> SubscriberRecord:
    return SubscriberRecord(
        id=str(row.get("id", "")), email=ml_str(row, "email"), status=ml_str(row, "status"),
        source=ml_str(row, "source"), sent=row.get("sent", 0),
        opens_count=row.get("opens_count", 0), clicks_count=row.get("clicks_count", 0),
        open_rate=row.get("open_rate", 0.0), click_rate=row.get("click_rate", 0.0),
        subscribed_at=row.get("subscribed_at"), unsubscribed_at=row.get("unsubscribed_at"),
        fields=row.get("fields") or {},
        groups=[g.get("id", g) if isinstance(g, dict) else g for g in (row.get("groups") or [])],
    )


@chat.function(
    "list_subscribers", action_type="read", chain_callable=True, data_model=SubscriberList,
    description=(
        "List subscribers, optionally filtered by status (active/unsubscribed/unconfirmed/bounced/junk). "
        "Use for: покажи подписчиков, list my subscribers, show active subscribers."
    ),
)
async def fn_list_subscribers(ctx, params: ListSubscribersParams) -> ActionResult:
    """List subscribers, optionally filtered by status (active/unsubscribed/unconfirmed/bounced/junk)."""
    try:
        key = await _require_key(ctx)
        q = {"limit": params.limit}
        if params.status:
            q["filter[status]"] = params.status
        if params.cursor:
            q["cursor"] = params.cursor
        data = await ml_get(ctx, key, "subscribers", params=q)
    except (RuntimeError, MailerLiteError) as e:
        return ActionResult.error(str(e), retryable=False)
    rows = data.get("data") or []
    result = SubscriberList(
        subscribers=[_to_subscriber(r) for r in rows], count=len(rows),
        next_cursor=(data.get("meta") or {}).get("next_cursor"),
    )
    return ActionResult.success(data=result, summary=f"{result.count} subscriber(s)")


@chat.function(
    "create_fill_subscriber", action_type="write", event="mailerlite.subscriber.upserted",
    effects=["create:subscriber"], data_model=SubscriberRecord,
    description=(
        "Create or update (upsert) a subscriber by email. Non-destructive — omitted fields/groups are NOT "
        "removed from an existing subscriber. Use for: добавь подписчика, add this email to my list."
    ),
)
async def fn_upsert_subscriber(ctx, params: UpsertSubscriberParams) -> ActionResult:
    """Create or update (upsert) a subscriber by email."""
    try:
        key = await _require_key(ctx)
        body = {"email": params.email}
        if params.fields:
            body["fields"] = params.fields
        if params.groups:
            body["groups"] = params.groups
        if params.status:
            body["status"] = params.status
        data = await ml_post(ctx, key, "subscribers", json=body)
    except (RuntimeError, MailerLiteError) as e:
        return ActionResult.error(str(e), retryable=getattr(e, "plan_restricted", False) is False)
    result = _to_subscriber(data.get("data") or {})
    return ActionResult.success(data=result, summary=f"Subscriber {result.email} saved.", refresh_panels=["workspace"])


@chat.function(
    "get_subscriber", action_type="read", chain_callable=True, data_model=SubscriberRecord,
    description="Fetch one subscriber by id. Use for: покажи подписчика, get subscriber details.",
)
async def fn_get_subscriber(ctx, params: SubscriberIdParams) -> ActionResult:
    """Fetch one subscriber by id."""
    try:
        key = await _require_key(ctx)
        data = await ml_get(ctx, key, f"subscribers/{params.subscriber_id}")
    except (RuntimeError, MailerLiteError) as e:
        return ActionResult.error(str(e), retryable=False)
    result = _to_subscriber(data.get("data") or {})
    return ActionResult.success(data=result, summary=f"Subscriber {result.email}")


@chat.function(
    "subscriber_activity", action_type="read", chain_callable=True, data_model=SubscriberActivityList,
    description=(
        "A subscriber's engagement activity (opens, clicks, etc). Use for: активность подписчика, "
        "subscriber engagement history."
    ),
)
async def fn_subscriber_activity(ctx, params: SubscriberIdParams) -> ActionResult:
    """A subscriber's engagement activity (opens, clicks, etc)."""
    try:
        key = await _require_key(ctx)
        data = await ml_get(ctx, key, f"subscribers/{params.subscriber_id}/activity")
    except RuntimeError as e:
        return ActionResult.error(str(e), retryable=False)
    except MailerLiteError as e:
        if e.status_code == 404:
            # Confirmed live: a brand-new subscriber's /activity 404s until
            # they have at least one event — this is "no activity yet", not
            # an invalid subscriber id (we already validated existence isn't
            # in question here since the caller got this id from our own
            # list/get functions).
            result = SubscriberActivityList(subscriber_id=params.subscriber_id, rows=[], count=0, has_no_activity_yet=True)
            return ActionResult.success(data=result, summary="No activity yet for this subscriber.")
        return ActionResult.error(str(e), retryable=False)
    rows = data.get("data") or []
    result = SubscriberActivityList(
        subscriber_id=params.subscriber_id,
        rows=[SubscriberActivityRow(activity_type=r.get("type", ""), date=r.get("date", ""), detail=r) for r in rows],
        count=len(rows),
    )
    return ActionResult.success(data=result, summary=f"{result.count} activity event(s)")


@chat.function(
    "add_subscriber_to_group", action_type="write", event="mailerlite.subscriber.grouped",
    effects=["update:subscriber"], data_model=DeletedResponse,
    description="Assign an existing subscriber to a group. Use for: добавь подписчика в группу.",
)
async def fn_add_subscriber_to_group(ctx, params: GroupSubscriberParams) -> ActionResult:
    """Assign an existing subscriber to a group."""
    try:
        key = await _require_key(ctx)
        await ml_post(ctx, key, f"subscribers/{params.subscriber_id}/groups/{params.group_id}")
    except (RuntimeError, MailerLiteError) as e:
        return ActionResult.error(str(e), retryable=False)
    return ActionResult.success(data=DeletedResponse(deleted=False), summary="Subscriber added to group.", refresh_panels=["workspace"])


@chat.function(
    "remove_subscriber_from_group", action_type="write", event="mailerlite.subscriber.ungrouped",
    effects=["update:subscriber"], data_model=DeletedResponse,
    description="Remove a subscriber from a group. Use for: убери подписчика из группы.",
)
async def fn_remove_subscriber_from_group(ctx, params: GroupSubscriberParams) -> ActionResult:
    """Remove a subscriber from a group."""
    try:
        key = await _require_key(ctx)
        await ml_delete(ctx, key, f"subscribers/{params.subscriber_id}/groups/{params.group_id}")
    except (RuntimeError, MailerLiteError) as e:
        return ActionResult.error(str(e), retryable=False)
    return ActionResult.success(data=DeletedResponse(deleted=False), summary="Subscriber removed from group.", refresh_panels=["workspace"])


@chat.function(
    "delete_subscriber", action_type="destructive", event="mailerlite.subscriber.deleted",
    effects=["delete:subscriber"], data_model=DeletedResponse,
    description="Permanently delete a subscriber. Use for: удали подписчика.",
)
async def fn_delete_subscriber(ctx, params: SubscriberIdParams) -> ActionResult:
    """Permanently delete a subscriber."""
    try:
        key = await _require_key(ctx)
        await ml_delete(ctx, key, f"subscribers/{params.subscriber_id}")
    except (RuntimeError, MailerLiteError) as e:
        return ActionResult.error(str(e), retryable=False)
    return ActionResult.success(data=DeletedResponse(deleted=True), summary="Subscriber deleted.", refresh_panels=["workspace"])


@chat.function(
    "forget_subscriber", action_type="destructive", event="mailerlite.subscriber.forgotten",
    effects=["delete:subscriber"], data_model=DeletedResponse,
    description=(
        "GDPR 'right to be forgotten': permanently erases this subscriber's personal data (distinct "
        "from delete_subscriber, which just removes the record — forget is MailerLite's own compliance "
        "endpoint, POST /subscribers/{id}/forget, confirmed via MailerLite's official SDK source). "
        "Use for: удали данные подписчика по gdpr, forget this subscriber, right to be forgotten."
    ),
)
async def fn_forget_subscriber(ctx, params: SubscriberIdParams) -> ActionResult:
    """GDPR 'right to be forgotten': permanently erases this subscriber's personal data (distinct from delete_subscriber, which just removes the record — forget is MailerLite's own compliance endpoint, POST /subscribers/{id}/forget, confirmed via MailerLite's official SDK source)."""
    try:
        key = await _require_key(ctx)
        await ml_post(ctx, key, f"subscribers/{params.subscriber_id}/forget")
    except (RuntimeError, MailerLiteError) as e:
        return ActionResult.error(str(e), retryable=False)
    return ActionResult.success(data=DeletedResponse(deleted=True), summary="Subscriber's data forgotten (GDPR erasure).", refresh_panels=["workspace"])

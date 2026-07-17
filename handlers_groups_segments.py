"""Chat-function handlers: groups (full CRUD) and segments (read/rename/
delete ONLY — confirmed live + docs: MailerLite's public API has no way to
author a segment's filter rules, only list/rename/delete existing ones — no
create_segment function exists here on purpose, see docs/research.md).
"""
from imperal_sdk.types import ActionResult

from app import chat
from accounts import _active_api_key
from ml_api import ml_get, ml_post, ml_put, ml_delete, MailerLiteError
from params import (
    ListGroupsParams, CreateGroupParams, GroupIdParams, RenameGroupParams, GroupSubscribersParams,
    ListSegmentsParams, SegmentIdParams, RenameSegmentParams, SegmentSubscribersParams,
)
from response_models import (
    GroupRecord, GroupList, SegmentRecord, SegmentList, SubscriberList, DeletedResponse,
)
from handlers_subscribers import _to_subscriber


async def _require_key(ctx) -> str:
    key = await _active_api_key(ctx)
    if not key:
        raise RuntimeError("No MailerLite account connected. Call save_mailerlite_key first.")
    return key


def _to_group(row: dict) -> GroupRecord:
    return GroupRecord(
        id=str(row.get("id", "")), name=row.get("name", ""),
        active_count=row.get("active_count", 0), sent_count=row.get("sent_count", 0),
        open_rate=(row.get("open_rate") or {}).get("float", 0.0) if isinstance(row.get("open_rate"), dict) else row.get("open_rate", 0.0),
        click_rate=(row.get("click_rate") or {}).get("float", 0.0) if isinstance(row.get("click_rate"), dict) else row.get("click_rate", 0.0),
        unsubscribed_count=row.get("unsubscribed_count", 0), created_at=row.get("created_at", ""),
    )


def _to_segment(row: dict) -> SegmentRecord:
    return SegmentRecord(
        id=str(row.get("id", "")), name=row.get("name", ""), total=row.get("total", 0),
        open_rate=(row.get("open_rate") or {}).get("float", 0.0) if isinstance(row.get("open_rate"), dict) else 0.0,
        click_rate=(row.get("click_rate") or {}).get("float", 0.0) if isinstance(row.get("click_rate"), dict) else 0.0,
        created_at=row.get("created_at", ""),
        automations_using_segment_count=row.get("automations_using_segment_count", 0),
    )


# ── Groups ───────────────────────────────────────────────────────────────

@chat.function(
    "list_groups", action_type="read", chain_callable=True, data_model=GroupList,
    description="List mailing groups. Use for: покажи группы, list my groups.",
)
async def fn_list_groups(ctx, params: ListGroupsParams) -> ActionResult:
    """List mailing groups."""
    try:
        key = await _require_key(ctx)
        q = {"limit": params.limit, "page": params.page}
        if params.name_contains:
            q["filter[name]"] = params.name_contains
        data = await ml_get(ctx, key, "groups", params=q)
    except (RuntimeError, MailerLiteError) as e:
        return ActionResult.error(str(e), retryable=False)
    rows = data.get("data") or []
    result = GroupList(groups=[_to_group(r) for r in rows], count=len(rows))
    return ActionResult.success(data=result, summary=f"{result.count} group(s)")


@chat.function(
    "create_group", action_type="write", event="mailerlite.group.created",
    effects=["create:group"], data_model=GroupRecord,
    description="Create a new mailing group. Use for: создай группу, new group called X.",
)
async def fn_create_group(ctx, params: CreateGroupParams) -> ActionResult:
    """Create a new mailing group."""
    try:
        key = await _require_key(ctx)
        data = await ml_post(ctx, key, "groups", json={"name": params.name})
    except (RuntimeError, MailerLiteError) as e:
        return ActionResult.error(str(e), retryable=False)
    result = _to_group(data.get("data") or {})
    return ActionResult.success(data=result, summary=f"Group '{result.name}' created.", refresh_panels=["workspace"])


@chat.function(
    "rename_group", action_type="write", event="mailerlite.group.updated",
    effects=["update:group"], data_model=GroupRecord,
    description="Rename a group. Use for: переименуй группу.",
)
async def fn_rename_group(ctx, params: RenameGroupParams) -> ActionResult:
    """Rename a group."""
    try:
        key = await _require_key(ctx)
        data = await ml_put(ctx, key, f"groups/{params.group_id}", json={"name": params.name})
    except (RuntimeError, MailerLiteError) as e:
        return ActionResult.error(str(e), retryable=False)
    result = _to_group(data.get("data") or {})
    return ActionResult.success(data=result, summary=f"Group renamed to '{result.name}'.", refresh_panels=["workspace"])


@chat.function(
    "delete_group", action_type="destructive", event="mailerlite.group.deleted",
    effects=["delete:group"], data_model=DeletedResponse,
    description="Permanently delete a group (subscribers stay, just un-grouped). Use for: удали группу.",
)
async def fn_delete_group(ctx, params: GroupIdParams) -> ActionResult:
    """Permanently delete a group (subscribers stay, just un-grouped)."""
    try:
        key = await _require_key(ctx)
        await ml_delete(ctx, key, f"groups/{params.group_id}")
    except (RuntimeError, MailerLiteError) as e:
        return ActionResult.error(str(e), retryable=False)
    return ActionResult.success(data=DeletedResponse(deleted=True), summary="Group deleted.", refresh_panels=["workspace"])


@chat.function(
    "group_subscribers", action_type="read", chain_callable=True, data_model=SubscriberList,
    description="List subscribers belonging to a group. Use for: покажи подписчиков группы.",
)
async def fn_group_subscribers(ctx, params: GroupSubscribersParams) -> ActionResult:
    """List subscribers belonging to a group."""
    try:
        key = await _require_key(ctx)
        q = {"limit": params.limit}
        if params.status:
            q["filter[status]"] = params.status
        if params.cursor:
            q["cursor"] = params.cursor
        data = await ml_get(ctx, key, f"groups/{params.group_id}/subscribers", params=q)
    except (RuntimeError, MailerLiteError) as e:
        return ActionResult.error(str(e), retryable=False)
    rows = data.get("data") or []
    result = SubscriberList(
        subscribers=[_to_subscriber(r) for r in rows], count=len(rows),
        next_cursor=(data.get("meta") or {}).get("next_cursor"),
    )
    return ActionResult.success(data=result, summary=f"{result.count} subscriber(s) in group")


# ── Segments (read/rename/delete only) ────────────────────────────────────

@chat.function(
    "list_segments", action_type="read", chain_callable=True, data_model=SegmentList,
    description=(
        "List dynamic subscriber segments. NOTE: segment filter rules are built in the MailerLite UI "
        "only — this extension can list/rename/delete existing segments but not author new filter logic. "
        "Use for: покажи сегменты, list my segments."
    ),
)
async def fn_list_segments(ctx, params: ListSegmentsParams) -> ActionResult:
    """List dynamic subscriber segments."""
    try:
        key = await _require_key(ctx)
        data = await ml_get(ctx, key, "segments", params={"limit": params.limit, "page": params.page})
    except (RuntimeError, MailerLiteError) as e:
        return ActionResult.error(str(e), retryable=False)
    rows = data.get("data") or []
    result = SegmentList(segments=[_to_segment(r) for r in rows], count=len(rows))
    return ActionResult.success(data=result, summary=f"{result.count} segment(s)")


@chat.function(
    "rename_segment", action_type="write", event="mailerlite.segment.updated",
    effects=["update:segment"], data_model=SegmentRecord,
    description="Rename a segment (filter rules themselves can't be edited via API). Use for: переименуй сегмент.",
)
async def fn_rename_segment(ctx, params: RenameSegmentParams) -> ActionResult:
    """Rename a segment (filter rules themselves can't be edited via API)."""
    try:
        key = await _require_key(ctx)
        data = await ml_put(ctx, key, f"segments/{params.segment_id}", json={"name": params.name})
    except (RuntimeError, MailerLiteError) as e:
        return ActionResult.error(str(e), retryable=False)
    result = _to_segment(data.get("data") or {})
    return ActionResult.success(data=result, summary=f"Segment renamed to '{result.name}'.", refresh_panels=["workspace"])


@chat.function(
    "delete_segment", action_type="destructive", event="mailerlite.segment.deleted",
    effects=["delete:segment"], data_model=DeletedResponse,
    description="Permanently delete a segment. Use for: удали сегмент.",
)
async def fn_delete_segment(ctx, params: SegmentIdParams) -> ActionResult:
    """Permanently delete a segment."""
    try:
        key = await _require_key(ctx)
        await ml_delete(ctx, key, f"segments/{params.segment_id}")
    except (RuntimeError, MailerLiteError) as e:
        return ActionResult.error(str(e), retryable=False)
    return ActionResult.success(data=DeletedResponse(deleted=True), summary="Segment deleted.", refresh_panels=["workspace"])


@chat.function(
    "segment_subscribers", action_type="read", chain_callable=True, data_model=SubscriberList,
    description="List subscribers matching a segment's rules. Use for: покажи подписчиков сегмента.",
)
async def fn_segment_subscribers(ctx, params: SegmentSubscribersParams) -> ActionResult:
    """List subscribers matching a segment's rules."""
    try:
        key = await _require_key(ctx)
        q = {"limit": params.limit}
        if params.status:
            q["filter[status]"] = params.status
        if params.cursor:
            q["cursor"] = params.cursor
        data = await ml_get(ctx, key, f"segments/{params.segment_id}/subscribers", params=q)
    except (RuntimeError, MailerLiteError) as e:
        return ActionResult.error(str(e), retryable=False)
    rows = data.get("data") or []
    result = SubscriberList(
        subscribers=[_to_subscriber(r) for r in rows], count=len(rows),
        next_cursor=(data.get("meta") or {}).get("next_cursor"),
    )
    return ActionResult.success(data=result, summary=f"{result.count} subscriber(s) in segment")

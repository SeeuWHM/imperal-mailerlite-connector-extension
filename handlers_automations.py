"""Chat-function handlers: automations — list/get/activity/create-draft/
delete ONLY. Confirmed via docs/research.md: MailerLite's public REST API
has NO way to author an automation's trigger/steps — you can only list
existing automations, inspect their stats/subscriber activity, create an
empty draft (name only — steps must then be built in the MailerLite UI),
or delete one. No update_automation / add_step function exists here because
no such endpoint exists.
"""
from imperal_sdk.types import ActionResult

from app import chat
from accounts import _active_api_key
from ml_api import ml_get, ml_post, ml_delete, ml_str, MailerLiteError
from params import ListAutomationsParams, AutomationIdParams, AutomationActivityParams, CreateAutomationDraftParams
from response_models import AutomationRecord, AutomationList, AutomationActivityRow, AutomationActivityList, DeletedResponse


async def _require_key(ctx) -> str:
    key = await _active_api_key(ctx)
    if not key:
        raise RuntimeError("No MailerLite account connected. Call save_mailerlite_key first.")
    return key


def _to_automation(row: dict) -> AutomationRecord:
    return AutomationRecord(
        id=str(row.get("id", "")), name=ml_str(row, "name"), enabled=bool(row.get("enabled", False)),
        created_at=ml_str(row, "created_at"),
    )


@chat.function(
    "list_automations", action_type="read", chain_callable=True, data_model=AutomationList,
    description=(
        "List automations (name, enabled/disabled, created date) — read-only. MailerLite's API can't "
        "build or edit automation steps; those are UI-only. Use for: list my "
        "automations, show automation workflows."
    ),
)
async def fn_list_automations(ctx, params: ListAutomationsParams) -> ActionResult:
    """List automations (name, enabled/disabled, created date) — read-only."""
    try:
        key = await _require_key(ctx)
        query = {"limit": params.limit, "page": params.page}
        if params.enabled is not None:
            query["filter[enabled]"] = "true" if params.enabled else "false"
        if params.name:
            query["filter[name]"] = params.name
        data = await ml_get(ctx, key, "automations", query)
    except (MailerLiteError, RuntimeError) as e:
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    rows = data.get("data") or []
    result = AutomationList(automations=[_to_automation(r) for r in rows], count=len(rows))
    return ActionResult.success(data=result, summary=f"{result.count} automation(s)")


@chat.function(
    "get_automation", action_type="read", chain_callable=True, data_model=AutomationRecord,
    description="Fetch one automation's basic info by id. Use for: get this automation.",
)
async def fn_get_automation(ctx, params: AutomationIdParams) -> ActionResult:
    """Fetch one automation's basic info by id."""
    try:
        key = await _require_key(ctx)
        data = await ml_get(ctx, key, f"automations/{params.automation_id}")
    except (MailerLiteError, RuntimeError) as e:
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    return ActionResult.success(data=_to_automation(data.get("data") or {}), summary="Automation fetched.")


@chat.function(
    "automation_activity", action_type="read", chain_callable=True, data_model=AutomationActivityList,
    description=(
        "Subscriber activity flowing through an automation, filtered by status (completed/active/"
        "canceled/failed — required). Use for: who's in this automation, "
        "automation subscriber activity."
    ),
)
async def fn_automation_activity(ctx, params: AutomationActivityParams) -> ActionResult:
    """Subscriber activity flowing through an automation, filtered by status (completed/active/canceled/failed — required)."""
    try:
        key = await _require_key(ctx)
        query = {"filter[status]": params.status, "limit": params.limit, "page": params.page}
        data = await ml_get(ctx, key, f"automations/{params.automation_id}/activity", query)
    except (MailerLiteError, RuntimeError) as e:
        if isinstance(e, MailerLiteError) and e.status_code == 404:
            return ActionResult.success(
                data=AutomationActivityList(automation_id=params.automation_id, rows=[], count=0),
                summary="No activity matching that filter yet.",
            )
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    rows = data.get("data") or []
    result = AutomationActivityList(
        automation_id=params.automation_id,
        rows=[AutomationActivityRow(status=r.get("status", ""), date=r.get("date", ""),
                                     reason=r.get("reason_description") or r.get("reason")) for r in rows],
        count=len(rows),
    )
    return ActionResult.success(data=result, summary=f"{result.count} activity record(s)")


@chat.function(
    "create_automation_draft", action_type="write", event="mailerlite.automation.created",
    effects=["create:automation"], data_model=AutomationRecord,
    description=(
        "Create an EMPTY draft automation (name only) — MailerLite's API can't define triggers/steps, "
        "so the user still needs to open MailerLite's UI to actually build the workflow. Use for: "
        "create a draft automation shell."
    ),
)
async def fn_create_automation_draft(ctx, params: CreateAutomationDraftParams) -> ActionResult:
    """Create an EMPTY draft automation (name only) — MailerLite's API can't define triggers/steps, so the user still needs to open MailerLite's UI to actually build the workflow."""
    try:
        key = await _require_key(ctx)
        data = await ml_post(ctx, key, "automations", {"name": params.name})
    except (MailerLiteError, RuntimeError) as e:
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    result = _to_automation(data.get("data") or {})
    return ActionResult.success(
        data=result,
        summary=f"Draft automation '{result.name}' created — open MailerLite's UI to build its steps.",
        refresh_panels=["workspace"],
    )


@chat.function(
    "delete_automation", action_type="destructive", event="mailerlite.automation.deleted",
    effects=["delete:automation"], data_model=DeletedResponse,
    description="Permanently delete an automation. Use for: delete this automation.",
)
async def fn_delete_automation(ctx, params: AutomationIdParams) -> ActionResult:
    """Permanently delete an automation."""
    try:
        key = await _require_key(ctx)
        await ml_delete(ctx, key, f"automations/{params.automation_id}")
    except (MailerLiteError, RuntimeError) as e:
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    return ActionResult.success(data=DeletedResponse(deleted=True), summary="Automation deleted.", refresh_panels=["workspace"])

"""Chat-function handlers: campaigns — list/get/create/update/schedule/
cancel/delete + sent-campaign subscriber activity.

Paths confirmed against MailerLite's own official Node.js SDK source
(@mailerlite/mailerlite-nodejs, read directly — see docs/research.md), NOT
guessed from prose docs, because the prose docs describe these as generic
"POST request" without ever spelling out the literal path:
  - schedule:  POST /api/campaigns/{id}/schedule
  - cancel:    POST /api/campaigns/{id}/cancel
  - activity:  POST /api/campaigns/{id}/reports/subscriber-activity (POST
    with a filter body, NOT a GET — easy to get wrong by analogy with
    subscriber/automation activity, which ARE GETs)

Confirmed live quirks (see docs/research.md/capability.py):
  - GET /campaigns?limit=N only accepts {1,10,25,50,100} — anything else
    422s with a generic message; we snap to the nearest valid value.
  - type=resend/multivariate and rich HTML content can 422 with MailerLite's
    own plan-restriction wording — surfaced verbatim via MailerLiteError.
"""
from imperal_sdk.types import ActionResult

from app import chat
from accounts import _active_account, _active_api_key
from ml_api import ml_get, ml_post, ml_put, ml_delete, MailerLiteError, validate_campaigns_limit
from capability import record_verdict
from params import ListCampaignsParams, CampaignIdParams, CreateCampaignParams, ScheduleCampaignParams
from response_models import CampaignRecord, CampaignList, DeletedResponse


async def _require_key(ctx) -> str:
    key = await _active_api_key(ctx)
    if not key:
        raise RuntimeError("No MailerLite account connected. Call save_mailerlite_key first.")
    return key


def _to_campaign(row: dict) -> CampaignRecord:
    email0 = (row.get("emails") or [{}])[0] if row.get("emails") else {}
    return CampaignRecord(
        id=str(row.get("id", "")), name=row.get("name", ""), type=row.get("type", ""),
        status=row.get("status", ""), subject=email0.get("subject", ""),
        missing_data=row.get("missing_data") or [],
        created_at=row.get("created_at", ""), scheduled_for=row.get("scheduled_for"),
    )


async def _record_plan_verdict_if_any(ctx, capability_key: str, e: MailerLiteError) -> None:
    if not e.plan_restricted:
        return
    account = await _active_account(ctx)
    if account:
        await record_verdict(ctx, account.get("label", ""), capability_key, restricted=True, message=e.message)


@chat.function(
    "list_campaigns", action_type="read", chain_callable=True, data_model=CampaignList,
    description=(
        "List campaigns filtered by status (sent/draft/ready) and/or type (regular/ab/resend/rss). "
        "Use for: покажи мои кампании, list my campaigns, show draft/sent campaigns."
    ),
)
async def fn_list_campaigns(ctx, params: ListCampaignsParams) -> ActionResult:
    """List campaigns filtered by status (sent/draft/ready) and/or type (regular/ab/resend/rss)."""
    try:
        key = await _require_key(ctx)
        query = {"limit": validate_campaigns_limit(params.limit), "page": params.page}
        if params.status:
            query["filter[status]"] = params.status
        if params.type:
            query["filter[type]"] = params.type
        data = await ml_get(ctx, key, "campaigns", query)
    except (MailerLiteError, RuntimeError) as e:
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    rows = data.get("data") or []
    result = CampaignList(campaigns=[_to_campaign(r) for r in rows], count=len(rows))
    return ActionResult.success(data=result, summary=f"{result.count} campaign(s)")


@chat.function(
    "get_campaign", action_type="read", chain_callable=True, data_model=CampaignRecord,
    description="Fetch one campaign by id. Use for: покажи кампанию, get this campaign.",
)
async def fn_get_campaign(ctx, params: CampaignIdParams) -> ActionResult:
    """Fetch one campaign by id."""
    try:
        key = await _require_key(ctx)
        data = await ml_get(ctx, key, f"campaigns/{params.campaign_id}")
    except (MailerLiteError, RuntimeError) as e:
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    return ActionResult.success(data=_to_campaign(data.get("data") or {}), summary="Campaign fetched.")


@chat.function(
    "create_campaign", action_type="write", event="mailerlite.campaign.created",
    effects=["create:campaign"], data_model=CampaignRecord,
    description=(
        "Create a draft campaign. type='resend'/'multivariate' and content_html both carry a REAL risk of "
        "being rejected on lower MailerLite plans — any such rejection is surfaced with MailerLite's own "
        "exact wording, never guessed. Use for: создай кампанию, draft a new campaign called X."
    ),
)
async def fn_create_campaign(ctx, params: CreateCampaignParams) -> ActionResult:
    """Create a draft campaign."""
    try:
        key = await _require_key(ctx)
        email = {"subject": params.subject, "from_name": params.from_name, "from": params.from_email}
        if params.reply_to:
            email["reply_to"] = params.reply_to
        if params.content_html:
            email["content"] = params.content_html
        body = {"name": params.name, "type": params.type, "emails": [email]}
        if params.language_id:
            body["language_id"] = params.language_id
        data = await ml_post(ctx, key, "campaigns", body)
    except RuntimeError as e:
        return ActionResult.error(str(e), retryable=False)
    except MailerLiteError as e:
        capability_key = "campaign_rich_content" if params.content_html else "campaign_type_resend_multivariate"
        await _record_plan_verdict_if_any(ctx, capability_key, e)
        return ActionResult.error(e.message, retryable=False)
    result = _to_campaign(data.get("data") or {})
    return ActionResult.success(data=result, summary=f"Campaign '{result.name}' created.", refresh_panels=["workspace"])


@chat.function(
    "schedule_campaign", action_type="write", event="mailerlite.campaign.scheduled",
    effects=["update:campaign"], data_model=CampaignRecord,
    description=(
        "Schedule a ready campaign to send (or send it instantly with delivery='instant'). "
        "Use for: отправь кампанию, schedule this campaign for tomorrow, send now."
    ),
)
async def fn_schedule_campaign(ctx, params: ScheduleCampaignParams) -> ActionResult:
    """Schedule a ready campaign to send (or send it instantly with delivery='instant')."""
    try:
        key = await _require_key(ctx)
        body: dict = {"delivery": params.delivery}
        if params.delivery in ("scheduled", "timezone_based", "smart_sending"):
            schedule: dict = {}
            if params.date:
                schedule["date"] = params.date
            if params.hours:
                schedule["hours"] = params.hours
            if params.minutes:
                schedule["minutes"] = params.minutes
            if params.timezone_id:
                schedule["timezone_id"] = params.timezone_id
            if schedule:
                body["schedule"] = schedule
        # Confirmed via official SDK source: POST /api/campaigns/{id}/schedule
        data = await ml_post(ctx, key, f"campaigns/{params.campaign_id}/schedule", body)
    except (MailerLiteError, RuntimeError) as e:
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    result = _to_campaign(data.get("data") or {})
    return ActionResult.success(data=result, summary=f"Campaign '{result.name}' scheduled/sent.", refresh_panels=["workspace"])


@chat.function(
    "cancel_campaign", action_type="write", event="mailerlite.campaign.canceled",
    effects=["update:campaign"], data_model=CampaignRecord,
    description="Cancel a campaign that's currently in 'ready' state (queued to send). Use for: отмени кампанию, cancel this send.",
)
async def fn_cancel_campaign(ctx, params: CampaignIdParams) -> ActionResult:
    """Cancel a campaign that's currently in 'ready' state (queued to send)."""
    try:
        key = await _require_key(ctx)
        # Confirmed via official SDK source: POST /api/campaigns/{id}/cancel
        data = await ml_post(ctx, key, f"campaigns/{params.campaign_id}/cancel")
    except (MailerLiteError, RuntimeError) as e:
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    result = _to_campaign(data.get("data") or {})
    return ActionResult.success(data=result, summary=f"Campaign '{result.name}' canceled.", refresh_panels=["workspace"])


@chat.function(
    "delete_campaign", action_type="destructive", event="mailerlite.campaign.deleted",
    effects=["delete:campaign"], data_model=DeletedResponse,
    description="Permanently delete a campaign. Use for: удали кампанию, delete this campaign.",
)
async def fn_delete_campaign(ctx, params: CampaignIdParams) -> ActionResult:
    """Permanently delete a campaign."""
    try:
        key = await _require_key(ctx)
        await ml_delete(ctx, key, f"campaigns/{params.campaign_id}")
    except (MailerLiteError, RuntimeError) as e:
        return ActionResult.error(str(e), retryable=isinstance(e, MailerLiteError) and e.status_code >= 500)
    return ActionResult.success(data=DeletedResponse(deleted=True), summary="Campaign deleted.", refresh_panels=["workspace"])

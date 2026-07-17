"""Chat-function handlers: plan-capability status.

See docs/capability-matrix.md for the full design. Two layers of truth,
best one first:
  1. `GET /account` — confirmed LIVE (2026-07-16/17, against a real
     webhostmost account) to return the account's real plan directly:
     `plan.name`/`amount`/`min_subscribers`/`max_subscribers` and
     `features.smart_sending`. This endpoint is NOT in MailerLite's own
     documented endpoint list at developers.mailerlite.com, so we treat it
     as best-effort ground truth (call it, and if it ever 404s/disappears,
     degrade gracefully to layer 2 — never hard-fail the whole function).
  2. Sub-capabilities `/account` itself doesn't describe (e.g. whether HTML
     campaign content submission is unlocked at this exact tier) still rely
     on: (a) any LIVE verdicts already recorded from real 422 responses hit
     while using this extension, and (b) the short, honestly-sourced
     GATED_HINTS list (documented plan gates) as a heads-up, never a hard
     block.
"""
from imperal_sdk.types import ActionResult

from app import chat
from accounts import _active_account, _active_api_key
from capability import GATED_HINTS, get_cached_verdicts
from ml_api import ml_get, MailerLiteError
from params import EmptyParams
from response_models import CapabilityHint, CapabilityStatus, PlanInfo


async def _fetch_plan(ctx, api_key: str) -> PlanInfo | None:
    """Best-effort real plan lookup via GET /account. Returns None (not an
    error) if the call fails for any reason — this is a bonus ground-truth
    layer, not something the whole capability report should die over."""
    try:
        data = await ml_get(ctx, api_key, "account")
    except MailerLiteError:
        return None
    row = data.get("data") or {}
    plan = row.get("plan") or {}
    features = row.get("features") or {}
    if not plan:
        return None
    return PlanInfo(
        name=plan.get("name", ""),
        interval=plan.get("interval", ""),
        amount=plan.get("amount", 0) or 0,
        min_subscribers=plan.get("min_subscribers", 0) or 0,
        max_subscribers=plan.get("max_subscribers", 0) or 0,
        smart_sending_enabled=bool(features.get("smart_sending", False)),
        paid_features=bool(row.get("paid_features", False)),
    )


@chat.function(
    "mailerlite_capability_status", action_type="read", chain_callable=True, data_model=CapabilityStatus,
    description=(
        "Show this MailerLite account's REAL plan (name, price, subscriber tier, smart-sending flag — "
        "read directly from MailerLite's own account endpoint) plus any capability restrictions actually "
        "observed from live API responses, and MailerLite's own documented plan gates for things the "
        "account endpoint doesn't itself describe (e.g. whether HTML campaign content is unlocked at "
        "this tier). Use for: какой у меня план MailerLite, what MailerLite features am I limited to, "
        "plan limits, сколько стоит мой план mailerlite."
    ),
)
async def fn_mailerlite_capability_status(ctx, params: EmptyParams) -> ActionResult:
    """Show this MailerLite account's REAL plan plus any capability restrictions actually observed from live API responses and MailerLite's own documented plan gates."""
    account = await _active_account(ctx)
    if not account:
        return ActionResult.error("No MailerLite account connected. Call save_mailerlite_key first.", retryable=False)
    label = account.get("label", "")
    api_key = await _active_api_key(ctx)

    plan = await _fetch_plan(ctx, api_key)

    verdicts = await get_cached_verdicts(ctx, label)
    hints = [
        CapabilityHint(capability_key=k, note=v, confirmed_restricted=None)
        for k, v in GATED_HINTS.items()
        if k not in verdicts
    ]
    for key, verdict in verdicts.items():
        hints.append(CapabilityHint(
            capability_key=key,
            note=verdict.get("message", ""),
            confirmed_restricted=verdict.get("restricted"),
        ))

    result = CapabilityStatus(
        account_label=label, plan=plan, plan_lookup_failed=(plan is None),
        hints=hints, count=len(hints),
    )
    n_confirmed = sum(1 for h in hints if h.confirmed_restricted is not None)
    plan_bit = f"Plan: {plan.name} (${plan.amount}/{plan.interval})." if plan else "Plan lookup unavailable."
    summary = (
        f"{plan_bit} {n_confirmed} capability fact(s) observed live; "
        f"{len(hints) - n_confirmed} documented gate(s) not yet tested on this account."
    )
    return ActionResult.success(data=result, summary=summary)

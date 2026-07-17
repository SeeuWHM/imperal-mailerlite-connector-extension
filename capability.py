"""Per-account plan-capability cache — see docs/capability-matrix.md for the
full design rationale (no static plan/feature table anywhere; MailerLite's
own live error text is the only source of truth we trust).

Stored alongside the account's own secrets under a per-account cache key so
switching accounts doesn't mix up capability verdicts between them.
"""
from __future__ import annotations

import json
import time

CACHE_TTL_SECONDS = 7 * 24 * 3600  # 7 days — plans change (upgrade/downgrade)

# Short, HONEST list of operations MailerLite's own docs/live errors called
# out as plan-restricted (verbatim source cited — see docs/research.md).
# This is advisory context for Webbee, never a client-side hard block: only
# MailerLite itself actually knows the caller's plan.
GATED_HINTS = {
    "campaign_type_resend_multivariate": (
        "Campaign types 'resend' and 'multivariate' — MailerLite's docs state these are "
        "\"only available for accounts on growing or advanced plans\" (their wording, not ours)."
    ),
    "campaign_rich_content": (
        "Rich/HTML campaign content — observed live: MailerLite rejected it with "
        "\"Content submission is only available on Premium plan.\" on a non-upgraded test account."
    ),
}


def _cache_key(label: str) -> str:
    return f"mailerlite_capability_cache::{label}"


async def _load(ctx, account_label: str) -> dict:
    raw = await ctx.secrets.get(_cache_key(account_label))
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def _save(ctx, account_label: str, cache: dict) -> None:
    await ctx.secrets.set(_cache_key(account_label), json.dumps(cache))


async def get_cached_verdicts(ctx, account_label: str) -> dict:
    """All non-expired cached verdicts for this account, capability_key ->
    {"restricted": bool, "message": str, "checked_at": iso-ish str}."""
    cache = await _load(ctx, account_label)
    now = time.time()
    fresh = {
        k: v for k, v in cache.items()
        if isinstance(v, dict) and (now - v.get("checked_at_epoch", 0)) < CACHE_TTL_SECONDS
    }
    if len(fresh) != len(cache):
        await _save(ctx, account_label, fresh)
    return fresh


async def record_verdict(ctx, account_label: str, capability_key: str, restricted: bool, message: str) -> None:
    """Record a REAL observed outcome (success or plan_restricted 422) for
    this capability on this account. A success always overwrites a stale
    'restricted' verdict — never the other way around from a guess."""
    cache = await _load(ctx, account_label)
    cache[capability_key] = {
        "restricted": restricted,
        "message": message,
        "checked_at_epoch": time.time(),
    }
    await _save(ctx, account_label, cache)

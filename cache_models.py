"""MailerLite · ctx.cache model registration (SDK v1.6.0).

Sidebar's "Last Campaign" block used to hit the live MailerLite API on
EVERY sidebar render — expensive and pointless since these numbers don't
change second-to-second. `ctx.skeleton` (the platform's LLM-context cache)
is NOT usable here: it's guarded to `@ext.skeleton` context only
(`_SkeletonAccessGuard` raises `SkeletonAccessForbidden` from panel calls)
— see imperal_sdk/context.py. The panel-facing equivalent for "refresh on
a timer instead of every render" is `ctx.cache`, which is what this module
backs.

Same split as mail-client/cache_models.py + cache_model_defs.py: the pure
Pydantic class lives here (no other module imports needed) since MailerLite
only has this one small cache model — no import-cycle risk to split further.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app import ext


class SidebarStats(BaseModel):
    """Cached MailerLite "last campaign" quick-stats for one connected
    account. TTL-bound (see panels.py's `_STATS_TTL_SECONDS`) so the
    sidebar doesn't call MailerLite on every single render — only once per
    TTL window per account.

    Subscriber/campaign totals were dropped from the sidebar display (user
    call: an approximate "1,000+" subscriber figure and a "Campaigns
    sent" counter added no real value) — this model now only holds what's
    actually shown: the most recently sent campaign's subject + its exact
    open/click counts.
    """
    account_label: str
    last_campaign_name: str = ""       # subject/name of the most recently
                                        # sent campaign (empty if none sent)
    last_campaign_opens: int = 0       # EXACT — that campaign's stats.opens_count
    last_campaign_clicks: int = 0      # EXACT — that campaign's stats.clicks_count
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


ext.cache_model("mailerlite_sidebar_stats")(SidebarStats)


class CampaignsPayload(BaseModel):
    """Generic cache envelope for a raw MailerLite `campaigns` list/detail
    JSON response (sidebar's \"Recent campaigns\", workspace's overview list,
    and workspace's single-campaign detail) — these three call sites used to
    hit ml_get() live on every single panel render, on top of the sidebar's
    already-cached quick-stats. MailerLite campaign stats only change when a
    campaign is actually sent/opened/clicked, not second-to-second, so a
    short TTL window (see panels.py/panels_workspace.py's *_CACHE_TTL
    constants) costs no real freshness.
    """
    data: dict = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


ext.cache_model("mailerlite_campaigns_payload")(CampaignsPayload)


def campaigns_cache_key(scope: str, account_key: str, extra: str = "") -> str:
    """ctx.cache keys are capped at 128 chars and restricted to
    [A-Za-z0-9_\\-:] (I-CACHE-KEY-SAFETY) — the API key is a live credential
    and extra params (campaign_id, limit) are free-ish text, so hash the
    whole thing rather than embed anything raw."""
    import hashlib
    digest = hashlib.sha256(f"{scope}:{account_key}:{extra}".encode("utf-8")).hexdigest()[:32]
    return f"mailerlite-camp-{digest}"

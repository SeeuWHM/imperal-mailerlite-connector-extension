"""MailerLite · ctx.cache model registration (SDK v1.6.0).

Sidebar quick-stats (subscriber count, sent-campaign count) used to hit the
live MailerLite API on EVERY sidebar render — expensive and pointless since
these numbers don't change second-to-second. `ctx.skeleton` (the platform's
LLM-context cache) is NOT usable here: it's guarded to `@ext.skeleton`
context only (`_SkeletonAccessGuard` raises `SkeletonAccessForbidden` from
panel calls) — see imperal_sdk/context.py. The panel-facing equivalent for
"refresh on a timer instead of every render" is `ctx.cache`, which is what
this module backs.

Same split as mail-client/cache_models.py + cache_model_defs.py: the pure
Pydantic class lives here (no other module imports needed) since MailerLite
only has this one small cache model — no import-cycle risk to split further.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app import ext


class SidebarStats(BaseModel):
    """Cached MailerLite quick-stats for one connected account. TTL-bound
    (see panels.py's `_STATS_TTL_SECONDS`) so the sidebar doesn't call
    MailerLite on every single render — only once per TTL window per
    account."""
    account_label: str
    subscriber_display: str = "0"     # exact count, or "N+" when the account
                                        # has more subscribers than fit in one
                                        # page (MailerLite's /subscribers has
                                        # no exact total — cursor pagination)
    sent_campaigns: int = 0            # EXACT — from /campaigns meta.total
                                        # with filter[status]=sent
    total_campaigns: int = 0           # EXACT — meta.aggregations.all
    last_campaign_name: str = ""       # name/subject of the most recently
                                        # sent campaign (empty if none sent)
    last_campaign_opens: int = 0       # EXACT — that campaign's stats.opens_count
    last_campaign_clicks: int = 0      # EXACT — that campaign's stats.clicks_count
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


ext.cache_model("mailerlite_sidebar_stats")(SidebarStats)

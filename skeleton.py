"""Skeleton context providers for MailerLite — LLM context cache holding
ready answers. Degrades to configured:false WITHOUT calling MailerLite when
nothing is connected (never leak errors, never block routing). Lists capped
at 5 per the skeleton contract.
"""
from __future__ import annotations

from app import ext
from accounts import _active_api_key, mailerlite_ready
from ml_api import ml_get, MailerLiteError


@ext.skeleton("mailerlite_config", ttl=300,
              description="MailerLite connection status — whether the user has connected an API key")
async def skeleton_mailerlite_config(ctx) -> dict:
    configured = await mailerlite_ready(ctx)
    return {"response": {
        "configured": configured,
        "instruction": (
            "MailerLite not connected — tell the user to call save_mailerlite_key with their "
            "MailerLite API key (MailerLite -> Integrations -> MailerLite API -> Generate new "
            "token) before asking about subscribers, campaigns, or automations."
            if not configured else
            "MailerLite is connected. Call list_subscribers/list_groups/list_campaigns etc. to "
            "read the user's data. Remember: automations can only be listed/inspected/deleted via "
            "this API — steps must be built in the MailerLite UI. Segments/forms can only be "
            "listed/renamed/deleted — creation is UI-only."
        ),
    }}


@ext.skeleton("mailerlite_groups", ttl=600,
              description="The user's MailerLite groups — name and subscriber counts (up to 5 shown)")
async def skeleton_mailerlite_groups(ctx) -> dict:
    if not await mailerlite_ready(ctx):
        return {"response": {"configured": False, "groups": [], "total": 0}}
    try:
        key = await _active_api_key(ctx)
        data = await ml_get(ctx, key, "groups", params={"limit": 5})
        rows = data.get("data") or []
        meta = data.get("meta") or {}
    except MailerLiteError as e:
        return {"response": {"configured": True, "groups": [], "total": 0, "error": e.message}}
    return {"response": {
        "configured": True,
        "groups": [{"id": r.get("id"), "name": r.get("name"), "active_count": r.get("active_count", 0)} for r in rows],
        "total": meta.get("total", len(rows)),
    }}

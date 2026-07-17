"""Thin HTTP client over the MailerLite REST API — one primitive per HTTP
verb, no business orchestration here. All calls go directly to
connect.mailerlite.com via ctx.http with the caller's own API key (no shared
backend proxy — see app.py's docstring for why).

Error classification is the important part of this module: MailerLite's own
422 error text is the ONLY reliable signal we have for plan-gating (see
docs/capability-matrix.md) — no static plan table exists anywhere in this
codebase. Every quirk handled here was directly confirmed against a live
account during development (see docs/research.md):
  - 401 body: {"message": "Unauthenticated."}
  - 404 body: {"message": "Resource does not exist."}
  - 422 body: {"message": "...", "errors": {"field": ["msg", ...]}}
  - A 422 whose error text contains "plan" (case-insensitive) is MailerLite
    itself saying a feature needs a higher plan — we surface that verbatim.
"""
from __future__ import annotations

import re

from app import MAILERLITE_API_BASE

_PLAN_HINT = re.compile(r"\bplan\b", re.IGNORECASE)

# Confirmed live: GET /campaigns only accepts these exact limit values;
# anything else 422s with "The selected limit is invalid." This isn't in the
# prose docs — found by direct probing. We validate client-side so the user
# gets one clear message instead of MailerLite's generic validation error.
CAMPAIGNS_LIST_VALID_LIMITS = (1, 10, 25, 50, 100)


class MailerLiteError(Exception):
    """Raised for any non-2xx MailerLite response. `plan_restricted` is set
    when MailerLite's own error text names a plan requirement — callers use
    this to phrase the failure honestly instead of as a generic error."""

    def __init__(self, message: str, status_code: int = 0, plan_restricted: bool = False):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.plan_restricted = plan_restricted


def _extract_message(status_code: int, body: dict | None) -> tuple[str, bool]:
    body = body or {}
    top = body.get("message") or ""
    errors = body.get("errors") or {}
    flat_msgs: list[str] = []
    for field, msgs in errors.items():
        if isinstance(msgs, list):
            flat_msgs.extend(str(m) for m in msgs)
        elif msgs:
            flat_msgs.append(str(msgs))

    plan_restricted = bool(_PLAN_HINT.search(top)) or any(_PLAN_HINT.search(m) for m in flat_msgs)

    if status_code == 401:
        return ("MailerLite rejected this API key (invalid or revoked). Reconnect with a fresh "
                "key from MailerLite -> Integrations -> MailerLite API."), False
    if status_code == 404:
        return top or "That MailerLite resource doesn't exist.", False
    if status_code == 429:
        return ("MailerLite's rate limit was hit (120 requests/minute per key, or 5/minute during "
                "bulk subscriber imports). Wait a moment and try again."), False
    if flat_msgs:
        detail = "; ".join(f"{k}: {', '.join(v) if isinstance(v, list) else v}" for k, v in errors.items())
        return (top or "Validation error") + f" ({detail})", plan_restricted
    if top:
        return top, plan_restricted
    return f"MailerLite API error (HTTP {status_code})", plan_restricted


async def ml_get(ctx, api_key: str, path: str, params: dict | None = None) -> dict:
    resp = await ctx.http.get(
        f"{MAILERLITE_API_BASE}/{path.lstrip('/')}",
        params=params or {},
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    )
    return await _handle(resp)


async def ml_post(ctx, api_key: str, path: str, json: dict | None = None) -> dict:
    resp = await ctx.http.post(
        f"{MAILERLITE_API_BASE}/{path.lstrip('/')}",
        json=json or {},
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    return await _handle(resp)


async def ml_put(ctx, api_key: str, path: str, json: dict | None = None) -> dict:
    resp = await ctx.http.put(
        f"{MAILERLITE_API_BASE}/{path.lstrip('/')}",
        json=json or {},
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    return await _handle(resp)


async def ml_delete(ctx, api_key: str, path: str) -> dict:
    resp = await ctx.http.delete(
        f"{MAILERLITE_API_BASE}/{path.lstrip('/')}",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    )
    return await _handle(resp)


async def _handle(resp) -> dict:
    """Shared response handling. 204 No Content (confirmed on DELETE and on
    unassign-from-group) has no body — returns {} rather than trying to
    parse JSON from nothing."""
    if resp.status_code == 204:
        return {}
    try:
        body = resp.json()
    except Exception:
        body = None
    if 200 <= resp.status_code < 300:
        return body if isinstance(body, dict) else {"data": body}
    message, plan_restricted = _extract_message(resp.status_code, body if isinstance(body, dict) else None)
    raise MailerLiteError(message, status_code=resp.status_code, plan_restricted=plan_restricted)


def validate_campaigns_limit(limit: int) -> int:
    """GET /campaigns' limit only accepts {1,10,25,50,100} (confirmed live,
    undocumented). Snap to the nearest valid value rather than forwarding a
    confusing generic 422 to the user."""
    if limit in CAMPAIGNS_LIST_VALID_LIMITS:
        return limit
    return min(CAMPAIGNS_LIST_VALID_LIMITS, key=lambda v: abs(v - limit))


def ml_str(row: dict, key: str, default: str = "") -> str:
    """Safe string extraction from a MailerLite API row. `dict.get(key,
    default)` only falls back when the KEY IS ABSENT — but MailerLite
    genuinely returns JSON `null` for present-but-empty fields (confirmed
    live: a draft campaign's `emails[0].subject` is `null`, not an empty
    string, until the user fills it in — this crashed list_campaigns() on
    real draft campaigns before this helper existed). Treats null-or-missing
    the same way, which `dict.get` alone does not.
    """
    value = row.get(key)
    return value if isinstance(value, str) else default

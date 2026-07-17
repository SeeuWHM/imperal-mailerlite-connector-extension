"""Multi-account MailerLite API key storage.

Same JSON-blob pattern as bing_accounts.py / SE Ranking's accounts.py:
several MailerLite API keys can be connected simultaneously and switched
between, one active at a time. `mailerlite_accounts` holds a JSON list of
[{"label": str, "api_key": str, "is_active": bool}, ...].
"""
from __future__ import annotations

import json

ACCOUNTS_SECRET = "mailerlite_accounts"


def _mask(key: str) -> str:
    key = (key or "").strip()
    if not key:
        return ""
    tail = key[-4:] if len(key) >= 4 else key
    return f"••••{tail}"


async def _load_raw(ctx) -> list[dict]:
    raw = await ctx.secrets.get(ACCOUNTS_SECRET)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


async def _save_raw(ctx, accounts: list[dict]) -> None:
    await ctx.secrets.set(ACCOUNTS_SECRET, json.dumps(accounts))


async def _all_accounts(ctx) -> list[dict]:
    """Every connected MailerLite account."""
    return await _load_raw(ctx)


async def _active_account(ctx) -> dict | None:
    accounts = await _all_accounts(ctx)
    if not accounts:
        return None
    return next((a for a in accounts if a.get("is_active")), accounts[0])


async def _active_api_key(ctx) -> str:
    account = await _active_account(ctx)
    return (account or {}).get("api_key", "").strip()


async def mailerlite_ready(ctx) -> bool:
    """Whether the caller has at least one MailerLite account connected."""
    return bool(await _active_api_key(ctx))


async def _add_account(ctx, api_key: str, label: str = "") -> dict:
    """Add a new MailerLite account. First account connected becomes active
    automatically; later ones are added inactive (call switch to activate)."""
    accounts = await _all_accounts(ctx)
    label = (label or "").strip() or f"Account {len(accounts) + 1}"
    new_account = {"label": label, "api_key": api_key.strip(), "is_active": not accounts}
    accounts.append(new_account)
    await _save_raw(ctx, accounts)
    return new_account


async def _switch_account(ctx, label: str) -> bool:
    accounts = await _all_accounts(ctx)
    if not any(a.get("label") == label for a in accounts):
        return False
    for a in accounts:
        a["is_active"] = a.get("label") == label
    await _save_raw(ctx, accounts)
    return True


async def _disconnect_account(ctx, label: str) -> int:
    """Remove one account by label. If it was active, the first remaining
    account (if any) becomes active. Returns remaining account count."""
    accounts = await _all_accounts(ctx)
    was_active = any(a.get("label") == label and a.get("is_active") for a in accounts)
    accounts = [a for a in accounts if a.get("label") != label]
    if was_active and accounts:
        accounts[0]["is_active"] = True
    await _save_raw(ctx, accounts)
    return len(accounts)

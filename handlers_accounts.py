"""Chat-function handlers: connecting/disconnecting/switching the user's own
MailerLite account(s). No OAuth — MailerLite issues a plain per-account API
key (Integrations -> MailerLite API -> Generate new token). Multi-account:
several keys can be connected and switched between (accounts.py owns the
JSON-blob storage). Mirrors bing-webmaster-connector/handlers_accounts.py.
"""
from imperal_sdk.types import ActionResult

from app import chat
from accounts import (
    _active_api_key, _add_account, _all_accounts, _disconnect_account, _mask, _switch_account,
)
from ml_api import ml_get, MailerLiteError
from params import AccountLabelParams, EmptyParams, SaveKeyParams
from response_models import (
    AccountDisconnected, AccountRecord, AccountsList, AccountSwitched, ConnectionStatus,
)


def _build_accounts_list(accounts: list[dict]) -> AccountsList:
    records = [
        AccountRecord(label=a.get("label", ""), masked_key=_mask(a.get("api_key", "")), is_active=bool(a.get("is_active")))
        for a in accounts
    ]
    return AccountsList(accounts=records, count=len(records))


@chat.function(
    "connection_status", action_type="read", chain_callable=True, data_model=ConnectionStatus,
    description=(
        "Whether the user's own MailerLite API key is connected. Use for: "
        "is my MailerLite account connected, connection status."
    ),
)
async def fn_connection_status(ctx, params: EmptyParams) -> ActionResult:
    """Whether the user's own MailerLite API key is connected."""
    key = await _active_api_key(ctx)
    masked = _mask(key)
    result = ConnectionStatus(connected=bool(key), masked_key=masked)
    summary = f"Connected ({masked})" if key else "Not connected"
    return ActionResult.success(data=result, summary=summary)


@chat.function(
    "save_mailerlite_key", action_type="write", event="mailerlite.account.connected",
    effects=["create:secret"], data_model=AccountRecord,
    description=(
        "Connect a MailerLite account by saving its API key. Validates the key against MailerLite before "
        "saving. Use for: connect my MailerLite account, save this API key."
    ),
)
async def fn_save_mailerlite_key(ctx, params: SaveKeyParams) -> ActionResult:
    """Connect a MailerLite account by saving its API key."""
    api_key = params.mailerlite_api_key.strip()
    try:
        await ml_get(ctx, api_key, "subscribers", params={"limit": 1})
    except MailerLiteError as e:
        return ActionResult.error(
            f"That API key doesn't seem to work: {e.message}. Double-check it in MailerLite -> "
            "Integrations -> MailerLite API.",
            retryable=False,
        )
    account = await _add_account(ctx, api_key, params.label)
    return ActionResult.success(
        data=AccountRecord(label=account["label"], masked_key=_mask(api_key), is_active=account["is_active"]),
        summary=f"Connected MailerLite account '{account['label']}'.",
        refresh_panels=["sidebar"],
    )


@chat.function(
    "list_mailerlite_accounts", action_type="read", chain_callable=True, data_model=AccountsList,
    description="List every MailerLite account you've connected — label, masked key, which one is active.",
)
async def fn_list_mailerlite_accounts(ctx, params: EmptyParams) -> ActionResult:
    """List every MailerLite account you've connected — label, masked key, which one is active."""
    accounts = await _all_accounts(ctx)
    result = _build_accounts_list(accounts)
    return ActionResult.success(data=result, summary=f"{result.count} MailerLite account(s) connected")


@chat.function(
    "switch_mailerlite_account", action_type="write", event="mailerlite.account.switched",
    effects=["update:secret"], data_model=AccountSwitched,
    description="Switch which connected MailerLite account is active — all following calls use this one.",
)
async def fn_switch_mailerlite_account(ctx, params: AccountLabelParams) -> ActionResult:
    """Switch which connected MailerLite account is active — all following calls use this one."""
    ok = await _switch_account(ctx, params.label)
    if not ok:
        return ActionResult.error(f"No connected MailerLite account labeled '{params.label}'.", retryable=False)
    return ActionResult.success(
        data=AccountSwitched(active=params.label), summary=f"Switched to '{params.label}'.",
        refresh_panels=["sidebar"],
    )


@chat.function(
    "disconnect_mailerlite_account", action_type="destructive", event="mailerlite.account.disconnected",
    effects=["delete:secret"], data_model=AccountDisconnected,
    description="Disconnect ONE specific connected MailerLite account by its label — removes only that key.",
)
async def fn_disconnect_mailerlite_account(ctx, params: AccountLabelParams) -> ActionResult:
    """Disconnect ONE specific connected MailerLite account by its label — removes only that key."""
    remaining = await _disconnect_account(ctx, params.label)
    return ActionResult.success(
        data=AccountDisconnected(label=params.label, remaining=remaining),
        summary=f"Disconnected '{params.label}'. {remaining} account(s) remain.",
        refresh_panels=["sidebar"],
    )

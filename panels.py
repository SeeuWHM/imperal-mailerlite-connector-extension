"""MailerLite sidebar panel — connect form when nothing's connected;
account selector + quick stats when connected. No OAuth here (MailerLite
issues a plain per-user API key) — same shape as
bing-webmaster-connector/panels.py (password-masked form + multi-account
selector, active one marked, click to switch).
"""
from __future__ import annotations

from imperal_sdk import ui

from app import ext
from accounts import _active_account, _all_accounts, mailerlite_ready
from ml_api import ml_get, MailerLiteError


def _key_form(error: str = "") -> list[ui.UINode]:
    """The API-key entry form itself — reused by the not-connected prompt and
    by the inline "add another account" block, so both stay in sync."""
    children = []
    if error:
        children.append(ui.Alert(message=error, type="error"))
    children.append(ui.Form(
        action="save_mailerlite_key",
        submit_label="Connect",
        children=[
            ui.Password(placeholder="Paste your MailerLite API key…", param_name="mailerlite_api_key"),
            ui.Input(placeholder="Label (optional, e.g. \"Client X\")", param_name="label"),
        ],
    ))
    children.append(ui.Text(
        content="Get your key at MailerLite → Integrations → MailerLite API → Generate new token.",
        variant="caption",
    ))
    return children


def _connect_form(error: str = "") -> ui.UINode:
    return ui.Stack(children=[
        ui.Header(text="MailerLite", level=4),
        ui.Badge(label="○ not connected", color="gray"),
        ui.Divider(),
        ui.Text(content=(
            "Connect your MailerLite API key to manage subscribers, groups, segments, "
            "campaigns, automations, forms, and webhooks from chat. You can connect more "
            "than one account and switch between them below."
        ), variant="body"),
        *_key_form(error),
    ])


def _account_items(accounts: list[dict]) -> list[ui.UINode]:
    """Every connected MailerLite account, active one marked, click any other
    to switch."""
    items = []
    for acc in accounts:
        label = acc.get("label", "")
        is_active = bool(acc.get("is_active"))
        items.append(ui.ListItem(
            id=label, title=label,
            subtitle="✓ Active" if is_active else "Click to switch",
            avatar=ui.Avatar(fallback=label[0].upper() if label else "?", size="sm"),
            badge=ui.Badge("✓", color="green") if is_active else None,
            on_click=None if is_active else ui.Call("switch_mailerlite_account", label=label),
            actions=[{"label": "Disconnect", "icon": "Trash2",
                      "on_click": ui.Call("disconnect_mailerlite_account", label=label)}],
        ))
    return items


@ext.panel("mailerlite_sidebar", slot="left", title="MailerLite", icon="Mail",
           default_width=260,
           refresh="on_event:mailerlite.account.connected,mailerlite.account.switched,mailerlite.account.disconnected")
async def sidebar_panel(ctx, show_add: bool = False):
    if not await mailerlite_ready(ctx):
        return _connect_form()

    accounts = await _all_accounts(ctx)
    active = await _active_account(ctx)
    active_label = (active or {}).get("label", "")
    active_key = (active or {}).get("api_key", "")

    subscriber_total = None
    group_total = None
    try:
        subs = await ml_get(ctx, active_key, "subscribers", params={"limit": 1})
        subscriber_total = (subs.get("meta") or {}).get("total")
        groups = await ml_get(ctx, active_key, "groups", params={"limit": 1})
        group_total = (groups.get("meta") or {}).get("total")
    except MailerLiteError as e:
        return ui.Stack(children=[
            ui.Header(text="MailerLite", level=4),
            ui.Badge(label="● connected", color="green"),
            ui.Divider(),
            ui.Alert(message=f"Couldn't reach MailerLite: {e.message}", type="error"),
            ui.Text(content=f"Accounts ({len(accounts)})", variant="caption"),
            ui.List(items=_account_items(accounts)) if accounts else ui.Empty(message="No accounts"),
        ])

    return ui.Stack(children=[
        ui.Header(text="MailerLite", level=4),
        ui.Badge(label="● connected", color="green"),
        ui.Divider(),
        ui.Text(content=f"Accounts ({len(accounts)})", variant="caption"),
        ui.List(items=_account_items(accounts)) if accounts else ui.Empty(message="No accounts"),
        ui.Stack(children=[
            ui.Divider(),
            ui.Text(content="Add another MailerLite account", variant="caption"),
            *_key_form(),
            ui.Button(label="Cancel", variant="ghost", size="sm",
                      on_click=ui.Call("__panel__mailerlite_sidebar", show_add=False)),
        ]) if show_add else
        ui.Button(label="Add another account", icon="Plus", variant="outline",
                  on_click=ui.Call("__panel__mailerlite_sidebar", show_add=True)),
        ui.Divider(),
        ui.Stats(children=[
            ui.Stat(label="Subscribers", value=str(subscriber_total or 0), icon="Users"),
            ui.Stat(label="Groups", value=str(group_total or 0), icon="Folder"),
        ]),
        ui.Text(content=f"{active_label} — connected", variant="caption"),
    ])

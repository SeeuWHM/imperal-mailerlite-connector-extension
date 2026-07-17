"""MailerLite sidebar panel — connect form when nothing's connected;
account selector + quick stats + a recent-campaigns list when connected.
No OAuth here (MailerLite issues a plain per-user API key) — same shape as
bing-webmaster-connector/panels.py (password-masked form + multi-account
selector, active one marked, click to switch).

Campaign list items open the center workspace (panels_workspace.py) — the
same "click a sidebar row -> open center dashboard" pattern as the GSC/Bing/
SE Ranking connectors' sidebars, so the center slot isn't a dead empty pane.
"""
from __future__ import annotations

from imperal_sdk import ui

from app import ext
from accounts import _active_account, _all_accounts, mailerlite_ready
from cache_models import SidebarStats
from ml_api import ml_get, MailerLiteError, validate_campaigns_limit

_SIDEBAR_CAMPAIGNS_LIMIT = 8
_STATS_TTL_SECONDS = 300  # 5 min — quick stats don't need to be live-fresh


def _stats_cache_key(label: str) -> str:
    # ctx.cache keys are capped at 128 chars and restricted to
    # [A-Za-z0-9_\-:] (I-CACHE-KEY-SAFETY) — account labels are free text
    # from the user, so hash rather than embed them raw.
    import hashlib
    digest = hashlib.sha256(label.encode("utf-8")).hexdigest()[:24]
    return f"mailerlite-stats-{digest}"


async def _fetch_sidebar_stats(ctx, active_key: str, active_label: str) -> SidebarStats:
    """The actual MailerLite calls — only runs on a cache miss (once per
    account per _STATS_TTL_SECONDS), not on every sidebar render.

    Subscriber count: GET /subscribers uses CURSOR pagination — confirmed
    live, its `meta` never carries a `total` field (only
    next_cursor/prev_cursor), unlike page-based endpoints. The documented
    GET /subscribers/count also 404s live despite being in MailerLite's own
    docs outline — not usable. So we pull one page at MailerLite's max page
    size (1000, confirmed live) and show the exact count when it all fits,
    or "N+" when a next_cursor says there's more.

    Campaigns: GET /campaigns IS page-based and DOES carry an exact
    meta.total + meta.aggregations (confirmed live) — used as-is, no
    approximation needed.
    """
    subs = await ml_get(ctx, active_key, "subscribers", params={"limit": 1000})
    sub_rows = subs.get("data") or []
    has_more = bool((subs.get("meta") or {}).get("next_cursor"))
    subscriber_display = f"{len(sub_rows):,}" + ("+" if has_more else "")

    campaigns = await ml_get(ctx, active_key, "campaigns", params={
        "limit": validate_campaigns_limit(10), "filter[status]": "sent",
    })
    camp_meta = campaigns.get("meta") or {}
    sent_campaigns = camp_meta.get("total", 0)
    total_campaigns = (camp_meta.get("aggregations") or {}).get("all", sent_campaigns)

    return SidebarStats(
        account_label=active_label,
        subscriber_display=subscriber_display,
        sent_campaigns=sent_campaigns,
        total_campaigns=total_campaigns,
    )


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

    campaigns_section: list[ui.UINode] = []
    try:
        # Quick-stats (subscriber count, sent/total campaigns) used to hit
        # the live MailerLite API on EVERY sidebar render. That's both
        # wasteful and was the root cause of the earlier stale-"0" bug's
        # sibling complaint: no reason to re-fetch a number that only
        # changes over minutes/hours. ctx.skeleton is off-limits from panel
        # context (guarded to @ext.skeleton only), so we use ctx.cache —
        # the panel-facing equivalent: refreshes once per
        # _STATS_TTL_SECONDS window instead of on every open.
        stats = await ctx.cache.get_or_fetch(
            _stats_cache_key(active_label), SidebarStats,
            lambda: _fetch_sidebar_stats(ctx, active_key, active_label),
            ttl_seconds=_STATS_TTL_SECONDS,
        )
        subscriber_total = stats.subscriber_display
        sent_campaigns = stats.sent_campaigns
        total_campaigns = stats.total_campaigns

        campaigns = await ml_get(ctx, active_key, "campaigns", params={
            "limit": validate_campaigns_limit(_SIDEBAR_CAMPAIGNS_LIMIT),
            "filter[status]": "sent",
        })
        camp_rows = campaigns.get("data") or []
        if camp_rows:
            campaigns_section = [
                ui.Divider(),
                ui.Text(content=f"Recent campaigns ({len(camp_rows)})", variant="caption"),
                ui.List(items=[
                    ui.ListItem(
                        id=str(r.get("id", "")),
                        title=((r.get("emails") or [{}])[0].get("subject") or r.get("name") or "(no subject)"),
                        subtitle=f"{(r.get('stats') or {}).get('sent', 0)} sent",
                        badge=ui.Badge(label=((r.get("stats") or {}).get("open_rate") or {}).get("string", ""), color="green"),
                        on_click=ui.Call("__panel__mailerlite_workspace", campaign_id=str(r.get("id", ""))),
                    )
                    for r in camp_rows
                ]),
                ui.Button(label="Open dashboard", icon="LayoutDashboard", variant="outline", size="sm",
                          # campaign_id="" explicit — platform carries forward
                          # the last-opened campaign's id otherwise (param
                          # accumulation across __panel__ calls), which is why
                          # this button did nothing when a campaign was open.
                          on_click=ui.Call("__panel__mailerlite_workspace", campaign_id="")),
            ]
    except MailerLiteError as e:
        return ui.Stack(children=[
            ui.Header(text="MailerLite", level=4),
            ui.Badge(label="● connected", color="green"),
            ui.Divider(),
            ui.Alert(message=f"Couldn't reach MailerLite: {e.message}", type="error"),
            ui.Text(content=f"Accounts ({len(accounts)})", variant="caption"),
            ui.List(items=_account_items(accounts)) if accounts else ui.Empty(message="No accounts"),
        ])

    root = ui.Stack(children=[
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
            ui.Stat(label="Subscribers", value=subscriber_total, icon="Users"),
            ui.Stat(label="Campaigns sent", value=f"{sent_campaigns}/{total_campaigns}", icon="Send"),
        ]),
        *campaigns_section,
        ui.Text(content=f"{active_label} — connected", variant="caption"),
    ])
    # Claim the center slot so opening this panel also opens the campaign
    # dashboard there instead of leaving it an empty pane — same fix
    # GSC/SE Ranking's sidebars needed.
    root.props["auto_action"] = ui.Call("__panel__mailerlite_workspace", campaign_id="").to_dict()
    return root

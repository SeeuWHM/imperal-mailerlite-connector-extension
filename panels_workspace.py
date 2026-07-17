"""MailerLite center workspace — a real dashboard instead of an empty pane.

Two views in one panel (same "overview vs detail" shape as
bing-webmaster-connector/se-ranking's workspace panels):
  - no campaign_id: overview — aggregate stats across recent sent campaigns
    + a sortable table to browse them.
  - campaign_id set: one campaign's full performance — stat cards, a
    send-funnel bar chart (sent -> delivered -> opened -> clicked), and its
    engagement rates, all straight from MailerLite's own `stats` block
    (confirmed live shape — see docs/research.md).

Reuses ml_get directly (zero LLM tokens, same pattern as every other
connector's workspace panel).
"""
from __future__ import annotations

from imperal_sdk import ui

from app import ext
from accounts import _active_account, mailerlite_ready
from ml_api import ml_get, MailerLiteError, validate_campaigns_limit

_OVERVIEW_LIMIT = 10


def _rate_str(stats: dict, key: str) -> str:
    """MailerLite returns rates as {"float": ..., "string": "12.3%"} — we
    always want the pre-formatted string, falling back safely if absent."""
    block = stats.get(key)
    if isinstance(block, dict):
        return block.get("string", "") or "0%"
    return "0%"


def _campaign_row(row: dict) -> dict:
    email0 = (row.get("emails") or [{}])[0] if row.get("emails") else {}
    stats = row.get("stats") or {}
    return {
        "subject": email0.get("subject") or row.get("name") or "(no subject)",
        "status": row.get("status", "") or "",
        "sent": stats.get("sent", 0) or 0,
        "open_rate": _rate_str(stats, "open_rate"),
        "click_rate": _rate_str(stats, "click_rate"),
        "id": str(row.get("id", "")),
    }


def _retry_button() -> ui.UINode:
    """Always-present recovery action — without this, an error mid-load left
    the user with zero clickable path back (the actual bug behind \"back to
    overview\"/\"open dashboard\" doing nothing for one particular connected
    account: its campaigns call failed and the error screen had no button
    at all, not even a broken one)."""
    return ui.Button(label="↻ Retry", variant="outline", size="sm",
                      on_click=ui.Call("__panel__mailerlite_workspace"))


async def _overview(ctx, key: str) -> ui.UINode:
    try:
        data = await ml_get(ctx, key, "campaigns", {
            "limit": validate_campaigns_limit(_OVERVIEW_LIMIT),
            "filter[status]": "sent",
        })
    except MailerLiteError as e:
        return ui.Stack(children=[
            ui.Alert(message=f"Couldn't reach MailerLite: {e.message}", type="error"),
            _retry_button(),
        ])
    except Exception as e:
        # A non-MailerLiteError (network hiccup, unexpected response shape)
        # must still leave the user a way out — never a dead-end blank/error
        # screen with no clickable path back.
        return ui.Stack(children=[
            ui.Alert(message=f"Unexpected error loading campaigns: {e}", type="error"),
            _retry_button(),
        ])

    rows = data.get("data") or []
    if not rows:
        return ui.Stack(children=[
            ui.Header(text="Campaigns", level=4),
            ui.Empty(message="No sent campaigns yet — once you send one, its results show up here."),
        ])

    parsed = [_campaign_row(r) for r in rows]
    total_sent = sum(p["sent"] for p in parsed)
    # Average the *float* rates for the summary stat cards (string form is
    # per-campaign display only); recompute from the raw rows so we don't
    # need to re-parse the formatted string.
    open_floats = [
        ((r.get("stats") or {}).get("open_rate") or {}).get("float", 0) or 0 for r in rows
    ]
    click_floats = [
        ((r.get("stats") or {}).get("click_rate") or {}).get("float", 0) or 0 for r in rows
    ]
    avg_open = (sum(open_floats) / len(open_floats) * 100) if open_floats else 0
    avg_click = (sum(click_floats) / len(click_floats) * 100) if click_floats else 0

    chart_data = [
        {"campaign": p["subject"][:18] + ("…" if len(p["subject"]) > 18 else ""),
         "opens": round(float(p["open_rate"].rstrip("%") or 0), 1),
         "clicks": round(float(p["click_rate"].rstrip("%") or 0), 1)}
        for p in reversed(parsed)  # oldest -> newest reads left to right
    ]

    # A plain DataTable's on_row_click can only carry ONE shared UIAction, not
    # a per-row campaign_id — so navigation uses a ListItem list instead (each
    # item can bind its own on_click), same workaround the GSC/SE Ranking
    # workspace panels use for per-row navigation.
    list_view = ui.List(items=[
        ui.ListItem(
            id=p["id"], title=p["subject"],
            subtitle=f"{p['sent']} sent · {p['open_rate']} opens · {p['click_rate']} clicks",
            badge=ui.Badge(label=p["status"], color="green" if p["status"] == "sent" else "gray"),
            on_click=ui.Call("__panel__mailerlite_workspace", campaign_id=p["id"]),
        )
        for p in parsed
    ])

    return ui.Stack(children=[
        ui.Header(text="Campaign performance", level=4, subtitle=f"Last {len(parsed)} sent campaigns"),
        ui.Stats(children=[
            ui.Stat(label="Total sent", value=f"{total_sent:,}", icon="Send", color="blue"),
            ui.Stat(label="Avg. open rate", value=f"{avg_open:.1f}%", icon="MailOpen", color="green"),
            ui.Stat(label="Avg. click rate", value=f"{avg_click:.1f}%", icon="MousePointerClick", color="purple"),
        ]),
        ui.Chart(data=chart_data, type="bar", x_key="campaign", height=220,
                 colors={"opens": "#03A154", "clicks": "#6366F1"}),
        ui.Divider(),
        ui.Header(text="Recent campaigns", level=5),
        list_view,
    ])


async def _detail(ctx, key: str, campaign_id: str) -> ui.UINode:
    back_btn = ui.Button(label="← Back to overview", variant="ghost", size="sm",
                          on_click=ui.Call("__panel__mailerlite_workspace"))
    try:
        data = await ml_get(ctx, key, f"campaigns/{campaign_id}")
    except MailerLiteError as e:
        return ui.Stack(children=[
            back_btn,
            ui.Alert(message=f"Couldn't load that campaign: {e.message}", type="error"),
        ])
    except Exception as e:
        return ui.Stack(children=[
            back_btn,
            ui.Alert(message=f"Unexpected error loading that campaign: {e}", type="error"),
        ])

    row = data.get("data") or {}
    email0 = (row.get("emails") or [{}])[0] if row.get("emails") else {}
    stats = row.get("stats") or {}
    subject = email0.get("subject") or row.get("name") or "(no subject)"

    funnel = [
        {"stage": "Sent", "count": stats.get("sent", 0) or 0},
        {"stage": "Delivered", "count": stats.get("deliveries_count", 0) or 0},
        {"stage": "Opened", "count": stats.get("opens_count", 0) or 0},
        {"stage": "Clicked", "count": stats.get("clicks_count", 0) or 0},
    ]

    return ui.Stack(children=[
        back_btn,
        ui.Header(text=subject, level=4,
                   subtitle=f"{row.get('type_for_humans', row.get('type', ''))} · {row.get('status', '')}"),
        ui.Stats(children=[
            ui.Stat(label="Sent", value=f"{stats.get('sent', 0):,}", icon="Send", color="blue"),
            ui.Stat(label="Opens", value=f"{stats.get('opens_count', 0):,}",
                    trend=_rate_str(stats, "open_rate"), icon="MailOpen", color="green"),
            ui.Stat(label="Clicks", value=f"{stats.get('clicks_count', 0):,}",
                    trend=_rate_str(stats, "click_rate"), icon="MousePointerClick", color="purple"),
            ui.Stat(label="Unsubscribes", value=f"{stats.get('unsubscribes_count', 0):,}",
                    trend=_rate_str(stats, "unsubscribe_rate"), icon="UserMinus", color="red"),
        ]),
        ui.Chart(data=funnel, type="bar", x_key="stage", height=200,
                 colors={"count": "#03A154"}),
        ui.Divider(),
        ui.KeyValue(items=[
            {"key": "Delivery rate", "value": _rate_str(stats, "delivery_rate")},
            {"key": "Click-to-open rate", "value": _rate_str(stats, "click_to_open_rate")},
            {"key": "Hard bounces", "value": str(stats.get("hard_bounces_count", 0))},
            {"key": "Soft bounces", "value": str(stats.get("soft_bounces_count", 0))},
            {"key": "Spam complaints", "value": str(stats.get("spam_count", 0))},
            {"key": "From", "value": email0.get("from", "") or "—"},
            {"key": "Sent at", "value": row.get("finished_at") or row.get("scheduled_for") or "—"},
        ], columns=2),
    ])


@ext.panel("mailerlite_workspace", slot="center", title="MailerLite", icon="Mail")
async def workspace_panel(ctx, campaign_id: str = ""):
    try:
        if not await mailerlite_ready(ctx):
            return ui.Empty(message="Connect your MailerLite account first — paste your API key in the left panel.")

        active = await _active_account(ctx)
        key = (active or {}).get("api_key", "")
        if campaign_id:
            return await _detail(ctx, key, campaign_id)
        return await _overview(ctx, key)
    except Exception as e:
        # Last-resort safety net: whatever went wrong, the user must always
        # get a working button back to the overview — this is the actual
        # root cause of "back to overview"/"open dashboard" doing nothing
        # for one particular account: an unhandled exception here meant the
        # panel rendered NOTHING, so there was no button to click at all.
        return ui.Stack(children=[
            ui.Alert(message=f"Something went wrong loading the MailerLite dashboard: {e}", type="error"),
            _retry_button(),
        ])

"""MailerLite Connector — core init + shared helpers.

Architecture: like the Bing Webmaster Connector (plain per-user API key, no
OAuth dance) and UNlike the SE Ranking connector (one shared company key
proxied through a backend microservice) — MailerLite issues a personal API
key per account (MailerLite -> Integrations -> MailerLite API -> "Generate
new token"), so each Imperal user brings their OWN key and this extension
calls https://connect.mailerlite.com/api directly with ctx.http. No shared
backend microservice is architecturally required for this reason (see
docs/research.md for the full trade-off note and exact doc citations).

Multi-account: several MailerLite accounts (each with its own API key) can be
connected simultaneously and switched between — same JSON-blob pattern as
bing_accounts.py / gsc's accounts.py (see accounts.py in this extension).

Reference docs read to build this (see docs/research.md for the full list
and exact quotes):
  https://developers.mailerlite.com/docs/  (getting started: auth, base URL,
    rate limits, errors)
  https://developers.mailerlite.com/api/*  (per-entity endpoint reference:
    subscribers, groups, segments, campaigns, automations, forms, fields,
    webhooks, campaign-languages, timezones, batching)
  https://www.mailerlite.com/pricing        (current plan names/limits)
"""
from __future__ import annotations

from imperal_sdk import Extension, ChatExtension

MAILERLITE_API_BASE = "https://connect.mailerlite.com/api"

# Confirmed via developers.mailerlite.com/docs/ ("Getting started" -> rate
# limits section) and cross-checked against independent mirrors (Zapier's
# MailerLite guide, Rollout's integration guide) since the live docs page
# renders its numbers inside an interactive widget our reader couldn't
# extract verbatim. Global cap; a separate 5 req/min cap applies ONLY to
# bulk-subscriber-upsert batches (api/batching docs — confirmed verbatim).
GLOBAL_RATE_LIMIT_PER_MINUTE = 120
SUBSCRIBER_IMPORT_RATE_LIMIT_PER_MINUTE = 5
BATCH_MAX_REQUESTS = 50

ext = Extension(
    "mailerlite-connector",
    version="0.1.0",
    display_name="MailerLite Connector",
    description=(
        "MailerLite email marketing — manage subscribers, groups, segments, "
        "campaigns, automations, forms, custom fields, and webhooks. Connect "
        "your own MailerLite API key to read and manage your own account's "
        "data here. Some features are plan-gated by MailerLite itself (e.g. "
        "resend/multivariate campaigns, advanced automation triggers) — this "
        "extension detects and reports that honestly rather than guessing."
    ),
    icon="icon.svg",
    actions_explicit=True,
    capabilities=[
        "Subscribers",
        "Groups",
        "Segments",
        "Campaigns",
        "Automations",
        "Forms",
        "Custom Fields",
        "Webhooks",
        "Plan-aware feature gating",
    ],
)

chat = ChatExtension(
    ext,
    tool_name="mailerlite",
    description=(
        "MailerLite — email marketing platform. Use for: subscribers, mailing "
        "groups/segments, email campaigns, automations, signup forms, custom "
        "fields, webhooks."
    ),
)


# File Mage L3 — declares this app as a valid destination when the user has
# an uploaded file (via the file-reader system ext) and wants it turned into
# a MailerLite campaign. `arg="content_html"` maps the file's EXTRACTED TEXT
# straight into the existing content_html field (arg_kind="text") — e.g. a
# ready-made HTML email template dropped in and turned into a draft campaign.
# Text-only source formats since content_html expects markup/text, not a
# structured document.
ext.file_sink(
    "create_campaign",
    accepts=["text/html", "text/*"],
    arg="content_html",
    arg_kind="text",
    description="Turn an uploaded HTML email template into a new draft campaign",
)


@ext.health_check
async def health(ctx) -> dict:
    """Report whether the user has at least one MailerLite account connected."""
    from accounts import mailerlite_ready
    return {"status": "ok", "version": ext.version, "mailerlite_connected": await mailerlite_ready(ctx)}


# ── User-scope secret: every connected MailerLite API key ────────────────────
# A real per-user credential, interpreted literally as the key value: no URL
# or account identifier is ever assembled or guessed from it. JSON list of
# {label, api_key, is_active} — same multi-account shape as the Bing
# Webmaster connector's `bing_accounts` / SE Ranking's `seranking_accounts`.
# write_mode="extension": only this extension's own connect/switch/disconnect
# handlers write it, never the platform's generic Secrets panel, since its
# shape is a JSON blob, not one opaque value.
#
# THIS DECLARATION WAS MISSING (the bug that made the left sidebar panel
# vanish almost instantly): without it, the secret this whole extension reads
# on every panel render (accounts.py's ACCOUNTS_SECRET) was never registered
# in the manifest, so the platform had no declared secret to back the panel's
# ctx.secrets reads/writes against.
ext.secret(
    name="mailerlite_accounts",
    description=(
        "Every MailerLite account you've connected (JSON list of "
        "{label, api_key, is_active}) — lets you track multiple MailerLite "
        "accounts and switch between them. Managed only through this "
        "extension's own connect/switch/disconnect actions."
    ),
    required=False,
    write_mode="extension",
    scope="user",
    max_bytes=8192,
)(lambda: None)

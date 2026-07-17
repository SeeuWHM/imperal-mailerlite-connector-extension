# MailerLite Connector

[![Imperal SDK](https://img.shields.io/badge/imperal--sdk-5.9.9-blue)](https://pypi.org/project/imperal-sdk/)
[![Version](https://img.shields.io/badge/version-0.1.0-green)](https://github.com/SeeuWHM/imperal-mailerlite-connector-extension/releases)
[![License](https://img.shields.io/badge/license-LGPL--2.1-orange)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Imperal%20Cloud-purple)](https://panel.imperal.io)

**[MailerLite](https://www.mailerlite.com/) email marketing extension for [Imperal Cloud](https://panel.imperal.io).**

Subscribers, groups, segments, campaigns, automations, forms, custom fields, and webhooks — via the user's own MailerLite API key, no OAuth, no shared backend proxy.

---

## What It Does

Talk to it naturally:

```
"add this subscriber to my newsletter group"
"create a campaign for the summer sale"
"how many subscribers do I have in the VIP segment"
"delete the old promotion form"
"what's my automation activity look like this month"
"am I on a plan that supports multivariate campaigns?"
```

---

## Architecture

Like `bing-webmaster-connector`: a plain per-user API key model. MailerLite
issues one personal API token per account (Integrations → MailerLite API →
Generate new token). Each Imperal user brings their own key; this extension
calls `https://connect.mailerlite.com/api` directly. Multiple accounts can be
connected and switched between (`accounts.py`, same JSON-blob pattern as the
other connectors in this repo).

No shared backend microservice is required — unlike `se-ranking-extension`,
where one company-wide API key is proxied for all users, MailerLite's auth
model is inherently per-user.

## Coverage

| Category | Operations |
|---|---|
| Accounts | connect/list/switch/disconnect (multi-account) |
| Subscribers | list, upsert, get, delete, forget (GDPR), activity, group assign/unassign |
| Groups | list, create, rename, delete, subscribers |
| Segments | list, rename, delete, subscribers (no create — MailerLite's API has none) |
| Campaigns | list, get, create, update, schedule, cancel, delete |
| Automations | list, get, activity, create draft (name only), delete (no step authoring — MailerLite's API has none) |
| Forms | list (by type: popup/embedded/promotion), rename, delete, subscribers |
| Fields | list, create, rename, delete |
| Webhooks | list, create, delete |
| Reference | campaign languages, timezones |
| Capability | plan-limit status (never a guess — either a live-observed fact or a direct MailerLite doc quote) |

See [`docs/research.md`](docs/research.md) for the full research trail (every
endpoint verified against live account calls, not just prose docs) and
[`docs/capability-matrix.md`](docs/capability-matrix.md) for the
plan-awareness design rationale.

## Plan-awareness

MailerLite's API has no "what plan am I on" endpoint. This extension never
guesses: `mailerlite_capability_status` reports either (a) an outcome actually
observed from a real API call this account made (cached 7 days), or (b) a
direct quote from MailerLite's own docs about a plan-gated feature — always
labeled as to which it is.

## Development

```bash
python3 -m venv .venv
./.venv/bin/pip install imperal-sdk pytest pytest-asyncio
./.venv/bin/python -m pytest tests/ -q
./.venv/bin/imperal build .
./.venv/bin/imperal validate .
```

64 pytest cases, 0 errors / 0 warnings on `imperal validate`.

---

## Built with

- [imperal-sdk](https://github.com/imperalcloud/imperal-sdk) 5.9.9
- [Imperal Cloud](https://panel.imperal.io)

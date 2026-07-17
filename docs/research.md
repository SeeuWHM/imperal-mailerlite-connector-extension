# MailerLite API — research notes

Sources read (2026-07-17): developers.mailerlite.com/docs (getting started),
developers.mailerlite.com/api/{subscribers,groups,segments,campaigns,
automations,forms,fields,webhooks,campaign-languages,timezones,batching},
mailerlite.com/pricing, plus **live verification against a real account's API
key** (read-only probes + create/delete round-trips, cleaned up immediately —
see "Empirically confirmed" section). Nothing below is invented; anything not
directly confirmed is marked as such.

## Auth & transport

- Base URL: `https://connect.mailerlite.com/api` (confirmed live).
- Header: `Authorization: Bearer <api_key>` + `Accept: application/json` +
  `Content-Type: application/json` on writes.
- Key is generated in MailerLite UI: Integrations -> MailerLite API ->
  "Generate new token". Bound to the creating user; revoked if that user is
  removed from the account.
- No OAuth. One key = one MailerLite account. Confirmed format: a
  dot-separated 3-segment token (JWT-shaped), ~900+ chars.
- API versioning: requests use "latest" unless a specific date is pinned via
  a header (docs mention this but exact header name wasn't extracted
  verbatim from the rendered page — treat as unconfirmed, don't hardcode).

## Rate limits

- Global: confirmed via docs + 2 independent third-party integration guides
  (Zapier, Rollout) as **120 requests/minute** per API key. Exceeding it
  returns `429`.
- Bulk subscriber-upsert batches (POST requests consisting entirely of
  `POST api/subscribers`) are auto-detected server-side as an import job and
  are ADDITIONALLY capped at **5 requests/minute** for that import path.
- Batch endpoint (`POST /api/batching`): up to **50** sub-requests per call,
  each `{method, path, body}`; `path` must start with `api/`; order of
  responses matches order of requests; a failed sub-request doesn't fail the
  whole batch (its own error is returned in its slot). Webhooks are not
  supported inside a batch.

## Error shapes — CONFIRMED LIVE (not from docs prose, from real responses)

- `401` unauthenticated / bad key: `{"message": "Unauthenticated."}`
- `404` unknown resource (bad subscriber/group/automation id, or a
  subscriber with literally no activity yet): `{"message": "Resource does
  not exist."}` — **important gotcha**: a brand-new subscriber's
  `/activity` endpoint 404s (not an empty list) until they have at least one
  event. Don't treat 404 there as "invalid id".
- `422` validation error: `{"message": "<human summary>", "errors": {
  "<field>": ["<message>", ...] }}` — Laravel-style validation body.
- **Plan-gating surfaces INSIDE a 422 body as a field-level message**, e.g.
  creating a campaign with rich `content` on this account's plan returned:
  `"errors": {"emails.0.content": ["Content submission is only available on
  Premium plan."]}`. This is the load-bearing discovery for our
  plan-awareness design (see docs/capability-matrix.md) — MailerLite itself
  tells you in plain English when a field/feature needs a higher plan. We
  detect this pattern (look for "plan" in the 422 error text) rather than
  memorizing a static table.

## Entities & endpoints actually documented (developers.mailerlite.com/api/*)

### Subscribers (`/api/subscribers`)
- `GET /subscribers` — list, filter[status], limit (default 25), cursor,
  include=groups
- `POST /subscribers` — create/upsert (non-destructive: omitted
  fields/groups are NOT removed)
- `PUT /subscribers/{id}` — update
- `GET /subscribers/{id}` — fetch one
- `GET /subscribers/count` (per docs outline) — total count. **NOTE**: not
  independently re-verified live in this pass (only `?limit=1` list was
  probed) — treat path as documented-not-reverified.
- `GET /subscribers/{id}/activity` — confirmed live: 404s if no activity yet
- `DELETE /subscribers/{id}` — confirmed live (204)
- `POST /subscribers/{id}/forget` — GDPR-style anonymize (documented, not
  live-tested — destructive/irreversible, correctly not probed against a
  real user's data)
- `POST /subscribers/{sub_id}/groups/{group_id}` — assign to group
  (confirmed live, 200, returns the group object)
- `DELETE /subscribers/{sub_id}/groups/{group_id}` — unassign (confirmed
  live, 204)
- `GET /subscribers/import/{id}` — single import status

### Groups (`/api/groups`)
- `GET /groups` — list, limit (max 1000 per account), page, filter[name],
  sort
- `POST /groups` — create (confirmed live, 201)
- `PUT /groups/{id}` — rename
- `DELETE /groups/{id}` — delete (confirmed live, 204)
- `GET /groups/{id}/subscribers` — list members, filter[status] (default
  active), limit (default 50, max 1000), cursor, include=groups

### Segments (`/api/segments`) — **read/rename/delete ONLY, no create**
- `GET /segments` — list (max 250 segments/account)
- `GET /segments/{id}/subscribers` — members
- `PUT /segments/{id}` — rename only (`name` field)
- `DELETE /segments/{id}`
- Segment RULES (the filter logic itself) are built in the MailerLite UI
  only — the public REST API has no documented way to define/edit a
  segment's matching criteria, only to list/rename/delete existing ones.

### Campaigns (`/api/campaigns`)
- `GET /campaigns` — filter[status] (sent/draft/ready, default ready),
  filter[type] (regular/ab/resend/rss, default all). **`limit` is NOT a free
  integer — confirmed live whitelist: {1, 10, 25, 50, 100}; any other value
  (2, 5, 9, 20, 30, 150, 200, 0) returns 422 "The selected limit is
  invalid."** This isn't in the prose docs; found by direct probing.
- `GET /campaigns/{id}` — fetch one
- `POST /campaigns` — create. `type` must be one of regular/ab/resend/
  multivariate. **Per the docs text (still using OLD plan names): "Types
  `resend` and `multivariate` are only available for accounts on growing or
  advanced plans."** Confirmed live that submitting rich HTML `content` on
  this test account's current plan is rejected with a 422 naming "Premium
  plan" as the requirement — i.e. the doc's own plan-name vocabulary
  ("growing/advanced") does NOT match MailerLite's current public plan names
  (Free/Comfort/Power/Enterprise, formerly Free/Growing Business/Advanced;
  "Premium" appears nowhere in the current public plan list either) — this
  three-way naming mismatch is exactly why we do NOT hardcode a plan name
  string anywhere in the gating logic; we surface MailerLite's own error
  text verbatim to the user instead of translating it into a specific plan
  name that might already be stale.
- `PUT /campaigns/{id}` — update
- `POST /campaigns/{id}/schedule` — schedule
- `POST /campaigns/{id}/cancel` — cancel a ready (not-yet-sent) campaign
- `DELETE /campaigns/{id}` — delete
- `GET /campaigns/{id}/reports/...` (activity of a SENT campaign, per-
  subscriber opens/clicks) — documented, not live-probed (this account had
  no sent campaigns with reportable activity in-scope to test against
  safely)

### Automations (`/api/automations`) — **view-only, no step/workflow editing**
- `GET /automations` — filter[enabled], filter[name], filter[group], page,
  limit (default 10)
- `GET /automations/{id}` — fetch one
- `GET /automations/{id}/activity` — confirmed live: rich per-subscriber
  step-run history (status, step descriptions, timestamps, current step,
  even the email content of the step). filter[status] is REQUIRED
  (completed/active/canceled/failed) plus a date-range filter appropriate to
  that status.
- `POST /automations` — create a DRAFT automation shell (name only) — you
  cannot programmatically define triggers/steps/emails via the public API;
  that part is UI-only.
- `DELETE /automations/{id}`

### Forms (`/api/forms/{type}`) — **type is a PATH SEGMENT, not a query
param** (confirmed live: `/forms/popup`, `/forms/embedded`,
`/forms/promotion` all 200; a `?type=` query param is silently ignored by
the router and would list the wrong/default set — this is a real bug class
to avoid in our client code)
- `GET /forms/{popup|embedded|promotion}` — list + basic stats, limit, page,
  filter[name], sort (created_at/name/conversions_count/opens_count/
  visitors/conversion_rate/last_registration_at)
- `GET /forms/{id}` — fetch one (id, not type, in the path here)
- `PUT /forms/{id}` — rename only
- `DELETE /forms/{id}`
- `GET /forms/{id}/subscribers` — signups through that form

### Fields (`/api/fields`)
- `GET /fields` — list (max 100/account), filter[keyword], filter[type]
  (text/number/date), sort
- `POST /fields` — create (name, type: text/number/date)
- `PUT /fields/{id}` — rename
- `DELETE /fields/{id}`

### Webhooks (`/api/webhooks`)
- Full CRUD (list/get/create/update/delete) — event catalogue confirmed:
  subscriber.{created,updated,unsubscribed,added_to_group,
  removed_from_group,bounced,automation_triggered,automation_completed,
  spam_reported,deleted,active}, campaign.{sent,click,open}.
  `campaign.click`/`campaign.open`/`subscriber.deleted` REQUIRE
  `batchable: true` to be set on the webhook. Only fires for active
  accounts.

### Reference/lookup data
- `GET /campaigns/languages` — language_id values for the unsubscribe
  template
- `GET /timezones` — valid timezone ids for automations/campaign scheduling

### Batching
- `POST /batching` — see Rate limits above for the full contract.

## Scope NOT covered in v1 (explicit, so nothing is silently missing)

- **Ecommerce endpoints** — MailerLite's MCP server description mentions
  broader e-commerce integration surface, but this wasn't independently
  verified against the public REST docs in this pass; deferred out of v1
  rather than guessed at.
- **Sites/landing pages/websites builder** — mentioned on the pricing page
  as a product feature, no corresponding public REST API found in
  developers.mailerlite.com/api/* during this research pass. Not included.
- **Automation step/trigger authoring** — confirmed NOT possible via public
  REST API (see Automations above) — draft-shell create + read/delete only.
- **Segment rule authoring** — confirmed NOT possible via public REST API
  (see Segments above) — read/rename/delete only.
- **Account/plan info endpoint** — no such endpoint found anywhere in the
  public docs. This is why capability-matrix.md's detection strategy is
  runtime-error-based rather than "ask the API what plan you're on".

## Plan naming — confirmed inconsistency (do not paper over this)

Three different vocabularies exist simultaneously, confirmed from three
different official/semi-official sources on the same day:
1. Current public pricing page (mailerlite.com/pricing): **Free, Growing
   Business, Advanced** tier *tiles*, but third-party trackers report
   MailerLite recently renamed the paid tiers to **Comfort** and **Power**
   (Enterprise unchanged) — the live pricing page content extracted in this
   session showed unlabeled comparison numbers (extraction lost the header
   row), so tier-to-limit mapping from the page itself is NOT fully
   reconstructed here; only the third-party rename report is used, flagged
   as un-primary-sourced.
2. developers.mailerlite.com/api/campaigns still literally says "growing or
   advanced plans" for `resend`/`multivariate` campaign types.
3. The LIVE 422 error text this session actually received said **"Premium
   plan"** — a name that appears in NONE of the above lists.
This is exactly the scenario the task anticipated ("если по планам нет
точной публичной матрицы... явно зафиксировать это") — see
capability-matrix.md for how the extension handles it without guessing.

# Plan-awareness / capability-matrix design

## The core problem

MailerLite has no public "what plan am I on / what can I do" API endpoint
(confirmed in research.md). Its own plan *names* are inconsistent across its
own docs, marketing site, and live error messages (three different
vocabularies observed in one research session — see research.md's "Plan
naming" section). Hardcoding a static "Free/Comfort/Power/Enterprise ->
these exact endpoints" table would therefore be **fabricating precision
MailerLite itself doesn't expose consistently** — exactly what the user
told us not to do.

## The mechanism: runtime detection + cache, not a static table

### 1. Known-gated operations (a short, HONEST list — not a full matrix)

We keep a small `GATED_HINTS` list in `capability.py` of operations that
MailerLite's own **documentation prose** explicitly calls out as
plan-restricted (verbatim source cited per entry, from research.md):
- Campaign type `resend` / `multivariate` — "only available for accounts on
  growing or advanced plans" (developers.mailerlite.com/api/campaigns)
- Rich HTML campaign `content` — confirmed LIVE via 422 body: "Content
  submission is only available on Premium plan."

These are used only to give Webbee an UPFRONT hint ("this might be plan-
gated, expect a possible rejection") — never as a hard client-side block.
We never refuse to attempt a call because of this list; MailerLite is the
only authority that actually knows the caller's plan.

### 2. Live detection: read MailerLite's own error text

Every write call goes through one shared `_post`/`_put` wrapper in
`ml_api.py`. On a `422`, we inspect `errors.*` messages: if any message
contains "plan" (case-insensitive) — MailerLite's actual observed
vocabulary for this ("...only available on X plan.") — we classify the
error as `plan_restricted` instead of a generic validation error, and:
- Return that EXACT sentence to the user (never translated/reworded into a
  guessed plan name — see research.md's 3-way naming mismatch), plus which
  field/feature triggered it.
- Cache the fact "operation X is plan_restricted for this account" (see
  below) so we don't need to hit the API again to warn pre-emptively next
  time.

### 3. Per-account capability cache

`ctx.secrets` (same store as the API key) holds a small JSON blob per
connected account: `mailerlite_capability_cache` = `{"<capability_key>":
{"restricted": true, "message": "...", "checked_at": "<iso ts>"}, ...}`.
- Populated lazily, only from REAL observed 422s (never guessed).
- TTL: 7 days (plans can change — upgrade/downgrade — so a stale "blocked"
  verdict must expire and get re-checked rather than becoming permanent
  truth).
- `check_capability` chat function reads this cache (skeleton-friendly, zero
  extra HTTP call) so Webbee can proactively say "this needs a higher
  MailerLite plan — want me to try anyway?" instead of discovering it only
  after a failed create.
- A cache entry is invalidated immediately if the SAME capability_key
  succeeds later (e.g. user upgraded) — success always overwrites a stale
  "restricted" verdict.

### 4. What Webbee is told to do (skeleton instruction + function
descriptions)

- Skeleton (`skeleton_mailerlite_config`) exposes `plan_notes`: the raw list
  of GATED_HINTS descriptions plus any cached restricted verdicts — so
  Webbee has this context without an extra tool round-trip.
- Every write-side chat function whose underlying endpoint is a known
  candidate for gating (create_campaign with type=resend/multivariate or
  rich content, create_automation trigger authoring which isn't possible at
  all via API) states this plainly in its own `description` — so the LLM
  doesn't need runtime discovery to know it might not work.
- On an actual `plan_restricted` error, `ActionResult.error()` carries
  MailerLite's own sentence verbatim plus a short, honest note: "This is a
  MailerLite plan limit, not an Imperal limit — check your MailerLite
  billing plan if you want this feature." No guessing which specific plan
  tier is required (see the 3-way naming mismatch — we'd likely say the
  WRONG plan name).

### 5. Explicitly-impossible-via-API operations (not a plan issue at all)

Two real API gaps are NOT plan-gating and must never be described as such
(would be actively misleading):
- Automation step/trigger authoring — impossible via public API on ANY
  plan; `create_automation` only creates a nameless draft shell. The
  function description says this outright.
- Segment rule (filter) authoring — impossible via public API on ANY plan;
  only list/rename/delete exist. Function set reflects this (no
  `create_segment`/`update_segment_rules` function exists at all — we don't
  offer a tool that can't do anything real).

### 6. Known API quirks folded into the same honesty principle

- `campaigns` list `limit` only accepts {1,10,25,50,100} (confirmed live,
  undocumented) — `ml_api.py` validates client-side before the call and
  returns a clear message rather than forwarding MailerLite's generic 422.
- `forms` "type" is a path segment (`/forms/{type}`), not a query param —
  our client signature makes `form_type` a required positional-style field
  so this mistake can't happen silently.
- A subscriber's `/activity` 404s when they have no activity yet (not an
  empty list) — handlers treat that specific 404 as "no activity yet"
  (empty result), not as "invalid subscriber id".

## What this buys the user

- Zero fabricated plan-limit numbers anywhere in the codebase.
- The ONE thing we know for certain (MailerLite's own live error text) is
  what actually reaches the user, verbatim, every time.
- A capability actually improves over time per-account (cache) without ever
  requiring us to maintain a plan/feature matrix by hand — because
  MailerLite's own plan names/limits are demonstrably a moving target (the
  Growing Business/Advanced -> Comfort/Power rename happened recently, per
  research.md), a hand-maintained table would go stale immediately.

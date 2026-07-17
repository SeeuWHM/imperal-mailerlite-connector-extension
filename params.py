"""Pydantic param models for MailerLite Connector chat functions.

Field constraints mirror what MailerLite's own API documents AND what was
directly confirmed against a live account (see docs/research.md) — this
extension is a thin, faithful client, not a second source of truth for
validation rules. Where MailerLite's real behavior diverges from its prose
docs (confirmed live), the more accurate rule wins, e.g.:
  - campaigns list `limit` only accepts {1,10,25,50,100} (not any int)
  - forms are addressed by /forms/{type} (type is a path segment, not a
    query filter, despite how the prose docs read)
  - webhook creation takes `events` (a LIST), not a single `event` string
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class EmptyParams(BaseModel):
    """No input required."""


# ── Accounts ─────────────────────────────────────────────────────────────

class SaveKeyParams(BaseModel):
    mailerlite_api_key: str = Field(
        ..., min_length=1, max_length=2000,
        description="Your MailerLite API key, from MailerLite -> Integrations -> MailerLite API -> Generate new token",
    )
    label: str = Field(default="", max_length=60, description="Optional display name for this account")


class AccountLabelParams(BaseModel):
    label: str = Field(..., description="Account label (from list_mailerlite_accounts)")


# ── Subscribers ──────────────────────────────────────────────────────────

class ListSubscribersParams(BaseModel):
    status: Optional[str] = Field(
        default=None, description="Filter: active, unsubscribed, unconfirmed, bounced, junk",
    )
    limit: int = Field(default=25, ge=1, le=1000)
    cursor: str = Field(default="", description="Pagination cursor from a previous page's response")


class SubscriberIdParams(BaseModel):
    subscriber_id: str = Field(..., description="MailerLite subscriber id (from list_subscribers)")


class UpsertSubscriberParams(BaseModel):
    email: str = Field(..., description="Subscriber's email address")
    fields: dict = Field(default_factory=dict, description="Custom field values, e.g. {'name': 'Jane'}. Never removes omitted fields.")
    groups: List[str] = Field(default_factory=list, description="Group ids to add this subscriber to. Never removes omitted groups.")
    status: Optional[str] = Field(default=None, description="active, unsubscribed, unconfirmed, bounced, or junk")


class GroupSubscriberParams(BaseModel):
    subscriber_id: str = Field(..., description="MailerLite subscriber id")
    group_id: str = Field(..., description="MailerLite group id")


# ── Groups ───────────────────────────────────────────────────────────────

class ListGroupsParams(BaseModel):
    limit: int = Field(default=25, ge=1, le=1000)
    page: int = Field(default=1, ge=1)
    name_contains: Optional[str] = Field(default=None, description="Partial-match filter on group name")


class CreateGroupParams(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class GroupIdParams(BaseModel):
    group_id: str = Field(..., description="MailerLite group id (from list_groups)")


class RenameGroupParams(BaseModel):
    group_id: str = Field(...)
    name: str = Field(..., min_length=1, max_length=255)


class GroupSubscribersParams(BaseModel):
    group_id: str = Field(...)
    status: Optional[str] = Field(default=None, description="active, unsubscribed, unconfirmed, bounced, junk")
    limit: int = Field(default=50, ge=1, le=1000)
    cursor: str = Field(default="")


# ── Segments ─────────────────────────────────────────────────────────────

class ListSegmentsParams(BaseModel):
    limit: int = Field(default=25, ge=1, le=250)
    page: int = Field(default=1, ge=1)


class SegmentIdParams(BaseModel):
    segment_id: str = Field(..., description="MailerLite segment id (from list_segments)")


class RenameSegmentParams(BaseModel):
    segment_id: str = Field(...)
    name: str = Field(..., min_length=1, max_length=255)


class SegmentSubscribersParams(BaseModel):
    segment_id: str = Field(...)
    status: Optional[str] = Field(default=None)
    limit: int = Field(default=25, ge=1)
    cursor: str = Field(default="")


# ── Campaigns ────────────────────────────────────────────────────────────

# Confirmed live against a real account: any limit outside this exact set
# 422s with "The selected limit is invalid." — not documented in prose docs.
CAMPAIGNS_LIST_LIMITS = (1, 10, 25, 50, 100)


class ListCampaignsParams(BaseModel):
    status: Optional[str] = Field(default=None, description="sent, draft, or ready (defaults to ready)")
    type: Optional[str] = Field(default=None, description="regular, ab, resend, or rss")
    limit: int = Field(default=25, description="Must be one of 1, 10, 25, 50, or 100 (confirmed live) — any other value is rejected")
    page: int = Field(default=1, ge=1)


class CampaignIdParams(BaseModel):
    campaign_id: str = Field(..., description="MailerLite campaign id (from list_campaigns)")


class CreateCampaignParams(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    type: str = Field(
        default="regular",
        description=(
            "regular, ab, resend, or multivariate. 'resend' and 'multivariate' are documented by "
            "MailerLite as available only on growing/advanced-tier plans — expect a possible plan-restricted "
            "rejection on lower plans, surfaced verbatim from MailerLite's own error."
        ),
    )
    subject: str = Field(default="", max_length=255)
    from_name: str = Field(default="", max_length=255)
    from_email: str = Field(default="", description="Must be an email address already verified in MailerLite")
    reply_to: str = Field(default="", description="Must be an email address already verified in MailerLite")
    content_html: str = Field(
        default="", max_length=500000,
        description=(
            "Raw HTML email body. Observed live: MailerLite can reject this with "
            "\"Content submission is only available on Premium plan.\" on non-Premium accounts — "
            "surfaced verbatim, never silently swallowed."
        ),
    )
    language_id: Optional[str] = Field(default=None, description="From list_campaign_languages; defaults to English")


class ScheduleCampaignParams(BaseModel):
    campaign_id: str = Field(...)
    delivery: str = Field(default="instant", description="instant or scheduled")
    schedule_type: Optional[str] = Field(default=None, description="unix_timestamp or timezone-relative — see MailerLite docs")
    date: Optional[str] = Field(default=None, description="Y-m-d, required if delivery=scheduled")
    hours: Optional[str] = Field(default=None)
    minutes: Optional[str] = Field(default=None)
    timezone_id: Optional[str] = Field(default=None, description="From list_timezones")


# ── Automations ──────────────────────────────────────────────────────────

class ListAutomationsParams(BaseModel):
    enabled: Optional[bool] = Field(default=None)
    name: Optional[str] = Field(default=None)
    limit: int = Field(default=10, ge=1, le=100)
    page: int = Field(default=1, ge=1)


class AutomationIdParams(BaseModel):
    automation_id: str = Field(..., description="MailerLite automation id (from list_automations)")


class AutomationActivityParams(BaseModel):
    automation_id: str = Field(...)
    status: str = Field(..., description="completed, active, canceled, or failed (required by MailerLite)")
    limit: int = Field(default=10, ge=1, le=100)
    page: int = Field(default=1, ge=1)


class CreateAutomationDraftParams(BaseModel):
    name: str = Field(
        ..., min_length=1,
        description=(
            "Draft name only — MailerLite's API cannot define an automation's trigger/steps; "
            "those must still be built in the MailerLite UI after this draft is created."
        ),
    )


# ── Forms ────────────────────────────────────────────────────────────────

class ListFormsParams(BaseModel):
    form_type: str = Field(..., description="popup, embedded, or promotion (required — path segment, not a filter)")
    name: Optional[str] = Field(default=None, description="Partial-match filter on form name")
    limit: int = Field(default=25, ge=1)
    page: int = Field(default=1, ge=1)


class FormIdParams(BaseModel):
    form_id: str = Field(..., description="MailerLite form id (from list_forms)")


class RenameFormParams(BaseModel):
    form_id: str = Field(...)
    name: str = Field(..., min_length=1, max_length=255)


class FormSubscribersParams(BaseModel):
    form_id: str = Field(...)
    status: Optional[str] = Field(default=None)
    limit: int = Field(default=25, ge=1)
    cursor: str = Field(default="")


# ── Fields ───────────────────────────────────────────────────────────────

class ListFieldsParams(BaseModel):
    field_type: Optional[str] = Field(default=None, description="text, number, or date")
    limit: int = Field(default=25, ge=1, le=100)
    page: int = Field(default=1, ge=1)


class CreateFieldParams(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    field_type: str = Field(..., description="text, number, or date")


class FieldIdParams(BaseModel):
    field_id: str = Field(..., description="MailerLite field id (from list_fields)")


class RenameFieldParams(BaseModel):
    field_id: str = Field(...)
    name: str = Field(..., min_length=1, max_length=255)


# ── Webhooks ─────────────────────────────────────────────────────────────

class ListWebhooksParams(BaseModel):
    """No filters documented for this endpoint — lists everything."""


class CreateWebhookParams(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    events: List[str] = Field(
        ..., min_length=1,
        description=(
            "One or more MailerLite webhook event names, e.g. subscriber.created, campaign.sent. "
            "campaign.click, campaign.open, and subscriber.deleted REQUIRE batchable=true (MailerLite's own rule)."
        ),
    )
    url: str = Field(..., description="Your endpoint URL that will receive the webhook POST")
    batchable: bool = Field(default=False)


class WebhookIdParams(BaseModel):
    webhook_id: str = Field(..., description="MailerLite webhook id (from list_webhooks)")

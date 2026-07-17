"""Pydantic response models for MailerLite Connector chat functions.

Every @chat.function(action_type="read") declares a data_model so the
platform validates return shapes and prevents naming drift (federal V23).
Field names/shapes mirror MailerLite's own JSON verbatim where sensible
(confirmed live against a real account — see docs/research.md) rather than
inventing our own vocabulary.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


# ── Accounts ─────────────────────────────────────────────────────────────

class ConnectionStatus(BaseModel):
    connected: bool = False
    masked_key: str = ""


class AccountRecord(BaseModel):
    label: str = ""
    masked_key: str = ""
    is_active: bool = False


class AccountsList(BaseModel):
    accounts: List[AccountRecord] = Field(default_factory=list)
    count: int = 0


class AccountSwitched(BaseModel):
    active: str = ""


class AccountDisconnected(BaseModel):
    label: str = ""
    remaining: int = 0


class DeletedResponse(BaseModel):
    deleted: bool = True


# ── Subscribers ──────────────────────────────────────────────────────────

class SubscriberRecord(BaseModel):
    id: str = ""
    email: str = ""
    status: str = ""
    source: str = ""
    sent: int = 0
    opens_count: int = 0
    clicks_count: int = 0
    open_rate: float = 0.0
    click_rate: float = 0.0
    subscribed_at: Optional[str] = None
    unsubscribed_at: Optional[str] = None
    fields: dict = Field(default_factory=dict)
    groups: List[str] = Field(default_factory=list)


class SubscriberList(BaseModel):
    subscribers: List[SubscriberRecord] = Field(default_factory=list)
    count: int = 0
    next_cursor: Optional[str] = None


class SubscriberActivityRow(BaseModel):
    activity_type: str = ""
    date: str = ""
    detail: dict = Field(default_factory=dict)


class SubscriberActivityList(BaseModel):
    subscriber_id: str = ""
    rows: List[SubscriberActivityRow] = Field(default_factory=list)
    count: int = 0
    has_no_activity_yet: bool = False


# ── Groups ───────────────────────────────────────────────────────────────

class GroupRecord(BaseModel):
    id: str = ""
    name: str = ""
    active_count: int = 0
    sent_count: int = 0
    open_rate: float = 0.0
    click_rate: float = 0.0
    unsubscribed_count: int = 0
    created_at: str = ""


class GroupList(BaseModel):
    groups: List[GroupRecord] = Field(default_factory=list)
    count: int = 0


# ── Segments ─────────────────────────────────────────────────────────────

class SegmentRecord(BaseModel):
    id: str = ""
    name: str = ""
    total: int = 0
    open_rate: float = 0.0
    click_rate: float = 0.0
    created_at: str = ""
    automations_using_segment_count: int = 0


class SegmentList(BaseModel):
    segments: List[SegmentRecord] = Field(default_factory=list)
    count: int = 0


# ── Campaigns ────────────────────────────────────────────────────────────

class CampaignRecord(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""
    status: str = ""
    subject: str = ""
    missing_data: List[str] = Field(default_factory=list)
    created_at: str = ""
    scheduled_for: Optional[str] = None


class CampaignList(BaseModel):
    campaigns: List[CampaignRecord] = Field(default_factory=list)
    count: int = 0


# ── Automations ──────────────────────────────────────────────────────────

class AutomationRecord(BaseModel):
    id: str = ""
    name: str = ""
    enabled: bool = False
    created_at: str = ""


class AutomationList(BaseModel):
    automations: List[AutomationRecord] = Field(default_factory=list)
    count: int = 0


class AutomationActivityRow(BaseModel):
    status: str = ""
    date: str = ""
    reason: Optional[str] = None


class AutomationActivityList(BaseModel):
    automation_id: str = ""
    rows: List[AutomationActivityRow] = Field(default_factory=list)
    count: int = 0


# ── Forms ────────────────────────────────────────────────────────────────

class FormRecord(BaseModel):
    id: str = ""
    name: str = ""
    conversions_count: int = 0
    visitors: int = 0
    created_at: str = ""


class FormList(BaseModel):
    forms: List[FormRecord] = Field(default_factory=list)
    count: int = 0
    form_type: str = ""


# ── Fields ───────────────────────────────────────────────────────────────

class FieldRecord(BaseModel):
    id: str = ""
    name: str = ""
    type: str = ""


class FieldList(BaseModel):
    fields: List[FieldRecord] = Field(default_factory=list)
    count: int = 0


# ── Webhooks ─────────────────────────────────────────────────────────────

class WebhookRecord(BaseModel):
    id: str = ""
    name: str = ""
    event: str = ""  # display convenience: joined events[0] or "multiple" — see handlers_webhooks_reference._to_webhook
    url: str = ""
    enabled: bool = True


class WebhookList(BaseModel):
    webhooks: List[WebhookRecord] = Field(default_factory=list)
    count: int = 0


# ── Reference lookups ────────────────────────────────────────────────────

class LanguageRecord(BaseModel):
    id: str = ""
    shortcode: str = ""
    name: str = ""


class LanguageList(BaseModel):
    languages: List[LanguageRecord] = Field(default_factory=list)
    count: int = 0


class TimezoneRecord(BaseModel):
    id: str = ""
    name: str = ""


class TimezoneList(BaseModel):
    timezones: List[TimezoneRecord] = Field(default_factory=list)
    count: int = 0


# ── Capability / plan-awareness ─────────────────────────────────────────

class CapabilityHint(BaseModel):
    capability_key: str = ""
    note: str = ""
    confirmed_restricted: Optional[bool] = None  # None = documented hint only, not yet tested live


class PlanInfo(BaseModel):
    """The account's REAL plan, read directly from GET /account — confirmed
    live to return real plan data (200 OK) even though it isn't in the
    documented endpoint list at developers.mailerlite.com. This is ground
    truth when the call succeeds; GATED_HINTS/cached verdicts remain the
    fallback for sub-capabilities /account doesn't itself describe (e.g.
    whether HTML content submission is unlocked at this exact tier)."""
    name: str = ""
    interval: str = ""
    amount: float = 0.0
    min_subscribers: int = 0
    max_subscribers: int = 0
    smart_sending_enabled: bool = False
    paid_features: bool = False


class CapabilityStatus(BaseModel):
    account_label: str = ""
    plan: Optional[PlanInfo] = None
    plan_lookup_failed: bool = False
    hints: List[CapabilityHint] = Field(default_factory=list)
    count: int = 0

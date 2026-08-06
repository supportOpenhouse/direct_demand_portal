"""Neon tables. Mapped columns are a projection of `raw` — the full sheet row
always lands in `raw` JSONB, so sheet column changes never break the sync."""
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    TIMESTAMP,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class InventoryUnit(Base):
    __tablename__ = "inventory_units"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    row_key: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    society: Mapped[str | None] = mapped_column(Text)
    locality: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    configuration: Mapped[str | None] = mapped_column(Text)
    area_sqft: Mapped[float | None] = mapped_column(Numeric)
    price_text: Mapped[str | None] = mapped_column(Text)
    price_lacs: Mapped[float | None] = mapped_column(Numeric)
    status: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Numeric)
    lng: Mapped[float | None] = mapped_column(Numeric)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    synced_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class GeocodeCache(Base):
    """Address → lat/lng, so we geocode each unique address only once."""

    __tablename__ = "geocode_cache"

    address: Mapped[str] = mapped_column(Text, primary_key=True)
    lat: Mapped[float | None] = mapped_column(Numeric)
    lng: Mapped[float | None] = mapped_column(Numeric)
    geocoded_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class SyncState(Base):
    __tablename__ = "sync_state"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    last_synced_at: Mapped[str | None] = mapped_column(TIMESTAMP(timezone=True))
    last_status: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(Integer)


# ============================================================
# LEADS — two raw ingest tables (insert-only, one per source category) feeding a
# unified `leads` spine. The 4-hourly cron only ever INSERTs new rows here; it
# never updates or deletes. `dedupe_key` (normalized phone) is UNIQUE so re-runs
# skip leads already ingested.
# ============================================================


class MetaLead(Base):
    """Raw rows from the 'Meta Affordable_New' sheet (source = Meta)."""

    __tablename__ = "meta_leads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dedupe_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)  # added to the Meta sheet later
    society: Mapped[str | None] = mapped_column(Text)  # added to the Meta sheet later
    budget_range: Mapped[str | None] = mapped_column(Text)
    plan_to_buy: Mapped[str | None] = mapped_column(Text)
    preferred_visit_day: Mapped[str | None] = mapped_column(Text)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    ingested_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class ListingLead(Base):
    """Raw rows from the 'Listing Leads_New' sheet (source = 99acres | MagicBricks)."""

    __tablename__ = "listing_leads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dedupe_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)  # '99acres' | 'magicbricks'
    city: Mapped[str | None] = mapped_column(Text)
    property: Mapped[str | None] = mapped_column(Text)  # society of interest from portal
    lead_type: Mapped[str | None] = mapped_column(Text)  # Individual | Dealer
    phone_verification_status: Mapped[str | None] = mapped_column(Text)
    assigned_to: Mapped[str | None] = mapped_column(Text)
    lead_date: Mapped[str | None] = mapped_column(Text)
    remarks: Mapped[str | None] = mapped_column(Text)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    ingested_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class Lead(Base):
    """Unified lifecycle spine — one row per ingested lead, normalized across
    sources. New Leads / segments read this. Source-captured fields are filled at
    ingest; confirmed (Q1-Q6) fields live in lead_confirmed_data."""

    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # origin_key = "<category>:<dedupe_key>" — UNIQUE so the cron never double-creates a spine row
    origin_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    source_category: Mapped[str] = mapped_column(Text, nullable=False)  # 'meta' | 'listing'
    source: Mapped[str] = mapped_column(Text, nullable=False)  # 'meta' | '99acres' | 'magicbricks'

    name: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    assigned_to: Mapped[str | None] = mapped_column(Text)

    # source-captured (what the ad form / portal gave us — locked, admin-editable later)
    city: Mapped[str | None] = mapped_column(Text)
    society: Mapped[str | None] = mapped_column(Text)
    configuration: Mapped[str | None] = mapped_column(Text)
    budget_band: Mapped[str | None] = mapped_column(Text)
    plan_to_buy: Mapped[str | None] = mapped_column(Text)
    preferred_visit_day: Mapped[str | None] = mapped_column(Text)
    source_remarks: Mapped[str | None] = mapped_column(Text)
    source_meta: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    # when the lead came in (source date for listing; ingest time for meta)
    received_at: Mapped[str | None] = mapped_column(TIMESTAMP(timezone=True))

    # lifecycle
    stage: Mapped[str] = mapped_column(Text, nullable=False, server_default="new")
    tat_deadline: Mapped[str | None] = mapped_column(TIMESTAMP(timezone=True))
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    qualified_at: Mapped[str | None] = mapped_column(TIMESTAMP(timezone=True))
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # call worklist / follow-up flow — a lead with an open follow_up_at lives in the
    # Follow-up tab; miss_count = consecutive not-connected calls (reset on connect);
    # never-connected leads hitting 10 misses move to the terminal 'rnr' stage.
    follow_up_at: Mapped[str | None] = mapped_column(TIMESTAMP(timezone=True))
    miss_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # when "No" was last logged on this lead. Rapid repeats are rejected for 2 hours
    # so a caller can't inflate miss_count (and drive a lead to RNR) by clicking.
    last_no_timestamp: Mapped[str | None] = mapped_column(TIMESTAMP(timezone=True))
    ever_connected: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_hot: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")  # starred
    # rejection
    reject_reason: Mapped[str | None] = mapped_column(Text)
    reject_notes: Mapped[str | None] = mapped_column(Text)
    rejected_at: Mapped[str | None] = mapped_column(TIMESTAMP(timezone=True))

    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[str | None] = mapped_column(TIMESTAMP(timezone=True), onupdate=func.now())


class LeadConfirmedData(Base):
    """The Q1-Q6 call-confirmed form (1:1 with leads). Written only by the
    confirm endpoint — a user action, never the cron."""

    __tablename__ = "lead_confirmed_data"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True
    )
    purpose: Mapped[str | None] = mapped_column(Text)  # Q1: Self-use | Investment
    budget_value_lacs: Mapped[float | None] = mapped_column(Numeric)  # legacy single value
    budget_min_lacs: Mapped[float | None] = mapped_column(Numeric)  # Q2 range
    budget_max_lacs: Mapped[float | None] = mapped_column(Numeric)
    configuration: Mapped[str | None] = mapped_column(Text)  # Q3
    size_sqft: Mapped[float | None] = mapped_column(Numeric)  # legacy single value
    size_min_sqft: Mapped[float | None] = mapped_column(Numeric)  # Q4 size range
    size_max_sqft: Mapped[float | None] = mapped_column(Numeric)
    preferred_micromarkets: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    shortlisted_societies: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    preferred_localities: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    office_willing: Mapped[str | None] = mapped_column(Text)  # Yes | No | Maybe
    office_preferred_date: Mapped[str | None] = mapped_column(Date)
    remark: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class Visit(Base):
    """A saved multi-stop visit plan for a lead (from the visit planner)."""

    __tablename__ = "visits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trip_date: Mapped[str | None] = mapped_column(Date)
    # legacy single field — kept populated until nothing reads it (see
    # scripts/split_visit_rm.sql). Its value was always the lead's own RM.
    rm: Mapped[str | None] = mapped_column(Text)
    lead_rm: Mapped[str | None] = mapped_column(Text)          # who owns the lead
    # who actually goes; defaults to lead_rm. Their smid is what the Openhouse
    # booking API receives as sales_manager_id.
    rm_accompanying: Mapped[str | None] = mapped_column(Text)
    start_lat: Mapped[float | None] = mapped_column(Numeric)
    start_lng: Mapped[float | None] = mapped_column(Numeric)
    total_km: Mapped[float | None] = mapped_column(Numeric)
    total_min: Mapped[float | None] = mapped_column(Numeric)
    route_source: Mapped[str | None] = mapped_column(Text)  # 'google' | 'est'
    stops: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class CrmVisit(Base):
    """A visit actually booked on the Openhouse app via POST /v1/visits/book.

    `visit_id` is the Core visit number returned by the booking API and is the join key
    into the ops visits sheet, from which `status` (upcoming | completed | cancelled) and
    the feedback fields are synced. A lead with any row here is a Pipeline lead."""

    __tablename__ = "crm_visits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    visit_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)  # Core visit id
    home_id: Mapped[int | None] = mapped_column(Integer)
    society: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    selected_date: Mapped[str | None] = mapped_column(Text)
    selected_time: Mapped[str | None] = mapped_column(Text)
    # synced from the ops sheet
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="upcoming")
    visit_date: Mapped[str | None] = mapped_column(Text)
    buyer_feedback: Mapped[str | None] = mapped_column(Text)
    sales_feedback: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[str | None] = mapped_column(TIMESTAMP(timezone=True))
    booked_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class User(Base):
    """Google-authenticated user. Created on first sign-in."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    picture: Mapped[str | None] = mapped_column(Text)
    # admin | rm | test_rm. test_rm is a calling RM used for dry runs: dialled by
    # campaigns (tagged TEST in the picker) but never assigned a WhatsApp conversation.
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="rm")
    # the name as it appears in the sheet's "Assigned to" column (defaults to the
    # user's first name); maps this user to their leads
    assignment_name: Mapped[str | None] = mapped_column(Text)
    # mobile number — click-to-call rings this handset first, then dials the lead
    phone: Mapped[str | None] = mapped_column(Text)
    # Openhouse Core SalesManager.id — used as sales_manager_id when booking visits.
    # No smid → the user can't book (clear "not set up" message).
    smid: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    last_login_at: Mapped[str | None] = mapped_column(TIMESTAMP(timezone=True))


class LeadNote(Base):
    """Conversation thread on a lead. Seeded from the sheet's Remarks / Remarks 2;
    new notes appended with author + timestamp."""

    __tablename__ = "lead_notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="note")  # 'remarks' | 'note'
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class CallLog(Base):
    """One row per call leg, built up by the Bonvoice callback.

    Bonvoice fires three lifecycle events (0 initiated, 1 answered, 2 hangup) for each
    of two legs, so up to six callbacks describe one conversation. They upsert onto
    (call_id, leg) and apply progressively, so duplicate and out-of-order deliveries
    converge on the same row.

    lead_id comes from callBackParams — we send it when placing the call and Bonvoice
    echoes it back — so logs attach by explicit id, not by matching phone numbers."""

    __tablename__ = "call_logs"

    call_id: Mapped[str] = mapped_column(Text, primary_key=True)
    leg: Mapped[str] = mapped_column(Text, primary_key=True)  # 'A' caller | 'B' callee
    event_id: Mapped[str | None] = mapped_column(Text, index=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"), index=True
    )
    direction: Mapped[str | None] = mapped_column(Text)
    source_number: Mapped[str | None] = mapped_column(Text)
    destination_number: Mapped[str | None] = mapped_column(Text)
    display_number: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)        # callee status
    agent_status: Mapped[str | None] = mapped_column(Text)  # caller status (outbound)
    answered: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    start_at: Mapped[str | None] = mapped_column(TIMESTAMP(timezone=True))
    end_at: Mapped[str | None] = mapped_column(TIMESTAMP(timezone=True))
    # stored if Bonvoice sends it; nothing downloads or renders it yet
    recording_url: Mapped[str | None] = mapped_column(Text)
    placed_by: Mapped[str | None] = mapped_column(Text)     # portal user who dialled
    # which auto-dialer campaign placed this call, NULL for manual click-to-call.
    # Resolved from dial_queue.event_id when the callback lands, because that row's
    # event_id is cleared once a retry is scheduled — after which the link is gone.
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dial_campaigns.id", ondelete="SET NULL"), index=True
    )
    raw: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class WaContact(Base):
    """What a WhatsApp number turned out to be, marked by hand from the chat.

    Keyed by the last 10 digits of the phone — the same key leads dedupe on — so the
    mark survives whether the number arrives as 919871578484 or +91 98715 78484.
    One row per contact; re-marking overwrites."""

    __tablename__ = "wa_contacts"

    phone10: Mapped[str] = mapped_column(Text, primary_key=True)
    # nullable: a contact can be assigned to an RM before anyone classifies it
    tag: Mapped[str | None] = mapped_column(Text)  # broker|buyer|seller|rejected
    # owning RM, by canonical full name — same convention as leads.assigned_to
    assigned_to: Mapped[str | None] = mapped_column(Text, index=True)
    assigned_at: Mapped[str | None] = mapped_column(TIMESTAMP(timezone=True))
    marked_by: Mapped[str | None] = mapped_column(Text)
    marked_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class WaMessage(Base):
    """WhatsApp conversation, both directions. Inbound rows are written by the Gupshup
    webhook, outbound by the send endpoint. `phone` is always the CUSTOMER's number
    regardless of direction, so it keys the thread."""

    __tablename__ = "wa_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    direction: Mapped[str] = mapped_column(Text, nullable=False)  # 'in' | 'out'
    phone: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(Text)          # sender name, inbound only
    body: Mapped[str | None] = mapped_column(Text)          # text, or a caption
    msg_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="text")
    # inbound media (audio/voice notes, images, documents). Gupshup hosts the file on
    # filemanager.gupshup.io behind a link that EXPIRES at media_expiry — we store the
    # link, not the bytes, so an old voice note stops playing once that passes.
    # ponytail: no blob storage in this stack; to keep media, fetch it in _persist and
    # push it to S3/R2, then store that URL here instead.
    media_url: Mapped[str | None] = mapped_column(Text)
    media_expiry: Mapped[str | None] = mapped_column(TIMESTAMP(timezone=True))
    media_name: Mapped[str | None] = mapped_column(Text)   # documents carry a filename
    # provider message id — the join key for the delivery events that arrive later
    gupshup_id: Mapped[str | None] = mapped_column(Text, index=True)
    status: Mapped[str | None] = mapped_column(Text)        # submitted|sent|delivered|read|failed
    author: Mapped[str | None] = mapped_column(Text)        # portal user who sent it
    raw: Mapped[dict | None] = mapped_column(JSONB)         # full callback, for anything unmodelled
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_wa_messages_phone_created", phone, created_at.desc()),)


class DialCampaign(Base):
    """An auto-dialer run: who to call (a rule tree), who calls them (a pool of RMs),
    and the pacing.

    Concurrency is bounded by the pool, not by a dial rate — Click2Call rings the RM's
    own handset first, so one RM can only ever hold one live call. N RMs in the pool =
    at most N calls in flight."""

    __tablename__ = "dial_campaigns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # the AND/OR condition tree from the builder; compiled to SQL when the campaign starts
    rules: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    rms: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")  # user emails
    strategy: Mapped[str] = mapped_column(Text, nullable=False, server_default="round_robin")
    # seconds of breathing room after a call ends before that RM is dialled again;
    # 0 = the next lead rings the moment the hangup callback lands
    gap_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    window_start: Mapped[str] = mapped_column(Text, nullable=False, server_default="10:00")
    window_end: Mapped[str] = mapped_column(Text, nullable=False, server_default="19:00")
    # a lead that never connected goes back in the queue until it has used up its
    # attempts, but not before cooldown_minutes have passed
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    cooldown_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="180")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    # draft | running | paused | done
    created_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[str | None] = mapped_column(TIMESTAMP(timezone=True))


class DialQueueItem(Base):
    """One lead's slot in a campaign queue.

    `status` is the whole scheduler: pending → dialing (an RM's phone is ringing) →
    done. The Bonvoice hangup callback flips dialing → done by `event_id`, which is
    what frees that RM for the next lead."""

    __tablename__ = "dial_queue"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dial_campaigns.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rm_email: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    # pending | dialing | done | failed | skipped
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    event_id: Mapped[str | None] = mapped_column(Text, index=True)
    # did this attempt actually connect — decides whether a retry is owed. Kept here
    # rather than read from call_logs so the dialer works when callbacks don't arrive
    # and the poller is the only source of truth.
    answered: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    outcome: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text)  # why a dial failed, verbatim
    dialed_at: Mapped[str | None] = mapped_column(TIMESTAMP(timezone=True))
    ended_at: Mapped[str | None] = mapped_column(TIMESTAMP(timezone=True))
    # What the RM said happened, from the Live Calls page. Distinct from `outcome`,
    # which is the PBX's view (ANSWER / NOANSWER / 'no callback'): a call Bonvoice
    # reports as answered can still be a wrong number, and only the RM knows that.
    # NULL = not marked yet, which is what drives the "needs result" badge.
    call_result: Mapped[str | None] = mapped_column(Text)  # 'connected' | 'missed'
    call_result_at: Mapped[str | None] = mapped_column(TIMESTAMP(timezone=True))
    call_result_by: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        # one slot per lead per campaign — re-materialising a queue can't duplicate calls
        Index("ux_dial_queue_campaign_lead", campaign_id, lead_id, unique=True),
        Index("ix_dial_queue_campaign_status", campaign_id, status),
    )


class AuditLog(Base):
    """Audit trail — one row per meaningful API action, written by the audit
    middleware. Insert-only; surfaced on the admin Logs page."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[str] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    actor_email: Mapped[str | None] = mapped_column(Text)   # who did it (None = anonymous)
    actor_name: Mapped[str | None] = mapped_column(Text)
    actor_role: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, nullable=False)        # human label, e.g. "Confirmed lead"
    category: Mapped[str] = mapped_column(Text, nullable=False)      # auth | write | read
    method: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)          # raw request path
    route: Mapped[str] = mapped_column(Text, nullable=False)         # ids masked, for grouping
    status_code: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    ip: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_audit_logs_created_at", created_at.desc()),
        Index("ix_audit_logs_actor_email", actor_email),
        Index("ix_audit_logs_category", category),
    )

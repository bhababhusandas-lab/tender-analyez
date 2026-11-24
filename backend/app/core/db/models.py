from datetime import datetime, date
from sqlalchemy import Integer, String, Date, DateTime, Text, Float, Boolean, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db.session import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    full_name: Mapped[str] = mapped_column(String, default="")
    company_name: Mapped[str] = mapped_column(String, default="")
    phone: Mapped[str] = mapped_column(String, default="")
    plan: Mapped[str] = mapped_column(String, default="free")  # free / starter / growth / professional / enterprise
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_code: Mapped[str | None] = mapped_column(String, nullable=True)
    verification_code_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    stored_filename: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    stored_size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    compression: Mapped[str] = mapped_column(String(20), default="identity")
    mime_type: Mapped[str] = mapped_column(String, default="application/octet-stream")
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CompanyProfile(Base):
    # A separate table removes the legacy one-profile-per-user unique constraint.
    # Startup migration copies each user's existing profile into this table.
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    # Basic
    company_name: Mapped[str] = mapped_column(String, default="")
    company_type: Mapped[str] = mapped_column(String, default="")        # Pvt Ltd / Partnership / Proprietorship
    established_year: Mapped[str] = mapped_column(String, default="")
    website: Mapped[str] = mapped_column(String, default="")
    address: Mapped[str] = mapped_column(String, default="")
    # Registrations
    gst_no: Mapped[str] = mapped_column(String, default="")
    pan_no: Mapped[str] = mapped_column(String, default="")
    cin_no: Mapped[str] = mapped_column(String, default="")
    msme_no: Mapped[str] = mapped_column(String, default="")
    msme_category: Mapped[str] = mapped_column(String, default="")       # Micro / Small / Medium
    iso_certs: Mapped[str] = mapped_column(String, default="")           # comma-separated
    other_certs: Mapped[str] = mapped_column(String, default="")
    # Financial
    turnover_y1: Mapped[str] = mapped_column(String, default="")         # FY 2023-24
    turnover_y2: Mapped[str] = mapped_column(String, default="")         # FY 2022-23
    turnover_y3: Mapped[str] = mapped_column(String, default="")         # FY 2021-22
    net_worth: Mapped[str] = mapped_column(String, default="")
    emd_capacity: Mapped[str] = mapped_column(String, default="")        # max EMD we can handle
    bg_limit: Mapped[str] = mapped_column(String, default="")            # bank BG limit
    bank_name: Mapped[str] = mapped_column(String, default="")
    # Portals
    gem_seller_id: Mapped[str] = mapped_column(String, default="")
    cppp_registered: Mapped[str] = mapped_column(String, default="")
    telangana_reg: Mapped[str] = mapped_column(String, default="")
    other_portals: Mapped[str] = mapped_column(String, default="")
    # Work categories & geography
    work_categories: Mapped[str] = mapped_column(Text, default="")       # comma-separated
    states_registered: Mapped[str] = mapped_column(String, default="")
    # Key personnel (JSON string)
    key_personnel: Mapped[str] = mapped_column(Text, default="[]")
    # Past projects (JSON string)
    past_projects: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Bid(Base):
    __tablename__ = "bids"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    tender_name: Mapped[str] = mapped_column(String, nullable=False)
    reference_no: Mapped[str] = mapped_column(String, default="")
    portal: Mapped[str] = mapped_column(String, default="")
    department: Mapped[str] = mapped_column(String, default="")
    estimated_value: Mapped[str] = mapped_column(String, default="")
    emd_amount: Mapped[str] = mapped_column(String, default="")
    submission_deadline: Mapped[str] = mapped_column(String, default="")
    recommended_quote: Mapped[str] = mapped_column(String, default="")
    bid_confidence: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="draft")         # draft/submitted/won/lost/withdrawn
    pipeline_result: Mapped[str] = mapped_column(Text, default="{}")     # full JSON of all agent outputs
    tender_text: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class UsageEvent(Base):
    """One row per Bid Pipeline or 7-Phase Analysis run. Used to enforce plan limits."""
    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String, default="pipeline")  # "pipeline" | "roadmap"
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class PastBid(Base):
    __tablename__ = "past_bids"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    department: Mapped[str] = mapped_column(String, default="")
    contract_value: Mapped[str] = mapped_column(String, default="")
    year_won: Mapped[str] = mapped_column(String, default="")
    outcome: Mapped[str] = mapped_column(String, default="won")          # won / submitted
    original_filename: Mapped[str] = mapped_column(String, default="")
    text_content: Mapped[str] = mapped_column(Text, default="")          # transparent zstd envelope for large text
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AnalysisJob(Base):
    """Durable parent record for a pipeline or 7-phase analysis run."""
    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # pipeline | roadmap
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    tender_text: Mapped[str] = mapped_column(Text, default="")
    context_json: Mapped[str] = mapped_column(Text, default="{}")
    final_content: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class AnalysisStep(Base):
    """A single resumable agent/phase within an AnalysisJob."""
    __tablename__ = "analysis_steps"
    __table_args__ = (UniqueConstraint("job_id", "step_id", name="uq_analysis_job_step"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("analysis_jobs.id"), nullable=False, index=True)
    step_id: Mapped[str] = mapped_column(String(80), nullable=False)
    step_name: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(20), default="waiting", index=True)
    content: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Tender(Base):
    """A tender in the user's history — the "conversation" that holds versions."""
    __tablename__ = "tenders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    reference_no: Mapped[str] = mapped_column(String(200), default="")
    latest_decision: Mapped[str] = mapped_column(String(80), default="")
    latest_quote: Mapped[str] = mapped_column(String(120), default="")
    latest_deadline: Mapped[str] = mapped_column(String(160), default="")
    version_count: Mapped[int] = mapped_column(Integer, default=0)
    bid_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("bids.id"), nullable=True, index=True)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TenderVersion(Base):
    """One analysis run of a tender. `number` is set only when the run finishes."""
    __tablename__ = "tender_versions"
    __table_args__ = (UniqueConstraint("tender_id", "number", name="uq_tender_version_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tender_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenders.id"), nullable=False, index=True)
    number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label: Mapped[str] = mapped_column(String(300), default="")
    analysis_job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("analysis_jobs.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(20), default="pipeline")   # pipeline | roadmap
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|completed|review_required|stopped|failed
    note: Mapped[str] = mapped_column(Text, default="")
    decision: Mapped[str] = mapped_column(String(80), default="")
    quote: Mapped[str] = mapped_column(String(120), default="")
    deadline: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TenderHistoryDocument(Base):
    """A file (or pasted text) added to a tender by a specific run.

    Named `TenderHistoryDocument` (table `tender_history_documents`) rather than
    `TenderDocument`/`tender_documents` because that name is already taken by the
    unrelated public tender-discovery document model below (`TenderDocument`,
    tied to `TenderNotice`). Renaming the pre-existing, already-shipped discovery
    feature to make room here was judged riskier than picking a distinct name for
    this brand-new model.
    """
    __tablename__ = "tender_history_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tender_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenders.id"), nullable=False, index=True)
    version_id: Mapped[int] = mapped_column(Integer, ForeignKey("tender_versions.id"), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(200), default="application/octet-stream")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    stored_filename: Mapped[str] = mapped_column(String(300), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    compression: Mapped[str] = mapped_column(String(20), default="identity")
    extracted_text: Mapped[str] = mapped_column(Text, default="")  # compression.encode_text envelope
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TenderNotice(Base):
    """Durable public tender-discovery record collected from an official source."""
    __tablename__ = "tender_notices"
    __table_args__ = (UniqueConstraint("source_id", "official_id", name="uq_tender_notice_source_id"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(160), nullable=False)
    official_id: Mapped[str] = mapped_column(String(300), nullable=False)
    reference: Mapped[str] = mapped_column(String(500), default="", index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    closing_date: Mapped[str] = mapped_column(String(160), default="")
    opening_date: Mapped[str] = mapped_column(String(160), default="")
    official_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class TenderDocument(Base):
    """A public document link discovered on an official tender notice.

    Public files may be mirrored by the discovery service after their official host
    and content type are verified. Portals protected by a session or CAPTCHA remain
    metadata-only and must be opened on the authoritative government website.
    """
    __tablename__ = "tender_documents"
    __table_args__ = (UniqueConstraint("tender_id", "official_url", name="uq_tender_document_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tender_id: Mapped[str] = mapped_column(String(40), ForeignKey("tender_notices.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    official_url: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(String(30), default="document")
    status: Mapped[str] = mapped_column(String(30), default="available", index=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_checked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class DiscussionMessage(Base):
    """One turn of the "Discuss with the team" chat, kept per analysis job."""
    __tablename__ = "discussion_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("analysis_jobs.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, default="")        # compression.encode_text envelope
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class NotificationRead(Base):
    """A user has seen the deadline alert for one tender at one stage."""
    __tablename__ = "notification_reads"
    __table_args__ = (UniqueConstraint("user_id", "tender_id", "stage", name="uq_notification_read"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    tender_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenders.id"), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(10), nullable=False)
    read_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

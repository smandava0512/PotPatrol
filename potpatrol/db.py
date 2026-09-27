from sqlalchemy import JSON, CheckConstraint, Float, ForeignKey, Index, Integer, String, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class Drive(Base):
    __tablename__ = "drives"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="created")
    stage: Mapped[str | None] = mapped_column(String(50))
    error: Mapped[str | None] = mapped_column(String(500))
    video_key: Mapped[str | None] = mapped_column(String(300))
    upload_expires_at: Mapped[str | None] = mapped_column(String(40))
    video_started_at: Mapped[str | None] = mapped_column(String(40))
    analysis_mode: Mapped[str | None] = mapped_column(String(20))
    vision_mode: Mapped[str | None] = mapped_column(String(30))
    validator_model: Mapped[str | None] = mapped_column(String(100))
    gemini_frames_scanned: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))


class DeletionReceipt(Base):
    """Opaque owner-bound tombstone; retained indefinitely for idempotent DELETE."""
    __tablename__ = "deletion_receipts"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("drive_id", "offset_ms"), Index("ix_locations_drive_offset", "drive_id", "offset_ms"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    drive_id: Mapped[str] = mapped_column(ForeignKey("drives.id"), index=True)
    offset_ms: Mapped[int] = mapped_column(Integer)
    recorded_at: Mapped[str] = mapped_column(String(40))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    horizontal_accuracy_m: Mapped[float | None] = mapped_column(Float)
    speed_mps: Mapped[float | None] = mapped_column(Float)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    drive_id: Mapped[str] = mapped_column(ForeignKey("drives.id"), unique=True)
    state: Mapped[str] = mapped_column(String(20), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    claim_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[str | None] = mapped_column(String(40))
    started_at: Mapped[str | None] = mapped_column(String(40))
    finished_at: Mapped[str | None] = mapped_column(String(40))
    error: Mapped[str | None] = mapped_column(String(500))


class Hazard(Base):
    __tablename__ = "hazards"
    __table_args__ = (UniqueConstraint("drive_id", "event_index"), Index("ix_hazards_drive_offset", "drive_id", "video_offset_ms"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    drive_id: Mapped[str] = mapped_column(ForeignKey("drives.id"), index=True)
    event_index: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(80))
    confidence: Mapped[float] = mapped_column(Float)
    severity: Mapped[str | None] = mapped_column(String(40))
    severity_basis: Mapped[str | None] = mapped_column(String(200))
    video_offset_ms: Mapped[int] = mapped_column(Integer)
    observed_at: Mapped[str | None] = mapped_column(String(40))
    location: Mapped[dict | None] = mapped_column(JSON)
    review_state: Mapped[str] = mapped_column(String(30), default="needs_review")
    source: Mapped[str | None] = mapped_column(String(40))
    validation: Mapped[dict | None] = mapped_column(JSON)


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    hazard_id: Mapped[str] = mapped_column(ForeignKey("hazards.id"), unique=True)
    storage_key: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(40), default="image/jpeg")


class ReportDraft(Base):
    __tablename__ = "report_drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    hazard_id: Mapped[str] = mapped_column(ForeignKey("hazards.id"), unique=True)
    fields: Mapped[dict] = mapped_column(JSON)
    destination: Mapped[dict] = mapped_column(JSON)
    submission_status: Mapped[str] = mapped_column(String(30), default="not_submitted")


def session_factory(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {}, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)

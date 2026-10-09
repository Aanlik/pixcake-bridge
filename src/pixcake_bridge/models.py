from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(unique=True)
    name: Mapped[str] = mapped_column(String(255))
    stage: Mapped[str] = mapped_column(String(16), default="SELECTING")
    # Once editing has started, moving the visible stage backwards must never
    # make cancellation delete a RAW that may already be in an editor.
    has_entered_editing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    connected: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sync: Mapped[datetime | None] = mapped_column(DateTime)


class Photo(Base):
    __tablename__ = "photos"
    __table_args__ = (UniqueConstraint("project_id", "photo_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    photo_id: Mapped[int] = mapped_column(Integer)
    source_filename: Mapped[str] = mapped_column(String(512))
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    added_during_editing: Mapped[bool] = mapped_column(Boolean, default=False)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_path: Mapped[str | None] = mapped_column(Text)
    selected_path: Mapped[str | None] = mapped_column(Text)
    raw_hash: Mapped[str | None] = mapped_column(String(64))
    materialized_hash: Mapped[str | None] = mapped_column(String(64))
    delivery_hash: Mapped[str | None] = mapped_column(String(64))
    remote_filename: Mapped[str | None] = mapped_column(String(512))
    error: Mapped[str | None] = mapped_column(Text)


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (UniqueConstraint("photo_pk", "sha256"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    photo_pk: Mapped[int] = mapped_column(ForeignKey("photos.id"))
    sha256: Mapped[str] = mapped_column(String(64))
    marker: Mapped[str] = mapped_column(String(512))
    snapshot: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(16), default="PENDING")
    attempts: Mapped[int] = mapped_column(default=0)
    updated: Mapped[datetime] = mapped_column(DateTime, default=now)
    error: Mapped[str | None] = mapped_column(Text)


class SyncRun(Base):
    __tablename__ = "sync_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    started: Mapped[datetime] = mapped_column(DateTime, default=now)
    finished: Mapped[datetime | None] = mapped_column(DateTime)
    success: Mapped[bool] = mapped_column(default=False)


class Error(Base):
    __tablename__ = "errors"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    message: Mapped[str] = mapped_column(Text)
    created: Mapped[datetime] = mapped_column(DateTime, default=now)
    resolved: Mapped[bool] = mapped_column(default=False)


def database(url):
    engine = create_engine(url, **({"connect_args": {"check_same_thread": False, "timeout": 30}} if url.startswith("sqlite") else {}))
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def pragmas(conn, _):
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
    Base.metadata.create_all(engine)
    if "has_entered_editing" not in {c["name"] for c in inspect(engine).get_columns("projects")}:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE projects ADD COLUMN has_entered_editing BOOLEAN NOT NULL DEFAULT FALSE"))
            conn.execute(text("UPDATE projects SET has_entered_editing = TRUE WHERE stage IN ('EDITING', 'DELIVERED', 'ARCHIVED')"))
    if "added_during_editing" not in {c["name"] for c in inspect(engine).get_columns("photos")}:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE photos ADD COLUMN added_during_editing BOOLEAN NOT NULL DEFAULT FALSE"))
    return engine, sessionmaker(engine, expire_on_commit=False)

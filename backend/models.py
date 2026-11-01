from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow

# Version of the per-review AI tags. v2 added severity, user type, churn risk, competitors and accessibility;
# v3 requires quoted evidence for churn and checks competitor names appear in the review.
# Insights are cached per model *and* tag version, so older analyses keep working with the fields they have.
TAG_VERSION = 3


class RunStatus:
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TERMINAL = frozenset({COMPLETED, FAILED, CANCELLED})


class App(Base):
    __tablename__ = "apps"
    __table_args__ = (UniqueConstraint("platform", "store_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(16))
    store_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(255))
    developer: Mapped[str | None] = mapped_column(String(255))
    icon_url: Mapped[str | None] = mapped_column(Text)
    genre: Mapped[str | None] = mapped_column(String(128))
    score: Mapped[float | None]
    ratings_count: Mapped[int | None]
    installs: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[str | None] = mapped_column(String(64))
    store_url: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("app_id", "store_review_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    app_id: Mapped[int] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), index=True)
    store_review_id: Mapped[str] = mapped_column(String(255))
    rating: Mapped[int]
    content: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime | None]
    app_version: Mapped[str | None] = mapped_column(String(64))
    thumbs_up: Mapped[int] = mapped_column(default=0)
    reply_content: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(8))
    lang: Mapped[str | None] = mapped_column(String(16))


class Run(Base):
    """One analysis request: an app + market + filters + model."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    app_id: Mapped[int] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), index=True)
    country: Mapped[str | None] = mapped_column(String(8))
    lang: Mapped[str | None] = mapped_column(String(16))
    ratings: Mapped[list[int] | None] = mapped_column(JSON)
    requested_count: Mapped[int]
    # Optional period: reviews written between these days (inclusive), picked newest-first or spread evenly.
    date_from: Mapped[date | None]
    date_to: Mapped[date | None]
    sampling: Mapped[str] = mapped_column(String(16), default="newest", server_default=text("'newest'"))
    output_language: Mapped[str] = mapped_column(String(32), default="English")
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    tag_version: Mapped[int] = mapped_column(default=1, server_default=text("1"))

    status: Mapped[str] = mapped_column(String(16), default=RunStatus.QUEUED)
    stage: Mapped[str | None] = mapped_column(String(32))
    progress_done: Mapped[int] = mapped_column(default=0)
    progress_total: Mapped[int] = mapped_column(default=0)
    message: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)

    review_count: Mapped[int] = mapped_column(default=0)
    tagged_count: Mapped[int] = mapped_column(default=0)
    failed_count: Mapped[int] = mapped_column(default=0)
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    # Raw theme label -> canonical theme, produced by the grouping pass.
    theme_map: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]

    app: Mapped[App] = relationship(lazy="joined")

    @property
    def model_key(self) -> str:
        base = f"{self.provider}:{self.model}"
        return base if (self.tag_version or 1) == 1 else f"{base}#v{self.tag_version}"


class RunReview(Base):
    __tablename__ = "run_reviews"

    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"), primary_key=True)


class Insight(Base):
    """AI tags for one review, cached per model so re-runs don't pay twice."""

    __tablename__ = "insights"
    __table_args__ = (
        UniqueConstraint("review_id", "model_key"),
        Index("ix_insights_model_key", "model_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"))
    model_key: Mapped[str] = mapped_column(String(160))
    category: Mapped[str | None] = mapped_column(String(32))
    themes: Mapped[list[str]] = mapped_column(JSON, default=list)
    journey_stage: Mapped[str | None] = mapped_column(String(32))
    emotion: Mapped[str | None] = mapped_column(String(32))
    # Tag version 2
    severity: Mapped[str | None] = mapped_column(String(16))
    user_type: Mapped[str | None] = mapped_column(String(24))
    churn_risk: Mapped[str | None] = mapped_column(String(16))
    competitors: Mapped[list[str] | None] = mapped_column(JSON)
    accessibility: Mapped[bool | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ChatEntry(Base):
    """One message of the assistant conversation about a run (user, assistant or tool result)."""

    __tablename__ = "chat_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text, default="")
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    tool_call_id: Mapped[str | None] = mapped_column(String(128))
    name: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Artifact(Base):
    """AI-written output for a run (decisions, research report, what changed, personas). Latest per kind."""

    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("run_id", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Benchmark(Base):
    """A saved comparison of 2-4 analyses (competitors, markets or periods). The first run is "yours"."""

    __tablename__ = "benchmarks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    run_ids: Mapped[list[str]] = mapped_column(JSON)
    content: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # AI topic alignment + summary
    provider: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)

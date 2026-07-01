from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text)
    remaining_story_points: Mapped[int] = mapped_column(Integer, default=0)
    blocked_items: Mapped[int] = mapped_column(Integer, default=0)
    actions: Mapped[list[str]] = mapped_column(JSON)


class SprintMetric(Base):
    __tablename__ = "sprint_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    remaining_story_points: Mapped[int] = mapped_column(Integer, default=0)
    blocked_items: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text)


class CurrentSprintSnapshot(Base):
    __tablename__ = "current_sprint_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), unique=True, index=True
    )
    project: Mapped[str] = mapped_column(String(255))
    user_email: Mapped[str] = mapped_column(String(255))
    assigned_items: Mapped[int] = mapped_column(Integer, default=0)
    blocked_items: Mapped[int] = mapped_column(Integer, default=0)
    open_prs: Mapped[int] = mapped_column(Integer, default=0)
    user_stories: Mapped[int] = mapped_column(Integer, default=0)
    remaining_story_points: Mapped[int] = mapped_column(Integer, default=0)
    remaining_work_hours: Mapped[int] = mapped_column(Integer, default=0)
    raw_payload: Mapped[dict] = mapped_column(JSON)

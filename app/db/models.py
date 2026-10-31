"""PostgreSQL tables. Only the postgres repositories import this module;
upper layers work with the plain dataclasses in app/domain instead."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class School(Base):
    __tablename__ = "schools"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    """Teachers, school admins and the superadmin all live here."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('teacher', 'school_admin', 'superadmin')", name="users_role_check"),
        # superadmin belongs to no school; everyone else must belong to one
        CheckConstraint(
            "(role = 'superadmin') = (school_id IS NULL)", name="users_school_by_role_check"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # NULL for teachers added through the agent who have no login yet
    email: Mapped[str | None] = mapped_column(String(200), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(200))
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))
    school_id: Mapped[int | None] = mapped_column(ForeignKey("schools.id"))
    # False = removed from the school (soft delete)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SchoolClass(Base):
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"))
    name: Mapped[str] = mapped_column(String(20))  # "4A"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("uq_class_name_per_school", "school_id", "name", unique=True),)


class ClassTeacher(Base):
    """Which teacher leads which class (many-to-many)."""

    __tablename__ = "class_teachers"

    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'inactive')", name="students_status_check"),
        Index("ix_students_class_id", "class_id"),
        Index("ix_students_school_name", "school_id", "full_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"))
    # An inactive student keeps the last class they were in, so we can say where they were
    class_id: Mapped[int | None] = mapped_column(ForeignKey("classes.id"))
    full_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(10), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ChangeLog(Base):
    """Append-only history. Rows are written in the same transaction as the change."""

    __tablename__ = "change_log"
    __table_args__ = (
        CheckConstraint("source IN ('agent', 'user', 'seed')", name="change_log_source_check"),
        Index("ix_change_log_entity", "entity_type", "entity_id"),
        Index("ix_change_log_school", "school_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # e.g. student_added, student_deactivated, student_transferred, teacher_assigned
    action: Mapped[str] = mapped_column(String(50))
    entity_type: Mapped[str] = mapped_column(String(20))  # student / teacher / class
    entity_id: Mapped[int] = mapped_column(Integer)
    school_id: Mapped[int | None] = mapped_column(ForeignKey("schools.id"))
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(10))
    conversation_id: Mapped[str | None] = mapped_column(String(64))


class PendingAction(Base):
    """A change waiting for the user's confirmation.

    `status` moves pending -> confirmed exactly once; that is the idempotency guard."""

    __tablename__ = "pending_actions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'cancelled', 'expired')",
            name="pending_actions_status_check",
        ),
    )

    token: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    conversation_id: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(50))
    params: Mapped[dict] = mapped_column(JSONB)
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict | None] = mapped_column(JSONB)


class RequestLog(Base):
    """One row per chat request, used for the analytics by request type."""

    __tablename__ = "request_log"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('resolved', 'permission_denied', 'needs_clarification', "
            "'out_of_scope', 'error')",
            name="request_log_outcome_check",
        ),
        Index("ix_request_log_type", "request_type"),
        Index("ix_request_log_at", "at"),
        Index("ix_request_log_conversation", "conversation_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    conversation_id: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    request_type: Mapped[str] = mapped_column(String(30))
    outcome: Mapped[str] = mapped_column(String(25))
    tools_called: Mapped[list | None] = mapped_column(JSONB)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)  # all input, cached or not
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # the part of input served from the cache
    llm_calls: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)


class Conversation(Base):
    """One chat. Belongs to one user; nobody else can read or continue it."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatMessage(Base):
    """One message of a conversation, in order. `payload` is the model-facing message
    (text, tool calls, tool results); `blocks` are the cards the app shows with it."""

    __tablename__ = "chat_messages"
    __table_args__ = (UniqueConstraint("conversation_id", "seq", name="uq_chat_message_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"))
    seq: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSONB)
    blocks: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

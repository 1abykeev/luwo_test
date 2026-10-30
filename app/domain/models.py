"""Plain data types shared by every layer. No database or LLM code in here."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class Role(StrEnum):
    TEACHER = "teacher"
    SCHOOL_ADMIN = "school_admin"
    SUPERADMIN = "superadmin"


class StudentStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


@dataclass(frozen=True)
class School:
    id: int
    name: str


@dataclass(frozen=True)
class SchoolClass:
    id: int
    school_id: int
    name: str


@dataclass(frozen=True)
class Student:
    id: int
    school_id: int
    class_id: int | None
    class_name: str | None  # filled in by the repository so cards need no extra lookups
    full_name: str
    status: StudentStatus


@dataclass(frozen=True)
class Teacher:
    id: int
    school_id: int
    full_name: str
    email: str | None
    is_active: bool


@dataclass(frozen=True)
class User:
    """A login account. Teachers are users too (role = teacher)."""

    id: int
    email: str | None
    full_name: str
    role: Role
    school_id: int | None  # None only for the superadmin
    is_active: bool
    password_hash: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class Actor:
    """Who is making the request, as loaded from the database for this request.

    Built by the backend, never by the model and never from chat text."""

    user_id: int
    full_name: str
    role: Role
    school_id: int | None
    class_ids: frozenset[int]  # classes this person leads (teachers only)


@dataclass(frozen=True)
class Scope:
    """Which data a search is allowed to look at. None means 'no restriction'."""

    school_id: int | None = None
    class_ids: frozenset[int] | None = None


@dataclass(frozen=True)
class ChangeEntry:
    """One line of the append-only history."""

    action: str  # student_added, student_deactivated, student_transferred, ...
    entity_type: str  # student / teacher / class
    entity_id: int
    school_id: int | None
    actor_user_id: int | None
    source: str  # agent / user / seed
    before: dict | None = None
    after: dict | None = None
    conversation_id: str | None = None
    id: int | None = None
    at: datetime | None = None


@dataclass(frozen=True)
class PendingAction:
    """A change the user still has to confirm."""

    token: str
    actor_user_id: int
    action: str
    params: dict
    summary: str
    status: str  # pending / confirmed / cancelled / expired
    expires_at: datetime
    conversation_id: str | None = None
    result: dict | None = None

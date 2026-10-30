"""What read operations return. Plain data; the agent tools turn these into JSON."""

from dataclasses import dataclass
from datetime import datetime

from app.domain.models import SchoolClass, Student, Teacher


@dataclass(frozen=True)
class ClassSummary:
    cls: SchoolClass
    school_name: str
    active_students: int
    teachers: list[Teacher] | None  # None = this person is not allowed to see assignments


@dataclass(frozen=True)
class ClassRoster:
    cls: SchoolClass
    school_name: str
    teachers: list[Teacher] | None
    students: list[Student]


@dataclass(frozen=True)
class TeacherEntry:
    teacher: Teacher
    school_name: str
    class_names: list[str]


@dataclass(frozen=True)
class StudentHit:
    student: Student
    school_name: str | None


@dataclass(frozen=True)
class HistoryEvent:
    action: str
    at: datetime | None
    from_class: str | None  # None also means "a class you cannot see"
    to_class: str | None


@dataclass(frozen=True)
class StudentDetail:
    student: Student
    school_name: str | None
    events: list[HistoryEvent]


@dataclass(frozen=True)
class StudentFinding:
    """One possible match when someone says 'a student disappeared from my list'."""

    student_id: int
    full_name: str
    state: str  # active / deactivated / moved_out_of_your_access
    current_class: str | None  # None when the student is outside what the user may see
    events: list[HistoryEvent]


@dataclass(frozen=True)
class Proposal:
    token: str
    action: str
    summary: str
    details: dict
    warnings: list[dict]
    expires_at: datetime


@dataclass(frozen=True)
class ConfirmResult:
    result: dict
    already_applied: bool  # True when the same token was confirmed before (double tap)

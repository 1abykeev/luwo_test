"""In-memory repositories. Same contracts as the Postgres ones, plain Python inside."""

from dataclasses import replace
from datetime import datetime, timezone

from app.domain.errors import NotFound
from app.domain.models import (
    ChangeEntry,
    PendingAction,
    Role,
    School,
    SchoolClass,
    Scope,
    Student,
    StudentStatus,
    Teacher,
    User,
)

from .store import MemoryData


def _contains(name: str, query: str) -> bool:
    return query.casefold() in name.casefold()


def _in_scope(student: Student, scope: Scope) -> bool:
    if scope.school_id is not None and student.school_id != scope.school_id:
        return False
    if scope.class_ids is not None and student.class_id not in scope.class_ids:
        return False
    return True


def _by_name_then_id(student: Student):
    return (student.full_name, student.id)


class MemoryStudentRepository:
    def __init__(self, data: MemoryData):
        self.data = data

    async def get(self, student_id: int) -> Student | None:
        return self.data.students.get(student_id)

    async def list_by_class(self, class_id: int, *, include_inactive: bool = False) -> list[Student]:
        found = [
            s for s in self.data.students.values()
            if s.class_id == class_id and (include_inactive or s.status == StudentStatus.ACTIVE)
        ]
        return sorted(found, key=_by_name_then_id)

    async def search(self, name: str, scope: Scope, *, include_inactive: bool = False) -> list[Student]:
        found = [
            s for s in self.data.students.values()
            if _contains(s.full_name, name)
            and _in_scope(s, scope)
            and (include_inactive or s.status == StudentStatus.ACTIVE)
        ]
        return sorted(found, key=_by_name_then_id)

    async def find_duplicate_groups(self, scope: Scope) -> list[list[Student]]:
        groups: dict[str, list[Student]] = {}
        for s in sorted(self.data.students.values(), key=lambda s: s.id):
            if s.status == StudentStatus.ACTIVE and _in_scope(s, scope):
                groups.setdefault(s.full_name.casefold(), []).append(s)
        return [group for _, group in sorted(groups.items()) if len(group) > 1]

    async def add(self, *, school_id: int, class_id: int, full_name: str) -> Student:
        student = Student(
            id=max(self.data.students, default=0) + 1,
            school_id=school_id,
            class_id=class_id,
            class_name=self.data.classes[class_id].name,
            full_name=full_name,
            status=StudentStatus.ACTIVE,
        )
        self.data.students[student.id] = student
        return student

    async def set_status(self, student_id: int, status: StudentStatus) -> Student:
        student = self._require(student_id)
        self.data.students[student_id] = replace(student, status=status)
        return self.data.students[student_id]

    async def move_to_class(self, student_id: int, class_id: int) -> Student:
        student = self._require(student_id)
        new_class = self.data.classes[class_id]
        self.data.students[student_id] = replace(
            student, class_id=class_id, class_name=new_class.name, school_id=new_class.school_id
        )
        return self.data.students[student_id]

    def _require(self, student_id: int) -> Student:
        if student_id not in self.data.students:
            raise NotFound(f"Student {student_id} not found")
        return self.data.students[student_id]


def _to_teacher(user: User) -> Teacher:
    return Teacher(
        id=user.id, school_id=user.school_id, full_name=user.full_name,
        email=user.email, is_active=user.is_active,
    )


class MemoryTeacherRepository:
    def __init__(self, data: MemoryData):
        self.data = data

    def _teachers(self) -> list[User]:
        return [u for u in self.data.users.values() if u.role == Role.TEACHER]

    async def get(self, teacher_id: int) -> Teacher | None:
        user = self.data.users.get(teacher_id)
        return _to_teacher(user) if user and user.role == Role.TEACHER else None

    async def list_by_school(self, school_id: int, *, include_inactive: bool = False) -> list[Teacher]:
        found = [
            u for u in self._teachers()
            if u.school_id == school_id and (include_inactive or u.is_active)
        ]
        return [_to_teacher(u) for u in sorted(found, key=lambda u: (u.full_name, u.id))]

    async def find_by_name(self, name: str, school_id: int | None) -> list[Teacher]:
        found = [
            u for u in self._teachers()
            if _contains(u.full_name, name) and (school_id is None or u.school_id == school_id)
        ]
        return [_to_teacher(u) for u in sorted(found, key=lambda u: (u.full_name, u.id))]

    async def list_for_classes(self, class_ids: list[int]) -> dict[int, list[Teacher]]:
        result: dict[int, list[Teacher]] = {class_id: [] for class_id in class_ids}
        for class_id, teacher_id in self.data.class_teachers:
            user = self.data.users[teacher_id]
            if class_id in result and user.is_active:
                result[class_id].append(_to_teacher(user))
        for teachers in result.values():
            teachers.sort(key=lambda t: t.full_name)
        return result

    async def add(self, *, school_id: int, full_name: str, email: str | None = None) -> Teacher:
        user = User(
            id=max(self.data.users, default=0) + 1, email=email, full_name=full_name,
            role=Role.TEACHER, school_id=school_id, is_active=True,
        )
        self.data.users[user.id] = user
        return _to_teacher(user)

    async def set_active(self, teacher_id: int, is_active: bool) -> Teacher:
        user = self.data.users.get(teacher_id)
        if user is None or user.role != Role.TEACHER:
            raise NotFound(f"Teacher {teacher_id} not found")
        self.data.users[teacher_id] = replace(user, is_active=is_active)
        return _to_teacher(self.data.users[teacher_id])

    async def assign(self, teacher_id: int, class_id: int) -> None:
        self.data.class_teachers.add((class_id, teacher_id))

    async def unassign(self, teacher_id: int, class_id: int) -> None:
        self.data.class_teachers.discard((class_id, teacher_id))


class MemoryClassRepository:
    def __init__(self, data: MemoryData):
        self.data = data

    async def get(self, class_id: int) -> SchoolClass | None:
        return self.data.classes.get(class_id)

    async def list_by_school(self, school_id: int) -> list[SchoolClass]:
        return sorted(
            (c for c in self.data.classes.values() if c.school_id == school_id), key=lambda c: c.name
        )

    async def find_by_name(self, school_id: int, name: str) -> SchoolClass | None:
        return next(
            (c for c in self.data.classes.values() if c.school_id == school_id and c.name == name), None
        )

    async def list_led_by(self, teacher_id: int) -> list[SchoolClass]:
        ids = {class_id for class_id, t in self.data.class_teachers if t == teacher_id}
        return sorted((self.data.classes[i] for i in ids), key=lambda c: c.name)


class MemorySchoolRepository:
    def __init__(self, data: MemoryData):
        self.data = data

    async def get(self, school_id: int) -> School | None:
        return self.data.schools.get(school_id)

    async def list_all(self) -> list[School]:
        return sorted(self.data.schools.values(), key=lambda s: s.name)


class MemoryUserRepository:
    def __init__(self, data: MemoryData):
        self.data = data

    async def get(self, user_id: int) -> User | None:
        return self.data.users.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self.data.users.values() if u.email == email), None)


class MemoryHistoryRepository:
    def __init__(self, data: MemoryData):
        self.data = data

    async def add(self, entry: ChangeEntry) -> None:
        self.data.history.append(
            replace(entry, id=len(self.data.history) + 1, at=entry.at or datetime.now(timezone.utc))
        )

    async def list_for_entity(self, entity_type: str, entity_id: int) -> list[ChangeEntry]:
        found = [e for e in self.data.history if e.entity_type == entity_type and e.entity_id == entity_id]
        return sorted(found, key=lambda e: (e.at, e.id))

    async def list_transfers_out(self, scope: Scope) -> list[ChangeEntry]:
        found = []
        for e in self.data.history:
            if e.action != "student_transferred":
                continue
            if scope.school_id is not None and e.school_id != scope.school_id:
                continue
            if scope.class_ids is not None and (e.before or {}).get("class_id") not in scope.class_ids:
                continue
            found.append(e)
        return sorted(found, key=lambda e: (e.at, e.id))


class MemoryPendingActionRepository:
    def __init__(self, data: MemoryData):
        self.data = data

    async def add(self, action: PendingAction) -> None:
        self.data.pending[action.token] = action

    async def get(self, token: str) -> PendingAction | None:
        return self.data.pending.get(token)

    async def claim(self, token: str, now: datetime) -> PendingAction | None:
        action = self.data.pending.get(token)
        if action is None or action.status != "pending" or action.expires_at <= now:
            return None
        self.data.pending[token] = replace(action, status="confirmed")
        return self.data.pending[token]

    async def set_result(self, token: str, result: dict) -> None:
        self.data.pending[token] = replace(self.data.pending[token], result=result)

    async def cancel(self, token: str) -> bool:
        action = self.data.pending.get(token)
        if action is None or action.status != "pending":
            return False
        self.data.pending[token] = replace(action, status="cancelled")
        return True

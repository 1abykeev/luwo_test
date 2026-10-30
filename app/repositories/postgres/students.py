from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain.errors import NotFound
from app.domain.models import Scope, Student, StudentStatus


def _query():
    return (
        select(m.Student, m.SchoolClass.name)
        .outerjoin(m.SchoolClass, m.SchoolClass.id == m.Student.class_id)
        .execution_options(populate_existing=True)
    )


def _to_domain(row) -> Student:
    student, class_name = row
    return Student(
        id=student.id,
        school_id=student.school_id,
        class_id=student.class_id,
        class_name=class_name,
        full_name=student.full_name,
        status=StudentStatus(student.status),
    )


def _scope_conditions(scope: Scope) -> list:
    conditions = []
    if scope.school_id is not None:
        conditions.append(m.Student.school_id == scope.school_id)
    if scope.class_ids is not None:
        conditions.append(m.Student.class_id.in_(list(scope.class_ids)))
    return conditions


class PostgresStudentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, student_id: int) -> Student | None:
        row = (await self.session.execute(_query().where(m.Student.id == student_id))).first()
        return _to_domain(row) if row else None

    async def list_by_class(self, class_id: int, *, include_inactive: bool = False) -> list[Student]:
        query = _query().where(m.Student.class_id == class_id)
        if not include_inactive:
            query = query.where(m.Student.status == StudentStatus.ACTIVE)
        rows = await self.session.execute(query.order_by(m.Student.full_name, m.Student.id))
        return [_to_domain(r) for r in rows]

    async def search(
        self, name: str, scope: Scope, *, include_inactive: bool = False
    ) -> list[Student]:
        query = _query().where(m.Student.full_name.icontains(name, autoescape=True), *_scope_conditions(scope))
        if not include_inactive:
            query = query.where(m.Student.status == StudentStatus.ACTIVE)
        rows = await self.session.execute(query.order_by(m.Student.full_name, m.Student.id))
        return [_to_domain(r) for r in rows]

    async def find_duplicate_groups(self, scope: Scope) -> list[list[Student]]:
        conditions = [m.Student.status == StudentStatus.ACTIVE, *_scope_conditions(scope)]
        lowered = func.lower(m.Student.full_name)
        duplicated_names = select(lowered).where(*conditions).group_by(lowered).having(func.count() > 1)
        rows = await self.session.execute(
            _query().where(*conditions, lowered.in_(duplicated_names)).order_by(lowered, m.Student.id)
        )
        groups: dict[str, list[Student]] = {}
        for row in rows:
            student = _to_domain(row)
            groups.setdefault(student.full_name.lower(), []).append(student)
        return list(groups.values())

    async def add(self, *, school_id: int, class_id: int, full_name: str) -> Student:
        row = m.Student(school_id=school_id, class_id=class_id, full_name=full_name)
        self.session.add(row)
        await self.session.flush()
        return await self._require(row.id)

    async def set_status(self, student_id: int, status: StudentStatus) -> Student:
        await self.session.execute(
            update(m.Student).where(m.Student.id == student_id).values(status=status.value)
        )
        return await self._require(student_id)

    async def move_to_class(self, student_id: int, class_id: int) -> Student:
        # The student takes the school of the new class (matters for cross-school moves).
        new_school = select(m.SchoolClass.school_id).where(m.SchoolClass.id == class_id).scalar_subquery()
        await self.session.execute(
            update(m.Student)
            .where(m.Student.id == student_id)
            .values(class_id=class_id, school_id=new_school)
        )
        return await self._require(student_id)

    async def _require(self, student_id: int) -> Student:
        student = await self.get(student_id)
        if student is None:
            raise NotFound(f"Student {student_id} not found")
        return student

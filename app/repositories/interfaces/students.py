from typing import Protocol

from app.domain.models import Scope, Student, StudentStatus


class StudentRepository(Protocol):
    async def get(self, student_id: int) -> Student | None: ...

    async def list_by_class(self, class_id: int, *, include_inactive: bool = False) -> list[Student]: ...

    async def search(
        self, name: str, scope: Scope, *, include_inactive: bool = False
    ) -> list[Student]:
        """Case-insensitive 'contains' match on the full name, only inside `scope`."""
        ...

    async def find_duplicate_groups(self, scope: Scope) -> list[list[Student]]:
        """Active students sharing the same full name (ignoring case), inside `scope`."""
        ...

    async def add(self, *, school_id: int, class_id: int, full_name: str) -> Student: ...

    async def set_status(self, student_id: int, status: StudentStatus) -> Student: ...

    async def move_to_class(self, student_id: int, class_id: int) -> Student: ...

from typing import Protocol

from app.domain.models import SchoolClass


class ClassRepository(Protocol):
    async def get(self, class_id: int) -> SchoolClass | None: ...

    async def list_by_school(self, school_id: int) -> list[SchoolClass]: ...

    async def find_by_name(self, school_id: int, name: str) -> SchoolClass | None:
        """Exact match. The service normalizes the name first (Latin A vs Cyrillic А)."""
        ...

    async def list_led_by(self, teacher_id: int) -> list[SchoolClass]: ...

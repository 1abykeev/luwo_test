from typing import Protocol

from app.domain.models import School


class SchoolRepository(Protocol):
    async def get(self, school_id: int) -> School | None: ...

    async def list_all(self) -> list[School]: ...

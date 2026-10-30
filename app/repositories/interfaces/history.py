from typing import Protocol

from app.domain.models import ChangeEntry, Scope


class HistoryRepository(Protocol):
    """Append-only: there is deliberately no update or delete."""

    async def add(self, entry: ChangeEntry) -> None: ...

    async def list_for_entity(self, entity_type: str, entity_id: int) -> list[ChangeEntry]:
        """Oldest first."""
        ...

    async def list_transfers_out(self, scope: Scope) -> list[ChangeEntry]:
        """'student_transferred' entries where the student was moved OUT of a class inside
        `scope`. Used to find students who disappeared from someone's lists."""
        ...

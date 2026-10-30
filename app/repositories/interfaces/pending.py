from datetime import datetime
from typing import Protocol

from app.domain.models import PendingAction


class PendingActionRepository(Protocol):
    async def add(self, action: PendingAction) -> None: ...

    async def get(self, token: str) -> PendingAction | None: ...

    async def claim(self, token: str, now: datetime) -> PendingAction | None:
        """Atomically move pending -> confirmed. Returns the action only for the one caller
        that won; returns None if it was already used, cancelled or expired.
        This single step is what makes confirmation safe against double execution."""
        ...

    async def set_result(self, token: str, result: dict) -> None: ...

    async def cancel(self, token: str) -> bool: ...

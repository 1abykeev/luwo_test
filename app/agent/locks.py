import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class KeyedLock:
    """One lock per key (here: per conversation), created when needed and forgotten when unused.

    Two requests in the same conversation must not overlap: the second would read a stale history
    and both would write at the same position. In-process only: with several server instances the
    database (a row lock in the conversation store) is what keeps the writes in order."""

    def __init__(self) -> None:
        self._locks: dict[str, tuple[asyncio.Lock, int]] = {}  # key -> (lock, number of users)

    @asynccontextmanager
    async def hold(self, key: str) -> AsyncIterator[None]:
        lock, users = self._locks.get(key, (asyncio.Lock(), 0))
        self._locks[key] = (lock, users + 1)
        try:
            async with lock:
                yield
        finally:
            lock, users = self._locks[key]
            if users == 1:
                del self._locks[key]
            else:
                self._locks[key] = (lock, users - 1)

    def __len__(self) -> int:
        return len(self._locks)

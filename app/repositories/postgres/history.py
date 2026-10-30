from sqlalchemy import Integer, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain.models import ChangeEntry, Scope


def _to_domain(row: m.ChangeLog) -> ChangeEntry:
    return ChangeEntry(
        id=row.id,
        at=row.at,
        action=row.action,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        school_id=row.school_id,
        actor_user_id=row.actor_user_id,
        source=row.source,
        before=row.before,
        after=row.after,
        conversation_id=row.conversation_id,
    )


class PostgresHistoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, entry: ChangeEntry) -> None:
        self.session.add(
            m.ChangeLog(
                action=entry.action,
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                school_id=entry.school_id,
                actor_user_id=entry.actor_user_id,
                source=entry.source,
                before=entry.before,
                after=entry.after,
                conversation_id=entry.conversation_id,
            )
        )
        await self.session.flush()

    async def list_for_entity(self, entity_type: str, entity_id: int) -> list[ChangeEntry]:
        rows = await self.session.execute(
            select(m.ChangeLog)
            .where(m.ChangeLog.entity_type == entity_type, m.ChangeLog.entity_id == entity_id)
            .order_by(m.ChangeLog.at, m.ChangeLog.id)
        )
        return [_to_domain(r) for r in rows.scalars()]

    async def list_transfers_out(self, scope: Scope) -> list[ChangeEntry]:
        query = select(m.ChangeLog).where(m.ChangeLog.action == "student_transferred")
        if scope.school_id is not None:
            query = query.where(m.ChangeLog.school_id == scope.school_id)
        if scope.class_ids is not None:
            from_class = m.ChangeLog.before["class_id"].astext.cast(Integer)
            query = query.where(from_class.in_(list(scope.class_ids)))
        rows = await self.session.execute(query.order_by(m.ChangeLog.at, m.ChangeLog.id))
        return [_to_domain(r) for r in rows.scalars()]

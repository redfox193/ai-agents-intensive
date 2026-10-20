from collections.abc import Sequence

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import ClickEvent


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log_event(self, event: ClickEvent) -> ClickEvent:
        self._session.add(event)
        await self._session.flush()
        await self._session.refresh(event)
        return event

    async def count_by_link(self, link_id: int) -> int:
        stmt = select(func.count(ClickEvent.id)).where(ClickEvent.link_id == link_id)
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def count_unique_visitors(self, link_id: int) -> int:
        stmt = select(func.count(distinct(ClickEvent.ip_hash))).where(ClickEvent.link_id == link_id)
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def get_recent_events(self, link_id: int, limit: int = 20) -> Sequence[ClickEvent]:
        stmt = (
            select(ClickEvent)
            .where(ClickEvent.link_id == link_id)
            .order_by(ClickEvent.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

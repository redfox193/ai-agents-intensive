import hashlib
from collections import Counter

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models.analytics import ClickEvent
from app.repositories.analytics import AnalyticsRepository
from app.repositories.link import LinkRepository
from app.schemas.analytics import ClickEventResponse, LinkDetailedAnalytics
from app.services.link import LinkNotFoundError


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._analytics_repo = AnalyticsRepository(session)
        self._link_repo = LinkRepository(session)

    @staticmethod
    def hash_ip(client_ip: str) -> str:
        salt = "pytex-linksvc-anonymization-salt"
        return hashlib.sha256(f"{client_ip}:{salt}".encode()).hexdigest()

    async def record_click(
        self,
        short_code: str,
        client_ip: str,
        user_agent: str = "",
        referrer: str = "",
    ) -> None:
        link = await self._link_repo.get_by_code(short_code)
        if not link:
            return

        event = ClickEvent(
            link_id=link.id,
            ip_hash=self.hash_ip(client_ip),
            user_agent=user_agent[:512],
            referrer=referrer[:1024],
        )
        await self._analytics_repo.log_event(event)
        logger.info("analytics_event_logged", short_code=short_code, link_id=link.id)

    async def get_link_detailed_analytics(self, short_code: str) -> LinkDetailedAnalytics:
        link = await self._link_repo.get_by_code(short_code)
        if not link:
            raise LinkNotFoundError(f"Ссылка с кодом '{short_code}' не найдена")

        total = await self._analytics_repo.count_by_link(link.id)
        unique = await self._analytics_repo.count_unique_visitors(link.id)
        recent = await self._analytics_repo.get_recent_events(link.id, limit=20)

        referrers = [e.referrer for e in recent if e.referrer]
        top_referrers = Counter(referrers).most_common(5)

        return LinkDetailedAnalytics(
            short_code=short_code,
            total_clicks=total,
            unique_visitors=unique,
            top_referrers=top_referrers,
            recent_events=[ClickEventResponse.model_validate(e) for e in recent],
        )

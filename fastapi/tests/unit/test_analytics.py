import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.link import LinkCreate
from app.services.analytics import AnalyticsService
from app.services.link import LinkService


@pytest.mark.asyncio
async def test_analytics_record_and_aggregate(db_session: AsyncSession):
    link_service = LinkService(db_session)
    analytics_service = AnalyticsService(db_session)

    link = await link_service.create_link(
        LinkCreate(original_url="https://pytex.ru/analytics", custom_code="stats-link")
    )

    # Логируем 3 клика (два с одного IP, один с другого)
    await analytics_service.record_click(
        "stats-link", client_ip="192.168.1.1", user_agent="Mozilla", referrer="https://google.com"
    )
    await analytics_service.record_click(
        "stats-link", client_ip="192.168.1.1", user_agent="Mozilla", referrer="https://google.com"
    )
    await analytics_service.record_click(
        "stats-link", client_ip="10.0.0.1", user_agent="Safari", referrer="https://yandex.ru"
    )

    summary = await analytics_service.get_link_detailed_analytics("stats-link")
    assert summary.total_clicks == 3
    assert summary.unique_visitors == 2
    assert len(summary.top_referrers) == 2
    assert summary.top_referrers[0] == ("https://google.com", 2)

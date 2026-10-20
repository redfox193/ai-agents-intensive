from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.analytics import LinkDetailedAnalytics
from app.services.analytics import AnalyticsService
from app.services.link import LinkNotFoundError

router = APIRouter(prefix="/analytics", tags=["analytics"])


def get_analytics_service(session: AsyncSession = Depends(get_db)) -> AnalyticsService:
    return AnalyticsService(session)


@router.get(
    "/{short_code}",
    response_model=LinkDetailedAnalytics,
    summary="Получить подробную аналитику по кликам",
)
async def get_analytics(
    short_code: str,
    service: AnalyticsService = Depends(get_analytics_service),
) -> LinkDetailedAnalytics:
    try:
        return await service.get_link_detailed_analytics(short_code)
    except LinkNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err

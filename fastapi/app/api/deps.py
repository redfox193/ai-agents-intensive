from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.link import Link
from app.schemas.link import LinkResponse
from app.services.link import LinkService

SessionDep = Annotated[AsyncSession, Depends(get_db)]


def get_link_service(session: SessionDep) -> LinkService:
    """Dependency injection фабрики сервиса ссылок."""
    return LinkService(session)


ServiceDep = Annotated[LinkService, Depends(get_link_service)]


def to_response(link: Link) -> LinkResponse:
    """Полный ответ о ссылке с коротким адресом `BASE_URL/<код>`."""
    response = LinkResponse.model_validate(link)
    base = settings.BASE_URL.rstrip("/")
    return response.model_copy(update={"short_url": f"{base}/{link.short_code}"})

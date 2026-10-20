from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse

from app.api.deps import ServiceDep, to_response
from app.schemas.link import (
    LinkBulkCreateRequest,
    LinkBulkCreateResponse,
    LinkCreate,
    LinkResponse,
    LinkStats,
)
from app.services.link import (
    LinkExpiredError,
    LinkInactiveError,
    LinkNotFoundError,
    ShortCodeConflictError,
)

router = APIRouter(prefix="/links", tags=["links"])


@router.post(
    "",
    response_model=LinkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать короткую ссылку",
)
async def create_link(data: LinkCreate, service: ServiceDep) -> LinkResponse:
    """Создаёт новую короткую ссылку с опциональным кастомным кодом и TTL."""
    try:
        link = await service.create_link(data)
    except ShortCodeConflictError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err
    return to_response(link)


@router.get("", response_model=list[LinkResponse], summary="Список ссылок")
async def list_links(service: ServiceDep) -> list[LinkResponse]:
    """Последние ссылки: новые первыми."""
    return [to_response(item) for item in await service.list_links()]


@router.post(
    "/bulk",
    response_model=LinkBulkCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Массовое создание ссылок",
)
async def bulk_create_links(
    request: LinkBulkCreateRequest, service: ServiceDep
) -> LinkBulkCreateResponse:
    """Пакетное создание списка ссылок в единой транзакции."""
    try:
        return await service.bulk_create_links(request.items)
    except ShortCodeConflictError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err


@router.get(
    "/{short_code}",
    response_class=RedirectResponse,
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    summary="Перейти по короткой ссылке",
)
async def redirect_to_url(short_code: str, service: ServiceDep) -> RedirectResponse:
    """Разрешает короткий код и выполняет перенаправление на исходный URL."""
    try:
        url = await service.resolve_link(short_code)
    except LinkNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
    except (LinkInactiveError, LinkExpiredError) as err:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(err)) from err
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get(
    "/{short_code}/stats",
    response_model=LinkStats,
    summary="Получить аналитику по ссылке",
)
async def get_link_stats(short_code: str, service: ServiceDep) -> LinkStats:
    """Возвращает счетчик переходов и текущий статус ссылки."""
    try:
        return await service.get_stats(short_code)
    except LinkNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err


@router.post(
    "/{short_code}/disable",
    response_model=LinkResponse,
    summary="Деактивировать ссылку",
)
async def disable_link(short_code: str, service: ServiceDep) -> LinkResponse:
    """Выключает ссылку, запрещая дальнейшие переходы."""
    try:
        link = await service.disable_link(short_code)
    except LinkNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
    return to_response(link)


@router.post(
    "/{short_code}/enable",
    response_model=LinkResponse,
    summary="Включить ссылку",
)
async def enable_link(short_code: str, service: ServiceDep) -> LinkResponse:
    """Активирует ранее выключенную ссылку."""
    try:
        link = await service.enable_link(short_code)
    except LinkNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
    return to_response(link)

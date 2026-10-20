"""Плоские маршруты `/links` (контракты Дня 1 и Дня 2, спека LINK-42): CRUD и disable/enable."""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import ServiceDep, to_response
from app.api.errors import raise_flat
from app.schemas.link import LinkCreate, LinkCreated, LinkResponse
from app.services.link import LinkServiceError

router = APIRouter(prefix="/links", tags=["links"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_link(data: LinkCreate, service: ServiceDep) -> LinkCreated:
    """Создаёт ссылку: тело `target_url` (или `url`/`original_url`), опционально `ttl_seconds`."""
    try:
        link = await service.create_link(data)
    except LinkServiceError as exc:
        raise_flat(exc)
    return LinkCreated.model_validate(link)


@router.get("")
async def list_links(service: ServiceDep) -> list[LinkResponse]:
    links = await service.list_links()
    return [to_response(item) for item in links]


@router.get("/{short_code}")
async def read_link(short_code: str, service: ServiceDep) -> LinkResponse:
    """Чтение ссылки без счётчика кликов; отключённая ссылка скрыта (404)."""
    try:
        link = await service.get_link(short_code)
    except LinkServiceError as exc:
        raise_flat(exc)
    if link.disabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Link disabled")
    return to_response(link)


@router.post("/{short_code}/disable")
async def disable_link(short_code: str, service: ServiceDep) -> LinkCreated:
    try:
        link = await service.disable_link(short_code)
    except LinkServiceError as exc:
        raise_flat(exc)
    return LinkCreated.model_validate(link)


@router.post("/{short_code}/enable")
async def enable_link(short_code: str, service: ServiceDep) -> LinkCreated:
    try:
        link = await service.enable_link(short_code)
    except LinkServiceError as exc:
        raise_flat(exc)
    return LinkCreated.model_validate(link)

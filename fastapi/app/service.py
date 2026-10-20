"""Плоский функциональный фасад сервиса (имена Дня 2) над `app/services/link.py`."""

import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from app import repo
from app.models.link import Link
from app.services.link import LinkInactiveError, LinkNotFoundError

LinkDisabledError = LinkInactiveError

__all__ = [
    "LinkDisabledError",
    "LinkNotFoundError",
    "create_link",
    "make_code",
    "resolve_link",
]


def make_code(length: int = 8) -> str:
    return secrets.token_urlsafe(length)[:length]


async def create_link(session: AsyncSession, target_url: str, ttl_seconds: int | None) -> Link:
    if ttl_seconds is not None and ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be positive")
    return await repo.insert_link(session, make_code(), target_url, ttl_seconds)


async def resolve_link(session: AsyncSession, short_code: str) -> Link:
    """Переход по ссылке: у активной ссылки атомарно увеличивает счётчик кликов."""
    link = await repo.get_link(session, short_code)
    if link is None:
        raise LinkNotFoundError(short_code)
    if link.disabled:
        raise LinkDisabledError(short_code)
    clicked = await repo.increment_clicks(session, short_code)
    if clicked is None:
        raise LinkDisabledError(short_code)
    return clicked

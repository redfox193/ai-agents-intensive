"""Плоский функциональный фасад репозитория (имена Дня 2) над `app/repositories/link.py`."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.link import Link
from app.repositories.link import LinkRepository


async def insert_link(
    session: AsyncSession, short_code: str, target_url: str, ttl_seconds: int | None
) -> Link:
    """Вставляет ссылку; `ttl_seconds` пересчитывается в `expires_at` на стороне сервиса."""
    link = Link(short_code=short_code, target_url=target_url)
    if ttl_seconds is not None:
        link.expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    return await LinkRepository(session).create(link)


async def get_link(session: AsyncSession, short_code: str) -> Link | None:
    return await LinkRepository(session).get_by_code(short_code)


async def set_disabled(session: AsyncSession, short_code: str, disabled: bool) -> Link | None:
    return await LinkRepository(session).set_active(short_code, not disabled)


async def increment_clicks(session: AsyncSession, short_code: str) -> Link | None:
    """Атомарно: UPDATE links SET clicks = clicks + 1 для активной ссылки."""
    repo = LinkRepository(session)
    link = await repo.get_by_code(short_code)
    if link is None or link.disabled:
        return None
    await repo.increment_clicks(link.id)
    await session.refresh(link)
    return link

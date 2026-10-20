from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.link import Link


class LinkRepository:
    """Асинхронный репозиторий для сущности Link."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_code(self, short_code: str) -> Link | None:
        """Поиск ссылки по короткому коду."""
        stmt = select(Link).where(Link.short_code == short_code)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, link_id: int) -> Link | None:
        """Поиск ссылки по первичному ключу."""
        return await self._session.get(Link, link_id)

    async def create(self, link: Link) -> Link:
        """Сохранение новой ссылки в сессии."""
        self._session.add(link)
        await self._session.flush()
        await self._session.refresh(link)
        return link

    async def bulk_create(self, links: list[Link]) -> list[Link]:
        """Пакетное добавление сущностей."""
        self._session.add_all(links)
        await self._session.flush()
        for link in links:
            await self._session.refresh(link)
        return links

    async def increment_clicks(self, link_id: int) -> None:
        """Атомарный инкремент счетчика переходов."""
        stmt = update(Link).where(Link.id == link_id).values(clicks=Link.clicks + 1)
        await self._session.execute(stmt)

    async def set_active(self, short_code: str, is_active: bool) -> Link | None:
        """Изменение статуса активности ссылки."""
        link = await self.get_by_code(short_code)
        if link:
            link.is_active = is_active
            await self._session.flush()
            await self._session.refresh(link)
        return link

    async def list_all(self, limit: int = 100, offset: int = 0) -> Sequence[Link]:
        """Все ссылки (новые первыми) с пагинацией."""
        stmt = select(Link).order_by(Link.id.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def list_active(self, limit: int = 50, offset: int = 0) -> Sequence[Link]:
        """Список активных ссылок с пагинацией."""
        stmt = (
            select(Link)
            .where(Link.is_active == True)  # noqa: E712
            .order_by(Link.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

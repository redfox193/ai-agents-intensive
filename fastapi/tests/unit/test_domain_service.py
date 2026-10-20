from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_short_code, validate_target_url
from app.domain.errors import (
    InvalidUrlError,
    LinkDisabledError,
    LinkExpiredError,
    LinkNotFoundError,
    ShortCodeTakenError,
)
from app.domain.link import Link
from app.repositories.link_repository import LinkRepository
from app.services.link_service import LinkService


class MemoryRepository:
    def __init__(self) -> None:
        self.items: dict[str, Link] = {}

    async def add(self, link: Link) -> Link:
        self.items[link.short_code.value] = link
        return link

    async def get_by_code(self, short_code: str) -> Link | None:
        return self.items.get(short_code)

    async def list_all(self, limit: int = 100) -> list[Link]:
        return list(self.items.values())[:limit]

    async def update(self, link: Link) -> Link:
        self.items[link.short_code.value] = link
        return link

    async def increment_clicks(self, short_code: str) -> Link:
        link = self.items[short_code].with_click()
        self.items[short_code] = link
        return link


async def test_domain_service_create_resolve_disable() -> None:
    service = LinkService(MemoryRepository())
    created = await service.create_link("https://example.com", custom_code="mycode1")
    assert created.short_code.value == "mycode1"
    assert (await service.resolve("mycode1")).clicks == 1
    assert len(await service.list_links()) == 1
    await service.disable_link("mycode1")
    with pytest.raises(LinkDisabledError):
        await service.resolve("mycode1")


async def test_domain_service_errors() -> None:
    service = LinkService(MemoryRepository())
    await service.create_link("https://example.com", custom_code="taken01")
    with pytest.raises(ShortCodeTakenError):
        await service.create_link("https://example.com", custom_code="taken01")
    with pytest.raises(LinkNotFoundError):
        await service.get_link("missing")
    with pytest.raises(InvalidUrlError):
        await service.create_link("http://localhost")
    generated = await service.create_link("https://example.com", ttl_seconds=60)
    assert generated.expires_at is not None


async def test_domain_service_expired_link_is_gone() -> None:
    repo = MemoryRepository()
    service = LinkService(repo)
    link = await service.create_link("https://example.com", ttl_seconds=60, custom_code="soon123")
    repo.items["soon123"] = Link(
        short_code=link.short_code,
        target_url=link.target_url,
        created_at=link.created_at,
        expires_at=datetime(2000, 1, 1, tzinfo=UTC),
    )
    with pytest.raises(LinkExpiredError):
        await service.resolve("soon123")


async def test_sql_domain_repository_roundtrip(db_session: AsyncSession) -> None:
    service = LinkService(LinkRepository(db_session))
    created = await service.create_link("https://example.com/sql", custom_code="sqlcode1")
    assert created.id is not None
    assert (await service.get_link("sqlcode1")).target_url.value == "https://example.com/sql"
    assert (await service.resolve("sqlcode1")).clicks == 1
    await service.disable_link("sqlcode1")
    assert (await service.get_link("sqlcode1")).disabled is True
    assert [item.short_code.value for item in await service.list_links()] == ["sqlcode1"]
    with pytest.raises(LinkNotFoundError):
        await LinkRepository(db_session).increment_clicks("nothing1")
    assert await LinkRepository(db_session).get_by_code("nothing1") is None


def test_security_helpers() -> None:
    assert len(generate_short_code(9)) == 9
    assert validate_target_url(" https://example.com ") == "https://example.com"

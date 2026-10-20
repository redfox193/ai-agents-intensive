import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.link import LinkBulkCreateItem, LinkCreate
from app.services.link import (
    LinkInactiveError,
    LinkNotFoundError,
    LinkService,
    ShortCodeConflictError,
)


@pytest.mark.asyncio
async def test_create_link_auto_code(db_session: AsyncSession):
    service = LinkService(db_session)
    data = LinkCreate(original_url="https://example.com/very-long-url")
    link = await service.create_link(data)

    assert link.id is not None
    assert len(link.short_code) >= 6
    assert link.original_url == "https://example.com/very-long-url"
    assert link.is_active is True
    assert link.clicks_count == 0


@pytest.mark.asyncio
async def test_create_link_custom_code(db_session: AsyncSession):
    service = LinkService(db_session)
    data = LinkCreate(original_url="https://example.com", custom_code="custom-test")
    link = await service.create_link(data)

    assert link.short_code == "custom-test"


@pytest.mark.asyncio
async def test_custom_code_conflict(db_session: AsyncSession):
    service = LinkService(db_session)
    data1 = LinkCreate(original_url="https://a.com", custom_code="duplicate")
    await service.create_link(data1)

    data2 = LinkCreate(original_url="https://b.com", custom_code="duplicate")
    with pytest.raises(ShortCodeConflictError):
        await service.create_link(data2)


@pytest.mark.asyncio
async def test_resolve_link_success(db_session: AsyncSession):
    service = LinkService(db_session)
    data = LinkCreate(original_url="https://target.com", custom_code="resolve-me")
    await service.create_link(data)

    resolved_url = await service.resolve_link("resolve-me")
    assert resolved_url == "https://target.com"

    stats = await service.get_stats("resolve-me")
    assert stats.clicks_count == 1


@pytest.mark.asyncio
async def test_resolve_not_found(db_session: AsyncSession):
    service = LinkService(db_session)
    with pytest.raises(LinkNotFoundError):
        await service.resolve_link("non-existent")


@pytest.mark.asyncio
async def test_disable_and_enable_link(db_session: AsyncSession):
    service = LinkService(db_session)
    data = LinkCreate(original_url="https://toggle.com", custom_code="toggle")
    await service.create_link(data)

    await service.disable_link("toggle")
    with pytest.raises(LinkInactiveError):
        await service.resolve_link("toggle")

    await service.enable_link("toggle")
    resolved = await service.resolve_link("toggle")
    assert resolved == "https://toggle.com"


@pytest.mark.asyncio
async def test_bulk_create_links(db_session: AsyncSession):
    service = LinkService(db_session)
    items = [
        LinkBulkCreateItem(original_url="https://url1.com", custom_code="bulk_01"),
        LinkBulkCreateItem(original_url="https://url2.com", custom_code="bulk_02"),
    ]
    response = await service.bulk_create_links(items)

    assert response.created_count == 2
    assert len(response.links) == 2
    assert response.links[0].short_code == "bulk_01"
    assert response.links[1].short_code == "bulk_02"

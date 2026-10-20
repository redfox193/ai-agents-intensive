import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app import repo, service
from app.api.schemas import CreateLinkRequest, LinkCreate
from app.config import Settings, get_settings
from app.models_flat import Base, Link
from app.service import LinkDisabledError, LinkNotFoundError


def test_flat_modules_reexport_layered_objects() -> None:
    assert CreateLinkRequest is LinkCreate
    assert isinstance(get_settings(), Settings)
    assert Base.metadata.tables["links"] is Link.__table__


async def test_flat_repo_roundtrip(db_session: AsyncSession) -> None:
    link = await repo.insert_link(db_session, "flat0001", "https://example.com/flat", 60)
    assert link.expires_at is not None
    assert (await repo.get_link(db_session, "flat0001")) is not None
    assert (await repo.set_disabled(db_session, "flat0001", True)) is not None
    assert (await repo.increment_clicks(db_session, "flat0001")) is None
    await repo.set_disabled(db_session, "flat0001", False)
    clicked = await repo.increment_clicks(db_session, "flat0001")
    assert clicked is not None
    assert clicked.clicks == 1
    assert await repo.increment_clicks(db_session, "missing1") is None
    assert await repo.set_disabled(db_session, "missing1", True) is None


async def test_flat_service_rules(db_session: AsyncSession) -> None:
    created = await service.create_link(db_session, "https://example.com/svc", None)
    assert len(service.make_code()) == 8
    resolved = await service.resolve_link(db_session, created.short_code)
    assert resolved.clicks == 1
    await repo.set_disabled(db_session, created.short_code, True)
    with pytest.raises(LinkDisabledError):
        await service.resolve_link(db_session, created.short_code)
    with pytest.raises(LinkNotFoundError):
        await service.resolve_link(db_session, "nothing1")
    with pytest.raises(ValueError, match="ttl_seconds"):
        await service.create_link(db_session, "https://example.com/svc", 0)

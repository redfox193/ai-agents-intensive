from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.domain.link import Link
from app.domain.value_objects import ShortCode, TargetUrl
from app.services.link_service import LinkService


class RaceRepository:
    def __init__(self, workers: int) -> None:
        self.link = Link(
            short_code=ShortCode("race123"),
            target_url=TargetUrl("https://example.com"),
            created_at=datetime.now(UTC),
        )
        self._workers = workers
        self._reads = 0
        self._all_read = asyncio.Event()
        self._atomic_lock = asyncio.Lock()

    async def add(self, link: Link) -> Link:
        self.link = link
        return link

    async def get_by_code(self, short_code: str) -> Link | None:
        assert short_code == self.link.short_code.value
        snapshot = self.link
        self._reads += 1
        if self._reads == self._workers:
            self._all_read.set()
        await self._all_read.wait()
        return snapshot

    async def list_all(self, limit: int = 100) -> list[Link]:
        return [self.link]

    async def update(self, link: Link) -> Link:
        self.link = link
        return link

    async def delete_by_code(self, short_code: str) -> None:
        assert short_code == self.link.short_code.value

    async def increment_clicks(self, short_code: str) -> Link:
        async with self._atomic_lock:
            self.link = self.link.with_click()
            return self.link


@pytest.mark.asyncio
async def test_parallel_resolve_does_not_lose_clicks() -> None:
    workers = 20
    repository = RaceRepository(workers)
    service = LinkService(repository)
    results = await asyncio.gather(*(service.resolve("race123") for _ in range(workers)))
    assert repository.link.clicks == workers
    assert sorted(link.clicks for link in results) == list(range(1, workers + 1))


def test_sql_repository_uses_atomic_increment() -> None:
    source = Path("app/repositories/link_repository.py").read_text(encoding="utf-8")
    assert "async def increment_clicks(" in source
    assert "LinkModel.clicks + 1" in source
    assert ".returning(LinkModel)" in source

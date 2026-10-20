"""Фикстура плоского API (`/links`, `/{code}`): синхронный `TestClient` на SQLite во временном файле."""

import asyncio
import tempfile
from collections.abc import AsyncGenerator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    with tempfile.TemporaryDirectory(prefix="linksvc-tests-") as tmp:
        engine = create_async_engine(f"sqlite+aiosqlite:///{Path(tmp) / 'test_links.db'}")

        async def create_schema() -> None:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        asyncio.run(create_schema())
        factory = async_sessionmaker(engine, expire_on_commit=False)

        async def override_get_db() -> AsyncGenerator[AsyncSession]:
            async with factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as test_client:
                yield test_client
        finally:
            app.dependency_overrides.pop(get_db, None)
            asyncio.run(engine.dispose())

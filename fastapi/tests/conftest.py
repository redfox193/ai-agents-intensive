from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.base import Base
from app.db.session import get_db
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Указание бэкенда для pytest-asyncio."""
    return "asyncio"


@pytest.fixture(scope="function")
async def test_engine() -> AsyncGenerator[AsyncEngine]:
    """Создание изолированного асинхронного движка SQLite в памяти для каждого теста."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """Изолированная сессия БД для каждого теста."""
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        autoflush=False,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture(scope="function")
async def client(test_engine) -> AsyncGenerator[AsyncClient]:
    """Асинхронный HTTP-клиент с изолированной сессией на каждый запрос."""
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    app.dependency_overrides.clear()

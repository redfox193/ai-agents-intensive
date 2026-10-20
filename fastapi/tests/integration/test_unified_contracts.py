"""Единый контракт: плоские маршруты Дней 1-2 и версионированные маршруты Дня 3 на одной БД."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.models.link import Link


async def test_flat_and_v1_share_one_table(client: AsyncClient) -> None:
    created = await client.post("/links", json={"target_url": "https://example.com/shared"})
    assert created.status_code == 201
    code = created.json()["short_code"]
    assert set(created.json()) == {"short_code", "target_url", "disabled"}

    stats = await client.get(f"/api/v1/links/{code}/stats")
    assert stats.status_code == 200
    assert stats.json()["target_url"] == "https://example.com/shared"
    assert stats.json()["original_url"] == "https://example.com/shared"
    assert stats.json()["is_active"] is True

    listing = await client.get("/api/v1/links")
    assert code in [item["short_code"] for item in listing.json()]
    flat_listing = await client.get("/links")
    assert code in [item["short_code"] for item in flat_listing.json()]


async def test_request_body_accepts_all_url_aliases(client: AsyncClient) -> None:
    for field in ("url", "target_url", "original_url"):
        response = await client.post("/api/v1/links", json={field: f"https://example.com/{field}"})
        assert response.status_code == 201
        body = response.json()
        assert body["target_url"] == body["original_url"] == f"https://example.com/{field}"
        assert body["short_url"].endswith(f"/{body['short_code']}")
        assert body["status"] == "active"
        assert body["clicks"] == body["clicks_count"] == 0
        assert body["disabled"] is not body["is_active"]


async def test_flat_redirect_and_click_counter(client: AsyncClient) -> None:
    created = await client.post(
        "/links", json={"url": "https://example.com/go", "custom_code": "go-1"}
    )
    assert created.status_code == 201
    first = await client.get("/go-1", follow_redirects=False)
    assert first.status_code == 307
    assert first.headers["location"] == "https://example.com/go"
    detail = await client.get("/links/go-1")
    assert detail.json()["clicks"] == 1
    assert (await client.get("/api/v1/links/go-1/stats")).json()["clicks_count"] == 1


async def test_flat_error_contract(client: AsyncClient) -> None:
    await client.post("/links", json={"url": "https://example.com/e", "custom_code": "dup-1"})
    conflict = await client.post(
        "/links", json={"url": "https://example.com/e", "custom_code": "dup-1"}
    )
    assert conflict.status_code == 409
    assert conflict.json() == {"detail": "Short code already taken"}
    assert (await client.get("/links/unknown-code")).json() == {"detail": "Link not found"}
    await client.post("/links/dup-1/disable")
    assert (await client.get("/links/dup-1")).json() == {"detail": "Link disabled"}
    assert (await client.get("/dup-1", follow_redirects=False)).status_code == 404
    assert (await client.post("/api/v1/links/unknown-code/disable")).status_code == 404
    assert (await client.post("/api/v1/links/unknown-code/enable")).status_code == 404


async def test_expired_link_gives_410_on_flat_and_v1(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    await client.post("/links", json={"url": "https://example.com/old", "custom_code": "old-1"})
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(test_engine)
    async with factory() as session:
        past = datetime.now(UTC) - timedelta(hours=1)
        await session.execute(
            update(Link).where(Link.short_code == "old-1").values(expires_at=past)
        )
        await session.commit()
    flat = await client.get("/old-1", follow_redirects=False)
    assert flat.status_code == 410
    assert flat.json() == {"detail": "Link expired"}
    assert (await client.get("/api/v1/links/old-1", follow_redirects=False)).status_code == 410
    stats = await client.get("/api/v1/links/old-1/stats")
    assert stats.json()["status"] == "expired"
    assert stats.json()["is_expired"] is True


async def test_analytics_endpoint(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/analytics/nothing-here")).status_code == 404
    await client.post("/links", json={"url": "https://example.com/an", "custom_code": "an-1"})
    response = await client.get("/api/v1/analytics/an-1")
    assert response.status_code == 200
    assert response.json()["total_clicks"] == 0

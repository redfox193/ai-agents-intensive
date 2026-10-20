import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_api_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_api_create_and_redirect(client: AsyncClient):
    payload = {
        "original_url": "https://fastapi.tiangolo.com",
        "custom_code": "fastapi-docs",
    }
    create_res = await client.post("/api/v1/links", json=payload)
    assert create_res.status_code == 201
    body = create_res.json()
    assert body["short_code"] == "fastapi-docs"
    assert body["clicks_count"] == 0

    redirect_res = await client.get("/api/v1/links/fastapi-docs", follow_redirects=False)
    assert redirect_res.status_code == 307
    assert redirect_res.headers["location"] == "https://fastapi.tiangolo.com"

    stats_res = await client.get("/api/v1/links/fastapi-docs/stats")
    assert stats_res.status_code == 200
    assert stats_res.json()["clicks_count"] == 1


@pytest.mark.asyncio
async def test_api_conflict_custom_code(client: AsyncClient):
    payload = {"original_url": "https://a.com", "custom_code": "clash"}
    res1 = await client.post("/api/v1/links", json=payload)
    assert res1.status_code == 201

    res2 = await client.post("/api/v1/links", json=payload)
    assert res2.status_code == 409
    assert "уже используется" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_api_disable_link_flow(client: AsyncClient):
    payload = {"original_url": "https://disabled.com", "custom_code": "disable-api"}
    await client.post("/api/v1/links", json=payload)

    dis_res = await client.post("/api/v1/links/disable-api/disable")
    assert dis_res.status_code == 200
    assert dis_res.json()["is_active"] is False

    get_res = await client.get("/api/v1/links/disable-api")
    assert get_res.status_code == 410

    en_res = await client.post("/api/v1/links/disable-api/enable")
    assert en_res.status_code == 200
    assert en_res.json()["is_active"] is True


@pytest.mark.asyncio
async def test_api_bulk_create(client: AsyncClient):
    payload = {
        "items": [
            {"original_url": "https://item1.com", "custom_code": "bulk-1"},
            {"original_url": "https://item2.com", "custom_code": "bulk-2"},
        ]
    }
    response = await client.post("/api/v1/links/bulk", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["created_count"] == 2
    assert len(data["links"]) == 2

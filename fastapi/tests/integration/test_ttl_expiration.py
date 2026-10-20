import asyncio

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_link_ttl_expiration_flow(client: AsyncClient):
    res = await client.post(
        "/api/v1/links",
        json={"original_url": "https://expiring.com", "custom_code": "ttl-1s", "ttl_seconds": 1},
    )
    assert res.status_code == 201

    get_res1 = await client.get("/api/v1/links/ttl-1s", follow_redirects=False)
    assert get_res1.status_code == 307

    await asyncio.sleep(1.2)

    get_res2 = await client.get("/api/v1/links/ttl-1s", follow_redirects=False)
    assert get_res2.status_code == 410

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_atomic_bulk_rollback_on_conflict(client: AsyncClient):
    await client.post(
        "/api/v1/links", json={"original_url": "https://first.com", "custom_code": "already-taken"}
    )

    payload = {
        "items": [
            {"original_url": "https://new1.com", "custom_code": "will-rollback"},
            {"original_url": "https://new2.com", "custom_code": "already-taken"},
        ]
    }
    res = await client.post("/api/v1/links/bulk", json=payload)
    assert res.status_code == 409

    check_res = await client.get("/api/v1/links/will-rollback")
    assert check_res.status_code == 404

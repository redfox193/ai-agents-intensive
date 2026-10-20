import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_char_url_with_query_params_and_fragments(client: AsyncClient):
    target = "https://pytex.ru/search?q=agentic+sdlc&page=2#section-3"
    res = await client.post(
        "/api/v1/links", json={"original_url": target, "custom_code": "query-test"}
    )
    assert res.status_code == 201

    get_res = await client.get("/api/v1/links/query-test", follow_redirects=False)
    assert get_res.status_code == 307
    assert get_res.headers["location"] == target


@pytest.mark.asyncio
async def test_char_max_length_url(client: AsyncClient):
    long_url = "https://example.com/" + "a" * 2020
    res = await client.post(
        "/api/v1/links", json={"original_url": long_url, "custom_code": "max-url"}
    )
    assert res.status_code == 201

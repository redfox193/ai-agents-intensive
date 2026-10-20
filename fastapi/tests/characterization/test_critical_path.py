import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_char_non_existent_returns_404(client: AsyncClient):
    """Характеристика: запрос неизвестного короткого кода обязан возвращать 404."""
    response = await client.get("/api/v1/links/unknown-code-xyz")
    assert response.status_code == 404
    assert "не найдена" in response.json()["detail"]


@pytest.mark.asyncio
async def test_char_redirect_code_is_307_not_301(client: AsyncClient):
    """Характеристика: редирект ОБЯЗАН быть временным (307), чтобы браузер не кэшировал переход."""
    payload = {"original_url": "https://pytex.ru/char-test", "custom_code": "char307"}
    await client.post("/api/v1/links", json=payload)

    response = await client.get("/api/v1/links/char307", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "https://pytex.ru/char-test"


@pytest.mark.asyncio
async def test_char_invalid_custom_code_pattern(client: AsyncClient):
    """Характеристика: кастомный код с недопустимыми символами обязан отклоняться валидацией (422)."""
    payload = {"original_url": "https://pytex.ru", "custom_code": "bad code!"}
    response = await client.post("/api/v1/links", json=payload)
    assert response.status_code == 422

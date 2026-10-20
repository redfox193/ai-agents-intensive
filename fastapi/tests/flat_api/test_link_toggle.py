import logging

import pytest
from fastapi.testclient import TestClient


def test_link_default_is_active(client: TestClient) -> None:
    """R-01: Новая ссылка по умолчанию активна (disabled=False)."""
    created = client.post("/links", json={"target_url": "https://example.com/active-probe"})
    assert created.status_code == 201
    code = created.json()["short_code"]
    got = client.get(f"/links/{code}")
    assert got.status_code == 200
    assert got.json()["target_url"] == "https://example.com/active-probe"


def test_link_deactivation_roundtrip(client: TestClient) -> None:
    """R-01: Деактивация ссылки переводит чтение в 404 (disabled=True)."""
    created = client.post("/links", json={"target_url": "https://example.com/toggle-probe"})
    code = created.json()["short_code"]
    disabled = client.post(f"/links/{code}/disable")
    assert disabled.status_code == 200
    assert disabled.json()["disabled"] is True

    got = client.get(f"/links/{code}")
    assert got.status_code == 404


def test_link_reactivation_roundtrip(client: TestClient) -> None:
    """R-01: Повторная активация ссылки возвращает чтение в 200 (disabled=False)."""
    created = client.post("/links", json={"target_url": "https://example.com/reactivate-probe"})
    code = created.json()["short_code"]
    client.post(f"/links/{code}/disable")
    enabled = client.post(f"/links/{code}/enable")
    assert enabled.status_code == 200
    assert enabled.json()["disabled"] is False

    got = client.get(f"/links/{code}")
    assert got.status_code == 200


def test_toggle_does_not_log_target_url(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """R-04: Управление статусом не должно логировать чувствительный target_url."""
    created = client.post("/links", json={"target_url": "https://example.com/secret-auth-key"})
    code = created.json()["short_code"]
    with caplog.at_level(logging.INFO):
        client.post(f"/links/{code}/disable")
        client.post(f"/links/{code}/enable")
    assert "secret-auth-key" not in caplog.text

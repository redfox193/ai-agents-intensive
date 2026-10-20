import logging

import pytest
from fastapi.testclient import TestClient


def test_enable_missing_gives_404(client: TestClient) -> None:
    got = client.post("/links/no-such-code-xyz/enable")
    assert got.status_code == 404


def test_enable_roundtrip(client: TestClient) -> None:
    created = client.post("/links", json={"target_url": "https://example.com/e"})
    code = created.json()["short_code"]
    client.post(f"/links/{code}/disable")
    got = client.post(f"/links/{code}/enable")
    assert got.status_code == 200
    assert got.json()["disabled"] is False
    read = client.get(f"/links/{code}")
    assert read.status_code == 200


def test_enable_twice_stays_200(client: TestClient) -> None:
    created = client.post("/links", json={"target_url": "https://example.com/e2"})
    code = created.json()["short_code"]
    client.post(f"/links/{code}/disable")
    assert client.post(f"/links/{code}/enable").status_code == 200
    assert client.post(f"/links/{code}/enable").status_code == 200


def test_enable_does_not_log_target_url(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    created = client.post("/links", json={"target_url": "https://example.com/leak-probe"})
    code = created.json()["short_code"]
    client.post(f"/links/{code}/disable")
    with caplog.at_level(logging.INFO):
        got = client.post(f"/links/{code}/enable")
    assert got.status_code == 200
    assert "leak-probe" not in caplog.text

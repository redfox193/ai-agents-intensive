import uuid

from fastapi.testclient import TestClient

BASE = "http://localhost:8000"


def unique_target() -> str:
    return f"https://example.com/{uuid.uuid4().hex}"


def test_create_and_read_roundtrip(client: TestClient) -> None:
    target = unique_target()
    created = client.post("/links", json={"target_url": target})
    assert created.status_code == 201
    code = created.json()["short_code"]
    got = client.get(f"/links/{code}")
    assert got.status_code == 200
    assert got.json()["target_url"] == target


def test_read_missing_gives_404(client: TestClient) -> None:
    got = client.get("/links/no-such-code-xyz")
    assert got.status_code == 404


def test_negative_ttl_rejected(client: TestClient) -> None:
    bad = client.post("/links", json={"target_url": unique_target(), "ttl_seconds": -5})
    assert bad.status_code == 422


def test_zero_ttl_rejected(client: TestClient) -> None:
    bad = client.post("/links", json={"target_url": unique_target(), "ttl_seconds": 0})
    assert bad.status_code == 422

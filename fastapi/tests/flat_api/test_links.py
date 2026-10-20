"""LINK-42: создание, редирект `GET /{code}`, disable/enable и счётчик переходов."""

import uuid

from fastapi.testclient import TestClient


def make_link(client: TestClient) -> tuple[str, str]:
    target = f"https://example.com/{uuid.uuid4().hex}"
    created = client.post("/links", json={"target_url": target})
    assert created.status_code == 201
    return created.json()["short_code"], target


def test_create_returns_contract_fields(client: TestClient) -> None:
    code, target = make_link(client)
    created = client.post("/links", json={"target_url": target}).json()
    assert set(created) == {"short_code", "target_url", "disabled"}
    assert created["target_url"] == target
    assert created["disabled"] is False
    assert code != created["short_code"]


def test_active_link_redirects_307(client: TestClient) -> None:
    code, target = make_link(client)
    got = client.get(f"/{code}", follow_redirects=False)
    assert got.status_code == 307
    assert got.headers["location"] == target


def test_unknown_code_gives_404_link_not_found(client: TestClient) -> None:
    got = client.get("/no-such-code-xyz", follow_redirects=False)
    assert got.status_code == 404
    assert got.json() == {"detail": "Link not found"}


def test_disabled_link_blocks_redirect(client: TestClient) -> None:
    code, _ = make_link(client)
    client.post(f"/links/{code}/disable")
    got = client.get(f"/{code}", follow_redirects=False)
    assert got.status_code == 404
    assert got.json() == {"detail": "Link disabled"}
    assert "location" not in got.headers


def test_enable_restores_redirect(client: TestClient) -> None:
    code, target = make_link(client)
    client.post(f"/links/{code}/disable")
    assert client.get(f"/{code}", follow_redirects=False).status_code == 404
    client.post(f"/links/{code}/enable")
    got = client.get(f"/{code}", follow_redirects=False)
    assert got.status_code == 307
    assert got.headers["location"] == target


def test_disable_and_enable_return_contract_fields(client: TestClient) -> None:
    code, target = make_link(client)
    disabled = client.post(f"/links/{code}/disable")
    assert disabled.status_code == 200
    assert disabled.json() == {"short_code": code, "target_url": target, "disabled": True}
    enabled = client.post(f"/links/{code}/enable")
    assert enabled.status_code == 200
    assert enabled.json() == {"short_code": code, "target_url": target, "disabled": False}


def test_toggle_idempotency(client: TestClient) -> None:
    code, _ = make_link(client)
    first = client.post(f"/links/{code}/disable")
    second = client.post(f"/links/{code}/disable")
    assert first.status_code == second.status_code == 200
    assert second.json()["disabled"] is True
    assert client.post(f"/links/{code}/enable").status_code == 200
    again = client.post(f"/links/{code}/enable")
    assert again.status_code == 200
    assert again.json()["disabled"] is False


def test_toggle_nonexistent_link_gives_404(client: TestClient) -> None:
    for action in ("disable", "enable"):
        got = client.post(f"/links/no-such-code-xyz/{action}")
        assert got.status_code == 404
        assert got.json() == {"detail": "Link not found"}


def test_redirect_counts_clicks(client: TestClient) -> None:
    code, _ = make_link(client)
    assert client.get(f"/links/{code}").json()["clicks"] == 0
    client.get(f"/{code}", follow_redirects=False)
    client.get(f"/{code}", follow_redirects=False)
    assert client.get(f"/links/{code}").json()["clicks"] == 2


def test_disabled_link_does_not_increment_clicks(client: TestClient) -> None:
    code, _ = make_link(client)
    client.get(f"/{code}", follow_redirects=False)
    client.post(f"/links/{code}/disable")
    for _ in range(3):
        assert client.get(f"/{code}", follow_redirects=False).status_code == 404
    client.post(f"/links/{code}/enable")
    assert client.get(f"/links/{code}").json()["clicks"] == 1


def test_read_returns_target_url_and_flag(client: TestClient) -> None:
    code, target = make_link(client)
    got = client.get(f"/links/{code}").json()
    assert got["target_url"] == target
    assert got["short_code"] == code
    assert got["disabled"] is False

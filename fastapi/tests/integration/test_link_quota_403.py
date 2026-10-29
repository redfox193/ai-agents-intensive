"""Интеграционные тесты квоты активных ссылок плана FREE на HTTP-слое (волна 4)."""

import pytest
from fastapi.testclient import TestClient

from app.api.billing import _repo_instance
from app.main import app
from app.schemas.billing import PlanType, WalletBalance


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_quota_users():
    """Изолировать состояние квоты тестовых пользователей между тестами."""
    for uid in (7100, 7200, 7300):
        _repo_instance.wallets.pop(uid, None)
        _repo_instance.active_links.pop(uid, None)
    yield


def _create_link(client: TestClient, user_id: int | None = None, url: str | None = None):
    headers = {"X-User-Id": str(user_id)} if user_id is not None else None
    return client.post(
        "/links",
        json={"target_url": url or "https://example.com/page"},
        headers=headers,
    )


def test_anonymous_link_creation_not_quota_limited(client):
    """Анонимная ссылка (без user_id): квота не проверяется, anon path сохранён."""
    response = _create_link(client)
    assert response.status_code == 201
    assert response.json()["disabled"] is False


def test_free_plan_user_hits_403_on_eleventh_link(client):
    """11-я активная ссылка владельца FREE -> HTTP 403 с QuotaExceededResponse."""
    uid = 7100
    top_up = client.post("/billing/wallets/top-up", json={"user_id": uid, "amount": 100})
    assert top_up.status_code == 200

    for i in range(10):
        response = _create_link(client, user_id=uid, url=f"https://example.com/free{i}")
        assert response.status_code == 201, f"link #{i + 1}: {response.status_code}"

    exceeded = _create_link(client, user_id=uid, url="https://example.com/eleventh")
    assert exceeded.status_code == 403
    body = exceeded.json()["detail"]
    assert body["detail"] == "Free plan link quota exceeded"
    assert body["plan"] == "free"
    assert body["limit"] == 10
    assert body["active_links"] == 10


def test_pro_plan_user_is_not_limited(client):
    """PRO-план не лимитируется: больше 10 активных ссылок проходят со 201."""
    uid = 7200
    # Учебный контур: план задаётся фикстурой прямо в InMemory-репозитории
    # (API top-up всегда создаёт FREE-кошелёк).
    _repo_instance.wallets[uid] = WalletBalance(
        user_id=uid, balance=0, plan=PlanType.PRO
    )

    for i in range(12):
        response = _create_link(client, user_id=uid, url=f"https://example.com/pro{i}")
        assert response.status_code == 201, f"link #{i + 1}: {response.status_code}"


def test_disable_releases_quota_slot(client):
    """Disable снимает ссылку с учёта: следующий create снова проходит (201)."""
    uid = 7300
    top_up = client.post("/billing/wallets/top-up", json={"user_id": uid, "amount": 100})
    assert top_up.status_code == 200

    for i in range(10):
        response = _create_link(client, user_id=uid, url=f"https://example.com/rel{i}")
        assert response.status_code == 201

    assert _create_link(client, user_id=uid).status_code == 403

    # Disable одной активной ссылки
    code = client.get("/links").json()[0]["short_code"]
    disabled = client.post(f"/links/{code}/disable", headers={"X-User-Id": str(uid)})
    assert disabled.status_code == 200
    assert disabled.json()["disabled"] is True

    recreated = _create_link(client, user_id=uid, url="https://example.com/after-disable")
    assert recreated.status_code == 201

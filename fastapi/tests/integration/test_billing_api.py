import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "monolith": True}


def test_api_top_up(client):
    payload = {"user_id": 10, "amount": 1000}
    response = client.post("/billing/wallets/top-up", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == 10
    assert data["balance"] == 1000


def test_api_charge_success(client):
    # Сначала пополняем
    client.post("/billing/wallets/top-up", json={"user_id": 20, "amount": 500})

    # Списываем средства
    payload = {"user_id": 20, "link_id": 1, "amount": 50, "transaction_id": "tx_api_success_00001"}
    response = client.post("/billing/charges/click", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["remaining_balance"] == 450


def test_api_charge_insufficient_funds(client):
    payload = {
        "user_id": 20,
        "link_id": 1,
        "amount": 10000,  # Превышает баланс 450
        "transaction_id": "tx_api_fail_funds_0002",
    }
    response = client.post("/billing/charges/click", json=payload)
    assert response.status_code == 402  # HTTP 402 Payment Required!
    assert "Недостаточно средств" in response.json()["detail"]


def test_api_charge_idempotent(client):
    payload = {
        "user_id": 20,
        "link_id": 1,
        "amount": 25,
        "transaction_id": "tx_api_idempotent_0003",
    }
    # Первый вызов
    r1 = client.post("/billing/charges/click", json=payload)
    assert r1.status_code == 200
    bal1 = r1.json()["remaining_balance"]

    # Повторный вызов
    r2 = client.post("/billing/charges/click", json=payload)
    assert r2.status_code == 200
    bal2 = r2.json()["remaining_balance"]
    assert bal1 == bal2  # Баланс не списан повторно!

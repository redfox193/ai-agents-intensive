from fastapi.testclient import TestClient

from app.main import app


def test_full_monetization_cycle():
    client = TestClient(app)
    user_id = 777

    # Шаг 1: Проверяем начальное состояние сервера
    h = client.get("/health")
    assert h.status_code == 200
    assert h.json()["monolith"] is True

    # Шаг 2: Пополняем баланс пользователя на 300 коп. (3 рубля)
    r_topup = client.post("/billing/wallets/top-up", json={"user_id": user_id, "amount": 300})
    assert r_topup.status_code == 200
    assert r_topup.json()["balance"] == 300

    # Шаг 3: Совершаем первый переход по ссылке (стоимость: 100 коп.)
    tx_1 = "tx_e2e_cycle_test_0001"
    r_charge1 = client.post(
        "/billing/charges/click",
        json={"user_id": user_id, "link_id": 1, "amount": 100, "transaction_id": tx_1},
    )
    assert r_charge1.status_code == 200
    assert r_charge1.json()["remaining_balance"] == 200

    # Шаг 4: Повторный запрос с тем же transaction_id (проверка идемпотентности)
    r_charge_dup = client.post(
        "/billing/charges/click",
        json={"user_id": user_id, "link_id": 1, "amount": 100, "transaction_id": tx_1},
    )
    assert r_charge_dup.status_code == 200
    assert r_charge_dup.json()["remaining_balance"] == 200  # Баланс не списан повторно!

    # Шаг 5: Совершаем второй клик (стоимость: 150 коп.)
    tx_2 = "tx_e2e_cycle_test_0002"
    r_charge2 = client.post(
        "/billing/charges/click",
        json={"user_id": user_id, "link_id": 1, "amount": 150, "transaction_id": tx_2},
    )
    assert r_charge2.status_code == 200
    assert r_charge2.json()["remaining_balance"] == 50

    # Шаг 6: Попытка списать 100 коп. при остатке 50 коп. (нехватка средств)
    tx_3 = "tx_e2e_cycle_test_0003"
    r_fail = client.post(
        "/billing/charges/click",
        json={"user_id": user_id, "link_id": 1, "amount": 100, "transaction_id": tx_3},
    )
    assert r_fail.status_code == 402  # HTTP 402 Payment Required!
    assert "Недостаточно средств" in r_fail.json()["detail"]

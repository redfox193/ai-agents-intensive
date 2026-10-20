import pytest
from pydantic import ValidationError

from app.schemas.billing import ChargeRequest, PlanType, WalletBalance


def test_req_ears_01_balance_non_negative():
    """[REQ-EARS-01] Баланс обязан быть целым неотрицательным числом."""
    # Валидный баланс
    w = WalletBalance(user_id=1, balance=500, plan=PlanType.FREE)
    assert w.balance == 500

    # Отрицательный баланс должен вызывать ошибку
    with pytest.raises(ValidationError):
        WalletBalance(user_id=1, balance=-10, plan=PlanType.FREE)


def test_req_ears_02_pydantic_v2_strict_dto():
    """[REQ-EARS-02] Ответы возвращаются в формате типизированных DTO."""
    req = ChargeRequest(user_id=10, link_id=20, amount=50, transaction_id="tx_idempotent_12345678")
    assert isinstance(req.amount, int)
    assert len(req.transaction_id) >= 16


def test_req_ears_07_plan_types_supported():
    """[REQ-EARS-07] Поддержка тарифных планов FREE, PRO, ENTERPRISE."""
    assert PlanType.FREE == "free"
    assert PlanType.PRO == "pro"
    assert PlanType.ENTERPRISE == "enterprise"

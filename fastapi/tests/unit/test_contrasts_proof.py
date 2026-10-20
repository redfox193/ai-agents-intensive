import pytest

from app.schemas.billing import ChargeRequest, PlanType, WalletBalance
from app.services.billing import BillingService, InsufficientFundsError


class DummyRepo:
    def __init__(self, balance):
        self.balance = balance
        self.txs = {}

    async def get_wallet(self, user_id):
        return WalletBalance(user_id=user_id, balance=self.balance, plan=PlanType.PRO)

    async def update_balance(self, user_id, new_bal):
        self.balance = new_bal
        return True

    async def record_transaction(self, user_id, amount, tx_id, status):
        self.txs[tx_id] = {"amount": amount, "status": status}
        return True

    async def get_transaction(self, tx_id):
        return self.txs.get(tx_id)


@pytest.mark.asyncio
async def test_contrast_07_prevent_negative_balance():
    """Доказательство Разбора 7: Защита от списания ниже нуля."""
    service = BillingService(repo=DummyRepo(balance=100))

    # Попытка списать 150 при балансе 100
    with pytest.raises(InsufficientFundsError):
        await service.charge_click(
            user_id=1, link_id=1, amount=150, transaction_id="tx_neg_proof_001"
        )
    # Баланс остался нетронутым (100 коп.)
    wallet = await service.repo.get_wallet(1)
    assert wallet.balance == 100


@pytest.mark.asyncio
async def test_contrast_01_pydantic_field_validation():
    """Доказательство Разбора 1: Декларативная валидация без циклического импорта."""
    # Валидный запрос
    req = ChargeRequest(user_id=1, link_id=2, amount=100, transaction_id="tx_idemp_key_1234567")
    assert req.amount == 100

    # Нулевой запрос должен вызывать ValidationError Pydantic
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ChargeRequest(user_id=1, link_id=2, amount=0, transaction_id="tx_idemp_key_1234567")

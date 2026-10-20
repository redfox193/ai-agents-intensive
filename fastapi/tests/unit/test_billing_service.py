import pytest

from app.schemas.billing import PlanType, WalletBalance
from app.services.billing import BillingService, InsufficientFundsError, WalletNotFoundError


class MockRepo:
    def __init__(self, initial_balance=1000):
        self.wallets = {
            1: WalletBalance(user_id=1, balance=initial_balance, plan=PlanType.PRO),
            2: WalletBalance(user_id=2, balance=50, plan=PlanType.FREE),
        }
        self.transactions = {}

    async def get_wallet(self, user_id: int):
        return self.wallets.get(user_id)

    async def update_balance(self, user_id: int, new_balance: int):
        if user_id in self.wallets:
            self.wallets[user_id].balance = new_balance
        else:
            self.wallets[user_id] = WalletBalance(
                user_id=user_id, balance=new_balance, plan=PlanType.FREE
            )
        return True

    async def record_transaction(self, user_id, amount, transaction_id, status):
        self.transactions[transaction_id] = {
            "user_id": user_id,
            "amount": amount,
            "status": status,
            "remaining_balance": self.wallets[user_id].balance,
        }
        return True

    async def get_transaction(self, transaction_id: str):
        return self.transactions.get(transaction_id)


@pytest.fixture
def service():
    return BillingService(repo=MockRepo())


@pytest.mark.asyncio
async def test_top_up_existing_wallet(service):
    wallet = await service.top_up(user_id=1, amount=500)
    assert wallet.balance == 1500


@pytest.mark.asyncio
async def test_top_up_new_wallet(service):
    wallet = await service.top_up(user_id=99, amount=300)
    assert wallet.balance == 300
    assert wallet.plan == PlanType.FREE


@pytest.mark.asyncio
async def test_charge_click_success(service):
    res = await service.charge_click(
        user_id=1, link_id=10, amount=50, transaction_id="tx_test_success_12345"
    )
    assert res.success is True
    assert res.remaining_balance == 950
    assert "успешно списаны" in res.message


@pytest.mark.asyncio
async def test_charge_click_insufficient_funds(service):
    with pytest.raises(InsufficientFundsError) as exc_info:
        await service.charge_click(
            user_id=2, link_id=10, amount=100, transaction_id="tx_test_fail_12345"
        )
    assert "Недостаточно средств" in str(exc_info.value)


@pytest.mark.asyncio
async def test_charge_click_wallet_not_found(service):
    with pytest.raises(WalletNotFoundError):
        await service.charge_click(
            user_id=999, link_id=10, amount=10, transaction_id="tx_test_not_found_123"
        )


@pytest.mark.asyncio
async def test_charge_click_idempotency(service):
    # Первое списание
    tx_id = "tx_idempotency_key_99999"
    res1 = await service.charge_click(user_id=1, link_id=10, amount=50, transaction_id=tx_id)
    assert res1.remaining_balance == 950

    # Повторный запрос с тем же transaction_id
    res2 = await service.charge_click(user_id=1, link_id=10, amount=50, transaction_id=tx_id)
    assert res2.success is True
    assert res2.remaining_balance == 950  # Баланс не изменился вторично!
    assert "Идемпотентный ответ" in res2.message

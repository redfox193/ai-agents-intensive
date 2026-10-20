import pytest

from app.schemas.billing import PlanType, WalletBalance
from app.services.billing import BillingService


class FaultyMockRepo:
    def __init__(self):
        self.wallet = WalletBalance(user_id=1, balance=1000, plan=PlanType.PRO)

    async def get_wallet(self, user_id: int):
        return self.wallet

    async def update_balance(self, user_id: int, new_balance: int):
        # Имитируем сбой диска или СУБД
        raise OSError("Сбой дисковой подсистемы базы данных при записи!")

    async def record_transaction(self, user_id, amount, tx_id, status):
        return True

    async def get_transaction(self, tx_id):
        return None


@pytest.mark.asyncio
async def test_billing_service_handles_db_failure_gracefully():
    """Тест: при сбое репозитория сервис не оставляет данные в рассинхроне."""
    service = BillingService(repo=FaultyMockRepo())

    with pytest.raises(IOError) as exc_info:
        await service.charge_click(
            user_id=1, link_id=10, amount=50, transaction_id="tx_faulty_test_001"
        )

    assert "Сбой дисковой подсистемы" in str(exc_info.value)

import logging

from app.core.protocols import BillingRepositoryProtocol
from app.schemas.billing import ChargeResponse, PlanType, WalletBalance

logger = logging.getLogger(__name__)


class BillingError(Exception):
    """Базовое исключение домена биллинга."""


class InsufficientFundsError(BillingError):
    """Исключение: недостаточно средств на балансе."""


class WalletNotFoundError(BillingError):
    """Исключение: кошелек пользователя не найден."""


class BillingService:
    def __init__(self, repo: BillingRepositoryProtocol) -> None:
        self.repo = repo

    async def top_up(self, user_id: int, amount: int) -> WalletBalance:
        wallet = await self.repo.get_wallet(user_id)
        if not wallet:
            # Создаем кошелек по умолчанию
            new_balance = amount
            wallet = WalletBalance(user_id=user_id, balance=new_balance, plan=PlanType.FREE)
        else:
            new_balance = wallet.balance + amount
            wallet.balance = new_balance

        await self.repo.update_balance(user_id, new_balance)
        return wallet

    async def charge_click(
        self, user_id: int, link_id: int, amount: int, transaction_id: str
    ) -> ChargeResponse:
        # 1. Проверка идемпотентности
        existing_tx = await self.repo.get_transaction(transaction_id)
        if existing_tx:
            logger.info("Повторная транзакция идемпотентности: %s", transaction_id)
            return ChargeResponse(
                success=True,
                transaction_id=transaction_id,
                remaining_balance=existing_tx["remaining_balance"],
                message="Идемпотентный ответ: транзакция уже была обработана",
            )

        # 2. Получение кошелька
        wallet = await self.repo.get_wallet(user_id)
        if not wallet:
            raise WalletNotFoundError(f"Кошелек пользователя {user_id} не найден")

        # 3. Проверка достаточности средств
        if wallet.balance < amount:
            raise InsufficientFundsError(
                f"Недостаточно средств: баланс {wallet.balance} коп., требуется {amount} коп."
            )

        # 4. Атомарное списание
        new_balance = wallet.balance - amount
        await self.repo.update_balance(user_id, new_balance)
        await self.repo.record_transaction(
            user_id=user_id, amount=amount, transaction_id=transaction_id, status="SUCCESS"
        )

        return ChargeResponse(
            success=True,
            transaction_id=transaction_id,
            remaining_balance=new_balance,
            message="Средства успешно списаны",
        )

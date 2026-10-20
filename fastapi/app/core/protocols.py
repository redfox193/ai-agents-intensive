from typing import Any, Protocol

from app.schemas.billing import WalletBalance


class BillingRepositoryProtocol(Protocol):
    """Контракт хранилища данных биллинга (PEP 544)."""

    async def get_wallet(self, user_id: int) -> WalletBalance | None:
        """Получить информацию о балансе пользователя."""
        ...

    async def update_balance(self, user_id: int, new_balance: int) -> bool:
        """Атомарно обновить баланс пользователя."""
        ...

    async def record_transaction(
        self, user_id: int, amount: int, transaction_id: str, status: str
    ) -> bool:
        """Зафиксировать транзакцию в журнале."""
        ...

    async def get_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        """Проверить статус транзакции для обеспечения идемпотентности."""
        ...


class PaymentGatewayProtocol(Protocol):
    """Контракт внешнего платежного шлюза."""

    async def process_external_charge(self, token: str, amount: int) -> str:
        """Инициировать списание через сторонний провайдер (Stripe/Банк)."""
        ...
